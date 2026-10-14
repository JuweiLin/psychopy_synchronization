"""PsychoPy window creation and the calibration check's display target.

Call these functions on the PsychoPy main thread.
"""

from .config import DisplayConfig


def create_window(config: DisplayConfig, *, allow_gui=None):
    from psychopy import visual

    options = {} if allow_gui is None else {"allowGUI": allow_gui}
    win = visual.Window(
        size=(config.width, config.height),
        screen=config.screen_index,
        fullscr=config.fullscreen,
        units="pix",
        color="black",
        waitBlanking=True,
        **options,
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


def preload_article_audio(cached_audio, allow_demo=False, speaker=None):
    """Load a verified local file on the main thread before releasing its article.

    Use PTB explicitly so the stimulus can be scheduled against a display flip.
    Demo silence is allowed only when the caller explicitly selects dummy mode.
    """
    from shared.contracts import sha256_file

    if cached_audio.metadata.get("generation", {}).get("demo_only") and not allow_demo:
        raise ValueError("Demo silence cannot be used as an experimental stimulus")
    if sha256_file(cached_audio.path) != cached_audio.metadata["audio_sha256"]:
        raise ValueError("Cached audio changed after download")
    from psychopy.sound.backend_ptb import SoundPTB

    options = dict(preBuffer=-1, autoLog=False)
    if speaker is not None:
        options["speaker"] = speaker
    return SoundPTB(str(cached_audio.path), **options)
