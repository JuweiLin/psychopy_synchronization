"""Run the experiment in its own main thread and return a result to the desktop UI."""

import argparse
import json
from pathlib import Path
import traceback

from .condition1 import ExperimentAborted
from .event_log import validate_participant_id


def execute(participant_id, result_path, runner=None):
    try:
        validate_participant_id(participant_id)
        if runner is None:
            from .experiment import run_experiment
            runner = run_experiment
        summary, directory = runner(participant_id)
        metadata = json.loads((Path(directory) / "session.json").read_text(encoding="utf-8"))
        result = dict(status="completed", summary=summary, directory=str(directory),
                      tts_status=metadata.get("tts_status"), condition2_status=metadata.get("condition2_status"),
                      dummy_mode=metadata.get("dummy_mode", False))
        code = 0
    except (ExperimentAborted, KeyboardInterrupt):
        result = dict(status="aborted")
        code = 130
    except Exception as exc:
        traceback.print_exc()
        result = dict(status="failed", error=str(exc))
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
