"""One generation worker, atomic WAV publication, persistent job metadata."""

import json
import logging
import math
from pathlib import Path
import queue
import re
import threading
import uuid

from shared.contracts import inspect_wav, sha256_file
from .startup_check import verify_generator


class AudioNotAvailable(RuntimeError):
    pass


class ServiceNotReady(RuntimeError):
    pass


class JobQueue:
    def __init__(self, output_dir, generator, wpm_tolerance=0.05, verify_startup=False):
        if not math.isfinite(wpm_tolerance) or not 0 <= wpm_tolerance < 1:
            raise ValueError("WPM tolerance must be a fraction in [0, 1)")
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generator = generator
        self.wpm_tolerance = wpm_tolerance
        self._jobs = {}
        self._lock = threading.Lock()
        self._pending = queue.Queue()
        self._stop = threading.Event()
        self._verify_startup = verify_startup
        self._startup_status = "starting" if verify_startup else "unchecked"
        self._startup_error = None
        self._worker = threading.Thread(target=self._run, name="tts-worker", daemon=True)
        self._worker.start()

    def _directory(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise KeyError(job_id)
        return self.output_dir / job_id

    def _persist(self, job):
        directory = self._directory(job["job_id"])
        temporary = directory / "metadata.json.tmp"
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / "metadata.json")

    def submit_batch(self, requests):
        snapshots = []
        with self._lock:
            if self._stop.is_set():
                raise ServiceNotReady("Generation service is stopping")
            if self._verify_startup and self._startup_status != "ready":
                raise ServiceNotReady(self._startup_error or "Model loading and startup audio test in progress")
            for request in requests:
                job_id = uuid.uuid4().hex
                self._directory(job_id).mkdir()
                job = dict(request.identity(), job_id=job_id, status="queued", error=None)
                self._persist(job)
                self._jobs[job_id] = job
                snapshots.append(dict(job))
                self._pending.put((job_id, request))
        return snapshots

    def readiness(self):
        with self._lock:
            status = "stopping" if self._stop.is_set() else self._startup_status
            return dict(status=status, ready=status == "ready",
                        warmup_verified=self._startup_status == "ready", error=self._startup_error)

    def snapshot(self, job_id):
        with self._lock:
            if job_id not in self._jobs:
                path = self._directory(job_id) / "metadata.json"
                if not path.is_file():
                    raise KeyError(job_id)
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["status"] not in ("available", "failed"):
                    job.update(status="failed", error="Service restarted before generation finished")
                    self._persist(job)
                self._jobs[job_id] = job
            return dict(self._jobs[job_id])

    def audio_path(self, job_id):
        job = self.snapshot(job_id)
        if job["status"] != "available":
            raise AudioNotAvailable("The complete article audio is not available yet")
        return self._directory(job_id) / "audio.wav"

    def _update(self, job_id, **changes):
        with self._lock:
            job = dict(self._jobs[job_id], **changes)
            self._persist(job)
            self._jobs[job_id] = job

    def _run(self):
        if self._verify_startup:
            try:
                verify_generator(self.generator, self.wpm_tolerance)
            except Exception as exc:
                with self._lock:
                    self._startup_status, self._startup_error = "failed", str(exc)
                logging.exception("TTS startup self-test failed")
                return
            with self._lock:
                self._startup_status = "ready"
            print("TTS startup self-test passed. Service is ready.", flush=True)
        while not self._stop.is_set():
            item = self._pending.get()
            if item is None or self._stop.is_set():
                return
            job_id, request = item
            directory = self._directory(job_id)
            temporary = directory / "audio.partial.wav"
            try:
                self._update(job_id, status="generating")
                generation = self.generator.generate(request, temporary)
                self._update(job_id, status="validating")
                details = inspect_wav(temporary)
                actual_wpm = 60.0 * request.word_count / details["duration_s"]
                if abs(actual_wpm / request.target_wpm - 1) > self.wpm_tolerance:
                    raise ValueError(f"Actual WPM {actual_wpm:.2f} exceeds configured tolerance")
                checksum = sha256_file(temporary)
                temporary.replace(directory / "audio.wav")
                self._update(
                    job_id, status="available", **details,
                    actual_wpm=actual_wpm, audio_sha256=checksum,
                    audio_size_bytes=(directory / "audio.wav").stat().st_size,
                    download_path=f"/jobs/{job_id}/audio",
                    generation=generation,
                )
            except Exception as exc:
                logging.exception("Generation failed for job %s", job_id)
                temporary.unlink(missing_ok=True)
                try:
                    self._update(job_id, status="failed", error=str(exc))
                except Exception:
                    logging.exception("Could not save failure status for job %s", job_id)

    def close(self, timeout=1.0):
        # Inference already running cannot be interrupted by a Python event.
        self._stop.set()
        self._pending.put(None)
        self._worker.join(timeout=timeout)
