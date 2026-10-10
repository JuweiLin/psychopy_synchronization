"""Expose PsychoPy-managed packages without importing PsychoPy or EyeLink."""

import importlib
import os
from pathlib import Path
import site
import sys


def psychopy_package_paths():
    """Use this process's Python version, including redirected Windows AppData."""
    major, minor = sys.version_info[:2]
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return (appdata / "psychopy3" / "packages" / f"Python{major}{minor}" / "site-packages",)
    root = Path.home() / ".psychopy3" / "packages"
    version = f"python{major}.{minor}"
    paths = [root / "lib" / version / "site-packages"]
    if sys.platform == "darwin" and getattr(sys, "_framework", ""):
        # PsychoPy uses a different layout for macOS framework Python, with
        # versioned and legacy locations supported by its preferences code.
        paths = [root / version / "lib" / "python" / "site-packages",
                 root / "lib" / "python" / "site-packages"] + paths
    return tuple(paths)


def add_psychopy_packages():
    """Run in each process; sys.path changes are not inherited by subprocesses."""
    for path in psychopy_package_paths():
        if path.is_dir() and str(path) not in sys.path:
            site.addsitedir(str(path))
    importlib.invalidate_caches()
