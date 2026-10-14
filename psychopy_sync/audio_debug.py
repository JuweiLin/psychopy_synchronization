"""Dummy-only WPM sweep using the experiment's TTS transport and PTB playback."""

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import re
import threading
from types import SimpleNamespace
import uuid

from shared.contracts import GenerationRequest
from .audio_client import AudioClient, AudioFailure, BackgroundAudioClient
from .condition1 import ExperimentAborted
from .config import DisplayConfig, ExperimentConfig
from .display import create_window, preload_article_audio
from .event_log import EventLog, utc_now, write_csv
from .eyelink import DummyEyeLinkController
from .reading_display import ReadingDisplay
from .server_check import check_gpu_server


@dataclass(frozen=True)
class DebugOptions:
    text: str
    wpms: tuple
    repeats: int = 2
    source_article_id: str = ""
    source_page: int = 0

    def __post_init__(self):
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Enter text to synthesize.")
        if not 1 <= len(self.wpms) <= 20:
            raise ValueError("Enter between 1 and 20 WPM values.")
        if any(isinstance(wpm, bool) or not isinstance(wpm, (int, float))
               or not math.isfinite(wpm) or wpm <= 0 for wpm in self.wpms):
            raise ValueError("WPM values must be finite positive numbers.")
        if len(set(self.wpms)) != len(self.wpms):
            raise ValueError("Enter each WPM once; use repetitions to replay the same WAV.")
        if type(self.repeats) is not int or not 1 <= self.repeats <= 10:
            raise ValueError("Repetitions must be a whole number from 1 to 10.")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Invalid audio debug options.")
        speeds = data.get("wpms", ())
        if isinstance(speeds, str):
            try:
                speeds = tuple(float(value) for value in re.split(r"[,\s]+", speeds.strip()) if value)
            except ValueError as exc:
                raise ValueError("Separate WPM numbers with commas or spaces.") from exc
        if not isinstance(speeds, (list, tuple)):
            raise ValueError("Enter a list of WPM values.")
        return cls(text=data.get("text", ""), wpms=tuple(speeds), repeats=data.get("repeats", 2),
                   source_article_id=data.get("source_article_id", ""), source_page=data.get("source_page", 0))


class DebugDisplay(ReadingDisplay):
    def _page_on_flip(self, log, onset, condition, article_id, page_index):
        # Keep play_page unchanged, including its PTB scheduling and EOS loop.
        log.on_flip(self.win, onset, "PAGE_ONSET", condition="audio_debug",
                    article_id=article_id, page=page_index)

    def wait_generation(self, poll, text):
        self.keyboard.clearEvents()
        self.prompt.text = text
        while True:
            if self.keyboard.getKeys(keyList=[self.config.quit_key], waitRelease=False, clear=True):
                raise ExperimentAborted("Escape pressed during audio debug preparation")
            result = poll()
            if result is not None:
                return result
            self.prompt.draw()
            self.win.flip()

    def rate_onset(self, wpm):
        self.prompt.text = (f"{wpm:g} WPM — rate the beginning\n\n"
                            "C: first words complete\nM: beginning missing\nU: unsure\n"
                            "R: replay this same WAV\n\nEscape: stop and save")
        self.keyboard.clearEvents()
        # Reject held rating keys carried over from the preceding response.
        keys_allowed = ["c", "m", "u", "r", self.config.quit_key]
        armed = False
        while True:
            self.prompt.draw()
            self.win.flip()
            keys = self.keyboard.getKeys(keyList=keys_allowed, waitRelease=False, clear=True)
            if any(key.name == self.config.quit_key for key in keys):
                raise ExperimentAborted("Escape pressed during audio debug rating")
            held = [self.keyboard.getState(key) for key in keys_allowed[:-1]]
            if not armed:
                if not any(bool(value[0]) if isinstance(value, (tuple, list)) else bool(value) for value in held):
                    armed = True
                    self.keyboard.clearEvents()
                continue
            for key in keys:
                if key.name in keys_allowed[:-1]:
                    return {"c": "complete", "m": "missing_start", "u": "unsure", "r": "replay_requested"}[key.name]


class DebugEventLog(EventLog):
    def emit(self, event, condition="", *args, **kwargs):
        return super().emit(event, "audio_debug" if condition == "condition2" else condition, *args, **kwargs)


INDEX_FIELDS = ["article_id", "text", "word_count", "target_wpm", "target_duration_s", "status",
                "job_id", "audio_path", "duration_s", "actual_wpm", "sample_rate_hz", "audio_sha256", "error"]
RESULT_FIELDS = ["article_id", "target_wpm", "repetition", "attempt", "rating", "playback_status",
                 "start_event_id", "start_timestamp_s", "end_event_id", "end_timestamp_s",
                 "duration_s", "actual_wpm", "job_id", "audio_path", "audio_sha256", "error"]


def run_debug(options, config=None):
    config = replace(config or ExperimentConfig(), dummy_mode=True)
    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
    directory = config.output_dir / "dummy" / "audio_debug" / session_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = dict(session_id=session_id, participant_id="0", dummy_mode=True, audio_debug=True,
                    created_at_utc=utc_now(), status="preparing", server=config.tts_server_url,
                    options=asdict(options), playback="Condition 2 ReadingDisplay.play_page; PTB, no added padding",
                    ratings="Manual listening judgments; no automatic word-loss detection")
    requests = [GenerationRequest(session_id, "0", f"speed_{index:03d}", options.text, speed,
                                  len(options.text.split()), sentence_index=1)
                for index, speed in enumerate(options.wpms, 1)]
    entries = {request.article_id: dict(request.identity(), text=request.text, status="pending", job_id="",
                                        audio_path="", error="") for request in requests}
    results, cached = [], {}
    win = log = worker = speaker = playback = None
    code = 0

    def save():
        write_csv(directory / "audio_index.csv", INDEX_FIELDS,
                  [{name: entry.get(name, "") for name in INDEX_FIELDS} for entry in entries.values()])
        write_csv(directory / "onset_results.csv", RESULT_FIELDS, results)
        temporary = directory / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(directory / "manifest.json")

    save()
    try:
        if not config.tts_server_url:
            raise ValueError("Set tts_server_url in config.py before using audio debug.")
        from psychopy import logging

        win = create_window(DisplayConfig(assumed_refresh_rate_hz=None))
        view = DebugDisplay(win, config, DummyEyeLinkController())
        store = SimpleNamespace(directory=directory, participant_id="0", session_id=session_id, metadata=manifest)
        log = DebugEventLog(store, view.controller, logging.defaultClock.getTime)
        log.emit("AUDIO_DEBUG_START")
        page = view.prepare([SimpleNamespace(article_id="debug", title="Audio debug", pages=(options.text,))])["debug"][0]
        readiness = queue.Queue()
        threading.Thread(target=lambda: readiness.put(check_gpu_server(config.tts_server_url, allow_demo=False)),
                         name="audio-debug-readiness", daemon=True).start()

        def poll_readiness():
            try:
                return readiness.get_nowait()
            except queue.Empty:
                return None

        ready = view.wait_generation(poll_readiness, "Audio debug\n\nChecking the F5-TTS server...\n\nEscape: stop")
        if not ready.can_start or ready.status != "ready":
            raise RuntimeError(ready.message + " Audio debug requires real speech, not demo silence.")
        worker = BackgroundAudioClient(AudioClient(config.tts_server_url, directory / "wavs", use_article_filenames=True))
        worker.start(requests)
        manifest["status"] = "running"
        save()

        def poll_audio(identifier):
            for event in worker.poll_events():
                entry = entries[event.request.article_id]
                entry["job_id"] = event.job_id
                if isinstance(event, AudioFailure):
                    entry.update(status="failed", error=event.error)
                else:
                    cached[event.request.article_id] = event
                    entry.update(status="cached", audio_path=str(event.path))
                    entry.update({name: event.metadata.get(name, "") for name in
                                  ("duration_s", "actual_wpm", "sample_rate_hz", "audio_sha256")})
                    event.path.with_suffix(".json").write_text(json.dumps(event.metadata, indent=2), encoding="utf-8")
                log.emit("AUDIO_DEBUG_CACHED" if entry["status"] == "cached" else "AUDIO_DEBUG_FAILED",
                         "audio_debug", event.request.article_id, detail=entry["audio_path"] or entry["error"])
                log.flush()
                save()
            return entries[identifier] if entries[identifier]["status"] != "pending" else None

        for request in requests:
            entry = view.wait_generation(lambda: poll_audio(request.article_id),
                f"Audio debug\n\nGenerating {request.target_wpm:g} WPM...\n\nEscape: stop")
            if entry["status"] == "failed":
                # Keep testing later speeds if this particular generation fails.
                continue
            audio = cached[request.article_id]
            playback = preload_article_audio(audio, allow_demo=False, speaker=speaker)
            speaker = getattr(playback, "speaker", None)
            for repetition in range(1, options.repeats + 1):
                attempt = 0
                while True:
                    attempt += 1
                    view.wait_screen(f"Audio debug\n\n{request.target_wpm:g} WPM\n"
                        f"Repetition {repetition} / {options.repeats}\n\nSPACE: play\nEscape: stop",
                        log, "DEBUG_PLAY_WAIT", request.article_id, condition="audio_debug")
                    onset = {}
                    row = dict(article_id=request.article_id, target_wpm=request.target_wpm,
                               repetition=repetition, attempt=attempt, rating="not_rated", playback_status="playing",
                               start_event_id="", start_timestamp_s="", end_event_id="", end_timestamp_s="",
                               error="", **{name: entry[name] for name in
                                   ("duration_s", "actual_wpm", "job_id", "audio_path", "audio_sha256")})
                    results.append(row)
                    try:
                        view.play_page(page, playback, audio, log, onset, request.article_id, 1)
                        row["playback_status"] = "completed"
                        row["rating"] = view.rate_onset(request.target_wpm)
                    except BaseException as exc:
                        if row["playback_status"] != "completed":
                            row["playback_status"] = "aborted" if isinstance(exc, (ExperimentAborted, KeyboardInterrupt)) else "failed"
                        row["error"] = str(exc)
                        raise
                    finally:
                        row.update(start_event_id=onset.get("event_id", ""), start_timestamp_s=onset.get("timestamp_s", ""))
                        end = next((event for event in reversed(log.pending) if event["event"] in ("AUDIO_END", "AUDIO_ABORT")
                                    and event["article_id"] == request.article_id), None)
                        if end:
                            row.update(end_event_id=end["event_id"], end_timestamp_s=end["timestamp_s"])
                        log.flush()
                        save()
                    if row["rating"] != "replay_requested":
                        break
            playback.stop()
            playback = None
        failures = sum(entry["status"] == "failed" for entry in entries.values())
        manifest.update(status="failed" if failures == len(entries) else "completed", generation_failures=failures)
        if failures == len(entries):
            manifest["error"] = "Audio generation failed at every requested speed. See audio_index.csv."
            code = 1
    except (ExperimentAborted, KeyboardInterrupt) as exc:
        manifest.update(status="aborted", error=str(exc))
        code = 130
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        code = 1
    finally:
        cleanup_errors = []
        for action in (lambda: worker.stop() if worker is not None else None,
                       lambda: playback.stop() if playback is not None else None,
                       lambda: speaker.close() if speaker is not None else None,
                       lambda: log.flush() if log is not None else None,
                       lambda: win.close() if win is not None else None):
            try:
                action()
            except Exception as exc:
                cleanup_errors.append(str(exc))
        if cleanup_errors:
            manifest.update(cleanup_errors=cleanup_errors, status="failed", error="; ".join(cleanup_errors))
            code = 1
        for entry in entries.values():
            if entry["status"] == "pending":
                entry["status"] = "stopped"
        save()
    return code, dict(audio_debug=True, status=manifest["status"], directory=str(directory),
                      error=manifest.get("error", ""), generation_failures=manifest.get("generation_failures", 0),
                      generated=sum(entry["status"] == "cached" for entry in entries.values()),
                      rated=sum(row["rating"] in ("complete", "missing_start", "unsure") for row in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-id", choices=["0"], required=True)
    parser.add_argument("--options-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        options = DebugOptions.from_dict(json.loads(args.options_file.read_text(encoding="utf-8")))
        code, result = run_debug(options)
    except Exception as exc:
        code, result = 1, dict(audio_debug=True, status="failed", error=str(exc))
    temporary = args.result_file.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
    temporary.replace(args.result_file)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
