"""Condition 1: per-article visible intervals during one continuous recording."""

from .reading_speed import reading_summary


class ExperimentAborted(Exception):
    pass


def run_condition1(view, articles, prepared, log, store):
    log.emit("CONDITION_START", "condition1", marker="CONDITION_START condition1")
    log.flush()
    for article, row in zip(articles, store.rows["condition1"]):
        pages = prepared[article.article_id]
        row["page_count"] = len(pages)
        row["status"] = "presenting"
        store.save()
        start, end = {}, {}
        try:
            log.emit("TRIAL_START", "condition1", article.article_id)
            view.show_baseline(log, "condition1", article.article_id)
            view.show_title(article, log, "condition1")
            for page_index, page in enumerate(pages, 1):
                onset = start if page_index == 1 else {}
                view.read_page(page, log, onset, "ARTICLE_ONSET" if page_index == 1 else "PAGE_ONSET",
                               article.article_id, page_index)
            # The end event is coupled to the flip that removes the last page.
            view.clear_article(log, end, "ARTICLE_END", article.article_id)
            row.update(status="completed", start_event_id=start["event_id"], end_event_id=end["event_id"],
                       start_timestamp_s=start["timestamp_s"], end_timestamp_s=end["timestamp_s"],
                       elapsed_duration_s=end["timestamp_s"] - start["timestamp_s"],
                       **store.article_durations("condition1", article.article_id))
            store.save()
            view.ask_questions(article, log, store, "condition1")
            view.ask_feedback(article, log, store, "condition1")
        except BaseException as exc:
            if row["status"] != "completed":
                row["status"] = "aborted" if isinstance(exc, ExperimentAborted) else "failed"
            if start:
                row.update(start_event_id=start["event_id"], start_timestamp_s=start["timestamp_s"])
            if not end:
                try:
                    view.clear_article(log, end, "ARTICLE_ABORT", article.article_id, page_status=row["status"])
                except Exception:
                    pass  # Also close an aborted baseline before the first sentence.
            if end:
                row.update(end_event_id=end["event_id"], end_timestamp_s=end["timestamp_s"])
            raise
        finally:
            log.flush()
            store.save()
    log.emit("CONDITION_END", "condition1", marker="CONDITION_END condition1")
    log.flush()
    summary = reading_summary(store.rows["condition1"], len(articles))
    store.save_speed(summary)
    return summary
