"""HTTP API exposing complete generated article audio, never a directory listing."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from shared.contracts import GenerationRequest
from .f5_generator import DemoGenerator, F5Generator
from .job_queue import AudioNotAvailable, JobQueue


class AudioServer(ThreadingHTTPServer):
    def __init__(self, address, jobs):
        self.jobs = jobs
        super().__init__(address, AudioHandler)


class AudioHandler(BaseHTTPRequestHandler):
    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlsplit(self.path).path != "/jobs/batch":
            self._json(404, {"error": "Unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                raise ValueError("Request must contain at most 1 MiB of JSON")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
                raise ValueError("Expected an articles list")
            if not 1 <= len(data["articles"]) <= 100:
                raise ValueError("Submit between 1 and 100 audio requests per batch")
            # Validate the entire batch before any article enters the queue.
            requests = [GenerationRequest.from_dict(item) for item in data["articles"]]
            identities = [(r.session_id, r.participant_id, r.article_id, r.sentence_index) for r in requests]
            if len(identities) != len(set(identities)):
                raise ValueError("Duplicate article/sentence identity in batch")
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(202, {"jobs": self.server.jobs.submit_batch(requests)})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok", "model_loading": "on_first_job"})
            return
        match = re.fullmatch(r"/jobs/([0-9a-f]{32})(/audio)?", path)
        if not match:
            self._json(404, {"error": "Unknown endpoint"})
            return
        job_id, audio = match.groups()
        try:
            if not audio:
                self._json(200, self.server.jobs.snapshot(job_id))
                return
            file_path = self.server.jobs.audio_path(job_id)
            # Open before sending headers so a missing artifact returns an error.
            with file_path.open("rb") as stream:
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.end_headers()
                shutil.copyfileobj(stream, self.wfile)
        except KeyError:
            self._json(404, {"error": "Unknown job"})
        except AudioNotAvailable as exc:
            self._json(409, {"error": str(exc)})
        except FileNotFoundError:
            self._json(404, {"error": "Audio artifact is missing"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output-dir", default="generated_audio")
    parser.add_argument("--demo", action="store_true", help="Generate silence for transport testing")
    parser.add_argument("--ref-audio")
    parser.add_argument("--ref-text-file")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--model", default="F5TTS_v1_Base")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--wpm-tolerance", type=float, default=0.05)
    args = parser.parse_args()
    if args.demo:
        generator = DemoGenerator()
    else:
        if not args.ref_audio or not args.ref_text_file:
            parser.error("F5-TTS requires --ref-audio and --ref-text-file")
        generator = F5Generator(
            args.ref_audio, Path(args.ref_text_file).read_text(encoding="utf-8"),
            device=args.device, model=args.model, seed=args.seed,
        )
    jobs = JobQueue(args.output_dir, generator, args.wpm_tolerance)
    try:
        with AudioServer((args.host, args.port), jobs) as server:
            print(f"Audio service listening on {args.host}:{server.server_port}", flush=True)
            print("Demo silence only" if args.demo else "F5-TTS loads on the first job", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        jobs.close()


if __name__ == "__main__":
    main()
