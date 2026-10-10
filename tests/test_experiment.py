"""Event-paired timing, output tables and EDF lifecycle without hardware."""
import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from psychopy_sync.articles import load_experiment_articles
from psychopy_sync.condition1 import ExperimentAborted
from psychopy_sync.config import ExperimentConfig, EyeLinkConfig
from psychopy_sync.event_log import EventLog, SessionStore
from psychopy_sync.experiment import run_experiment
from psychopy_sync.eyelink import EyeLinkController
from psychopy_sync.reading_speed import reading_summary
from psychopy_sync.reading_display import ReadingDisplay


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class FakeWin:
    def __init__(self):
        self.size, self.now, self.callbacks, self.closed = (1920, 1080), 0.0, [], False

    def timeOnFlip(self, obj, key):
        self.callOnFlip(lambda: obj.update({key: self.now}))

    def callOnFlip(self, callback):
        self.callbacks.append(callback)

    def flip(self):
        callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()

    def close(self):
        self.closed = True


class FakeView:
    abort_article = None

    def __init__(self, win, config, controller):
        self.win, self.config, self.controller = win, config, controller

    def prepare(self, articles):
        return {a.article_id: list(a.pages) for a in articles}

    def wait_screen(self, text, log, event="WAIT", article_id=""):
        self.win.now += 100  # Long gaps must not enter the reading denominator.
        log.on_flip(self.win, {}, event, condition="condition1", article_id=article_id)
        self.win.flip()
        log.flush()

    def read_page(self, page, log, onset, event, article_id, page_index):
        self.win.now += 1
        log.on_flip(self.win, onset, event, condition="condition1", article_id=article_id, page=page_index)
        self.win.flip()
        if article_id == self.abort_article:
            raise ExperimentAborted("Escape pressed")

    def clear_article(self, log, end, event, article_id):
        self.win.now += 10
        log.on_flip(self.win, end, event, condition="condition1", article_id=article_id)
        self.win.flip()


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        assets = self.root / "assets"
        (assets / "articles").mkdir(parents=True)
        for article_id, title, count in (("A", "One", 10), ("B", "Two", 30), ("C", "Three", 2)):
            with (assets / "articles" / (article_id + ".csv")).open("w", newline="", encoding="utf-8-sig") as stream:
                csv.writer(stream).writerows([[title], [" ".join(["word"] * count)]])
        self.config = ExperimentConfig(assets_dir=assets, output_dir=self.root / "data", condition2_count=1,
                                       random_seed=4, dummy_mode=False, tts_server_url=None)
        selected = load_experiment_articles(self.config)
        self.article_ids = {a.title: a.article_id for articles in selected.values() for a in articles}
        self.win, self.controller = FakeWin(), MagicMock()
        self.controller.config = EyeLinkConfig()

        def finish(destination):
            Path(destination).write_bytes(b"mock-edf")
            return True

        self.controller.finish_session.side_effect = finish
        psychopy = types.SimpleNamespace(logging=types.SimpleNamespace(
            defaultClock=types.SimpleNamespace(getTime=lambda: self.win.now)))
        for patcher in (patch.dict("sys.modules", {"psychopy": psychopy}),
                        patch("psychopy_sync.experiment.create_window", return_value=self.win),
                        patch("psychopy_sync.experiment.EyeLinkController", return_value=self.controller),
                        patch("psychopy_sync.experiment.ReadingDisplay", FakeView),
                        patch.object(FakeView, "abort_article", None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def session_dir(self):
        return next((self.config.output_dir / "S001").iterdir())

    def test_session_pairs_events_excludes_gaps_and_keeps_condition2_unread(self):
        summary, directory = run_experiment("S001", self.config)
        self.assertEqual((summary["total_reading_s"], summary["total_units"], summary["speed_per_minute"]), (20, 40, 120))
        self.controller.start_recording.assert_called_once_with()
        self.controller.finish_session.assert_called_once_with(directory / "eyelink.edf")
        self.assertTrue(self.win.closed)
        events = {r["event_id"]: r for r in read_csv(directory / "user_logs.csv")}
        for row in read_csv(directory / "condition1.csv"):
            start, end = events[row["start_event_id"]], events[row["end_event_id"]]
            self.assertEqual((start["event"], end["event"]), ("ARTICLE_ONSET", "ARTICLE_END"))
            self.assertEqual(start["timestamp_s"], row["start_timestamp_s"])
            self.assertEqual(float(end["timestamp_s"]) - float(start["timestamp_s"]), float(row["reading_duration_s"]))
            self.assertEqual(start["timestamp_source"], "psychopy_flip")
        self.assertEqual(read_csv(directory / "condition2.csv")[0]["status"], "not_presented")
        self.assertEqual(len(read_csv(self.config.output_dir / "reading_speed.csv")), 1)
        self.assertEqual(len(read_csv(self.config.output_dir / "users.csv")), 1)
        self.assertEqual(json.loads((directory / "session.json").read_text())["edf_status"], "downloaded")
        self.assertTrue((directory / "stimuli" / (self.article_ids["One"] + ".txt")).exists())
        metadata = json.loads((directory / "session.json").read_text())
        self.assertEqual(metadata["selection_seed"], 4)
        self.assertEqual(metadata["article_pool_ids"], ["A", "B", "C"])
        self.assertEqual(metadata["selected_articles"]["condition1"][0]["title"], "One")
        self.assertEqual(metadata["selected_articles"]["condition1"][0]["article_id"], "A")
        self.assertEqual(metadata["selected_articles"]["condition1"][0]["path"], "articles/A.csv")
        self.assertEqual(read_csv(directory / "condition2.csv")[0]["page_count"], "1")
        tts_directory = (self.config.assets_dir / "TTS" / "S001" / directory.name).resolve()
        self.assertEqual(metadata["tts_directory"], str(tts_directory))
        self.assertEqual(metadata["tts_status"], "not_configured")
        requests = json.loads((tts_directory / "requests.json").read_text())["articles"]
        self.assertEqual([r["article_id"] for r in requests], ["C"])
        self.assertEqual(requests[0]["target_wpm"], 120)
        self.assertEqual(requests[0]["participant_id"], "S001")
        self.assertEqual(requests[0]["sentence_index"], 1)
        self.assertEqual(metadata["tts_index_path"], str(tts_directory / "tts_index.csv"))
        sentence_rows = read_csv(tts_directory / "tts_index.csv")
        self.assertEqual(len(sentence_rows), 1)
        self.assertEqual(sentence_rows[0]["text"], requests[0]["text"])
        self.assertEqual(sentence_rows[0]["audio_status"], "not_configured")
        self.assertEqual(sentence_rows[0]["audio_path"], "")
        self.assertTrue(sentence_rows[0]["planned_audio_path"].endswith("C/sentence_0001.wav"))
        self.assertEqual(list(tts_directory.glob("*.wav")), [])
        self.assertEqual(read_csv(directory / "condition2.csv")[0]["audio_status"], "not_configured")

    def test_dummy_session_runs_without_eyelink_packages_calibration_or_edf(self):
        config = replace(self.config, dummy_mode=True)
        with patch.dict("sys.modules", {"pylink": None, "EyeLinkCoreGraphicsPsychoPy": None}), \
                patch("psychopy_sync.experiment.EyeLinkController", side_effect=AssertionError("Real tracker used")):
            summary, directory = run_experiment("S001", config)
        self.assertEqual(directory.parent, config.output_dir / "dummy" / "S001")
        self.assertEqual(summary["speed_per_minute"], 120)
        self.assertEqual(len(read_csv(config.output_dir / "dummy" / "reading_speed.csv")), 1)
        self.assertFalse((config.output_dir / "reading_speed.csv").exists())
        self.assertFalse((config.output_dir / "users.csv").exists())
        metadata = json.loads((directory / "session.json").read_text())
        self.assertTrue(metadata["dummy_mode"])
        self.assertEqual(metadata["edf_status"], "disabled_dummy")
        self.assertEqual(metadata["host_edf_name"], "")
        self.assertIsNone(metadata["eyelink_config"])
        self.assertEqual(list(directory.glob("*.edf")), [])
        logs = read_csv(directory / "user_logs.csv")
        self.assertIn("DUMMY_READY", [row["event"] for row in logs])
        self.assertNotIn("CALIBRATION_CONFIRM", [row["event"] for row in logs])
        self.assertTrue(all(row["marker_status"] == "disabled_dummy" for row in logs))
        self.assertEqual([row["status"] for row in read_csv(directory / "condition1.csv")], ["completed", "completed"])
        manifest = json.loads((Path(metadata["tts_directory"]) / "manifest.json").read_text())
        self.assertTrue(manifest["dummy_mode"])
        self.assertEqual(manifest["status"], "not_configured")
        self.controller.assert_not_called()
        self.controller.connect.assert_not_called()
        self.controller.calibrate.assert_not_called()
        self.controller.finish_session.assert_not_called()
        self.assertTrue(self.win.closed)

    def test_configured_audio_continues_into_condition2_before_edf_cleanup(self):
        config = replace(self.config, tts_server_url="http://192.168.137.2:8765")
        audio = MagicMock()
        audio.manifest = {"status": "running"}

        def present(view, articles, prepared, session_audio, log, store):
            self.controller.finish_session.assert_not_called()
            self.assertEqual(store.metadata["reading_speed"]["speed_per_minute"], 120)
            self.assertEqual(session_audio, audio)
            self.assertIn(articles[0].article_id, prepared)
            store.rows["condition2"][0]["status"] = "completed"

        with patch("psychopy_sync.experiment.SessionAudio", return_value=audio) as prepare, \
                patch("psychopy_sync.experiment.run_condition2", side_effect=present) as run:
            _, directory = run_experiment("S001", config)
        prepare.assert_called_once()
        audio.start.assert_called_once_with()
        run.assert_called_once()
        audio.stop.assert_called_once_with()
        self.assertEqual(read_csv(directory / "condition2.csv")[0]["status"], "completed")
        metadata = json.loads((directory / "session.json").read_text())
        self.assertEqual((metadata["status"], metadata["condition2_status"]), ("completed", "completed"))
        self.controller.start_recording.assert_called_once_with()
        self.controller.finish_session.assert_called_once()

    def test_dummy_abort_keeps_partial_logs_without_speed_or_edf(self):
        config = replace(self.config, dummy_mode=True)
        with patch.dict("sys.modules", {"pylink": None, "EyeLinkCoreGraphicsPsychoPy": None}), \
                patch.object(FakeView, "abort_article", self.article_ids["Two"]):
            with self.assertRaises(ExperimentAborted):
                run_experiment("S001", config)
        directory = next((config.output_dir / "dummy" / "S001").iterdir())
        self.assertEqual([row["status"] for row in read_csv(directory / "condition1.csv")], ["completed", "aborted"])
        self.assertEqual(read_csv(config.output_dir / "dummy" / "reading_speed.csv"), [])
        self.assertEqual(json.loads((directory / "session.json").read_text())["edf_status"], "disabled_dummy")
        self.assertEqual(list(directory.glob("*.edf")), [])
        self.assertFalse((config.assets_dir / "TTS").exists())
        self.controller.connect.assert_not_called()
        self.controller.finish_session.assert_not_called()
        self.assertTrue(self.win.closed)

    def test_dummy_mode_requires_a_boolean(self):
        for invalid in ("False", "True", 0, 1, None):
            with self.subTest(dummy_mode=invalid), self.assertRaisesRegex(ValueError, "dummy_mode"):
                replace(self.config, dummy_mode=invalid)

    def test_abort_retains_partial_data_and_edf_without_publishing_speed(self):
        with patch.object(FakeView, "abort_article", self.article_ids["Two"]):
            with self.assertRaises(ExperimentAborted):
                run_experiment("S001", self.config)
        rows = read_csv(self.session_dir() / "condition1.csv")
        self.assertEqual([r["status"] for r in rows], ["completed", "aborted"])
        self.assertTrue(rows[1]["start_event_id"] and rows[1]["end_event_id"])
        self.assertEqual(rows[1]["reading_duration_s"], "")
        self.assertEqual(read_csv(self.config.output_dir / "reading_speed.csv"), [])
        self.assertTrue((self.session_dir() / "eyelink.edf").exists())
        self.assertTrue(self.win.closed)
        self.assertFalse((self.config.assets_dir / "TTS").exists())

    def test_transfer_failure_preserves_host_recovery_name_and_closes_resources(self):
        self.controller.finish_session.side_effect = IOError("connection lost")
        with self.assertRaisesRegex(RuntimeError, "EDF recovery required"):
            run_experiment("S001", self.config)
        metadata = json.loads((self.session_dir() / "session.json").read_text())
        self.assertEqual(metadata["edf_status"], "recovery_required")
        self.assertRegex(metadata["host_edf_name"], r"^[A-Z0-9]{8}\.EDF$")
        self.controller.close.assert_called_once_with()
        self.assertTrue(self.win.closed)

    def test_missing_articles_fail_before_hardware_or_registration(self):
        with self.assertRaisesRegex(ValueError, "requires 4 distinct"):
            run_experiment("S001", replace(self.config, condition1_count=3))
        self.controller.connect.assert_not_called()
        self.assertFalse(self.config.output_dir.exists())

    def test_same_user_new_sessions_with_id_only_registry(self):
        _, first = run_experiment("S001", self.config)
        _, second = run_experiment("S001", self.config)
        self.assertNotEqual(first, second)
        self.assertEqual(len(read_csv(self.config.output_dir / "users.csv")), 1)
        self.assertEqual(len(read_csv(self.config.output_dir / "reading_speed.csv")), 2)
        user = read_csv(self.config.output_dir / "users.csv")[0]
        self.assertEqual(set(user), {"participant_id", "created_at_utc"})
        self.assertEqual(user["participant_id"], "S001")
        self.assertTrue(user["created_at_utc"])

    def test_legacy_user_registry_drops_names_and_preserves_ids_and_dates(self):
        self.config.output_dir.mkdir(parents=True)
        users_path = self.config.output_dir / "users.csv"
        with users_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["participant_id", "name", "created_at_utc"])
            writer.writerow(["S001", "Legacy participant", "2026-01-01T00:00:00+00:00"])
        selected = load_experiment_articles(self.config)
        SessionStore(self.config, "S001", selected)
        SessionStore(self.config, "S002", selected)
        users = read_csv(users_path)
        self.assertEqual([row["participant_id"] for row in users], ["S001", "S002"])
        self.assertEqual(users[0]["created_at_utc"], "2026-01-01T00:00:00+00:00")
        self.assertTrue(all(set(row) == {"participant_id", "created_at_utc"} for row in users))
        self.assertNotIn("Legacy participant", users_path.read_text(encoding="utf-8-sig"))

    def test_pool_uses_filename_ids_without_catalog_and_rejects_path_escape(self):
        selected = load_experiment_articles(replace(self.config, condition1_count=1, condition2_count=0))
        self.assertEqual([a.title for a in selected["condition1"]], ["One"])
        self.assertEqual([a.article_id for a in selected["condition1"]], ["A"])
        self.assertEqual(selected["condition2"], [])
        (self.config.assets_dir / "articles" / "notes.txt").write_text("ignored")
        self.assertEqual(selected, load_experiment_articles(replace(self.config, condition1_count=1, condition2_count=0)))
        self.assertFalse((self.config.assets_dir / "articles.csv").exists())
        with self.assertRaisesRegex(ValueError, "inside assets"):
            load_experiment_articles(replace(self.config, articles_folder="../outside"))

    def test_repeated_titles_keep_distinct_filename_ids(self):
        (self.config.assets_dir / "articles" / "B.csv").write_text("One\nAnother article with the same title.\n")
        selected = load_experiment_articles(self.config)
        self.assertEqual([a.article_id for a in selected["condition1"]], ["A", "B"])
        self.assertEqual([a.title for a in selected["condition1"]], ["One", "One"])

    def test_invalid_filename_ids_are_rejected(self):
        (self.config.assets_dir / "articles" / "bad id.csv").write_text("Title\nA sentence.\n")
        with self.assertRaisesRegex(ValueError, "Invalid article ID"):
            load_experiment_articles(self.config)

    def test_case_variant_file_ids_are_rejected_before_reading(self):
        folder = self.config.assets_dir / "articles"
        # Simulate a case-sensitive filesystem even when the host is macOS.
        with patch.object(Path, "iterdir", return_value=iter([folder / "A.csv", folder / "a.csv"])), \
                patch.object(Path, "is_file", return_value=True):
            with self.assertRaisesRegex(ValueError, "Duplicate article ID"):
                load_experiment_articles(self.config)

    def test_csv_pages_preserve_quotes_newlines_order_and_skip_empty_cells(self):
        expected = ['First sentence, with a comma.', 'Second "quoted" sentence.\nStill the same page.']
        with (self.config.assets_dir / "articles" / "A.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            csv.writer(stream).writerows([["A title, with commas"], [expected[0]], [""], [expected[1]]])
        selected = load_experiment_articles(self.config)
        article = selected["condition1"][0]
        self.assertEqual(article.pages, tuple(expected))
        self.assertEqual(article.source_rows, (2, 4))
        self.assertEqual(article.article_id, "A")
        self.assertEqual(article.path, "articles/A.csv")
        self.assertEqual(article.unit_count, sum(len(page.split()) for page in expected))
        store = SessionStore(self.config, "S001", selected)
        for index, page in enumerate(expected, 1):
            self.assertEqual((store.directory / "stimuli" / f"{article.article_id}_page{index:03d}.txt").read_text(), page)

    def test_seed_reproduces_selection_and_conditions_never_overlap(self):
        first = load_experiment_articles(self.config)
        again = load_experiment_articles(self.config)
        other = load_experiment_articles(replace(self.config, random_seed=1))
        self.assertEqual(first, again)
        self.assertNotEqual([a.title for a in first["condition1"]], [a.title for a in other["condition1"]])
        ids = [a.article_id for selected in first.values() for a in selected]
        self.assertEqual(len(ids), len(set(ids)))
        with patch("psychopy_sync.articles.secrets.randbits", return_value=123):
            fresh = load_experiment_articles(replace(self.config, random_seed=None))
        store = SessionStore(self.config, "S001", fresh)
        self.assertEqual(store.metadata["selection_seed"], 123)

    def test_empty_articles_empty_titles_and_extra_cells_are_rejected(self):
        table = self.config.assets_dir / "articles" / "A.csv"
        for text, error in (("\ntext\n", "nonempty article title"),
                            ("Title\n\n", "no countable pages"),
                            ("Title\ntext,extra\n", "more than one column")):
            with self.subTest(text=text):
                table.write_text(text)
                with self.assertRaisesRegex(ValueError, error):
                    load_experiment_articles(self.config)

    def test_prepared_csv_pages_are_displayed_without_repagination(self):
        class TextStim:
            def __init__(self, win, text="", **kwargs):
                self.text = text

            @property
            def boundingBox(self):
                return len(self.text), 1

        article = load_experiment_articles(self.config)["condition1"][0]
        article = replace(article, pages=("A short page.", "A second, longer page."))
        view = ReadingDisplay.__new__(ReadingDisplay)
        view.win, view.config, view.visual = self.win, self.config, types.SimpleNamespace(TextStim=TextStim)
        view.text_width, view.text_height = 100, 20
        prepared = view.prepare([article])
        self.assertEqual(tuple(page.text for page in prepared[article.article_id]), article.pages)
        view.text_width = 10
        with self.assertRaisesRegex(ValueError, "page 1 exceeds"):
            view.prepare([article])

    def test_invalid_reading_intervals_are_rejected(self):
        row = dict(status="completed", count_mode="words", unit_count=10,
                   start_event_id="E1", end_event_id="E2", start_timestamp_s=10, end_timestamp_s=10)
        with self.assertRaises(ValueError):
            reading_summary([row], 1)
        with self.assertRaises(ValueError):
            reading_summary([dict(row, status="aborted")], 1)

    def test_flip_marker_and_log_share_timestamp_and_failed_markers_are_saved(self):
        store = SessionStore(self.config, "S001", load_experiment_articles(self.config))
        log = EventLog(store, self.controller, lambda: 999)
        target = {}
        self.win.now = 123.5
        log.on_flip(self.win, target, "ARTICLE_ONSET", article_id="A")
        self.assertEqual(target, {})
        self.win.flip()
        self.assertEqual(target["timestamp_s"], 123.5)
        self.assertEqual(read_csv(log.path), [])
        log.flush()
        self.controller.send_marker.side_effect = IOError("lost")
        with self.assertRaises(IOError):
            log.emit("SESSION_ERROR")
        log.flush()
        rows = read_csv(log.path)
        self.assertEqual(rows[1]["marker_status"], "failed")
        self.assertEqual(rows[1]["timestamp_source"], "psychopy_clock")


class EDFLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.controller = EyeLinkController(EyeLinkConfig())
        self.tracker = MagicMock()
        self.controller._tracker = self.tracker
        self.controller._pylink = MagicMock()
        for method in ("openDataFile", "startRecording", "isRecording", "sendMessage"):
            getattr(self.tracker, method).return_value = 0

    def test_pupil_fields_continuous_recording_and_atomic_transfer(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "session.edf"

            def receive(source, target):
                self.assertFalse(self.controller._recording)
                self.tracker.closeDataFile.assert_called_once_with()
                Path(target).write_bytes(b"edf")
                return 3

            self.tracker.receiveDataFile.side_effect = receive
            self.controller.open_edf("ABC123.EDF")
            self.controller.start_recording()
            self.controller.send_marker("ARTICLE_ONSET")
            self.controller.check_recording()
            self.controller.finish_session(destination)
            self.assertEqual(destination.read_bytes(), b"edf")
        self.tracker.startRecording.assert_called_once_with(1, 1, 0, 0)
        self.tracker.stopRecording.assert_called_once_with()
        self.assertTrue(any("AREA" in c.args[0] for c in self.tracker.sendCommand.call_args_list))

    def test_recording_failure_and_connection_loss_are_reported(self):
        self.controller.open_edf("TEST.EDF")
        self.tracker.startRecording.return_value = 2
        with self.assertRaisesRegex(RuntimeError, "recording failed"):
            self.controller.start_recording()
        self.tracker.startRecording.return_value = 0
        self.controller.start_recording()
        self.tracker.isRecording.return_value = 3
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.controller.check_recording()

    def test_marker_limits_and_negative_transfer_are_reported(self):
        self.controller.open_edf("TEST.EDF")
        for invalid in ("x" * 131, "中文"):
            with self.assertRaises(ValueError):
                self.controller.send_marker(invalid)
        with tempfile.TemporaryDirectory() as temp:
            self.tracker.receiveDataFile.return_value = -1
            with self.assertRaisesRegex(IOError, "recover TEST.EDF"):
                self.controller.finish_session(Path(temp) / "test.edf")


class KeyboardTimingTests(unittest.TestCase):
    def make_view(self):
        view = ReadingDisplay.__new__(ReadingDisplay)
        view.config = ExperimentConfig()
        view.win, view.controller, view.keyboard = FakeWin(), MagicMock(), MagicMock()
        return view

    def test_held_space_requires_release_then_fresh_press(self):
        for states in ([True, True, False], [[True], [True], [False]]):
            with self.subTest(states=states):
                view = self.make_view()
                space = types.SimpleNamespace(name="space")
                view.keyboard.getState.side_effect = states
                view.keyboard.getKeys.side_effect = [[space], [], [space]]
                draw = MagicMock()
                callback = MagicMock()
                view._wait(draw, callback)
                self.assertEqual(view.keyboard.getKeys.call_count, 3)
                self.assertEqual(draw.call_count, 3)
                callback.assert_called_once_with()
                self.assertEqual(view.keyboard.clearEvents.call_count, 2)

    def test_fresh_space_advances_with_scalar_or_sequence_key_state(self):
        for state in (False, [False]):
            with self.subTest(state=state):
                view = self.make_view()
                view.keyboard.getState.return_value = state
                view.keyboard.getKeys.return_value = [types.SimpleNamespace(name="space")]
                view._wait(MagicMock())
                view.keyboard.getKeys.assert_called_once()
                view.keyboard.getState.assert_called_once_with("space")

    def test_escape_takes_precedence_over_advance(self):
        view = self.make_view()
        view.keyboard.getState.return_value = False
        view.keyboard.getKeys.return_value = [types.SimpleNamespace(name="space"), types.SimpleNamespace(name="escape")]
        with self.assertRaises(ExperimentAborted):
            view._wait(MagicMock())

    def test_recording_loss_terminates_reading_loop(self):
        view = self.make_view()
        view.keyboard.getState.return_value = False
        view.controller.check_recording.side_effect = RuntimeError("recording lost")
        with self.assertRaisesRegex(RuntimeError, "recording lost"):
            view._wait(MagicMock())
        view.keyboard.getKeys.assert_not_called()


if __name__ == "__main__":
    unittest.main()
