"""Measure reading speed, then present sentence text/audio with optional EyeLink."""

import argparse
from dataclasses import replace
import json
import logging

from .articles import load_experiment_articles
from .assignments import load_assignment
from .condition1 import ExperimentAborted, run_condition1
from .condition2 import run_condition2
from .config import DisplayConfig, ExperimentConfig, EyeLinkConfig
from .display import create_window
from .event_log import EventLog, SessionStore
from .eyelink import DummyEyeLinkController, EyeLinkController
from .reading_display import ReadingDisplay
from .questions import load_question_sets
from .session_audio import SessionAudio


def run_experiment(participant_id, config=None, display_config=None, eyelink_config=None):
    config = config or ExperimentConfig()
    display_config = display_config or DisplayConfig(assumed_refresh_rate_hz=None)
    if participant_id in ("0", "00", "000"):
        participant_id = "0"
        config = replace(config, dummy_mode=True, condition1_count=1, condition2_count=2, random_seed=None)
    assignment = load_assignment(config, participant_id)
    if assignment is not None:
        participant_id = assignment.participant_id
        config = replace(config, dummy_mode=participant_id == "0")
    articles = load_experiment_articles(config, assignment)
    questions = load_question_sets(config, articles["condition1"] + articles["condition2"])
    store = SessionStore(config, participant_id, articles, assignment=assignment, questions=questions)
    controller = DummyEyeLinkController() if config.dummy_mode else EyeLinkController(eyelink_config or EyeLinkConfig())
    win, view, log, summary = None, None, None, None
    audio = None
    primary_error = None
    cleanup_errors = []
    try:
        from psychopy import logging as psychopy_logging

        if not config.dummy_mode:
            controller.connect()
        win = create_window(display_config)
        store.metadata["display_config"] = vars(display_config)
        store.metadata["eyelink_config"] = None if config.dummy_mode else vars(controller.config)
        store.metadata["window_size"] = [int(v) for v in win.size]
        store.save()
        view = ReadingDisplay(win, config, controller)
        prepared = view.prepare(articles["condition1"] + articles["condition2"])
        view.prepare_questions(questions)
        view.export_pages(store, articles, prepared)
        if not config.dummy_mode:
            controller.configure_display(win)
            controller.configure_calibration(win)
            controller.calibrate()
            controller.open_edf(store.metadata["host_edf_name"])
            store.metadata["edf_status"] = "opened"
            # DISPLAY_COORDS sent before opening EDF is not stored in that file.
            controller.configure_display(win)
        log = EventLog(store, controller, psychopy_logging.defaultClock.getTime)
        controller.send_marker(f"SESSION {store.session_id} USER {participant_id}")
        if config.dummy_mode:
            store.metadata["status"] = "dummy_running"
        else:
            controller.start_recording()
            store.metadata.update(status="recording", edf_status="recording")
        store.save()
        log.emit("SESSION_START")
        if assignment is not None:
            log.emit("PARTICIPANT_ASSIGNMENT", detail=json.dumps(assignment.metadata(), ensure_ascii=True))
        if config.dummy_mode:
            view.wait_screen("Dummy mode. No eye tracking will be recorded.\n\n"
                             f"Press {config.advance_key.upper()} to start Condition 1.", log, "DUMMY_READY")
        else:
            view.wait_screen("Confirm calibration and validation on the EyeLink Host.\n\n"
                             f"Press {config.advance_key.upper()} when ready to start Condition 1.", log, "CALIBRATION_CONFIRM")
        summary = run_condition1(view, articles["condition1"], prepared, log, store)
        store.metadata["status"] = "condition1_completed"
        log.emit("READING_SPEED", detail=f"{summary['speed_per_minute']:.6f} {summary['speed_unit']}")
        audio = SessionAudio(config, store, articles["condition2"], summary)
        audio.start()
        log.emit("TTS_START" if audio.worker is not None else "TTS_SKIPPED", "condition2",
                 detail=audio.manifest["status"])
        if audio.worker is not None:
            store.metadata.update(status="condition2_running", condition2_status="running")
            store.save()
            run_condition2(view, articles["condition2"], prepared, audio, log, store)
            store.metadata["condition2_status"] = "completed"
        else:
            store.metadata["condition2_status"] = "not_configured" if articles["condition2"] else "not_required"
            log.emit("CONDITION_SKIPPED", "condition2", detail=audio.manifest["status"])
        store.metadata["status"] = "completed"
        log.emit("SESSION_END")
    except BaseException as exc:
        primary_error = exc
        store.metadata.update(status="aborted" if isinstance(exc, ExperimentAborted) else "failed", error=str(exc))
        if store.metadata.get("condition2_status") == "running":
            store.metadata["condition2_status"] = store.metadata["status"]
        if log is not None:
            try:
                log.emit("SESSION_ABORT" if isinstance(exc, ExperimentAborted) else "SESSION_ERROR", detail=str(exc))
            except Exception:
                pass
    finally:
        if view is not None and view.data_viewer is not None:
            view.data_viewer.mark_interrupted()
        try:
            if audio is not None:
                audio.stop()
        except Exception as exc:
            cleanup_errors.append(f"Audio cleanup failed: {exc}")
        try:
            if log is not None:
                log.flush()
        except Exception as exc:
            cleanup_errors.append(f"Log save failed: {exc}")
        try:
            if not config.dummy_mode:
                if store.metadata["edf_status"] in ("opened", "recording"):
                    store.metadata["edf_status"] = "transferring"
                    store.save()
                if primary_error is None and view is not None:
                    # Only a normal run redraws here. Failed flips may still
                    # have pending callbacks, so do not replay them on abort.
                    try:
                        view.show_saving()
                    except Exception:
                        logging.warning("Could not show the saving screen", exc_info=True)
                destination = store.directory / "eyelink.edf"
                if controller.finish_session(destination):
                    if not destination.is_file() or destination.stat().st_size == 0:
                        raise IOError("EyeLink download produced no nonempty local EDF file")
                    store.metadata.update(edf_status="downloaded", edf_path=str(destination.resolve()),
                                          edf_bytes=destination.stat().st_size)
                elif primary_error is None:
                    raise IOError("EyeLink did not create an EDF file")
        except Exception as exc:
            store.metadata.update(edf_status="recovery_required", edf_error=str(exc))
            cleanup_errors.append(f"EDF recovery required ({store.metadata['host_edf_name']} on Host): {exc}")
        try:
            controller.close()
        except Exception as exc:
            cleanup_errors.append(f"Tracker cleanup failed: {exc}")
        try:
            if win is not None:
                win.close()
        except Exception as exc:
            cleanup_errors.append(f"Window cleanup failed: {exc}")
        if cleanup_errors:
            store.metadata["cleanup_errors"] = cleanup_errors
            if primary_error is None:
                store.metadata["status"] = "failed"
        store.save()
        for error in cleanup_errors:
            logging.error(error)
    if primary_error is not None:
        primary_error.session_result = dict(store.metadata, directory=str(store.directory))
        raise primary_error
    if cleanup_errors:
        error = RuntimeError("; ".join(cleanup_errors))
        error.session_result = dict(store.metadata, directory=str(store.directory))
        raise error
    return summary, store.directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-id", required=True)
    args = parser.parse_args()
    try:
        summary, directory = run_experiment(args.participant_id)
    except ExperimentAborted:
        print("Session aborted; partial logs and EDF recovery status saved.")
        raise SystemExit(130)
    print(f"Reading speed: {summary['speed_per_minute']:.2f} {summary['speed_unit']}")
    print(f"Session data: {directory}")
    metadata = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    print(f"TTS: {metadata.get('tts_status')} — {metadata.get('tts_directory')}")


if __name__ == "__main__":
    main()
