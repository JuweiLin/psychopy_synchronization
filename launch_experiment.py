
"""Desktop entry point for the Reading Experiment."""

import sys
from pathlib import Path

# Add PsychoPy's user-installed packages
plugin_path = (
    Path.home()
    / "AppData"
    / "Roaming"
    / "psychopy3"
    / "packages"
    / "Python310"
    / "site-packages"
)

if plugin_path.is_dir():
    sys.path.insert(0, str(plugin_path))

print("Experiment Python:", sys.executable)
print("Plugin path:", plugin_path)
print("Plugin path exists:", plugin_path.is_dir())

# Verify EyeLink imports
try:
    import pylink
    from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
    print("EyeLink modules: OK")
except Exception as e:
    print("EyeLink import error:", repr(e))

# Start the experiment
from psychopy_sync.launcher_bootstrap import main

if __name__ == "__main__":
    main()
