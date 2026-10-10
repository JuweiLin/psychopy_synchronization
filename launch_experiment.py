
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

# Start the experiment
from psychopy_sync.launcher_bootstrap import main

if __name__ == "__main__":
    main()
