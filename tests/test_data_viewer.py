"""Page capture fidelity, portable image messages and interrupted intervals."""

import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from psychopy_sync.articles import load_experiment_articles
from psychopy_sync.config import ExperimentConfig
from psychopy_sync.data_viewer import DataViewerExport
from psychopy_sync.event_log import EventLog, SessionStore
from psychopy_sync.reading_display import ReadingDisplay


class DataViewerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        assets = root / "assets"
        (assets / "articles").mkdir(parents=True)
        for article_id in ("A", "B"):
            with (assets / "articles" / f"{article_id}.csv").open("w", newline="") as stream:
                csv.writer(stream).writerows([[article_id], ["First, quoted sentence."], ["Second sentence."]])
        self.config = ExperimentConfig(assets_dir=assets, output_dir=root / "data", dummy_mode=True,
                                       condition1_count=1, condition2_count=1, random_seed=4, tts_server_url=None)
        self.articles = load_experiment_articles(self.config)
        self.store = SessionStore(self.config, "S001", self.articles)
        self.win = MagicMock(size=(1920, 1080), movieFrames=[])
        self.view = ReadingDisplay.__new__(ReadingDisplay)
        self.view.win, self.view.config, self.view.footer = self.win, self.config, MagicMock()
        self.prepared = {a.article_id: [MagicMock(), MagicMock()]
                         for selected in self.articles.values() for a in selected}
        self.drawn = []

        def capture(buffer):
            self.assertEqual(buffer, "back")
            self.drawn.append([p.draw.call_count for pages in self.prepared.values() for p in pages])
            image = SimpleNamespace(size=self.win.size,
                                    save=lambda path, format: Path(path).write_bytes(b"fake-full-screen-png"))
            self.win.movieFrames.append(image)
            return image

        self.win.getMovieFrame.side_effect = capture
        self.export = DataViewerExport(self.store)
        self.controller = MagicMock()
        self.log = EventLog(self.store, self.controller, lambda: 0)

    def test_capture_renders_every_page_with_its_actual_condition_layout_without_flipping(self):
        self.export.prepare(self.view, self.articles, self.prepared)
        self.win.flip.assert_not_called()
        self.assertEqual(self.view.footer.draw.call_count, 2)
        self.assertEqual(self.win.getMovieFrame.call_count, 4)
        self.assertEqual(self.win.movieFrames, [])
        self.assertEqual(self.drawn, [[1, 0, 0, 0], [1, 1, 0, 0], [1, 1, 1, 0], [1, 1, 1, 1]])
        for row in self.store.sentences:
            self.assertEqual((row["width_px"], row["height_px"]), (1920, 1080))
            self.assertEqual(row["status"], "not_presented")
            self.assertEqual(len(row["screenshot_sha256"]), 64)
            self.assertTrue((self.store.directory / row["screenshot_path"]).is_file())

    def test_mismatched_screenshot_dimensions_fail_without_silent_scaling(self):
        self.win.getMovieFrame.side_effect = lambda buffer: SimpleNamespace(size=(960, 540))
        with self.assertRaisesRegex(RuntimeError, "differs from EyeLink display coordinates"):
            self.export.prepare(self.view, self.articles, self.prepared)
        self.assertEqual(self.store.metadata["screenshots_status"], "failed")
        self.assertFalse(any(self.store.directory.rglob("*.png")))
        self.assertEqual(self.win.movieFrames, [])

    def test_image_messages_are_unprefixed_and_resolve_relative_to_the_edf(self):
        self.export.prepare(self.view, self.articles, self.prepared)
        row = self.store.sentences[0]
        self.export.start_page(self.log, row["condition"], row["article_id"], 1, 12.5)
        self.export.end_page(self.log, 15.0)
        markers = [call.args[0] for call in self.controller.send_marker.call_args_list]
        self.assertEqual(markers[0], f"TRIALID {row['trial_id']}")
        image_message = next(m for m in markers if m.startswith("!V IMGLOAD FILL "))
        path = image_message.removeprefix("!V IMGLOAD FILL ")
        self.assertFalse(Path(path).is_absolute())
        self.assertTrue((self.store.directory / path).is_file())
        self.assertEqual(markers[-1], "TRIAL_RESULT 0")
        self.assertEqual(row["duration_s"], 2.5)
        self.assertTrue(all(m.isascii() and len(m) <= 130 for m in markers))

    def test_connection_failure_keeps_an_open_sentence_without_inventing_an_offset(self):
        self.export.prepare(self.view, self.articles, self.prepared)
        row = self.store.sentences[0]
        self.export.start_page(self.log, row["condition"], row["article_id"], 1, 12.5)
        self.controller.send_marker.side_effect = IOError("connection lost")
        with self.assertRaises(IOError):
            self.export.end_page(self.log, 15.0)
        self.export.mark_interrupted()
        self.assertEqual(row["status"], "interrupted")
        self.assertEqual(row["end_timestamp_s"], "")
        self.assertEqual(row["duration_s"], "")


if __name__ == "__main__":
    unittest.main()
