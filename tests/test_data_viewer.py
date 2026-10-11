"""Page capture fidelity, portable image messages and interrupted intervals."""

import csv
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

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
        self.prepared = {}
        for selected in self.articles.values():
            for article in selected:
                pages = []
                for text in article.pages:
                    page = MagicMock()
                    page.word_areas = [dict(word_index=i, line_index=1, word=m.group(), ia_label=f"w{i:04d}",
                        char_start=m.start(), char_end=m.end(), left=i * 100, top=100,
                        right=i * 100 + 80, bottom=130)
                        for i, m in enumerate(re.finditer(r"\S+", text), 1)]
                    pages.append(page)
                self.prepared[article.article_id] = pages
        preview = patch("psychopy_sync.data_viewer.save_aoi_preview",
                        side_effect=lambda image, areas, path: path.write_bytes(b"fake-preview"))
        preview.start()
        self.addCleanup(preview.stop)
        baseline = patch.object(DataViewerExport, "prepare_baseline", autospec=True,
            side_effect=lambda exporter, view: exporter.store.metadata.update(baseline_assets_status="saved"))
        baseline.start()
        self.addCleanup(baseline.stop)
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
            self.assertEqual(row["ias_status"], "saved")
            self.assertEqual(row["word_count"], len(row["text"].split()))
            lines = (self.store.directory / row["ias_path"]).read_text().splitlines()
            self.assertEqual(len(lines), row["word_count"])
            self.assertTrue(all(line.startswith("RECTANGLE ") for line in lines))
        with (self.store.directory / "word_aois.csv").open(encoding="utf-8-sig", newline="") as stream:
            words = list(csv.DictReader(stream))
        self.assertEqual(len(words), sum(row["word_count"] for row in self.store.sentences))

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
        aoi_message = next(m for m in markers if m.startswith("!V IAREA FILE "))
        aoi_path = aoi_message.removeprefix("!V IAREA FILE ")
        self.assertEqual(aoi_path, row["ias_path"])
        self.assertTrue((self.store.directory / aoi_path).is_file())
        self.assertEqual(markers[-1], "TRIAL_RESULT 0")
        self.assertEqual(row["duration_s"], 2.5)
        self.assertTrue(all(m.isascii() and len(m) <= 130 for m in markers))

    def test_one_article_baseline_precedes_two_sentence_trials(self):
        self.export.prepare(self.view, self.articles, self.prepared)
        article = self.articles["condition1"][0]
        self.export.start_baseline(self.log, "condition1", article.article_id, 10.0)
        self.export.start_page(self.log, "condition1", article.article_id, 1, 11.5)
        self.export.start_page(self.log, "condition1", article.article_id, 2, 12.5)
        self.export.end_phase(self.log, 14.0)
        markers = [call.args[0] for call in self.controller.send_marker.call_args_list]
        self.assertEqual(markers.count("BASELINE_START"), 1)
        self.assertEqual(markers.count("BASELINE_END"), 1)
        self.assertEqual(markers.count("SENTENCE_START"), 2)
        self.assertEqual(markers.count("SENTENCE_END"), 2)
        self.assertLess(markers.index("BASELINE_END"), markers.index("SENTENCE_START"))
        self.assertTrue(markers[-2].startswith("PASSAGE_END "))
        row = self.store.rows["condition1"][0]
        self.assertEqual(row["baseline_duration_s"], 1.5)
        self.assertEqual(self.store.article_durations("condition1", article.article_id)["reading_duration_s"], 2.5)

    def test_escape_during_baseline_leaves_sentence_unpresented(self):
        self.export.prepare(self.view, self.articles, self.prepared)
        article = self.articles["condition1"][0]
        self.export.start_baseline(self.log, "condition1", article.article_id, 10.0)
        self.export.end_phase(self.log, 10.5, status="aborted")
        row = self.store.rows["condition1"][0]
        self.assertEqual(row["baseline_status"], "aborted")
        self.assertEqual(row["baseline_duration_s"], 0.5)
        self.assertEqual(self.store.sentences[0]["status"], "not_presented")
        markers = [call.args[0] for call in self.controller.send_marker.call_args_list]
        self.assertNotIn("SENTENCE_START", markers)
        self.assertEqual(markers[-1], "TRIAL_RESULT 1")

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
