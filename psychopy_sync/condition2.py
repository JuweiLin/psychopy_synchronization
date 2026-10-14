"""Condition 2: sentence text with the participant's generated sentence audio."""

from .condition1 import ExperimentAborted
from .display import preload_article_audio


def run_condition2(view, articles, prepared, audio, log, store):
    log.emit("CONDITION_START", "condition2", marker="CONDITION_START condition2")
    log.flush()
    speaker = None
    try:
        for article, row in zip(articles, store.rows["condition2"]):
            start, end, sounds = {}, {}, []
            page_index = None
            presentation_started = False
            row["status"] = "waiting_for_audio"
            store.save()
            try:
                view.wait_for_audio(audio, log, article.article_id)
                cached = audio.cached_article(article.article_id)
                pages = prepared[article.article_id]
                if len(cached) != len(pages):
                    raise RuntimeError(f"Sentence/audio count mismatch for article {article.article_id}")
                for sentence in cached:
                    playback = preload_article_audio(sentence, allow_demo=view.config.dummy_mode, speaker=speaker)
                    sounds.append(playback)
                    # Modern PsychoPy needs one shared device for all sentence tracks.
                    speaker = getattr(playback, "speaker", None)
                log.emit("ARTICLE_AUDIO_READY", "condition2", article.article_id,
                         detail=f"{len(sounds)} sentences preloaded")
                log.flush()
                view.show_title(article, log, "condition2")
                row["status"] = "presenting"
                store.save()
                log.emit("TRIAL_START", "condition2", article.article_id)
                presentation_started = True
                view.show_baseline(log, "condition2", article.article_id)
                for page_index, (page, playback, sentence) in enumerate(zip(pages, sounds, cached), 1):
                    view.play_page(page, playback, sentence, log, start, article.article_id, page_index)
                view.clear_article(log, end, "ARTICLE_END", article.article_id,
                                   condition="condition2", page=page_index)
                row.update(status="completed", start_event_id=start["event_id"], end_event_id=end["event_id"],
                           start_timestamp_s=start["timestamp_s"], end_timestamp_s=end["timestamp_s"],
                           elapsed_duration_s=end["timestamp_s"] - start["timestamp_s"],
                           **store.article_durations("condition2", article.article_id))
                store.save()
                view.ask_questions(article, log, store, "condition2")
            except BaseException as exc:
                if row["status"] != "completed":
                    row["status"] = "aborted" if isinstance(exc, ExperimentAborted) else "failed"
                if start:
                    row.update(start_event_id=start["event_id"], start_timestamp_s=start["timestamp_s"])
                if not end and presentation_started:
                    try:
                        view.clear_article(log, end, "ARTICLE_ABORT", article.article_id,
                                           condition="condition2", page=page_index, page_status=row["status"])
                    except Exception:
                        pass
                if end:
                    row.update(end_event_id=end["event_id"], end_timestamp_s=end["timestamp_s"])
                raise
            finally:
                try:
                    for playback in sounds:
                        playback.stop()
                finally:
                    # Release sentence tracks before closing their shared device.
                    sounds.clear()
                    playback = None
                    audio.poll(log)
                    log.flush()
                    store.save()
    finally:
        if speaker is not None:
            speaker.close()
    log.emit("CONDITION_END", "condition2", marker="CONDITION_END condition2")
    log.flush()
