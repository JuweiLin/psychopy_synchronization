"""Full-screen page captures and one Data Viewer trial per displayed sentence.

Images are rendered to the back buffer before calibration/recording. During
reading, flip callbacks only update memory and send EDF messages; no image or
CSV writes take place. AOIs are deliberately left to Data Viewer.
"""

from shared.contracts import sha256_file


class DataViewerExport:
    def __init__(self, store):
        self.store = store
        self.pages = {(row["condition"], row["article_id"], row["sentence_index"]): row
                      for row in store.sentences}
        self.active = None

    def prepare(self, view, articles, prepared):
        win = view.win
        size = tuple(int(value) for value in win.size)
        try:
            for condition, selected in articles.items():
                for article in selected:
                    for index, page in enumerate(prepared[article.article_id], 1):
                        row = self.pages[condition, article.article_id, index]
                        path = self.store.directory / row["screenshot_path"]
                        path.parent.mkdir(parents=True, exist_ok=True)
                        win.clearBuffer()
                        view.draw_page(page, condition)
                        image = win.getMovieFrame(buffer="back")
                        try:
                            if image.size != size:
                                raise RuntimeError(f"Screenshot size {image.size} differs from EyeLink display coordinates {size}")
                            image.save(str(path), format="PNG")
                        finally:
                            # getMovieFrame also appends to PsychoPy's movie stack.
                            # Do not retain hundreds of full-resolution frames.
                            win.movieFrames.clear()
                        row.update(screenshot_status="saved", screenshot_sha256=sha256_file(path),
                                   width_px=size[0], height_px=size[1])
            self.store.metadata["screenshots_status"] = "saved"
        except BaseException:
            self.store.metadata["screenshots_status"] = "failed"
            raise
        finally:
            win.clearBuffer()
            self.store.save()

    @staticmethod
    def _message(log, row, event, message, timestamp):
        return log.emit(event, row["condition"], row["article_id"], page=row["sentence_index"],
                        timestamp=timestamp, marker=message)

    def start_page(self, log, condition, article_id, index, timestamp):
        self.end_page(log, timestamp)
        row = self.pages[condition, article_id, index]
        if row["screenshot_status"] != "saved":
            raise RuntimeError(f"Screenshot was not prepared for {row['trial_id']}")
        self.active = row
        row["status"] = "presenting"
        self._message(log, row, "DV_TRIAL_START", f"TRIALID {row['trial_id']}", timestamp)
        for name in ("condition", "article_id", "sentence_index"):
            self._message(log, row, "DV_TRIAL_VAR", f"!V TRIAL_VAR {name} {row[name]}", timestamp)
        self._message(log, row, "DV_IMAGE", f"!V IMGLOAD FILL {row['screenshot_path']}", timestamp)
        self._message(log, row, "SENTENCE_ONSET", "SENTENCE_ONSET", timestamp)
        event = log.emit("PAGE_ONSET", condition, article_id, page=index, timestamp=timestamp)
        row.update(start_event_id=event["event_id"], start_timestamp_s=timestamp)

    def end_page(self, log, timestamp, status="completed"):
        row = self.active
        if row is None:
            return
        event = log.emit("PAGE_END", row["condition"], row["article_id"],
                         page=row["sentence_index"], timestamp=timestamp)
        self._message(log, row, "SENTENCE_OFFSET", "SENTENCE_OFFSET", timestamp)
        self._message(log, row, "DV_TRIAL_END", "TRIAL_RESULT 0" if status == "completed" else "TRIAL_RESULT 1", timestamp)
        row.update(status=status, end_event_id=event["event_id"], end_timestamp_s=timestamp,
                   duration_s=timestamp - row["start_timestamp_s"] if row["start_timestamp_s"] != "" else "")
        self.active = None

    def mark_interrupted(self):
        # A failed flip/connection gives no trustworthy visual offset. Preserve
        # the open interval instead of inventing an end timestamp.
        if self.active is not None:
            self.active["status"] = "interrupted"

