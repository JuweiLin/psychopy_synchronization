"""Desktop launch, runtime selection and experiment outcomes without hardware."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from psychopy_sync.condition1 import ExperimentAborted
from psychopy_sync.config import ExperimentConfig
from psychopy_sync.desktop_runner import execute
from psychopy_sync.event_log import validate_participant_id
from psychopy_sync.launcher import experiment_command, result_message
from psychopy_sync.launcher_bootstrap import Runtime, find_runtime, main, required_modules, windows_python_candidates


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.result_path = self.root / "result.json"

    def test_login_accepts_only_safe_participant_ids_and_builds_argument_list(self):
        self.assertEqual(validate_participant_id("S001-a_b"), "S001-a_b")
        command = experiment_command("S001", self.result_path)
        self.assertEqual(command[1:5], ["-m", "psychopy_sync.desktop_runner", "--participant-id", "S001"])
        self.assertEqual(command[5:], ["--result-file", str(self.result_path)])
        self.assertNotIn("--name", command)
        for participant_id in ("", " ", "../S001", "user name", "用户", "A" * 33, None):
            with self.subTest(participant_id=participant_id), self.assertRaises(ValueError):
                experiment_command(participant_id, self.result_path)

    def test_desktop_result_contains_reading_speed_and_session_directory(self):
        directory = self.root / "data" / "S001" / "session"
        directory.mkdir(parents=True)
        (directory / "session.json").write_text(json.dumps({"tts_status": "not_configured"}))
        summary = {"speed_per_minute": 240, "speed_unit": "words/min"}
        runner = Mock(return_value=(summary, directory))
        self.assertEqual(execute("S001", self.result_path, runner), 0)
        runner.assert_called_once_with("S001")
        result = json.loads(self.result_path.read_text())
        title, message = result_message(result)
        self.assertEqual(title, "Session complete")
        self.assertIn("240.00 words/min", message)
        self.assertIn(str(directory), message)
        self.assertIn("TTS server not configured", message)
        self.assertFalse(self.result_path.with_suffix(".json.tmp").exists())

    def test_escape_returns_an_aborted_outcome(self):
        runner = Mock(side_effect=ExperimentAborted("Escape pressed"))
        self.assertEqual(execute("S001", self.result_path, runner), 130)
        result = json.loads(self.result_path.read_text())
        self.assertEqual(result_message(result)[0], "Session stopped")

    def test_edf_download_success_is_visible_in_the_results(self):
        title, message = result_message(dict(status="completed", directory="data/S001/run",
            summary=dict(speed_per_minute=120, speed_unit="words/min"), edf_status="downloaded",
            edf_path="data/S001/run/eyelink.edf", edf_bytes=1234, screenshots_status="saved"))
        self.assertEqual(title, "Session complete")
        self.assertIn("EDF saved: data/S001/run/eyelink.edf (1,234 bytes)", message)
        self.assertIn("Data Viewer image links saved", message)

    def test_abort_retains_edf_recovery_name_and_directory_in_results(self):
        error = ExperimentAborted("Escape pressed")
        error.session_result = dict(directory="data/S001/run", edf_status="recovery_required", host_edf_name="ABC123.EDF")
        self.assertEqual(execute("S001", self.result_path, Mock(side_effect=error)), 130)
        result = json.loads(self.result_path.read_text())
        title, message = result_message(result)
        self.assertEqual(title, "Session stopped")
        self.assertIn("data/S001/run", message)
        self.assertIn("Recover ABC123.EDF", message)

    def test_failure_returns_an_error_instead_of_success(self):
        runner = Mock(side_effect=ConnectionError("EyeLink unavailable"))
        with patch("psychopy_sync.desktop_runner.traceback.print_exc"):
            self.assertEqual(execute("S001", self.result_path, runner), 1)
        result = json.loads(self.result_path.read_text())
        self.assertEqual(result_message(result), ("Session failed", "EyeLink unavailable"))

    def test_invalid_id_never_starts_the_experiment(self):
        runner = Mock()
        with patch("psychopy_sync.desktop_runner.traceback.print_exc"):
            self.assertEqual(execute("../S001", self.result_path, runner), 1)
        runner.assert_not_called()

    def test_runtime_selection_prefers_all_experiment_dependencies(self):
        first = Runtime(Path("/first/python"), {"runtime": "first"})
        second = Runtime(Path("/second/python"), {"runtime": "second"})
        partial = {"psychopy": True, "wx": True, "pylink": False, "EyeLinkCoreGraphicsPsychoPy": False}
        complete = {name: True for name in partial}
        with patch("psychopy_sync.launcher_bootstrap.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, json.dumps(partial)),
            subprocess.CompletedProcess([], 0, json.dumps(complete)),
        ]) as run:
            self.assertIs(find_runtime([first, second], config=ExperimentConfig(dummy_mode=False, tts_server_url=None)), second)
        self.assertEqual(run.call_args.kwargs["env"], second.environment)

    def test_runtime_selection_can_show_login_with_missing_eyelink_dependencies(self):
        runtime = Runtime(Path("/python"), {})
        partial = {"psychopy": True, "wx": True, "pylink": False, "EyeLinkCoreGraphicsPsychoPy": False}
        with patch("psychopy_sync.launcher_bootstrap.subprocess.run", side_effect=[
            OSError("missing"), subprocess.CompletedProcess([], 0, json.dumps(partial)),
        ]):
            self.assertIs(find_runtime([Runtime(Path("/missing"), {}), runtime],
                                       config=ExperimentConfig(dummy_mode=False)), runtime)

    def test_dummy_runtime_and_preflight_do_not_probe_eyelink_packages(self):
        config = ExperimentConfig(dummy_mode=True, tts_server_url=None)
        self.assertEqual(required_modules(config), ("psychopy", "wx"))
        self.assertEqual(required_modules(ExperimentConfig(dummy_mode=False, tts_server_url=None)),
                         ("psychopy", "wx", "pylink", "EyeLinkCoreGraphicsPsychoPy"))
        runtime = Runtime(Path("/python"), {})
        with patch("psychopy_sync.launcher_bootstrap.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, json.dumps({"psychopy": True, "wx": True}))) as run:
            self.assertIs(find_runtime([runtime], config=config), runtime)
        self.assertNotIn("pylink", run.call_args.args[0][2])
        self.assertNotIn("EyeLinkCoreGraphicsPsychoPy", run.call_args.args[0][2])

    def test_condition2_preflight_requires_ptb_audio_even_in_dummy_mode(self):
        for dummy in (True, False):
            config = ExperimentConfig(dummy_mode=dummy, condition2_count=1, tts_server_url="http://127.0.0.1:8765")
            self.assertIn("psychtoolbox", required_modules(config))
            self.assertIn("soundfile", required_modules(config))
        self.assertNotIn("psychtoolbox", required_modules(
            ExperimentConfig(dummy_mode=True, condition2_count=0, tts_server_url="http://127.0.0.1:8765")))

    def test_dummy_result_identifies_the_session_as_untracked(self):
        title, message = result_message(dict(status="completed", dummy_mode=True,
            summary=dict(speed_per_minute=120, speed_unit="words/min"), directory="data/dummy/S001/run"))
        self.assertEqual(title, "Session complete")
        self.assertIn("no eye tracking was recorded", message)

    def test_runtime_without_native_login_support_is_not_selected(self):
        with patch("psychopy_sync.launcher_bootstrap.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, json.dumps({"psychopy": True, "wx": False}))):
            self.assertIsNone(find_runtime([Runtime(Path("/python"), {})]))

    def test_windows_launch_preserves_program_files_path_and_child_exit_code(self):
        runtime = Runtime(Path("C:/Program Files/PsychoPy/pythonw.exe"), {"runtime": "standalone"})
        with patch("psychopy_sync.launcher_bootstrap.sys.platform", "win32"), \
             patch("psychopy_sync.launcher_bootstrap.find_runtime", return_value=runtime), \
             patch("psychopy_sync.launcher_bootstrap.os.execve") as execve, \
             patch("psychopy_sync.launcher_bootstrap.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 7)) as run:
            with self.assertRaises(SystemExit) as outcome:
                main()
        self.assertEqual(outcome.exception.code, 7)
        self.assertEqual(run.call_args.args[0],
                         [str(runtime.executable), "-m", "psychopy_sync.launcher"])
        self.assertEqual(run.call_args.kwargs["env"], runtime.environment)
        self.assertEqual(run.call_args.kwargs["cwd"], Path(__file__).resolve().parent.parent)
        execve.assert_not_called()

    def test_windows_discovery_handles_spaces_per_user_installs_and_missing_roots(self):
        system = self.root / "Program Files"
        local = self.root / "Local AppData"
        standalone = system / "PsychoPy 2026"
        per_user = local / "Programs" / "psychopy"
        standalone.mkdir(parents=True)
        per_user.mkdir(parents=True)
        (system / "Other Application").mkdir()
        candidates = list(windows_python_candidates({
            "ProgramFiles": str(system), "ProgramFiles(x86)": str(self.root / "Missing"),
            "LOCALAPPDATA": str(local),
        }))
        self.assertEqual(candidates, [standalone / "python.exe", standalone / "python" / "python.exe",
                                      per_user / "python.exe", per_user / "python" / "python.exe"])


if __name__ == "__main__":
    unittest.main()
