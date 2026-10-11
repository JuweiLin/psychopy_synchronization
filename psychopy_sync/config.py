"""Internal defaults and validation; edit the project's root config.py."""

from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import runpy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_USER_SETTINGS = runpy.run_path(str(PROJECT_ROOT / "config.py"))


@dataclass(frozen=True)
class DisplayConfig:
    screen_index: int = 0
    width: int = 1920
    height: int = 1080
    fullscreen: bool = True
    # Preserve the original calibration check's measurement bypass.
    # This is an assumed value; it does NOT set the monitor refresh rate.
    # Use None to let PsychoPy measure it for an experiment.
    assumed_refresh_rate_hz: Optional[float] = 60.0

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Display dimensions must be positive")
        if self.assumed_refresh_rate_hz is not None and self.assumed_refresh_rate_hz <= 0:
            raise ValueError("Assumed refresh rate must be positive")


@dataclass(frozen=True)
class EyeLinkConfig:
    ip: str = _USER_SETTINGS["eyelink_ip"]
    calibration_type: str = "HV9"
    automatic_pacing_ms: int = 1000
    auto_start_calibration: bool = True
    auto_calibration_delay_s: float = 2.0

    def __post_init__(self):
        if self.auto_calibration_delay_s < 0:
            raise ValueError("Auto-calibration delay cannot be negative")
        if self.automatic_pacing_ms <= 0:
            raise ValueError("Calibration pacing must be positive")


@dataclass(frozen=True)
class ExperimentConfig:
    dummy_mode: bool = False  # Selected in the login window for each session.
    assets_dir: Path = PROJECT_ROOT / "assets"
    articles_folder: str = "articles"  # Scan assets/articles/<article_id>.csv
    tts_folder: str = "TTS"  # assets/TTS/<participant_id>/<session_id>/
    tts_server_url: Optional[str] = _USER_SETTINGS["tts_server_url"] or None
    output_dir: Path = PROJECT_ROOT / "data"
    condition1_count: int = _USER_SETTINGS["condition1_count"]
    condition2_count: int = _USER_SETTINGS["condition2_count"]
    random_seed: Optional[int] = None  # None: a new seed per session; saved in session.json
    count_mode: str = "words"  # words: whitespace tokens; hanzi: Han characters only
    advance_key: str = "space"
    quit_key: str = "escape"
    font: str = "Arial"
    text_height_px: int = 28
    text_width_fraction: float = 0.8
    text_height_fraction: float = 0.7
    article_baseline_s: float = 1.5

    def __post_init__(self):
        if type(self.dummy_mode) is not bool:
            raise ValueError("dummy_mode must be True or False")
        if type(self.condition1_count) is not int or self.condition1_count < 1:
            raise ValueError("condition1_count must be a positive integer")
        if type(self.condition2_count) is not int or self.condition2_count < 0:
            raise ValueError("condition2_count must be a nonnegative integer")
        if self.count_mode not in ("words", "hanzi"):
            raise ValueError("count_mode must be words or hanzi")
        if self.random_seed is not None and (type(self.random_seed) is not int or self.random_seed < 0):
            raise ValueError("random_seed must be None or a nonnegative integer")
        if not self.advance_key or not self.quit_key or self.advance_key == self.quit_key:
            raise ValueError("Advance and quit keys must be distinct")
        if self.text_height_px <= 0 or not 0 < self.text_width_fraction < 1 or not 0 < self.text_height_fraction < 1:
            raise ValueError("Invalid text layout")
        if self.article_baseline_s != 1.5:
            raise ValueError("Article baseline duration must be 1.5 seconds")
