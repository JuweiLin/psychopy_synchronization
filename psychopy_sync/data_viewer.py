"""Full-screen captures and separate article-baseline/sentence trials.

Images are rendered to the back buffer before calibration/recording. During
reading, flip callbacks only update memory and send EDF messages; no image or
CSV writes take place. Word AOIs use the same layout as the displayed text.
"""

from shared.contracts import sha256_file
from .word_layout import interest_area_text


def save_aoi_preview(image, areas, path):
    """Save an inspection copy; this overlay is never shown to participants."""
    from PIL import ImageDraw

    preview = image.copy().convert("RGB")
    try:
        draw = ImageDraw.Draw(preview)
        for area in areas:
            draw.rectangle((area["left"], area["top"], area["right"], area["bottom"]),
                           outline=(255, 80, 80), width=1)
        preview.save(str(path), format="PNG")
    finally:
        preview.close()


class DataViewerExport:
    def __init__(self, store):
        self.store = store
        self.pages = {(row["condition"], row["article_id"], row["sentence_index"]): row
                      for row in store.sentences}
        self.articles = {(condition, row["article_id"]): row for condition, rows in store.rows.items() for row in rows}
        self.active = None
        self.active_baseline = None
        self.passage = None

    def prepare_baseline(self, view):
        """Capture the real cross and derive its AOI from its visible pixels."""
        win = view.win
        width, height = (int(value) for value in win.size)
        win.clearBuffer()
        view.baseline_cross.draw()
        image = win.getMovieFrame(buffer="back")
        try:
            if image.size != (width, height):
                raise RuntimeError(f"Screenshot size {image.size} differs from EyeLink display coordinates {(width, height)}")
            mask = image.convert("L").point(lambda value: 255 if value > 16 else 0)
            try:
                bounds = mask.getbbox()
            finally:
                mask.close()
            if bounds is None:
                raise RuntimeError("The baseline cross was not visible in its screenshot")
            x, y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
            half_width = max(28, (bounds[2] - bounds[0]) / 2 + 12)
            half_height = max(28, (bounds[3] - bounds[1]) / 2 + 12)
            area = dict(word_index=1, ia_label="baseline_cross",
                        left=max(0, int(x - half_width)), top=max(0, int(y - half_height)),
                        right=min(width - 1, int(x + half_width) - 1),
                        bottom=min(height - 1, int(y + half_height) - 1))
            paths = {name: self.store.directory / self.store.metadata[name] for name in (
                "baseline_screenshot_path", "baseline_ias_path", "baseline_preview_path")}
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(paths["baseline_screenshot_path"]), format="PNG")
            paths["baseline_ias_path"].write_text(interest_area_text([area]), encoding="ascii")
            save_aoi_preview(image, [area], paths["baseline_preview_path"])
            self.store.metadata.update(baseline_assets_status="saved", baseline_aoi=area,
                baseline_screenshot_sha256=sha256_file(paths["baseline_screenshot_path"]),
                baseline_ias_sha256=sha256_file(paths["baseline_ias_path"]))
        finally:
            win.movieFrames.clear()
            win.clearBuffer()

    def prepare(self, view, articles, prepared):
        win = view.win
        size = tuple(int(value) for value in win.size)
        self.store.words.clear()
        try:
            self.prepare_baseline(view)
            for condition, selected in articles.items():
                for article in selected:
                    for index, page in enumerate(prepared[article.article_id], 1):
                        row = self.pages[condition, article.article_id, index]
                        areas = page.word_areas
                        if len(areas) != len(row["text"].split()):
                            raise RuntimeError(f"Word AOI count differs from the page text: {row['trial_id']}")
                        path = self.store.directory / row["screenshot_path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        ias_path = self.store.directory / row["ias_path"]
                        ias_path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = ias_path.with_suffix(".ias.tmp")
                        temporary.write_text(interest_area_text(areas), encoding="ascii")
                        temporary.replace(ias_path)
                        preview_path = self.store.directory / row["aoi_preview_path"]
                        preview_path.parent.mkdir(parents=True, exist_ok=True)
                        win.clearBuffer()
                        view.draw_page(page, condition)
                        image = win.getMovieFrame(buffer="back")
                        try:
                            if image.size != size:
                                raise RuntimeError(f"Screenshot size {image.size} differs from EyeLink display coordinates {size}")
                            image.save(str(path), format="PNG")
                            save_aoi_preview(image, areas, preview_path)
                        finally:
                            # getMovieFrame also appends to PsychoPy's movie stack.
                            # Do not retain hundreds of full-resolution frames.
                            win.movieFrames.clear()
                        row.update(screenshot_status="saved", screenshot_sha256=sha256_file(path),
                                   width_px=size[0], height_px=size[1], ias_status="saved",
                                   ias_sha256=sha256_file(ias_path), word_count=len(areas))
                        identity = {name: row[name] for name in (
                            "participant_id", "session_id", "condition", "article_id", "sentence_index",
                            "trial_id", "screenshot_path", "ias_path")}
                        self.store.words.extend(dict(identity, **area) for area in areas)
            self.store.metadata["screenshots_status"] = "saved"
            self.store.metadata["word_aoi_status"] = "saved"
        except BaseException:
            self.store.metadata["screenshots_status"] = "failed"
            self.store.metadata["word_aoi_status"] = "failed"
            if self.store.metadata.get("baseline_assets_status") != "saved":
                self.store.metadata["baseline_assets_status"] = "failed"
            raise
        finally:
            win.clearBuffer()
            self.store.save()

    @staticmethod
    def _message(log, row, event, message, timestamp):
        return log.emit(event, row["condition"], row["article_id"], page=row.get("sentence_index", ""),
                        timestamp=timestamp, marker=message)

    def _assignment_variables(self, log, row, timestamp):
        assignment = self.store.metadata.get("assignment")
        if assignment is not None:
            for name in ("participant_id", "instruction_group", "allocation_slot", "list_id"):
                value = assignment[name] or "none"
                self._message(log, row, "DV_TRIAL_VAR", f"!V TRIAL_VAR {name} {value}", timestamp)

    def start_page(self, log, condition, article_id, index, timestamp):
        self.end_baseline(log, timestamp)
        self.end_page(log, timestamp)
        row = self.pages[condition, article_id, index]
        if row["screenshot_status"] != "saved":
            raise RuntimeError(f"Screenshot was not prepared for {row['trial_id']}")
        if row["ias_status"] != "saved":
            raise RuntimeError(f"Word AOIs were not prepared for {row['trial_id']}")
        self.active = row
        row["status"] = "presenting"
        self._message(log, row, "DV_TRIAL_START", f"TRIALID {row['trial_id']}", timestamp)
        for name in ("condition", "article_id", "sentence_index"):
            self._message(log, row, "DV_TRIAL_VAR", f"!V TRIAL_VAR {name} {row[name]}", timestamp)
        self._assignment_variables(log, row, timestamp)
        self._message(log, row, "DV_TRIAL_VAR", "!V TRIAL_VAR phase reading", timestamp)
        self._message(log, row, "DV_IMAGE", f"!V IMGLOAD FILL {row['screenshot_path']}", timestamp)
        self._message(log, row, "DV_WORD_AOI", f"!V IAREA FILE {row['ias_path']}", timestamp)
        if index == 1:
            self.passage = (condition, article_id)
            self._message(log, row, "PASSAGE_START", f"PASSAGE_START {condition} {article_id}", timestamp)
        self._message(log, row, "SENTENCE_START", "SENTENCE_START", timestamp)
        self._message(log, row, "SENTENCE_ONSET", "SENTENCE_ONSET", timestamp)
        event = log.emit("PAGE_ONSET", condition, article_id, page=index, timestamp=timestamp)
        row.update(start_event_id=event["event_id"], start_timestamp_s=timestamp)

    def end_page(self, log, timestamp, status="completed", finish_passage=False):
        row = self.active
        if row is None:
            return
        event = log.emit("PAGE_END", row["condition"], row["article_id"],
                         page=row["sentence_index"], timestamp=timestamp)
        self._message(log, row, "SENTENCE_OFFSET", "SENTENCE_OFFSET", timestamp)
        self._message(log, row, "SENTENCE_END", "SENTENCE_END", timestamp)
        if finish_passage:
            self.end_passage(log, timestamp, status)
        self._message(log, row, "DV_TRIAL_END", "TRIAL_RESULT 0" if status == "completed" else "TRIAL_RESULT 1", timestamp)
        row.update(status=status, end_event_id=event["event_id"], end_timestamp_s=timestamp,
                   duration_s=timestamp - row["start_timestamp_s"] if row["start_timestamp_s"] != "" else "")
        self.active = None

    def start_baseline(self, log, condition, article_id, timestamp):
        self.end_page(log, timestamp)
        if self.active_baseline is not None:
            raise RuntimeError("The preceding baseline has not ended")
        if self.store.metadata.get("baseline_assets_status") != "saved":
            raise RuntimeError("Baseline image and cross AOI were not prepared")
        row = self.articles[condition, article_id]
        self.active_baseline = row
        row["baseline_status"] = "presenting"
        self._message(log, row, "DV_BASELINE_TRIAL_START", f"TRIALID {row['baseline_trial_id']}", timestamp)
        for name in ("condition", "article_id"):
            self._message(log, row, "DV_TRIAL_VAR", f"!V TRIAL_VAR {name} {row[name]}", timestamp)
        self._assignment_variables(log, row, timestamp)
        self._message(log, row, "DV_TRIAL_VAR", "!V TRIAL_VAR sentence_index 0", timestamp)
        self._message(log, row, "DV_TRIAL_VAR", "!V TRIAL_VAR phase baseline", timestamp)
        self._message(log, row, "DV_IMAGE", f"!V IMGLOAD FILL {row['baseline_screenshot_path']}", timestamp)
        self._message(log, row, "DV_BASELINE_AOI", f"!V IAREA FILE {row['baseline_ias_path']}", timestamp)
        event = self._message(log, row, "BASELINE_START", "BASELINE_START", timestamp)
        row.update(baseline_start_event_id=event["event_id"], baseline_start_timestamp_s=timestamp)

    def end_baseline(self, log, timestamp, status="completed"):
        row = self.active_baseline
        if row is None:
            return
        event = self._message(log, row, "BASELINE_END", "BASELINE_END", timestamp)
        self._message(log, row, "DV_BASELINE_TRIAL_END", "TRIAL_RESULT 0" if status == "completed" else "TRIAL_RESULT 1", timestamp)
        row.update(baseline_status=status, baseline_end_event_id=event["event_id"],
                   baseline_end_timestamp_s=timestamp,
                   baseline_duration_s=timestamp - row["baseline_start_timestamp_s"]
                   if row["baseline_start_timestamp_s"] != "" else "")
        self.active_baseline = None

    def end_phase(self, log, timestamp, status="completed"):
        if self.active is None:
            self.end_passage(log, timestamp, status)
        self.end_baseline(log, timestamp, status)
        self.end_page(log, timestamp, status, finish_passage=True)

    def end_passage(self, log, timestamp, status="completed"):
        if self.passage is not None:
            condition, article_id = self.passage
            log.emit("PASSAGE_END", condition, article_id, timestamp=timestamp,
                     marker=f"PASSAGE_END {condition} {article_id}", detail=f"status={status}")
            self.passage = None

    def mark_interrupted(self):
        # A failed flip/connection gives no trustworthy visual offset. Preserve
        # the open interval instead of inventing an end timestamp.
        if self.active is not None:
            self.active["status"] = "interrupted"
        if self.active_baseline is not None:
            self.active_baseline["baseline_status"] = "interrupted"

