"""PsychoPy window creation and the calibration check's display target.

Call these functions on the PsychoPy main thread.
"""

from .config import DisplayConfig


def create_window(config: DisplayConfig):
    from psychopy import visual

    win = visual.Window(
        size=(config.width, config.height),
        screen=config.screen_index,
        fullscr=config.fullscreen,
        units="pix",
        color="black",
        waitBlanking=True,
    )
    if config.assumed_refresh_rate_hz is not None:
        rate = config.assumed_refresh_rate_hz
        print(f"Using assumed refresh rate {rate} Hz (measurement bypass only)")
        win.getActualFrameRate = lambda *args, **kwargs: rate
        win.monitorFramePeriod = 1.0 / rate
    return win


def show_test_target(win, duration_s: float = 2.0):
    from psychopy import core, visual

    outer = visual.Circle(
        win=win, radius=12, pos=(0, 0), fillColor="white", lineColor="white"
    )
    inner = visual.Circle(
        win=win, radius=4, pos=(0, 0), fillColor="black", lineColor="black"
    )
    outer.draw()
    inner.draw()
    win.flip()
    core.wait(duration_s)
    win.flip()


def preload_article_audio(cached_audio):
    """Load a verified local file on the main thread before releasing its article.

    Configure the PsychoPy audio backend before importing psychopy.sound.
    Returns a Sound; the experiment still controls the scheduled play time.
    """
    from shared.contracts import sha256_file

    if cached_audio.metadata.get("generation", {}).get("demo_only"):
        raise ValueError("Demo silence cannot be used as an experimental stimulus")
    if sha256_file(cached_audio.path) != cached_audio.metadata["audio_sha256"]:
        raise ValueError("Cached audio changed after download")
    from psychopy import sound

    return sound.Sound(str(cached_audio.path), preBuffer=-1)
