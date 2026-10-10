"""Download complete sentence/article WAVs in the background without PsychoPy."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import tempfile
import threading
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from shared.contracts import GenerationRequest, inspect_wav


@dataclass(frozen=True)
class CachedAudio:
    request: GenerationRequest
    job_id: str
    path: Path
    metadata: dict


@dataclass(frozen=True)
class AudioFailure:
    request: GenerationRequest
    job_id: str
    error: str


def load_articles(path):
    """Read the same articles object accepted by POST /jobs/batch."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        raise ValueError("Article file must contain an articles list")
    articles = [GenerationRequest.from_dict(item) for item in data["articles"]]
    if not articles:
        raise ValueError("Article file is empty")
    return articles


class AudioClient:
    """Blocking transport methods: call from a background worker, not a trial loop."""

    def __init__(self, base_url, cache_dir="audio_cache", timeout_s=10.0, use_article_filenames=False):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("Use the GPU server origin, e.g. http://192.168.1.20:8765")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("Network timeout must be finite and positive")
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.use_article_filenames = use_article_filenames

    def _json(self, path, data=None):
        body = None if data is None else json.dumps(data, allow_nan=False).encode("utf-8")
        request = Request(self.base_url + path, data=body)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=self.timeout_s) as response:
            return json.load(response)

    @staticmethod
    def _job_path(job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid job ID")
        return f"/jobs/{job_id}"

    @staticmethod
    def _check_identity(request, metadata):
        if any(metadata.get(key) != value for key, value in request.identity().items()):
            raise ValueError("Audio metadata does not match the requested participant/article/speed")

    def submit_articles(self, articles):
        articles = list(articles)
        response = self._json("/jobs/batch", {"articles": [a.to_dict() for a in articles]})
        jobs = response.get("jobs", [])
        if len(jobs) != len(articles):
            raise ValueError("Server returned an incomplete batch")
        for article, job in zip(articles, jobs):
            self._check_identity(article, job)
            self._job_path(job["job_id"])
        return jobs

    def get_status(self, job_id):
        return self._json(self._job_path(job_id))

    def download_audio(self, request, job_id, metadata, cancellation_event=None):
        self._check_identity(request, metadata)
        if metadata.get("job_id") != job_id or metadata.get("status") != "available":
            raise ValueError("Requested audio job is not available")
        checksum = metadata.get("audio_sha256", "")
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Missing or invalid audio checksum")
        if self.use_article_filenames and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", request.article_id):
            raise ValueError("Unsafe article ID for an audio filename")

        def check_cancelled():
            if cancellation_event is not None and cancellation_event.is_set():
                raise InterruptedError("Audio download cancelled")

        check_cancelled()
        descriptor, name = tempfile.mkstemp(prefix=job_id + "-", suffix=".partial", dir=self.cache_dir)
        temporary = Path(name)
        try:
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "wb") as local:
                # Build the URL from the configured origin and expected job ID,
                # not an arbitrary URL returned in metadata.
                with urlopen(self.base_url + self._job_path(job_id) + "/audio",
                             timeout=self.timeout_s) as response:
                    for block in iter(lambda: response.read(65536), b""):
                        check_cancelled()
                        digest.update(block)
                        local.write(block)
            if digest.hexdigest() != checksum:
                raise ValueError("Downloaded WAV checksum does not match")
            if temporary.stat().st_size != metadata.get("audio_size_bytes"):
                raise ValueError("Downloaded WAV size does not match")
            details = inspect_wav(temporary)
            if details["sample_rate_hz"] != metadata.get("sample_rate_hz"):
                raise ValueError("Downloaded WAV sample rate does not match")
            if abs(details["duration_s"] - metadata.get("duration_s", -1)) > 1e-6:
                raise ValueError("Downloaded WAV duration does not match")
            check_cancelled()
            if self.use_article_filenames and request.sentence_index is not None:
                directory = (self.cache_dir / request.article_id).resolve()
                if not directory.is_relative_to(self.cache_dir):
                    raise ValueError("Audio directory must stay inside the cache")
                directory.mkdir(exist_ok=True)
                destination = directory / f"sentence_{request.sentence_index:04d}.wav"
            else:
                name = request.article_id if self.use_article_filenames else job_id
                destination = self.cache_dir / f"{name}.wav"
            temporary.replace(destination)
            return CachedAudio(request, job_id, destination, dict(metadata))
        finally:
            temporary.unlink(missing_ok=True)


class BackgroundAudioClient:
    """Submit and fetch in request order; deliver cached files through an event queue."""

    def __init__(self, client, poll_interval_s=0.5):
        if not math.isfinite(poll_interval_s) or poll_interval_s <= 0:
            raise ValueError("Polling interval must be finite and positive")
        self.client = client
        self.poll_interval_s = poll_interval_s
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._worker = None

    def start(self, articles):
        if self._worker is not None:
            raise RuntimeError("Create a new background client for each batch")
        articles = list(articles)
        if not articles:
            raise ValueError("No articles to submit")
        self._worker = threading.Thread(
            target=self._run, args=(articles,), name="article-audio-client", daemon=True
        )
        self._worker.start()

    def _run(self, articles):
        # The service accepts at most 100 requests in one HTTP batch. Sentence
        # requests can exceed this even for a small selection of articles.
        for offset in range(0, len(articles), 100):
            if self._stop.is_set():
                return
            self._run_batch(articles[offset:offset + 100])

    def _run_batch(self, articles):
        if self._stop.is_set():
            return
        try:
            jobs = self.client.submit_articles(articles)
        except Exception as exc:
            for request in articles:
                self.events.put(AudioFailure(request, "", str(exc)))
            return
        for request, job in zip(articles, jobs):
            job_id = job["job_id"]
            try:
                while not self._stop.is_set():
                    metadata = self.client.get_status(job_id)
                    self.client._check_identity(request, metadata)
                    status = metadata.get("status")
                    if status == "available":
                        cached = self.client.download_audio(request, job_id, metadata, cancellation_event=self._stop)
                        if not self._stop.is_set():
                            self.events.put(cached)
                        break
                    if status == "failed":
                        raise RuntimeError(metadata.get("error") or "Audio generation failed")
                    if status not in ("queued", "generating", "validating"):
                        raise ValueError(f"Unknown job state: {status}")
                    self._stop.wait(self.poll_interval_s)
                if self._stop.is_set():
                    return
            except Exception as exc:
                if not self._stop.is_set():
                    self.events.put(AudioFailure(request, job_id, str(exc)))

    def poll_events(self):
        """Nonblocking; safe to call from the PsychoPy main loop."""
        results = []
        while True:
            try:
                results.append(self.events.get_nowait())
            except queue.Empty:
                return results

    def stop(self, timeout=0.0):
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description="Read articles, submit them, and download complete WAV files")
    parser.add_argument("--server", required=True)
    parser.add_argument("--articles", required=True)
    parser.add_argument("--cache-dir", default="audio_cache")
    args = parser.parse_args()
    articles = load_articles(args.articles)
    worker = BackgroundAudioClient(AudioClient(args.server, args.cache_dir))
    worker.start(articles)
    failed = False
    try:
        for _ in articles:
            event = worker.events.get()
            if isinstance(event, AudioFailure):
                failed = True
                print(f"FAILED {event.request.article_id}: {event.error}", flush=True)
            else:
                print(f"CACHED {event.request.article_id}: {event.path}", flush=True)
    finally:
        worker.stop(timeout=1.0)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
