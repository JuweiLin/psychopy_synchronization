"""Startup inference, readiness HTTP checks and GPU launch configuration."""

from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gpu_service.f5_generator import DemoGenerator
from gpu_service.job_queue import JobQueue
from gpu_service.launcher import server_arguments
from gpu_service.tts_server import AudioHandler, AudioServer
from psychopy_sync.server_check import check_gpu_server
from shared.contracts import GenerationRequest, TTS_PROTOCOL_VERSION, TTS_SERVICE


class StartupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        log_patch = patch.object(AudioHandler, "log_message")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def serve(self, generator, verify_startup=True):
        jobs = JobQueue(self.root / "generated", generator, verify_startup=verify_startup)
        server = AudioServer(("127.0.0.1", 0), jobs)
        worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        worker.start()

        def cleanup():
            if hasattr(generator, "release"):
                generator.release.set()
            server.shutdown()
            server.server_close()
            worker.join(timeout=1)
            jobs.close()

        self.addCleanup(cleanup)
        return jobs, f"http://127.0.0.1:{server.server_port}"

    def wait_initialized(self, jobs):
        deadline = time.monotonic() + 2
        while jobs.readiness()["status"] == "starting" and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertNotEqual(jobs.readiness()["status"], "starting")

    def assert_jobs_rejected(self, url):
        request = GenerationRequest("s", "u", "a", "Test sentence.", 120, 2)
        data = json.dumps({"articles": [request.to_dict()]}).encode()
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(url + "/jobs/batch", data=data), timeout=1)
        self.assertEqual(caught.exception.code, 503)
        caught.exception.close()

    def test_loading_blocks_jobs_then_demo_ready_is_allowed_only_for_dummy(self):
        class Controlled(DemoGenerator):
            def __init__(self):
                self.entered, self.release = threading.Event(), threading.Event()

            def generate(self, request, path):
                self.entered.set()
                if not self.release.wait(2):
                    raise RuntimeError("Startup test timed out")
                return super().generate(request, path)

        generator = Controlled()
        jobs, url = self.serve(generator)
        self.assertTrue(generator.entered.wait(1))
        with urlopen(url + "/health", timeout=1) as response:
            health = json.load(response)
        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["readiness"]["ready"])
        result = check_gpu_server(url)
        self.assertEqual(result.status, "starting")
        self.assertFalse(result.can_start)
        self.assert_jobs_rejected(url)
        self.assertEqual(list(jobs.output_dir.iterdir()), [])
        generator.release.set()
        self.wait_initialized(jobs)
        self.assertTrue(check_gpu_server(url, allow_demo=True).can_start)
        self.assertFalse(check_gpu_server(url, allow_demo=False).can_start)
        self.assertEqual(list(jobs.output_dir.iterdir()), [])

    def test_inference_failure_is_reported_even_though_http_service_is_alive(self):
        class Broken(DemoGenerator):
            def generate(self, request, path):
                raise RuntimeError("CUDA initialization failed")

        with patch("gpu_service.job_queue.logging.exception"):
            jobs, url = self.serve(Broken())
            self.wait_initialized(jobs)
        result = check_gpu_server(url, allow_demo=True)
        self.assertEqual(result.status, "failed")
        self.assertIn("CUDA initialization failed", result.message)
        self.assertFalse(result.can_start)
        self.assert_jobs_rejected(url)

    def test_unreadable_wav_or_wrong_duration_never_reports_ready(self):
        class InvalidWav(DemoGenerator):
            def generate(self, request, path):
                path.write_bytes(b"invalid WAV")
                return {"demo_only": True}

        class WrongDuration(DemoGenerator):
            def generate(self, request, path):
                return super().generate(replace(request, target_wpm=request.target_wpm / 2), path)

        for generator in (InvalidWav(), WrongDuration()):
            with self.subTest(generator=type(generator).__name__), patch("gpu_service.job_queue.logging.exception"):
                jobs, url = self.serve(generator)
                self.wait_initialized(jobs)
                self.assertEqual(check_gpu_server(url, allow_demo=True).status, "failed")

    def test_verified_non_demo_generator_reports_ready_for_real_experiment(self):
        class TestSpeechGenerator:
            # Only a fixture: no real GPU/model is exercised in this check.
            def generate(self, request, path):
                DemoGenerator().generate(request, path)
                return {"generator": "test-fixture"}

        jobs, url = self.serve(TestSpeechGenerator())
        self.wait_initialized(jobs)
        result = check_gpu_server(url)
        self.assertEqual(result.status, "ready")
        self.assertTrue(result.can_start)

    def test_service_without_startup_test_is_not_treated_as_ready(self):
        _, url = self.serve(DemoGenerator(), verify_startup=False)
        self.assertFalse(check_gpu_server(url, allow_demo=True).can_start)

    def test_absent_url_keeps_reading_only_flow_and_never_requests_network(self):
        with patch("psychopy_sync.server_check.urlopen") as open_url:
            self.assertTrue(check_gpu_server(None).can_start)
            self.assertEqual(check_gpu_server("").status, "not_configured")
        open_url.assert_not_called()

    def test_unreachable_and_timeout_prevent_start_with_bounded_request(self):
        for error in (URLError("Connection refused"), TimeoutError("Timed out")):
            with self.subTest(error=error), patch("psychopy_sync.server_check.urlopen", side_effect=error) as open_url:
                result = check_gpu_server("http://192.168.1.20:8765")
                self.assertEqual(result.status, "unavailable")
                self.assertFalse(result.can_start)
                self.assertEqual(open_url.call_args.kwargs["timeout"], 3.0)

    def test_unrelated_malformed_and_unverified_http_responses_cannot_pass(self):
        good = dict(service=TTS_SERVICE, protocol_version=TTS_PROTOCOL_VERSION, status="ready",
                    ready=True, warmup_verified=True, mode="f5-tts")
        bodies = [b"not JSON", json.dumps({"status": "ok"}).encode(),
                  json.dumps(dict(good, warmup_verified=False)).encode(),
                  json.dumps(dict(good, mode="unknown")).encode(),
                  json.dumps(dict(good, ready="true")).encode()]
        for body in bodies:
            with self.subTest(body=body):
                response = io.BytesIO(body)
                response.code = 200
                with patch("psychopy_sync.server_check.urlopen", return_value=response):
                    self.assertFalse(check_gpu_server("http://localhost:8765").can_start)

    def test_missing_ready_endpoint_requires_server_update(self):
        error = HTTPError("http://localhost:8765/ready", 404, "Not Found", {}, io.BytesIO())
        with patch("psychopy_sync.server_check.urlopen", side_effect=error):
            self.assertEqual(check_gpu_server("http://localhost:8765").status, "incompatible")

    def test_invalid_server_origin_is_rejected_without_network_access(self):
        for url in ("localhost:8765", "file:///tmp/server", "http://localhost:bad", "http://localhost?x=1"):
            with self.subTest(url=url), patch("psychopy_sync.server_check.urlopen") as open_url:
                self.assertFalse(check_gpu_server(url).can_start)
                open_url.assert_not_called()

    def test_gpu_config_resolves_reference_paths_with_spaces(self):
        (self.root / "voice sample.wav").write_bytes(b"fixture")
        (self.root / "voice sample.txt").write_text("Reference text.")
        config = self.root / "gpu_config.py"
        config.write_text('ref_audio = "voice sample.wav"\nref_text_file = "voice sample.txt"\n'
                          'host = "0.0.0.0"\nport = 8765\ndevice = "cuda"\ndemo_mode = False\n')
        arguments = server_arguments(config)
        self.assertEqual(arguments[arguments.index("--ref-audio") + 1], str(self.root / "voice sample.wav"))
        self.assertEqual(arguments[arguments.index("--ref-text-file") + 1], str(self.root / "voice sample.txt"))
        (self.root / "voice sample.wav").unlink()
        with self.assertRaisesRegex(ValueError, "Missing ref_audio"):
            server_arguments(config)
        self.assertIn("--demo", server_arguments(config, demo_override=True))


if __name__ == "__main__":
    unittest.main()
