"""Lifecycle checks without an installed PsychoPy/PyLink or connected tracker."""

import threading
import types
import unittest
from unittest.mock import MagicMock, patch

from psychopy_sync.calibration_check import run_connection_check
from psychopy_sync.config import DisplayConfig, EyeLinkConfig
from psychopy_sync.display import create_window
from psychopy_sync.eyelink import EyeLinkController


class CalibrationCheckTests(unittest.TestCase):
    def setUp(self):
        self.tracker = MagicMock()
        self.tracker.isConnected.return_value = True
        self.tracker.getTrackerVersion.return_value = 3
        self.win = MagicMock()
        self.win.size = (2560, 1440)
        self.pylink = types.SimpleNamespace(
            EyeLink=MagicMock(return_value=self.tracker),
            openGraphicsEx=MagicMock(),
            closeGraphics=MagicMock(),
            KB_PRESS=1,
            KB_RELEASE=0,
        )
        self.graphics_class = MagicMock()
        self.graphics_module = types.SimpleNamespace(
            EyeLinkCoreGraphicsPsychoPy=self.graphics_class
        )
        modules = {
            "pylink": self.pylink,
            "EyeLinkCoreGraphicsPsychoPy": self.graphics_module,
        }
        self.hardware_patch = patch.dict("sys.modules", modules)
        self.hardware_patch.start()
        self.addCleanup(self.hardware_patch.stop)
        self.window_patch = patch(
            "psychopy_sync.calibration_check.create_window", return_value=self.win
        )
        self.window_patch.start()
        self.addCleanup(self.window_patch.stop)
        self.target_patch = patch("psychopy_sync.calibration_check.show_test_target")
        self.target_patch.start()
        self.addCleanup(self.target_patch.stop)

    def test_normal_run_uses_actual_window_coordinates_and_closes_resources(self):
        run_connection_check(eyelink_config=EyeLinkConfig(auto_start_calibration=False))

        self.pylink.EyeLink.assert_called_once_with("100.1.1.1")
        self.tracker.sendCommand.assert_any_call("screen_pixel_coords = 0 0 2559 1439")
        self.tracker.sendCommand.assert_any_call("calibration_type = HV9")
        self.tracker.sendCommand.assert_any_call("enable_automatic_calibration = YES")
        self.tracker.sendCommand.assert_any_call("automatic_calibration_pacing = 1000")
        self.tracker.sendMessage.assert_called_once_with("DISPLAY_COORDS 0 0 2559 1439")
        self.tracker.doTrackerSetup.assert_called_once_with()
        self.tracker.close.assert_called_once_with()
        self.pylink.closeGraphics.assert_called_once_with()
        self.win.close.assert_called_once_with()

    def test_setup_exception_still_closes_window_graphics_and_tracker(self):
        self.tracker.doTrackerSetup.side_effect = RuntimeError("setup failed")
        with self.assertRaisesRegex(RuntimeError, "setup failed"):
            run_connection_check(eyelink_config=EyeLinkConfig(auto_start_calibration=False))
        self.tracker.close.assert_called_once_with()
        self.pylink.closeGraphics.assert_called_once_with()
        self.win.close.assert_called_once_with()

    def test_window_creation_exception_still_closes_tracker(self):
        with patch(
            "psychopy_sync.calibration_check.create_window",
            side_effect=RuntimeError("window failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "window failed"):
                run_connection_check()
        self.tracker.close.assert_called_once_with()
        self.pylink.openGraphicsEx.assert_not_called()

    def test_tracker_close_exception_still_closes_graphics_and_window(self):
        self.tracker.close.side_effect = RuntimeError("close failed")
        with self.assertRaisesRegex(RuntimeError, "close failed"):
            run_connection_check(eyelink_config=EyeLinkConfig(auto_start_calibration=False))
        self.pylink.closeGraphics.assert_called_once_with()
        self.win.close.assert_called_once_with()

    def test_early_setup_exit_cancels_delayed_keypress(self):
        # The long delay must be cancelled, not slept through, when setup returns.
        run_connection_check(eyelink_config=EyeLinkConfig(auto_calibration_delay_s=60.0))
        self.tracker.sendKeybutton.assert_not_called()
        self.assertFalse(
            any(t.name == "eyelink-auto-calibration" for t in threading.enumerate())
        )

    def test_auto_calibration_sends_press_and_release(self):
        pressed = threading.Event()
        self.tracker.sendKeybutton.side_effect = lambda *args: pressed.set()

        def wait_for_key():
            if not pressed.wait(timeout=1.0):
                raise RuntimeError("Automatic calibration key was not sent")

        self.tracker.doTrackerSetup.side_effect = wait_for_key
        run_connection_check(eyelink_config=EyeLinkConfig(auto_calibration_delay_s=0))
        self.assertEqual(
            [call.args for call in self.tracker.sendKeybutton.call_args_list],
            [(ord("c"), 0, 1), (ord("c"), 0, 0)],
        )

    def test_failed_connection_is_rejected_and_closed(self):
        self.tracker.isConnected.return_value = False
        with self.assertRaises(ConnectionError):
            run_connection_check()
        self.tracker.close.assert_called_once_with()
        self.tracker.doTrackerSetup.assert_not_called()

    def test_close_is_idempotent(self):
        controller = EyeLinkController(EyeLinkConfig())
        controller.connect()
        controller.configure_calibration(self.win)
        controller.close()
        controller.close()
        self.tracker.close.assert_called_once_with()
        self.pylink.closeGraphics.assert_called_once_with()

    def test_real_measurement_mode_does_not_override_window_refresh_methods(self):
        measurement = self.win.getActualFrameRate
        psychopy = types.SimpleNamespace(
            visual=types.SimpleNamespace(Window=MagicMock(return_value=self.win))
        )
        with patch.dict("sys.modules", {"psychopy": psychopy}):
            win = create_window(DisplayConfig(assumed_refresh_rate_hz=None))
        self.assertIs(win.getActualFrameRate, measurement)


if __name__ == "__main__":
    unittest.main()
