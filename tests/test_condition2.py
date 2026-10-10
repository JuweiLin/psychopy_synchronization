"""Sentence/audio correspondence, flip timing and partial Condition 2 recovery."""

import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from psychopy_sync.articles import load_experiment_articles
from psychopy_sync.audio_client import AudioFailure, CachedAudio
from psychopy_sync.condition1 import ExperimentAborted
from psychopy_sync.condition2 import run_condition2
from psychopy_sync.config import ExperimentConfig
from psychopy_sync.data_viewer import DataViewerExport
from psychopy_sync.event_log import EventLog, SessionStore
from psychopy_sync.reading_display import ReadingDisplay
from psychopy_sync.reading_speed import reading_summary
from psychopy_sync.session_audio import SessionAudio


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class Window:
    def __init__(self):
        self.now, self.callbacks = 0.0, []

    def clearBuffer(self):
        pass

    def callOnFlip(self, callback):
        self.callbacks.append(callback)

    def timeOnFlip(self, target, key):
        self.callOnFlip(lambda: target.update({key: self.now}))

    def getFutureFlipTime(self, clock):
        assert clock == "ptb"
        return 1000.0 + self.now + 0.05

    def flip(self):
        self.now += 0.05
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()


class Playback:
    def __init__(self, win, cached):
        self.win, self.cached = win, cached
        self.scheduled = None
        self.stopped = False

    def play(self, when):
        self.scheduled = when

    @property
    def isFinished(self):
        return self.win.now >= self.scheduled - 1000.0 + self.cached.metadata["duration_s"]

    def stop(self):
        self.stopped = True


class Condition2Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        assets = root / "assets"
        (assets / "articles").mkdir(parents=True)
        for name in ("A", "B", "C"):
            with (assets / "articles" / f"{name}.csv").open("w", newline="") as stream:
                csv.writer(stream).writerows([[name], [f"{name} first sentence."], [f"{name} second sentence."]])
        config = ExperimentConfig(assets_dir=assets, output_dir=root / "data", dummy_mode=True,
                                  condition1_count=1, condition2_count=2, random_seed=4,
                                  tts_server_url="http://127.0.0.1:8765")
        articles = load_experiment_articles(config)
        self.articles = articles["condition2"]
        self.store = SessionStore(config, "S001", articles)
        self.store.rows["condition1"][0].update(status="completed", start_event_id="C1_START", end_event_id="C1_END",
                                              start_timestamp_s=0.0, end_timestamp_s=0.6, reading_duration_s=0.6)
        self.summary = reading_summary(self.store.rows["condition1"], 1)
        self.store.save_speed(self.summary)
        self.audio = SessionAudio(config, self.store, self.articles, self.summary)
        self.audio.worker = MagicMock()
        self.audio.manifest["status"] = "running"
        self.cached = []
        for index, request in enumerate(self.audio.requests, 1):
            path = self.audio.directory / request.article_id / f"sentence_{request.sentence_index:04d}.wav"
            path.parent.mkdir(exist_ok=True)
            path.touch()
            self.cached.append(CachedAudio(request, f"{index:032x}", path,
                                           dict(request.identity(), duration_s=request.target_duration_s)))
        self.audio.worker.poll_events.side_effect = [self.cached[:2], [], self.cached[2:], []]
        self.win = Window()
        self.controller = MagicMock()
        self.log = EventLog(self.store, self.controller, lambda: self.win.now)
        self.view = ReadingDisplay.__new__(ReadingDisplay)
        self.view.win, self.view.config, self.view.controller = self.win, config, self.controller
        self.view.keyboard, self.view.prompt = MagicMock(), MagicMock()
        self.view.data_viewer = DataViewerExport(self.store)
        for row in self.store.sentences:
            row["screenshot_status"] = "saved"
        self.view.keyboard.getKeys.return_value = []
        self.prepared = {a.article_id: [MagicMock(name=text) for text in a.pages] for a in self.articles}
        self.playbacks = []
        self.speaker = MagicMock()

        def begin(text, log, event, article_id, condition):
            self.win.now += 100  # Excluded from the article interval.
            log.on_flip(self.win, {}, event, condition=condition, article_id=article_id)
            self.win.flip()

        self.view.wait_screen = begin

        def preload(cached, allow_demo, speaker):
            self.assertTrue(allow_demo)
            self.assertIs(speaker, self.speaker if self.playbacks else None)
            playback = Playback(self.win, cached)
            playback.speaker = self.speaker
            self.playbacks.append(playback)
            return playback

        patcher = patch("psychopy_sync.condition2.preload_article_audio", side_effect=preload)
        self.preload = patcher.start()
        self.addCleanup(patcher.stop)

    def run_condition(self):
        run_condition2(self.view, self.articles, self.prepared, self.audio, self.log, self.store)

    def test_text_and_matching_wavs_advance_without_space_and_share_flip_markers(self):
        self.run_condition()
        rows = csv_rows(self.store.directory / "condition2.csv")
        self.assertEqual([row["status"] for row in rows], ["completed", "completed"])
        self.assertTrue(all(0 < float(row["reading_duration_s"]) < 2 for row in rows))
        self.assertEqual([p.cached.request.text for p in self.playbacks],
                         [text for article in self.articles for text in article.pages])
        self.assertTrue(all(p.stopped for p in self.playbacks))
        self.speaker.close.assert_called_once_with()
        self.assertEqual(len(csv_rows(self.store.root / "reading_speed.csv")), 1)
        self.assertEqual(self.store.metadata["reading_speed"]["speed_per_minute"], 600)
        events = csv_rows(self.log.path)
        starts = [row for row in events if row["event"] == "AUDIO_START"]
        page_starts = [row for row in events if row["event"] == "PAGE_ONSET"]
        ends = [row for row in events if row["event"] == "AUDIO_END"]
        self.assertEqual(len(starts), 4)
        self.assertEqual(len(ends), 4)
        self.assertEqual(len([row for row in events if row["event"] == "PAGE_END"]), 4)
        for start, page, end, playback in zip(starts, page_starts, ends, self.playbacks):
            self.assertEqual(start["timestamp_s"], page["timestamp_s"])
            self.assertAlmostEqual(float(start["timestamp_s"]) + 1000, playback.scheduled)
            self.assertEqual(start["article_id"], playback.cached.request.article_id)
            self.assertEqual(start["page"], str(playback.cached.request.sentence_index))
            self.assertIn(str(playback.cached.path), start["detail"])
            self.assertGreaterEqual(float(end["timestamp_s"]), float(start["timestamp_s"]))
        self.assertTrue(all(row["condition"] == "condition2" for row in events))
        sentence_rows = [r for r in csv_rows(self.store.directory / "sentence_pages.csv")
                         if r["condition"] == "condition2"]
        self.assertEqual([r["status"] for r in sentence_rows], ["completed"] * 4)
        self.assertEqual(len([r for r in events if r["message"].startswith("TRIALID ")]), 4)
        self.assertEqual(len([r for r in events if r["message"].startswith("!V IMGLOAD FILL ")]), 4)
        for row, page in zip(sentence_rows, page_starts):
            self.assertEqual(row["start_timestamp_s"], page["timestamp_s"])
        self.assertTrue(all(call.kwargs["keyList"] == ["escape"]
                            for call in self.view.keyboard.getKeys.call_args_list))

    def test_first_article_plays_before_later_audio_is_ready(self):
        original = self.view.play_page
        readiness = []

        def play(*args):
            readiness.append(self.audio.article_ready(self.articles[1].article_id))
            return original(*args)

        self.view.play_page = play
        self.run_condition()
        self.assertEqual(readiness, [False, False, True, True])

    def test_escape_stops_playback_and_saves_partial_article_without_changing_wpm(self):
        def keys(**kwargs):
            if self.playbacks and self.playbacks[0].scheduled is not None:
                return [SimpleNamespace(name="escape")]
            return []

        self.view.keyboard.getKeys.side_effect = keys
        with self.assertRaises(ExperimentAborted):
            self.run_condition()
        rows = csv_rows(self.store.directory / "condition2.csv")
        self.assertEqual([r["status"] for r in rows], ["aborted", "not_presented"])
        self.assertTrue(rows[0]["start_event_id"] and rows[0]["end_event_id"])
        self.assertEqual(rows[0]["reading_duration_s"], "")
        self.assertTrue(all(p.stopped for p in self.playbacks))
        self.assertIn("AUDIO_ABORT", [r["event"] for r in csv_rows(self.log.path)])
        self.assertEqual(self.store.metadata["reading_speed"]["speed_per_minute"], 600)

    def test_current_article_generation_failure_stops_waiting_before_playback(self):
        self.audio.worker.poll_events.side_effect = [
            [AudioFailure(self.audio.requests[0], "", "model failed")], []]
        with self.assertRaisesRegex(RuntimeError, "model failed"):
            self.run_condition()
        self.preload.assert_not_called()
        row = csv_rows(self.store.directory / "condition2.csv")[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["audio_status"], "failed")
        self.assertEqual(row["start_event_id"], "")

    def test_later_failure_does_not_prevent_first_ready_article_from_playing(self):
        self.audio.worker.poll_events.side_effect = [
            self.cached[:2] + [AudioFailure(self.audio.requests[2], "", "later failure")], [], [], []]
        with self.assertRaisesRegex(RuntimeError, "later failure"):
            self.run_condition()
        self.assertEqual([r["status"] for r in csv_rows(self.store.directory / "condition2.csv")],
                         ["completed", "failed"])
        self.assertEqual(len(self.playbacks), 2)

    def test_preload_failure_never_starts_or_marks_article_completed(self):
        self.preload.side_effect = ValueError("Cached audio changed after download")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.run_condition()
        row = csv_rows(self.store.directory / "condition2.csv")[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["start_timestamp_s"], "")
        self.assertNotIn("AUDIO_START", [r["event"] for r in csv_rows(self.log.path)])

    def test_failed_audio_device_times_out_and_stops_playback(self):
        with patch.object(Playback, "isFinished", new_callable=lambda: property(lambda self: False)):
            with self.assertRaisesRegex(RuntimeError, "playback timed out"):
                self.run_condition()
        self.assertTrue(all(p.stopped for p in self.playbacks))
        self.assertEqual(csv_rows(self.store.directory / "condition2.csv")[0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
