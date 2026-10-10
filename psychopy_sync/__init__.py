"""PsychoPy display and EyeLink components.

Hardware libraries are imported only when the relevant component is used.
"""

from .package_paths import add_psychopy_packages

# This also runs for `python -m psychopy_sync.launcher` and desktop_runner.
# Configuring only launch_experiment.py leaves both child processes unable to
# find packages installed through PsychoPy's plugin manager.
add_psychopy_packages()
