"""Prepare one Condition 2 WAV per CSV sentence after measuring reading speed."""

import json
from pathlib import Path

from shared.contracts import GenerationRequest
from .audio_client import AudioClient, AudioFailure, BackgroundAudioClient, CachedAudio
from .event_log import write_csv

INDEX_FIELDS = ["participant_id", "session_id", "article_id", "sentence_index", "source_row",
                "text", "word_count", "target_wpm", "target_duration_s", "audio_status",
                "audio_path", "planned_audio_path", "job_id", "duration_s", "actual_wpm",
                "audio_sha256", "error"]


class SessionAudio:
    def __init__(self, config, store, articles, summary):
        self.config, self.store = config, store
        if "reading_speed" not in store.metadata or any(row["status"] != "completed" for row in store.rows["condition1"]):
            raise RuntimeError("Complete Condition 1 and save reading speed before preparing TTS")
        root = Path(config.assets_dir).resolve()
        tts_root = (root / config.tts_folder).resolve()
        if not tts_root.is_relative_to(root):
            raise ValueError("TTS folder must be inside assets_dir")
        self.directory = (tts_root / store.participant_id / store.session_id).resolve()
        if not self.directory.is_relative_to(root):
            raise ValueError("User TTS directory must stay inside assets_dir")
        if articles and summary["speed_unit"] != "words/min":
            raise ValueError("The current TTS interface requires English words/min")
        self.directory.mkdir(parents=True, exist_ok=False)
        self.index_path = self.directory / "tts_index.csv"
        self.worker = None
        self.cached = {}
        self.rows = {row["article_id"]: row for row in store.rows["condition2"]}
        self.requests, sentences = [], []
        for article in articles:
            for index, (text, source_row) in enumerate(zip(article.pages, article.source_rows), 1):
                request = GenerationRequest(
                    session_id=store.session_id, participant_id=store.participant_id,
                    article_id=article.article_id, sentence_index=index, text=text,
                    word_count=len(text.split()), target_wpm=summary["speed_per_minute"],
                )
                self.requests.append(request)
                planned_path = self.directory / article.article_id / f"sentence_{index:04d}.wav"
                sentences.append(dict(request.identity(), source_row=source_row, text=text,
                                      audio_status="pending", job_id="", path="",
                                      planned_audio_path=str(planned_path), error=""))
            self.rows[article.article_id]["audio_index_path"] = str(self.index_path)
        self.manifest = dict(participant_id=store.participant_id, session_id=store.session_id,
                             dummy_mode=config.dummy_mode,
                             server=config.tts_server_url, target_wpm=summary["speed_per_minute"],
                             granularity="sentence", status="prepared", sentences=sentences)
        self.entries = {(entry["article_id"], entry["sentence_index"]): entry for entry in sentences}
        self._write_json(self.directory / "requests.json", {"articles": [r.to_dict() for r in self.requests]})
        store.metadata.update(tts_directory=str(self.directory), tts_index_path=str(self.index_path))
        self._save()

    @staticmethod
    def _write_json(path, data):
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _save(self):
        self._write_json(self.directory / "manifest.json", self.manifest)
        index_rows = []
        for entry in self.entries.values():
            row = {key: entry.get(key, "") for key in INDEX_FIELDS}
            row["audio_path"] = entry["path"]
            for key in ("duration_s", "actual_wpm", "audio_sha256"):
                row[key] = entry.get("metadata", {}).get(key, "")
            index_rows.append(row)
        write_csv(self.index_path, INDEX_FIELDS, index_rows)
        self.store.metadata["tts_status"] = self.manifest["status"]
        self.store.save()

    def _update_article(self, article_id):
        entries = [entry for entry in self.entries.values() if entry["article_id"] == article_id]
        states = {entry["audio_status"] for entry in entries}
        row = self.rows[article_id]
        if states == {"cached"}:
            row.update(audio_status="cached", audio_path=str(self.directory / article_id))
        elif "failed" in states:
            row["audio_status"] = "failed"
        elif "pending" in states:
            row["audio_status"] = "pending"
        elif "stopped" in states:
            row["audio_status"] = "stopped"
        else:
            row["audio_status"] = next(iter(states))
        # Job IDs and WAV paths belong to sentence rows in tts_index.csv.
        row["audio_error"] = "; ".join(
            f"sentence {entry['sentence_index']}: {entry['error']}"
            for entry in entries if entry["error"])

    def start(self):
        if self.manifest["status"] != "prepared":
            raise RuntimeError("Start this session's TTS exactly once")
        if not self.requests:
            self.manifest["status"] = "not_required"
        elif not self.config.tts_server_url:
            self.manifest["status"] = "not_configured"
            for entry in self.entries.values():
                entry["audio_status"] = "not_configured"
        else:
            self.worker = BackgroundAudioClient(AudioClient(
                self.config.tts_server_url, self.directory, use_article_filenames=True))
            self.manifest["status"] = "running"
        for article_id in self.rows:
            if any(key[0] == article_id for key in self.entries):
                self._update_article(article_id)
        self._save()
        if self.worker is not None:
            self.worker.start(self.requests)

    @property
    def done(self):
        return self.manifest["status"] != "running"

    @property
    def failed(self):
        return self.manifest["status"] == "failed"

    def article_ready(self, article_id):
        entries = [entry for key, entry in self.entries.items() if key[0] == article_id]
        return bool(entries) and all(entry["audio_status"] == "cached" for entry in entries)

    def article_error(self, article_id):
        return self.rows[article_id]["audio_error"]

    def cached_article(self, article_id):
        """Return verified sentence audio in CSV order, never a partial article."""
        if not self.article_ready(article_id):
            raise RuntimeError(f"Audio for article {article_id} is not ready")
        return [self.cached[(request.article_id, request.sentence_index)]
                for request in self.requests if request.article_id == article_id]

    def poll(self, log=None):
        if self.worker is None:
            return []
        events = self.worker.poll_events()
        for event in events:
            article_id, index = event.request.article_id, event.request.sentence_index
            entry = self.entries[(article_id, index)]
            entry["job_id"] = event.job_id
            if isinstance(event, CachedAudio):
                self.cached[(article_id, index)] = event
                entry.update(audio_status="cached", path=str(event.path), metadata=event.metadata)
                self._write_json(event.path.with_suffix(".json"), event.metadata)
                event_name, detail = "AUDIO_CACHED", str(event.path)
            elif isinstance(event, AudioFailure):
                entry.update(audio_status="failed", error=event.error)
                event_name, detail = "AUDIO_FAILED", event.error
            else:
                raise TypeError("Unexpected audio event")
            self._update_article(article_id)
            if all(e["audio_status"] in ("cached", "failed") for e in self.entries.values()):
                self.manifest["status"] = "failed" if any(e["audio_status"] == "failed" for e in self.entries.values()) else "cached"
            self._save()
            if log is not None:
                log.emit(event_name, "condition2", article_id, page=index, detail=detail)
                log.flush()
        return events

    def stop(self):
        if self.worker is not None:
            self.worker.stop()
        if self.manifest["status"] == "running":
            self.manifest["status"] = "stopped"
            for entry in self.entries.values():
                if entry["audio_status"] == "pending":
                    entry["audio_status"] = "stopped"
            for article_id in self.rows:
                if any(key[0] == article_id for key in self.entries):
                    self._update_article(article_id)
            self._save()
