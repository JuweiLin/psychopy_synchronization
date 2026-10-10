"""Participant ID login and session results in a native desktop window."""

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from .config import ExperimentConfig, PROJECT_ROOT
from .event_log import validate_participant_id
from .launcher_bootstrap import required_modules


def experiment_command(participant_id, result_path):
    validate_participant_id(participant_id)
    return [sys.executable, "-m", "psychopy_sync.desktop_runner", "--participant-id",
            participant_id, "--result-file", str(result_path)]


def result_message(result):
    if result.get("status") == "completed":
        summary = result["summary"]
        text = f"Reading speed: {summary['speed_per_minute']:.2f} {summary['speed_unit']}\nData saved to: {result['directory']}"
        if result.get("dummy_mode"):
            text += "\nDummy mode: no eye tracking was recorded."
        if result.get("tts_status") == "not_configured":
            text += "\nTTS server not configured. Sentence index and requests saved."
        elif result.get("tts_status") == "cached":
            text += "\nCondition 2 sentence audio saved."
        return "Session complete", text
    if result.get("status") == "aborted":
        return "Session stopped", "Available session data has been saved."
    return "Session failed", result.get("error") or "The experiment process exited unexpectedly."


def main():
    import wx

    class LoginFrame(wx.Frame):
        def __init__(self):
            super().__init__(None, title="Reading Experiment", size=(540, 500),
                             style=wx.DEFAULT_FRAME_STYLE & ~wx.RESIZE_BORDER & ~wx.MAXIMIZE_BOX)
            self.process = self.temporary = self.log_stream = None
            self.config = ExperimentConfig()
            self.log_path = None
            self.timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.poll, self.timer)
            self.Bind(wx.EVT_CLOSE, self.close)
            panel = wx.Panel(self)
            panel.SetBackgroundColour("#F5F6F8")
            layout = wx.BoxSizer(wx.VERTICAL)

            def label(text, size, colour):
                control = wx.StaticText(panel, label=text)
                control.SetFont(wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
                control.SetForegroundColour(colour)
                return control

            layout.Add(label("Reading Experiment", 24, "#17253C"), 0, wx.LEFT | wx.TOP, 32)
            layout.AddSpacer(28)
            layout.Add(label("Participant ID", 13, "#40516A"), 0, wx.LEFT, 32)
            self.participant = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER, size=(-1, 42))
            self.participant.SetFont(wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            self.participant.SetHint("S001")
            layout.AddSpacer(10)
            layout.Add(self.participant, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 32)
            layout.AddSpacer(10)
            layout.Add(label("1–32 letters, numbers, _ or -", 11, "#63708A"), 0, wx.LEFT, 32)
            self.error = label("", 11, "#B42318")
            layout.AddSpacer(10)
            layout.Add(self.error, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 32)
            self.start_button = wx.Button(panel, label="Start Experiment", size=(-1, 40))
            self.start_button.SetDefault()
            self.start_button.Bind(wx.EVT_BUTTON, self.start)
            self.participant.Bind(wx.EVT_TEXT_ENTER, self.start)
            self.participant.Bind(wx.EVT_TEXT, lambda event: self.error.SetLabel(""))
            layout.AddSpacer(12)
            layout.Add(self.start_button, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 32)
            self.status_title = label("Dummy mode — no eye tracking" if self.config.dummy_mode else "", 12, "#40516A")
            self.status = label("", 11, "#63708A")
            layout.AddSpacer(16)
            layout.Add(self.status_title, 0, wx.LEFT | wx.RIGHT, 32)
            layout.AddSpacer(8)
            layout.Add(self.status, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 32)
            panel.SetSizer(layout)
            self.Centre()
            self.participant.SetFocus()

        def start(self, event):
            if self.process is not None:
                return
            participant_id = self.participant.GetValue().strip()
            try:
                validate_participant_id(participant_id)
            except ValueError:
                self.error.SetLabel("Enter 1–32 letters, numbers, underscores or hyphens.")
                self.participant.SetFocus()
                return
            missing = [name for name in required_modules(self.config) if importlib.util.find_spec(name) is None]
            if missing:
                self.error.SetLabel("Missing components: " + ", ".join(missing))
                self.error.Wrap(476)
                self.status_title.SetLabel("Setup required")
                self.status.SetLabel("Install the missing PsychoPy / EyeLink components, then try again.")
                self.Layout()
                return
            try:
                self.temporary = tempfile.TemporaryDirectory(prefix="reading-experiment-")
                self.result_path = Path(self.temporary.name) / "result.json"
                logs = self.config.output_dir / "launcher_logs"
                logs.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
                self.log_path = logs / f"{stamp}.log"
                self.log_stream = self.log_path.open("w", encoding="utf-8")
                self.process = subprocess.Popen(experiment_command(participant_id, self.result_path),
                                                cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                                                stdout=self.log_stream, stderr=subprocess.STDOUT)
            except Exception as exc:
                self.release()
                self.error.SetLabel("Could not start the experiment: " + str(exc))
                self.error.Wrap(476)
                self.Layout()
                return
            self.participant.SetValue(participant_id)
            self.start_button.Disable()
            self.participant.Disable()
            self.status_title.SetLabel("Session in progress")
            self.status.SetLabel("Continue in the experiment window. Press Escape to stop.")
            self.timer.Start(250)
            self.Hide()

        def poll(self, event):
            code = self.process.poll()
            if code is None:
                return
            self.timer.Stop()
            try:
                result = json.loads(self.result_path.read_text(encoding="utf-8"))
                if code != 0 and result.get("status") == "completed":
                    result = dict(status="failed", error="The experiment process exited unexpectedly.")
                title, message = result_message(result)
            except (OSError, ValueError, KeyError, TypeError):
                title, message = "Session failed", "The experiment process exited unexpectedly."
            if title == "Session failed":
                message += f"\nDiagnostic log: {self.log_path}"
            self.release()
            self.status_title.SetLabel(title)
            self.status.SetLabel(message)
            self.status.Wrap(476)
            self.start_button.SetLabel("Start New Session")
            self.start_button.Enable()
            self.participant.Enable()
            self.SetClientSize((540, 500))
            self.Layout()
            self.Show()
            self.Raise()
            self.participant.SetFocus()

        def release(self):
            self.process = None
            if self.log_stream is not None:
                self.log_stream.close()
                self.log_stream = None
            if self.temporary is not None:
                self.temporary.cleanup()
                self.temporary = None

        def close(self, event):
            if self.process is not None:
                wx.MessageBox("Please press Escape in the experiment window to stop the session.", "Session in progress", wx.OK | wx.ICON_INFORMATION, self)
                event.Veto()
                return
            self.release()
            self.Destroy()

    app = wx.App(False)
    app.SetAppName("Reading Experiment")
    frame = LoginFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
