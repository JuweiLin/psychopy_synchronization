"""Orchestrate the existing connection/display/calibration check."""

from .config import DisplayConfig, EyeLinkConfig
from .display import create_window, show_test_target
from .eyelink import EyeLinkController


def run_connection_check(display_config=None, eyelink_config=None):
    display_config = display_config if display_config is not None else DisplayConfig()
    eyelink_config = eyelink_config if eyelink_config is not None else EyeLinkConfig()
    controller = EyeLinkController(eyelink_config)
    win = None
    try:
        print("Connecting to EyeLink...")
        controller.connect()
        print("Creating PsychoPy window...")
        win = create_window(display_config)
        print("Actual PsychoPy window size:", *win.size)
        show_test_target(win)
        controller.configure_display(win)
        controller.configure_calibration(win)
        print("Entering EyeLink setup...")
        controller.calibrate()
        print("EyeLink setup returned; check calibration/validation on the Host.")
    finally:
        try:
            controller.close()
        finally:
            if win is not None:
                win.close()
    print("EyeLink disconnected. Test complete.")


def main():
    from psychopy import core

    run_connection_check()
    core.quit()


if __name__ == "__main__":
    main()
