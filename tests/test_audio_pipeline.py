"""Actual HTTP/file integration checks without GPU or PsychoPy dependencies."""

import csv
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gpu_service.f5_generator import DemoGenerator, F5Generator, split_article
from gpu_service.job_queue import JobQueue
from gpu_service.tts_server import AudioHandler, AudioServer
from psychopy_sync.audio_client import (
    AudioClient, AudioFailure, BackgroundAudioClient, CachedAudio, load_articles,
)
from psychopy_sync.display import preload_article_audio
from psychopy_sync.articles import load_experiment_articles
from psychopy_sync.config import ExperimentConfig
from psychopy_sync.event_log import SessionStore
from psychopy_sync.reading_speed import reading_summary
from psychopy_sync.session_audio import SessionAudio
from shared.contracts import GenerationRequest, inspect_wav, sha256_file


def article(article_id="A"):
    return GenerationRequest("session", "participant", article_id, "Alpha beta gamma delta.", 120, 4)


class ControlledGenerator(DemoGenerator):
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate(self, request, output_path):
        self.entered.set()
        if not self.release.wait(2.0):
            raise RuntimeError("Test generator timed out")
        return super().generate(request, output_path)


class AudioPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        log_patch = patch.object(AudioHandler, "log_message")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def serve(self, generator=None):
        jobs = JobQueue(self.root / "generated", generator or DemoGenerator())
        server = AudioServer(("127.0.0.1", 0), jobs)
        worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        worker.start()

        def cleanup():
            if isinstance(generator, ControlledGenerator):
                generator.release.set()
            server.shutdown()
            server.server_close()
            worker.join(timeout=1.0)
            jobs.close()

        self.addCleanup(cleanup)
        client = AudioClient(f"http://127.0.0.1:{server.server_port}", self.root / "cached")
        return jobs, server, client

    def wait_terminal(self, client, job_id):
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            metadata = client.get_status(job_id)
            if metadata["status"] in ("available", "failed"):
                return metadata
            time.sleep(0.005)
        self.fail("Audio job did not reach a terminal state")

    def test_background_submission_downloads_each_article_in_order(self):
        _, _, client = self.serve()
        worker = BackgroundAudioClient(client, poll_interval_s=0.005)
        self.addCleanup(lambda: worker.stop(timeout=1.0))
        worker.start([article("A"), article("B")])
        results = [worker.events.get(timeout=2.0) for _ in range(2)]
        self.assertTrue(all(isinstance(result, CachedAudio) for result in results))
        self.assertEqual([result.request.article_id for result in results], ["A", "B"])
        for result in results:
            self.assertEqual(inspect_wav(result.path)["duration_s"], 2.0)
            self.assertEqual(sha256_file(result.path), result.metadata["audio_sha256"])
            self.assertEqual(result.metadata["actual_wpm"], 120.0)
        self.assertEqual(list(client.cache_dir.glob("*.partial")), [])
        with self.assertRaisesRegex(ValueError, "Demo silence"):
            preload_article_audio(results[0])

    def test_unfinished_article_cannot_be_downloaded(self):
        generator = ControlledGenerator()
        _, _, client = self.serve(generator)
        job_id = client.submit_articles([article()])[0]["job_id"]
        self.assertTrue(generator.entered.wait(1.0))
        with self.assertRaises(HTTPError) as caught:
            urlopen(client.base_url + f"/jobs/{job_id}/audio", timeout=1.0)
        self.assertEqual(caught.exception.code, 409)
        caught.exception.close()
        generator.release.set()
        metadata = self.wait_terminal(client, job_id)
        self.assertEqual(metadata["status"], "available")
        self.assertTrue(client.download_audio(article(), job_id, metadata).path.is_file())

    def test_preload_checks_integrity_then_uses_ptb_and_the_shared_speaker(self):
        _, _, client = self.serve()
        request = article()
        job_id = client.submit_articles([request])[0]["job_id"]
        cached = client.download_audio(request, job_id, self.wait_terminal(client, job_id))
        sound, speaker = MagicMock(), MagicMock()
        with patch.dict("sys.modules", {"psychopy.sound.backend_ptb": types.SimpleNamespace(SoundPTB=sound)}):
            self.assertIs(preload_article_audio(cached, allow_demo=True, speaker=speaker), sound.return_value)
        sound.assert_called_once_with(str(cached.path), preBuffer=-1, autoLog=False, speaker=speaker)
        cached.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed after download"):
            preload_article_audio(cached, allow_demo=True)

    def test_failed_generation_reports_error_and_next_article_still_completes(self):
        class SometimesBroken(DemoGenerator):
            def generate(self, request, output_path):
                if request.article_id == "A":
                    Path(output_path).write_bytes(b"invalid WAV")
                    return {}
                return super().generate(request, output_path)

        _, _, client = self.serve(SometimesBroken())
        worker = BackgroundAudioClient(client, poll_interval_s=0.005)
        self.addCleanup(lambda: worker.stop(timeout=1.0))
        with patch("gpu_service.job_queue.logging.exception"):
            worker.start([article("A"), article("B")])
            failed = worker.events.get(timeout=2.0)
            cached = worker.events.get(timeout=2.0)
        self.assertIsInstance(failed, AudioFailure)
        self.assertIsInstance(cached, CachedAudio)
        self.assertEqual(failed.request.article_id, "A")
        self.assertEqual(cached.request.article_id, "B")

    def test_invalid_batch_does_not_enqueue_valid_prefix(self):
        jobs, _, client = self.serve()
        invalid = article("B").to_dict()
        invalid["target_wpm"] = float("nan")
        data = json.dumps({"articles": [article().to_dict(), invalid]}).encode()
        request = Request(client.base_url + "/jobs/batch", data=data)
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=1.0)
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(list(jobs.output_dir.iterdir()), [])

    def test_corrupt_checksum_is_rejected_without_publishing_cache(self):
        _, _, client = self.serve()
        job_id = client.submit_articles([article()])[0]["job_id"]
        metadata = self.wait_terminal(client, job_id)
        metadata["audio_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            client.download_audio(article(), job_id, metadata)
        self.assertEqual(list(client.cache_dir.iterdir()), [])

    def test_wrong_participant_metadata_is_rejected(self):
        _, _, client = self.serve()
        job_id = client.submit_articles([article()])[0]["job_id"]
        metadata = self.wait_terminal(client, job_id)
        metadata["participant_id"] = "someone_else"
        with self.assertRaisesRegex(ValueError, "does not match"):
            client.download_audio(article(), job_id, metadata)

    def test_completed_audio_remains_accessible_after_queue_restart(self):
        jobs, server, client = self.serve()
        job_id = client.submit_articles([article()])[0]["job_id"]
        self.assertEqual(self.wait_terminal(client, job_id)["status"], "available")
        jobs.close()
        recovered = JobQueue(jobs.output_dir, DemoGenerator())
        self.addCleanup(recovered.close)
        server.jobs = recovered
        metadata = client.get_status(job_id)
        self.assertTrue(client.download_audio(article(), job_id, metadata).path.is_file())

    def session_batch(self, server):
        assets = self.root / "assets"
        (assets / "articles").mkdir(parents=True)
        for index in range(3):
            with (assets / "articles" / f"article_{index}.csv").open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerows([["Title"], ["Alpha beta gamma delta."], [],
                                            ["Echo, foxtrot."], ["Alpha beta gamma delta."]])
        config = ExperimentConfig(assets_dir=assets, output_dir=self.root / "data", condition1_count=1,
                                  condition2_count=2, random_seed=4,
                                  tts_server_url=f"http://127.0.0.1:{server.server_port}")
        articles = load_experiment_articles(config)
        store = SessionStore(config, "S001", articles)
        row = store.rows["condition1"][0]
        row.update(status="completed", start_event_id="E1", end_event_id="E2",
                   start_timestamp_s=100.0, end_timestamp_s=105.0, reading_duration_s=5.0)
        summary = reading_summary(store.rows["condition1"], 1)
        store.save_speed(summary)
        return config, store, articles, summary

    def test_condition2_audio_has_one_wav_per_sentence_and_an_exact_user_index(self):
        _, server, _ = self.serve()
        config, store, articles, summary = self.session_batch(server)
        batch = SessionAudio(config, store, articles["condition2"], summary)
        self.addCleanup(batch.stop)
        batch.start()
        self.assertEqual(batch.directory, (config.assets_dir / "TTS" / "S001" / store.session_id).resolve())
        deadline = time.monotonic() + 2.0
        while not batch.done and time.monotonic() < deadline:
            batch.poll()
            time.sleep(0.005)
        self.assertEqual(batch.manifest["status"], "cached")
        with batch.index_path.open(encoding="utf-8-sig", newline="") as stream:
            index_rows = list(csv.DictReader(stream))
        self.assertEqual(len(index_rows), 6)
        self.assertEqual(len(list(batch.directory.rglob("*.wav"))), 6)
        for article_asset, row in zip(articles["condition2"], store.rows["condition2"]):
            sentence_rows = [r for r in index_rows if r["article_id"] == article_asset.article_id]
            self.assertEqual([r["text"] for r in sentence_rows], list(article_asset.pages))
            self.assertEqual([r["source_row"] for r in sentence_rows], ["2", "4", "5"])
            for index, sentence_row in enumerate(sentence_rows, 1):
                wav = batch.directory / article_asset.article_id / f"sentence_{index:04d}.wav"
                metadata = json.loads(wav.with_suffix(".json").read_text())
                self.assertTrue(wav.is_file())
                self.assertEqual(metadata["sentence_index"], index)
                self.assertEqual(metadata["target_wpm"], 120)
                self.assertEqual(metadata["participant_id"], "S001")
                self.assertEqual(metadata["session_id"], store.session_id)
                self.assertEqual(sha256_file(wav), metadata["audio_sha256"])
                self.assertEqual(sentence_row["audio_path"], str(wav))
                self.assertEqual(sentence_row["planned_audio_path"], str(wav))
                self.assertEqual(sentence_row["audio_status"], "cached")
                self.assertEqual(sentence_row["participant_id"], "S001")
                self.assertEqual(float(sentence_row["target_duration_s"]), len(sentence_row["text"].split()) / 2)
                self.assertEqual(float(sentence_row["duration_s"]), float(sentence_row["target_duration_s"]))
            self.assertEqual((row["status"], row["audio_status"]), ("not_presented", "cached"))
            self.assertEqual(row["audio_path"], str(batch.directory / article_asset.article_id))
            self.assertEqual(row["audio_index_path"], str(batch.index_path))
            self.assertEqual(row["audio_job_id"], "")
        self.assertEqual(list(batch.directory.glob("*.partial")), [])
        with self.assertRaisesRegex(RuntimeError, "exactly once"):
            batch.start()

    def test_generation_failure_is_saved_without_removing_reading_speed(self):
        class Broken(DemoGenerator):
            def generate(self, request, output_path):
                raise RuntimeError("model unavailable")

        _, server, _ = self.serve(Broken())
        config, store, articles, summary = self.session_batch(server)
        batch = SessionAudio(config, store, articles["condition2"], summary)
        self.addCleanup(batch.stop)
        with patch("gpu_service.job_queue.logging.exception"):
            batch.start()
            deadline = time.monotonic() + 2.0
            while not batch.done and time.monotonic() < deadline:
                batch.poll()
                time.sleep(0.005)
        self.assertTrue(batch.failed)
        self.assertTrue(all(r["audio_status"] == "failed" and "model unavailable" in r["audio_error"]
                            for r in store.rows["condition2"]))
        self.assertEqual(store.metadata["reading_speed"]["speed_per_minute"], 120)
        self.assertEqual(list(batch.directory.rglob("*.wav")), [])

    def test_first_article_is_released_while_later_article_is_still_generating(self):
        class LaterArticle(DemoGenerator):
            blocked_article = None

            def __init__(self):
                self.entered, self.release = threading.Event(), threading.Event()

            def generate(self, request, output_path):
                if request.article_id == self.blocked_article:
                    self.entered.set()
                    if not self.release.wait(3.0):
                        raise RuntimeError("Later article timed out")
                return super().generate(request, output_path)

        generator = LaterArticle()
        _, server, _ = self.serve(generator)
        self.addCleanup(generator.release.set)
        config, store, articles, summary = self.session_batch(server)
        first, second = articles["condition2"]
        generator.blocked_article = second.article_id
        batch = SessionAudio(config, store, articles["condition2"], summary)
        self.addCleanup(batch.stop)
        batch.start()
        self.assertTrue(generator.entered.wait(1.0))
        deadline = time.monotonic() + 2.0
        while not batch.article_ready(first.article_id) and time.monotonic() < deadline:
            batch.poll()
            time.sleep(0.005)
        self.assertTrue(batch.article_ready(first.article_id))
        self.assertFalse(batch.done)
        self.assertFalse(batch.article_ready(second.article_id))
        cached = batch.cached_article(first.article_id)
        self.assertEqual([c.request.text for c in cached], list(first.pages))
        self.assertEqual([c.request.sentence_index for c in cached], [1, 2, 3])
        self.assertTrue(all(c.path.is_file() for c in cached))
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            batch.cached_article(second.article_id)
        generator.release.set()

    def test_tts_requires_completed_condition1_and_keeps_participants_separate(self):
        _, server, _ = self.serve()
        config, store, articles, summary = self.session_batch(server)
        other = SessionStore(config, "S002", articles)
        with self.assertRaisesRegex(RuntimeError, "Complete Condition 1"):
            SessionAudio(config, other, articles["condition2"], summary)
        self.assertFalse((config.assets_dir / "TTS").exists())
        other.rows["condition1"][0].update(store.rows["condition1"][0])
        other.rows["condition1"][0].update(participant_id="S002", session_id=other.session_id)
        other.save_speed(summary)
        first = SessionAudio(config, store, articles["condition2"], summary)
        second = SessionAudio(config, other, articles["condition2"], summary)
        self.assertNotEqual(first.directory, second.directory)
        self.assertEqual(second.directory.parent.name, "S002")

    def test_failed_sentence_keeps_other_sentences_and_marks_article_failed(self):
        class BrokenSentence(DemoGenerator):
            def generate(self, request, output_path):
                if request.sentence_index == 2:
                    raise RuntimeError("sentence unavailable")
                return super().generate(request, output_path)

        _, server, _ = self.serve(BrokenSentence())
        config, store, articles, summary = self.session_batch(server)
        batch = SessionAudio(config, store, articles["condition2"], summary)
        self.addCleanup(batch.stop)
        log = MagicMock()
        with patch("gpu_service.job_queue.logging.exception"):
            batch.start()
            deadline = time.monotonic() + 3.0
            while not batch.done and time.monotonic() < deadline:
                batch.poll(log)
                time.sleep(0.005)
        self.assertTrue(batch.failed)
        self.assertEqual(len(list(batch.directory.rglob("*.wav"))), 4)
        with batch.index_path.open(encoding="utf-8-sig", newline="") as stream:
            index_rows = list(csv.DictReader(stream))
        for row in index_rows:
            if row["sentence_index"] == "2":
                self.assertEqual(row["audio_status"], "failed")
                self.assertEqual(row["audio_path"], "")
                self.assertIn("sentence unavailable", row["error"])
            else:
                self.assertEqual(row["audio_status"], "cached")
                self.assertTrue(Path(row["audio_path"]).is_file())
        self.assertTrue(all(r["audio_status"] == "failed" and "sentence 2" in r["audio_error"]
                            and not r["audio_path"] for r in store.rows["condition2"]))
        self.assertEqual([call.kwargs["page"] for call in log.emit.call_args_list], [1, 2, 3, 1, 2, 3])

    def test_wrong_sentence_identity_and_duplicate_sentence_are_rejected(self):
        jobs, _, client = self.serve()
        request = GenerationRequest("session", "participant", "A", "Same text.", 120, 2, sentence_index=1)
        with self.assertRaises(HTTPError) as caught:
            client.submit_articles([request, request])
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(list(jobs.output_dir.iterdir()), [])
        job_id = client.submit_articles([request])[0]["job_id"]
        metadata = self.wait_terminal(client, job_id)
        metadata["sentence_index"] = 2
        with self.assertRaisesRegex(ValueError, "does not match"):
            client.download_audio(request, job_id, metadata)

    def test_background_batches_more_than_100_sentences(self):
        _, _, client = self.serve()
        worker = BackgroundAudioClient(client, poll_interval_s=0.005)
        self.addCleanup(lambda: worker.stop(timeout=1.0))
        requests = [GenerationRequest("session", "participant", "A", "Word.", 600, 1, sentence_index=i)
                    for i in range(1, 102)]
        def check_all_submitted(job_id):
            self.assertEqual(submit.call_count, 2)
            return original_status(job_id)

        original_status = client.get_status
        with patch.object(client, "submit_articles", wraps=client.submit_articles) as submit, \
                patch.object(client, "get_status", side_effect=check_all_submitted):
            worker.start(requests)
            results = [worker.events.get(timeout=3.0) for _ in requests]
        self.assertEqual([len(call.args[0]) for call in submit.call_args_list], [100, 1])
        self.assertTrue(all(isinstance(result, CachedAudio) for result in results))
        self.assertEqual([result.request.sentence_index for result in results], list(range(1, 102)))
        self.assertEqual(len({result.path for result in results}), 101)

    def test_sentence_index_must_be_a_positive_integer(self):
        for index in (0, -1, True, 1.5, "1"):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "sentence_index"):
                GenerationRequest("s", "u", "a", "Text.", 120, 1, sentence_index=index)

    def test_cancelled_download_does_not_publish_an_audio_file(self):
        _, _, client = self.serve()
        job_id = client.submit_articles([article()])[0]["job_id"]
        metadata = self.wait_terminal(client, job_id)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            client.download_audio(article(), job_id, metadata, cancellation_event=cancel)
        self.assertEqual(list(client.cache_dir.iterdir()), [])

    def test_article_file_and_chunking_preserve_complete_text(self):
        request_file = self.root / "requests.json"
        request_file.write_text(json.dumps({"articles": [article("A").to_dict(), article("B").to_dict()]}),
                                encoding="utf-8")
        requests = load_articles(request_file)
        for request in requests:
            self.assertEqual(request.word_count, len(request.text.split()))
            chunks = split_article(request.text, request.target_wpm, max_bytes=12)
            self.assertEqual("".join(chunks), request.text)
            self.assertEqual(sum(len(chunk.split()) for chunk in chunks), request.word_count)

    def test_f5_adapter_accounts_for_reference_duration_and_writes_pcm(self):
        reference = self.root / "reference.wav"
        reference.write_bytes(b"mock-reference")
        generator = F5Generator(reference, "Reference transcript")
        generator._model = types.SimpleNamespace(
            ema_model=object(), vocoder=object(), mel_spec_type="vocos", device="cuda"
        )
        generator._reference = (object(), 24000)
        generator._ref_text = "Reference transcript"
        generator._ref_duration = 5.0
        infer = MagicMock(side_effect=lambda **kwargs: iter([([1, 2], 24000, None)]))
        sf = types.SimpleNamespace(write=MagicMock())
        modules = {
            "numpy": types.SimpleNamespace(concatenate=lambda chunks: [x for chunk in chunks for x in chunk]),
            "soundfile": sf,
            "f5_tts": types.ModuleType("f5_tts"),
            "f5_tts.infer": types.ModuleType("f5_tts.infer"),
            "f5_tts.infer.utils_infer": types.SimpleNamespace(infer_batch_process=infer),
            "f5_tts.model": types.ModuleType("f5_tts.model"),
            "f5_tts.model.utils": types.SimpleNamespace(seed_everything=MagicMock()),
        }
        with patch.dict("sys.modules", modules):
            generator.generate(article(), self.root / "result.wav")
        self.assertEqual(infer.call_args.kwargs["fix_duration"], 7.0)
        self.assertEqual(infer.call_args.kwargs["gen_text_batches"], [article().text])
        self.assertEqual(sf.write.call_args.kwargs["subtype"], "PCM_16")


if __name__ == "__main__":
    unittest.main()
