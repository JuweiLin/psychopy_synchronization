"""Run the experiment in its own main thread and return a result to the desktop UI."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import traceback

from .condition1 import ExperimentAborted
from .config import ExperimentConfig
from .event_log import validate_login_participant_id


def session_details(metadata, directory=None):
    fields = ("tts_status", "condition2_status", "dummy_mode", "edf_status", "edf_path", "edf_bytes",
              "host_edf_name", "edf_error", "screenshots_status", "screenshots_directory", "sentence_index_path",
              "word_aoi_status", "word_aoi_index_path", "word_aoi_directory")
    result = {name: metadata[name] for name in fields if name in metadata}
    if directory is not None:
        result["directory"] = str(directory)
    return result


def execute(participant_id, result_path, runner=None):
    try:
        participant_id = validate_login_participant_id(participant_id)
        if runner is None:
            from .experiment import run_experiment
            runner = run_experiment
        config = replace(ExperimentConfig(), dummy_mode=participant_id == "0")
        if config.dummy_mode:
            config = replace(config, condition1_count=1, condition2_count=2, random_seed=None)
        summary, directory = runner(participant_id, config=config)
        metadata = json.loads((Path(directory) / "session.json").read_text(encoding="utf-8"))
        result = dict(status="completed", summary=summary, **session_details(metadata, directory))
        code = 0
    except (ExperimentAborted, KeyboardInterrupt) as exc:
        metadata = getattr(exc, "session_result", {})
        result = dict(status="aborted", **session_details(metadata, metadata.get("directory")))
        code = 130
    except Exception as exc:
        traceback.print_exc()
        metadata = getattr(exc, "session_result", {})
        result = dict(status="failed", error=str(exc), **session_details(metadata, metadata.get("directory")))
        code = 1
    path = Path(result_path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--result-file", required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.participant_id, args.result_file))


if __name__ == "__main__":
    main()
