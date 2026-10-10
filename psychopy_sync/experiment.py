"""Measure reading speed and prepare sentence audio, with optional EyeLink recording."""

import argparse
import json
import logging

from .articles import load_experiment_articles
from .condition1 import ExperimentAborted, run_condition1
from .config import DisplayConfig, ExperimentConfig, EyeLinkConfig
from .display import create_window
from .event_log import EventLog, SessionStore
from .eyelink import DummyEyeLinkController, EyeLinkController
from .reading_display import ReadingDisplay
from .session_audio import SessionAudio


def run_experiment(participant_id, config=None, display_config=None, eyelink_config=None):
    config = config or ExperimentConfig()
    display_config = display_config or DisplayConfig(assumed_refresh_rate_hz=None)
    articles = load_experiment_articles(config)
    store = SessionStore(config, participant_id, articles)
    controller = DummyEyeLinkController() if config.dummy_mode else EyeLinkController(eyelink_config or EyeLinkConfig())
    win, log, summary = None, None, None
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
        prepared = view.prepare(articles["condition1"])
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
            view.wait_for_audio(audio, log)
        # Condition 2 presentation has not started; files remain cached for later.
        log.emit("SESSION_END")
    except BaseException as exc:
        primary_error = exc
        store.metadata.update(status="aborted" if isinstance(exc, ExperimentAborted) else "failed", error=str(exc))
        if log is not None:
            try:
                log.emit("SESSION_ABORT" if isinstance(exc, ExperimentAborted) else "SESSION_ERROR", detail=str(exc))
            except Exception:
                pass
    finally:
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
            if not config.dummy_mode and controller.finish_session(store.directory / "eyelink.edf"):
                store.metadata["edf_status"] = "downloaded"
        except Exception as exc:
            store.metadata["edf_status"] = "recovery_required"
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
        store.save()
        for error in cleanup_errors:
            logging.error(error)
    if primary_error is not None:
        raise primary_error
    if cleanup_errors:
        raise RuntimeError("; ".join(cleanup_errors))
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
