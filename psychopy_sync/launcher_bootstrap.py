"""Find a PsychoPy/wx runtime in project environments or standalone installs."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

from .config import ExperimentConfig, PROJECT_ROOT

def required_modules(config=None):
    config = config or ExperimentConfig()
    display = ("psychopy", "wx")
    return display if config.dummy_mode else display + ("pylink", "EyeLinkCoreGraphicsPsychoPy")


@dataclass
class Runtime:
    executable: Path
    environment: dict


def windows_python_candidates(environment):
    roots = [Path(environment[key]) for key in ("ProgramFiles", "ProgramFiles(x86)")
             if environment.get(key)]
    if environment.get("LOCALAPPDATA"):
        roots.append(Path(environment["LOCALAPPDATA"]) / "Programs")
    for root in roots:
        try:
            directories = sorted(root.iterdir(), key=lambda path: path.name.casefold())
        except OSError:
            continue
        for directory in directories:
            if directory.name.casefold().startswith("psychopy") and directory.is_dir():
                yield directory / "python.exe"
                yield directory / "python" / "python.exe"


def runtime_candidates(project_root=PROJECT_ROOT):
    inherited = dict(os.environ)
    normal = dict(inherited)
    normal.pop("PYTHONHOME", None)
    candidates = []
    override = os.environ.get("PSYCHOPY_PYTHON")
    if override:
        candidates.append(Runtime(Path(override), normal))
    for folder in (".venv", "venv"):
        relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        candidates.append(Runtime(project_root / folder / relative, normal))
    candidates.append(Runtime(Path(sys.executable), inherited))
    if sys.platform == "darwin":
        for directory in (Path("/Applications"), Path.home() / "Applications"):
            for app in sorted(directory.glob("*PsychoPy*.app")):
                resources = app / "Contents/Resources"
                environment = dict(normal, PYTHONHOME=str(resources))
                candidates.append(Runtime(app / "Contents/MacOS/python", environment))
    elif sys.platform == "win32":
        candidates.extend(Runtime(executable, normal) for executable in windows_python_candidates(normal))
    seen = set()
    for candidate in candidates:
        key = (str(candidate.executable), candidate.environment.get("PYTHONHOME"))
        if candidate.executable.is_file() and key not in seen:
            seen.add(key)
            yield candidate


def find_runtime(candidates=None, config=None):
    modules = required_modules(config)
    probe = ("import importlib.util, json; "
             f"print(json.dumps({{name: importlib.util.find_spec(name) is not None for name in {modules!r}}}))")
    fallback = None
    for candidate in runtime_candidates() if candidates is None else candidates:
        try:
            result = subprocess.run([str(candidate.executable), "-c", probe],
                                    cwd=PROJECT_ROOT, env=candidate.environment,
                                    capture_output=True, text=True, timeout=8)
            if result.returncode:
                continue
            available = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            continue
        if available.get("psychopy") and available.get("wx"):
            if all(available.get(name) for name in modules):
                return candidate
            if fallback is None:
                fallback = candidate
    return fallback


def show_error(message):
    print(message, file=sys.stderr)
    if sys.platform == "darwin":
        script = ('on run argv\n'
                  'display alert "Reading Experiment" message (item 1 of argv) as critical\n'
                  'end run')
        subprocess.run(["/usr/bin/osascript", "-e", script, message], check=False)


def main():
    runtime = find_runtime()
    if runtime is None:
        show_error("No compatible PsychoPy environment found. Install PsychoPy, or install PsychoPy and wxPython in the project .venv, then launch again.")
        raise SystemExit(1)
    command = [str(runtime.executable), "-m", "psychopy_sync.launcher"]
    if sys.platform == "win32":
        # Windows execve does not quote argv entries containing spaces. Use
        # subprocess's Windows argument conversion for Program Files installs.
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=runtime.environment, check=False)
        raise SystemExit(result.returncode)
    os.chdir(PROJECT_ROOT)
    os.execve(str(runtime.executable), command, runtime.environment)
