#!/bin/sh
set -eu
experiment_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$experiment_root"
mkdir -p "$experiment_root/data/launcher_logs"
exec >>"$experiment_root/data/launcher_logs/desktop-startup.log" 2>&1
for experiment_python in "$experiment_root/.venv/bin/python" "$experiment_root/venv/bin/python"; do
    if [ -x "$experiment_python" ]; then
        exec "$experiment_python" "$experiment_root/launch_experiment.py"
    fi
done
for experiment_app in /Applications/*PsychoPy*.app "$HOME"/Applications/*PsychoPy*.app; do
    experiment_python="$experiment_app/Contents/MacOS/python"
    if [ -x "$experiment_python" ]; then
        export PYTHONHOME="$experiment_app/Contents/Resources"
        exec "$experiment_python" "$experiment_root/launch_experiment.py"
    fi
done
experiment_python=$(command -v python3 || true)
if [ -n "$experiment_python" ]; then
    exec "$experiment_python" "$experiment_root/launch_experiment.py"
fi
/usr/bin/osascript -e 'display alert "Reading Experiment" message "Install PsychoPy, then double-click Start Experiment.command again." as critical'
exit 1
