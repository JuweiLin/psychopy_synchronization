"""EyeLink connection, display configuration, and calibration lifecycle.

Continuous EDF recording is started after calibration and stopped at session end.
Keep normal tracker operations on the main thread. The optional calibration
helper preserves the existing script's automatic C key behavior.
"""

import threading
import re
from pathlib import Path

from .config import EyeLinkConfig


class DummyEyeLinkController:
    """Keep display/local event code usable without importing any EyeLink SDK."""

    def check_recording(self):
        pass

    def send_marker(self, message):
        pass

    def close(self):
        pass


class EyeLinkController:
    def __init__(self, config: EyeLinkConfig):
        self.config = config
        self._pylink = None
        self._tracker = None
        self._graphics = None
        self._graphics_open = False
        self._edf_name = None
        self._edf_open = False
        self._recording = False

    @property
    def tracker(self):
        if self._tracker is None:
            raise RuntimeError("EyeLink is not connected")
        return self._tracker

    def connect(self):
        if self._tracker is not None:
            raise RuntimeError("EyeLink is already connected")
        import pylink

        self._pylink = pylink
        self._tracker = pylink.EyeLink(self.config.ip)
        if not self._tracker.isConnected():
            self.close()
            raise ConnectionError(f"EyeLink did not connect to {self.config.ip}")
        print("Connected:", self.tracker.isConnected())
        print("Tracker version:", self.tracker.getTrackerVersion())

    def configure_display(self, win):
        w, h = (int(value) for value in win.size)
        self.tracker.sendCommand(f"screen_pixel_coords = 0 0 {w - 1} {h - 1}")
        self.tracker.sendMessage(f"DISPLAY_COORDS 0 0 {w - 1} {h - 1}")

    def configure_calibration(self, win):
        from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy

        tracker = self.tracker
        tracker.sendCommand(f"calibration_type = {self.config.calibration_type}")
        tracker.sendCommand("enable_automatic_calibration = YES")
        tracker.sendCommand(
            f"automatic_calibration_pacing = {self.config.automatic_pacing_ms}"
        )
        self._graphics = EyeLinkCoreGraphicsPsychoPy(tracker, win)
        self._graphics.setCalibrationColors((1, 1, 1), (-1, -1, -1))
        self._pylink.openGraphicsEx(self._graphics)
        self._graphics_open = True

    def calibrate(self):
        """Enter setup; returning means setup exited, not validation succeeded."""
        tracker = self.tracker
        if not self._graphics_open:
            raise RuntimeError("Configure calibration graphics before entering setup")
        tracker.setOfflineMode()
        cancel = threading.Event()
        worker = None
        if self.config.auto_start_calibration:
            worker = threading.Thread(
                target=self._send_calibration_key,
                args=(cancel,),
                name="eyelink-auto-calibration",
                daemon=True,
            )
            worker.start()
        try:
            tracker.doTrackerSetup()
        finally:
            # Do not allow a delayed key press after setup returns or connection closes.
            cancel.set()
            if worker is not None:
                worker.join()

    def _send_calibration_key(self, cancel):
        if cancel.wait(self.config.auto_calibration_delay_s):
            return
        try:
            self.tracker.sendKeybutton(ord("c"), 0, self._pylink.KB_PRESS)
            cancel.wait(0.05)
            try:
                self.tracker.sendKeybutton(ord("c"), 0, self._pylink.KB_RELEASE)
            except Exception:
                # Preserve compatibility with versions without key-release support.
                pass
        except Exception as exc:
            print(f"Automatic C key failed; start calibration on the Host: {exc}")

    def open_edf(self, filename):
        if self._edf_name is not None:
            raise RuntimeError("An EDF session has already been opened")
        if not re.fullmatch(r"[A-Z0-9_]{1,8}\.EDF", filename):
            raise ValueError("Host EDF requires a 1–8 character ASCII basename")
        self.tracker.setOfflineMode()
        result = self.tracker.openDataFile(filename)
        if result != 0:
            raise RuntimeError(f"Could not open EDF: {result}")
        self._edf_name, self._edf_open = filename, True
        # AREA stores pupil size; raw gaze, blinks, fixations and messages stay in EDF.
        self.tracker.sendCommand("file_sample_data = LEFT,RIGHT,GAZE,AREA,GAZERES,STATUS,INPUT")
        self.tracker.sendCommand("file_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT")
        self.tracker.sendCommand("file_event_data = GAZE,GAZERES,AREA,VELOCITY,STATUS")

    def start_recording(self):
        if not self._edf_open or self._recording:
            raise RuntimeError("Open an EDF and start recording exactly once")
        result = self.tracker.startRecording(1, 1, 0, 0)
        if result != 0:
            raise RuntimeError(f"EyeLink recording failed: {result}")
        self._recording = True
        self._pylink.pumpDelay(100)
        self.check_recording()

    def check_recording(self):
        if not self._recording or not self.tracker.isConnected():
            raise RuntimeError("EyeLink recording is unavailable")
        result = self.tracker.isRecording()
        if result != 0:
            raise RuntimeError(f"EyeLink recording was interrupted: {result}")

    def send_marker(self, message):
        if not self._edf_open:
            raise RuntimeError("Cannot write a marker before opening EDF")
        if not message.isascii() or len(message.encode("ascii")) > 130:
            raise ValueError("EyeLink markers must be ASCII and at most 130 bytes")
        result = self.tracker.sendMessage(message)
        if result not in (None, 0):
            raise RuntimeError(f"EyeLink marker rejected: {result}")

    def stop_recording(self):
        if self._recording:
            self._pylink.pumpDelay(100)
            self.tracker.stopRecording()
            self._recording = False

    def finish_session(self, destination):
        if self._edf_name is None:
            return False
        self.stop_recording()
        self.tracker.setOfflineMode()
        self._pylink.pumpDelay(500)
        if self._edf_open:
            result = self.tracker.closeDataFile()
            if result not in (None, 0):
                raise IOError(f"Could not close {self._edf_name} on Host: {result}")
            self._edf_open = False
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".partial.edf")
        error = None
        for attempt in range(3):
            try:
                # A fresh staging file prevents a stale partial download from
                # passing verification after a failed retry.
                partial.unlink(missing_ok=True)
                transferred = self.tracker.receiveDataFile(self._edf_name, str(partial))
                size = partial.stat().st_size if partial.exists() else 0
                if not isinstance(transferred, int) or transferred <= 0 or size != transferred:
                    raise IOError(f"transfer returned {transferred!r}; local file has {size} bytes")
                partial.replace(destination)
                return True
            except Exception as exc:
                error = exc
                if attempt < 2:
                    self._pylink.pumpDelay(500)
        raise IOError(f"EDF transfer failed; recover {self._edf_name} from the Host: {error}") from error

    def close(self):
        """Release graphics and the connection, including after setup errors."""
        tracker = self._tracker
        try:
            if tracker is not None:
                try:
                    try:
                        self.stop_recording()
                    finally:
                        tracker.setOfflineMode()
                finally:
                    tracker.close()
        finally:
            self._tracker = None
            if self._graphics_open:
                self._graphics_open = False
                self._pylink.closeGraphics()
            self._graphics = None
