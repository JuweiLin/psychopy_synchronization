"""Load the small GPU config without importing display or EyeLink dependencies."""

import argparse
import importlib.util
from pathlib import Path
import runpy
import sys

from .tts_server import main as serve

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def server_arguments(config_path, demo_override=False):
    config_path = Path(config_path).resolve()
    settings = runpy.run_path(str(config_path))
    if type(settings["demo_mode"]) is not bool:
        raise ValueError("demo_mode must be True or False")
    if type(settings["port"]) is not int or not 1 <= settings["port"] <= 65535:
        raise ValueError("port must be an integer from 1 to 65535")
    for name in ("host", "device"):
        if not isinstance(settings[name], str) or not settings[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    arguments = ["--host", settings["host"], "--port", str(settings["port"]),
                 "--output-dir", str(PROJECT_ROOT / "generated_audio"), "--device", settings["device"]]
    if demo_override or settings["demo_mode"]:
        return arguments + ["--demo"]
    for setting, flag in (("ref_audio", "--ref-audio"), ("ref_text_file", "--ref-text-file")):
        path = (config_path.parent / settings[setting]).resolve()
        if not path.is_file():
            raise ValueError(f"Missing {setting}: {path}. Set its path in {config_path.name}.")
        arguments.extend([flag, str(path)])
    return arguments


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "gpu_config.py"))
    parser.add_argument("--demo", action="store_true", help="Test transport using silence; no GPU required")
    args = parser.parse_args(argv)
    try:
        arguments = server_arguments(args.config, args.demo)
        if "--demo" not in arguments and importlib.util.find_spec("f5_tts") is None:
            raise ValueError(f"F5-TTS is not installed in {sys.executable}. Activate the F5-TTS environment or set GPU_PYTHON.")
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        parser.error(str(exc))
    print(f"GPU service Python: {sys.executable}", flush=True)
    serve(arguments)
