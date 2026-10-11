"""Participant registry, per-session CSV tables and paired EDF/local event IDs.

Flip callbacks only buffer rows and send markers. Disk writes happen at article
boundaries and during cleanup. One experiment process owns an output directory.
"""

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

ARTICLE_FIELDS = ["participant_id", "session_id", "condition", "order", "article_id", "title", "path",
                  "source_rows", "source_sha256", "text_sha256", "pages_sha256",
                  "count_mode", "unit_count", "status", "page_count",
                  "start_event_id", "end_event_id", "start_timestamp_s", "end_timestamp_s",
                  "reading_duration_s", "elapsed_duration_s", "baseline_duration_s", "timing_source"]
ARTICLE_FIELDS += ["audio_status", "audio_path", "audio_index_path", "audio_job_id", "audio_error"]
ARTICLE_FIELDS += ["baseline_trial_id", "baseline_screenshot_path", "baseline_ias_path", "baseline_status",
                   "baseline_target_s", "baseline_start_event_id", "baseline_end_event_id",
                   "baseline_start_timestamp_s", "baseline_end_timestamp_s"]
LOG_FIELDS = ["participant_id", "session_id", "event_id", "event", "condition", "article_id",
              "page", "timestamp_s", "timestamp_source", "logged_at_utc", "message",
              "marker_status", "detail"]
USER_FIELDS = ["participant_id", "created_at_utc"]
SPEED_FIELDS = ["participant_id", "session_id", "article_count", "total_units", "count_mode",
                "total_reading_s", "speed_per_minute", "speed_unit", "timing_source"]
SENTENCE_FIELDS = ["participant_id", "session_id", "condition", "article_id", "sentence_index",
                   "source_row", "text", "trial_id", "screenshot_path", "screenshot_status",
                   "screenshot_sha256", "width_px", "height_px", "ias_path", "ias_status",
                   "ias_sha256", "aoi_preview_path", "word_count", "status", "start_event_id",
                   "end_event_id", "start_timestamp_s", "end_timestamp_s", "duration_s"]
WORD_AOI_FIELDS = ["participant_id", "session_id", "condition", "article_id", "sentence_index",
                   "trial_id", "screenshot_path", "ias_path", "word_index", "line_index", "word",
                   "ia_label", "char_start", "char_end", "left", "top", "right", "bottom"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_csv(path, fields, rows):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def append_csv(path, fields, row):
    exists = path.exists()
    with path.open("a" if exists else "w", encoding="utf-8" if exists else "utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def validate_participant_id(participant_id):
    if not isinstance(participant_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", participant_id):
        raise ValueError("Use a participant ID of 1–32 ASCII letters/digits/_/-")
    return participant_id


class SessionStore:
    def __init__(self, config, participant_id, articles, session_id=None):
        validate_participant_id(participant_id)
        self.participant_id = participant_id
        self.session_id = session_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.session_id):
            raise ValueError("Invalid session ID")
        self.root = Path(config.output_dir)
        if config.dummy_mode:
            self.root = self.root / "dummy"
        self.root.mkdir(parents=True, exist_ok=True)
        users_path = self.root / "users.csv"
        users, migrate_users = [], False
        if users_path.exists():
            with users_path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not set(USER_FIELDS).issubset(reader.fieldnames or []):
                    raise ValueError("User registry is missing required fields")
                migrate_users = reader.fieldnames != USER_FIELDS
                # Remove legacy name columns while retaining IDs and registration dates.
                users = [{field: row[field] for field in USER_FIELDS} for row in reader]
        self.directory = self.root / participant_id / self.session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        if not any(row["participant_id"] == participant_id for row in users):
            users.append(dict(participant_id=participant_id, created_at_utc=utc_now()))
            migrate_users = True
        if migrate_users:
            write_csv(users_path, USER_FIELDS, users)
        if not (self.root / "reading_speed.csv").exists():
            write_csv(self.root / "reading_speed.csv", SPEED_FIELDS, [])
        self.rows = {}
        for condition, selected in articles.items():
            self.rows[condition] = [dict(
                participant_id=participant_id, session_id=self.session_id, condition=condition, order=index,
                article_id=a.article_id, title=a.title, path=a.path, text_sha256=a.text_sha256,
                source_rows=json.dumps(a.source_rows), source_sha256=a.source_sha256, pages_sha256=a.pages_sha256,
                count_mode=a.count_mode, unit_count=a.unit_count, status="not_presented", page_count=len(a.pages),
                start_event_id="", end_event_id="", start_timestamp_s="", end_timestamp_s="",
                reading_duration_s="", elapsed_duration_s="", baseline_duration_s="", timing_source="psychopy_flip",
                audio_status="not_requested" if condition == "condition2" else "",
                audio_path="", audio_index_path="", audio_job_id="", audio_error="",
                baseline_trial_id=f"c{condition[-1]}_{a.article_id}_baseline",
                baseline_screenshot_path="screenshots/baseline.png", baseline_ias_path="interest_areas/baseline.ias",
                baseline_status="not_presented", baseline_target_s=config.article_baseline_s,
                baseline_start_event_id="", baseline_end_event_id="",
                baseline_start_timestamp_s="", baseline_end_timestamp_s="",
            ) for index, a in enumerate(selected, 1)]
        self.metadata = dict(participant_id=participant_id, session_id=self.session_id,
                             created_at_utc=utc_now(), status="initialized", config=asdict(config),
                             dummy_mode=config.dummy_mode,
                             host_edf_name="" if config.dummy_mode else uuid.uuid4().hex[:8].upper() + ".EDF",
                             edf_status="disabled_dummy" if config.dummy_mode else "not_opened")
        self.metadata.update(edf_path="", edf_bytes=0,
                             edf_expected_path=str((self.directory / "eyelink.edf").resolve()),
                             dataviewer_trial_unit="article_baseline_and_sentence", screenshots_status="pending",
                             screenshots_directory=str((self.directory / "screenshots").resolve()),
                             sentence_index_path=str((self.directory / "sentence_pages.csv").resolve()),
                             word_aoi_status="pending", word_aoi_unit="whitespace_token",
                             word_aoi_layout="positioned_word_textstim_v1",
                             word_aoi_coordinates="framebuffer_pixels_top_left_origin_inclusive",
                             word_aoi_index_path=str((self.directory / "word_aois.csv").resolve()),
                             word_aoi_directory=str((self.directory / "interest_areas").resolve()))
        self.metadata.update(article_baseline_s=config.article_baseline_s, baseline_scope="article",
                             baseline_assets_status="pending",
                             baseline_background="black", baseline_cross_color="white",
                             baseline_screenshot_path="screenshots/baseline.png",
                             baseline_ias_path="interest_areas/baseline.ias",
                             baseline_preview_path="aoi_previews/baseline.png",
                             reading_duration_method="sum_of_visible_sentence_intervals")
        self.sentences = []
        self.words = []
        for condition, selected in articles.items():
            for article in selected:
                for index, (text, source_row) in enumerate(zip(article.pages, article.source_rows), 1):
                    self.sentences.append(dict(
                        participant_id=participant_id, session_id=self.session_id, condition=condition,
                        article_id=article.article_id, sentence_index=index, source_row=source_row, text=text,
                        trial_id=f"c{condition[-1]}_{article.article_id}_s{index:04d}",
                        screenshot_path=f"screenshots/{condition}/{article.article_id}/sentence_{index:04d}.png",
                        screenshot_status="pending", screenshot_sha256="", width_px="", height_px="",
                        ias_path=f"interest_areas/{condition}/{article.article_id}/sentence_{index:04d}.ias",
                        ias_status="pending", ias_sha256="", word_count="",
                        aoi_preview_path=f"aoi_previews/{condition}/{article.article_id}/sentence_{index:04d}.png",
                        status="not_presented", start_event_id="", end_event_id="",
                        start_timestamp_s="", end_timestamp_s="", duration_s=""))
        first_article = articles["condition1"][0]
        self.metadata["selection_seed"] = first_article.sampling_seed
        self.metadata["article_pool_ids"] = first_article.pool_article_ids
        self.metadata["selected_articles"] = {
            condition: [dict(article_id=a.article_id, title=a.title, path=a.path, source_sha256=a.source_sha256)
                        for a in selected]
            for condition, selected in articles.items()
        }
        # Exact text used in this session survives later edits to assets.
        snapshots = self.directory / "stimuli"
        snapshots.mkdir()
        write_csv(self.directory / "user_logs.csv", LOG_FIELDS, [])
        for selected in articles.values():
            for article in selected:
                (snapshots / (article.article_id + ".txt")).write_text(article.text, encoding="utf-8")
                for index, page in enumerate(article.pages, 1):
                    (snapshots / f"{article.article_id}_page{index:03d}.txt").write_text(page, encoding="utf-8")
        self.save()

    def save(self):
        for condition, rows in self.rows.items():
            write_csv(self.directory / (condition + ".csv"), ARTICLE_FIELDS, rows)
        write_csv(self.directory / "sentence_pages.csv", SENTENCE_FIELDS, self.sentences)
        write_csv(self.directory / "word_aois.csv", WORD_AOI_FIELDS, self.words)
        temporary = self.directory / "session.json.tmp"
        temporary.write_text(json.dumps(self.metadata, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        temporary.replace(self.directory / "session.json")

    def article_durations(self, condition, article_id):
        pages = [row for row in self.sentences if row["condition"] == condition and row["article_id"] == article_id]
        if not pages or any(row["status"] != "completed" or not isinstance(row["duration_s"], (int, float))
                            or row["duration_s"] <= 0 for row in pages):
            raise ValueError("Reading duration requires every sentence interval to be completed")
        return dict(reading_duration_s=sum(row["duration_s"] for row in pages))

    def save_speed(self, summary):
        if "reading_speed" in self.metadata:
            raise RuntimeError("Reading speed has already been saved")
        row = dict(participant_id=self.participant_id, session_id=self.session_id, **summary)
        append_csv(self.root / "reading_speed.csv", SPEED_FIELDS, row)
        self.metadata["reading_speed"] = row
        self.save()


class EventLog:
    def __init__(self, store, controller, clock):
        self.store, self.controller, self.clock = store, controller, clock
        self.pending = []
        self.sequence = 0
        self.path = store.directory / "user_logs.csv"
        write_csv(self.path, LOG_FIELDS, [])

    def emit(self, event, condition="", article_id="", page="", timestamp=None, detail="", marker=None):
        self.sequence += 1
        event_id = f"E{self.sequence:06d}"
        source = "psychopy_clock" if timestamp is None else "psychopy_flip"
        timestamp = self.clock() if timestamp is None else timestamp
        # Data Viewer commands must start with TRIALID / !V / TRIAL_RESULT;
        # prefixing them with our event ID would make them unrecognizable.
        message = marker if marker is not None else f"{event_id} {event} {condition} {article_id} p={page} t={timestamp:.9f}"
        row = dict(participant_id=self.store.participant_id, session_id=self.store.session_id,
                   event_id=event_id, event=event, condition=condition, article_id=article_id,
                   page=page, timestamp_s=timestamp, timestamp_source=source, logged_at_utc=utc_now(),
                   message=message, marker_status="pending", detail=detail)
        self.pending.append(row)
        try:
            self.controller.send_marker(message)
        except Exception as exc:
            row["marker_status"] = "failed"
            row["detail"] += f" Marker failed: {exc}"
            raise
        row["marker_status"] = "disabled_dummy" if self.store.metadata["dummy_mode"] else "sent"
        return row

    def on_flip(self, win, target, event, **kwargs):
        timing = {}
        win.timeOnFlip(timing, "timestamp")

        def callback():
            target.update(self.emit(event, timestamp=timing["timestamp"], **kwargs))

        win.callOnFlip(callback)

    def flush(self):
        if not self.pending:
            return
        with self.path.open("a", encoding="utf-8", newline="") as stream:
            csv.DictWriter(stream, fieldnames=LOG_FIELDS).writerows(self.pending)
        self.pending.clear()
