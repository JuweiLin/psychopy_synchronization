"""Exercise login callbacks without starting a native GUI or experiment."""

from collections import deque
import types
import unittest
from unittest.mock import MagicMock, patch

from psychopy_sync.launcher import main
from psychopy_sync.server_check import ServerCheck


class LoginGpuChecks(unittest.TestCase):
    def create_frame(self, results):
        frames, callbacks = [], deque()

        class Frame:
            def __init__(self, *args, **kwargs):
                frames.append(self)

            def __getattr__(self, name):
                method = MagicMock()
                setattr(self, name, method)
                return method

        wx = types.ModuleType("wx")
        wx.Frame = Frame
        for name in ("App", "Panel", "BoxSizer", "StaticText", "TextCtrl", "Font", "Button", "Timer", "CallLater"):
            setattr(wx, name, MagicMock(side_effect=lambda *args, **kwargs: MagicMock()))
        for name in ("DEFAULT_FRAME_STYLE", "RESIZE_BORDER", "MAXIMIZE_BOX", "EVT_TIMER", "EVT_CLOSE",
                     "VERTICAL", "HORIZONTAL", "FONTFAMILY_DEFAULT", "FONTSTYLE_NORMAL", "FONTWEIGHT_NORMAL",
                     "LEFT", "TOP", "RIGHT", "BOTTOM", "EXPAND", "TE_PROCESS_ENTER", "EVT_BUTTON", "EVT_TEXT_ENTER",
                     "EVT_TEXT", "ALIGN_CENTER_VERTICAL"):
            setattr(wx, name, 0)
        wx.CallAfter = lambda function, *args: callbacks.append((function, args))
        patches = [patch.dict("sys.modules", {"wx": wx}),
                   patch("psychopy_sync.launcher.threading.Thread", side_effect=
                         lambda target, **kwargs: types.SimpleNamespace(start=target)),
                   patch("psychopy_sync.launcher.importlib.util.find_spec", return_value=object()),
                   patch("psychopy_sync.launcher.check_gpu_server", side_effect=results)]
        mocks = []
        for item in patches:
            mocks.append(item.start())
            self.addCleanup(item.stop)
        main()
        frame = frames[0]
        frame.participant.GetValue.return_value = "S001"

        def dispatch():
            function, args = callbacks.popleft()
            function(*args)

        return frame, dispatch, mocks[-1]

    def test_opening_login_checks_server_and_recheck_can_recover(self):
        failed = ServerCheck("unavailable", "Cannot reach GPU server.", False)
        ready = ServerCheck("ready", "GPU server ready.", True)
        frame, dispatch, check = self.create_frame([failed, ready])
        dispatch()  # Launch check runs in the worker; result is posted to the GUI.
        self.assertTrue(frame.server_check_in_progress)
        dispatch()
        frame.start_button.Enable.assert_called_with(False)
        self.assertEqual(frame.gpu_status.SetLabel.call_args.args, (failed.message,))
        frame.check_server()
        dispatch()
        frame.start_button.Enable.assert_called_with(True)
        self.assertEqual(check.call_count, 2)

    def test_server_disappearing_after_initial_check_prevents_session_launch(self):
        frame, dispatch, check = self.create_frame([
            ServerCheck("ready", "Ready", True), ServerCheck("unavailable", "Offline", False)])
        dispatch()
        dispatch()
        frame.launch_session = MagicMock()
        frame.start(None)
        frame.launch_session.assert_not_called()
        dispatch()
        frame.launch_session.assert_not_called()
        frame.start_button.Enable.assert_called_with(False)
        self.assertEqual(check.call_count, 2)

    def test_ready_recheck_launches_once_after_callback_and_closed_form_ignores_results(self):
        ready = ServerCheck("ready", "Ready", True)
        frame, dispatch, _ = self.create_frame([ready, ready, ready])
        dispatch()
        dispatch()
        frame.launch_session = MagicMock()
        frame.start(None)
        frame.launch_session.assert_not_called()
        dispatch()
        frame.launch_session.assert_called_once_with("S001")
        frame.check_server("S001")
        frame.close(None)
        dispatch()
        frame.launch_session.assert_called_once_with("S001")


if __name__ == "__main__":
    unittest.main()
