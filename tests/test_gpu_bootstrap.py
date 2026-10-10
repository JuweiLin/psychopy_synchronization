"""GPU installation orchestration without installing packages or using a GPU."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gpu_service import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gpu setup ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        replacement = patch.object(bootstrap.sys, "platform", "linux")
        replacement.start()
        self.addCleanup(replacement.stop)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_driver_selection_including_boundaries_and_multiple_gpus(self):
        for driver, expected in (("580.95.05", "cu128"), ("570.26", "cu128"),
                                 ("570.25", "cu126"), ("560.28.03", "cu126"),
                                 ("560.28.02", "cu118"), ("535.104.05", "cu118"),
                                 ("520.61.05", "cu118"), ("580.95.05\n535.104.05\n", "cu118")):
            with self.subTest(driver=driver):
                self.assertEqual(bootstrap.torch_backend(driver), expected)
        for driver in ("", "519.99", "N/A", "580.95.05\ninvalid"):
            with self.subTest(driver=driver), self.assertRaises(ValueError):
                bootstrap.torch_backend(driver)

    def run_setup(self, runner):
        with patch.object(bootstrap.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(bootstrap, "ensure_ffmpeg"), \
             patch.object(bootstrap.subprocess, "run", side_effect=runner):
            return bootstrap.prepare_environment("/path with spaces/uv", "cuda:0", self.root)

    def test_new_environment_installs_into_its_own_python_before_gpu_probe(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="580.95.05\n")

        python = self.run_setup(runner)
        self.assertEqual(python, self.root / ".venv-gpu" / "bin" / "python")
        self.assertEqual([command[1] for command in calls[1:3]], ["venv", "pip"])
        install = calls[2]
        self.assertEqual(install[install.index("--python") + 1], str(python))
        self.assertEqual(install[install.index("--torch-backend") + 1], "cu128")
        self.assertEqual(install[install.index("--requirements") + 1], str(self.root / "gpu_service" / "requirements.txt"))
        self.assertEqual(calls[-1], [str(python), "-c", bootstrap.GPU_PROBE, "cuda:0"])

    def test_existing_environment_is_reused_but_dependencies_and_cuda_are_checked(self):
        python = self.root / ".venv-gpu" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.touch()
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="550.54.14")

        self.run_setup(runner)
        self.assertFalse(any("venv" in command for command in calls))
        self.assertTrue(any("--requirements" in command for command in calls))
        self.assertEqual(calls[-1][-1], "cuda:0")

    def test_install_failure_does_not_continue_to_gpu_probe(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if "install" in command:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout="580.95.05")

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_setup(runner)
        self.assertFalse(any(bootstrap.GPU_PROBE in command for command in calls))

    def test_incomplete_environment_is_retained_and_reported(self):
        environment = self.root / ".venv-gpu"
        environment.mkdir()
        sentinel = environment / "keep.txt"
        sentinel.write_text("Do not erase")
        with self.assertRaisesRegex(ValueError, "Incomplete environment"):
            self.run_setup(lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="580.95.05"))
        self.assertEqual(sentinel.read_text(), "Do not erase")

    def test_missing_driver_stops_before_ffmpeg_or_package_installation(self):
        with patch.object(bootstrap.shutil, "which", return_value=None), \
             patch.object(bootstrap.subprocess, "run") as run, \
             patch.object(bootstrap, "ensure_ffmpeg") as ffmpeg:
            with self.assertRaisesRegex(ValueError, "nvidia-smi"):
                bootstrap.prepare_environment("uv", "cuda", self.root)
        run.assert_not_called()
        ffmpeg.assert_not_called()

    def test_ffmpeg_installs_only_when_missing_and_checks_the_result(self):
        available = {"apt-get", "sudo"}

        def install(command, **kwargs):
            if "install" in command:
                available.update(("ffmpeg", "ffprobe"))

        with patch.object(bootstrap.shutil, "which", side_effect=lambda name: name if name in available else None), \
             patch.object(bootstrap.os, "geteuid", return_value=1000), \
             patch.object(bootstrap.subprocess, "run", side_effect=install) as run:
            bootstrap.ensure_ffmpeg()
            self.assertEqual(run.call_args_list[-1].args[0], ["sudo", "apt-get", "install", "-y", "ffmpeg"])
            run.reset_mock()
            bootstrap.ensure_ffmpeg()
            run.assert_not_called()

    def config(self, demo):
        config = self.root / "gpu config.py"
        config.write_text('host="127.0.0.1"\nport=8765\ndevice="cuda"\n'
                          'ref_audio="missing.wav"\nref_text_file="missing.txt"\n'
                          f'demo_mode={demo}\n')
        return str(config)

    def test_configured_demo_skips_installation_and_gpu_checks(self):
        config = self.config(True)
        with patch.object(bootstrap, "prepare_environment") as prepare, patch.object(bootstrap, "launch") as launch:
            bootstrap.main(["--uv", "uv", "--config", config])
        prepare.assert_not_called()
        launch.assert_called_once_with(["--config", config, "--demo"])

    def test_missing_reference_stops_before_installation(self):
        config = self.config(False)
        with patch.object(bootstrap, "prepare_environment") as prepare, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                bootstrap.main(["--uv", "uv", "--config", config])
        self.assertEqual(error.exception.code, 2)
        prepare.assert_not_called()

    def test_failed_gpu_probe_prevents_launch(self):
        with patch.object(bootstrap, "server_arguments", return_value=["--device", "cuda"]), \
             patch.object(bootstrap, "prepare_environment", side_effect=subprocess.CalledProcessError(1, ["python", "-c", "probe"])), \
             patch.object(bootstrap.os, "execv") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                bootstrap.main(["--uv", "uv"])
        execute.assert_not_called()

    def test_success_launches_service_with_managed_python_and_config(self):
        python = self.root / ".venv-gpu" / "bin" / "python"
        config = str(self.root / "gpu config.py")
        with patch.object(bootstrap, "server_arguments", return_value=["--device", "cuda"]), \
             patch.object(bootstrap, "prepare_environment", return_value=python), \
             patch.object(bootstrap.os, "execv") as execute:
            bootstrap.main(["--uv", "uv", "--config", config])
        self.assertEqual(execute.call_args.args[0], str(python))
        self.assertEqual(execute.call_args.args[1][-2:], ["--config", config])

    @unittest.skipUnless(shutil.which("sh"), "Requires a POSIX shell")
    def test_shell_uses_uv_from_a_different_directory_and_preserves_arguments(self):
        project = self.root / "project with spaces"
        project.mkdir()
        shutil.copyfile(bootstrap.PROJECT_ROOT / "start_gpu_server.sh", project / "start_gpu_server.sh")
        tools = project / ".gpu-tools"
        tools.mkdir()
        uv = tools / "uv"
        uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 17\n')
        uv.chmod(0o755)
        # Isolate PATH so this exercises local uv discovery even on developer machines with uv.
        commands = self.root / "commands"
        commands.mkdir()
        (commands / "dirname").symlink_to(shutil.which("dirname"))
        result = subprocess.run([shutil.which("sh"), str(project / "start_gpu_server.sh"),
                                 "--config", "custom config.py"], cwd=self.root,
                                env={"PATH": str(commands)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["run", "--no-project", "--no-config", "--python", "3.11",
                                                     "-m", "gpu_service.bootstrap", "--uv", str(uv),
                                                     "--config", "custom config.py"])

    @unittest.skipUnless(shutil.which("sh"), "Requires a POSIX shell")
    def test_shell_first_start_installs_local_uv_without_python_or_profile_changes(self):
        project = self.root / "new project"
        project.mkdir()
        shutil.copyfile(bootstrap.PROJECT_ROOT / "start_gpu_server.sh", project / "start_gpu_server.sh")
        commands = self.root / "commands"
        commands.mkdir()
        for name in ("dirname", "mktemp", "rm", "sh", "mkdir", "cat", "chmod", "cp"):
            (commands / name).symlink_to(shutil.which(name))
        installer = self.root / "mock installer.sh"
        installer.write_text('mkdir -p "$UV_UNMANAGED_INSTALL"\n'
                             'cat > "$UV_UNMANAGED_INSTALL/uv" <<\'SH\'\n'
                             '#!/bin/sh\nprintf "%s\\n" "$@"\nSH\n'
                             'chmod +x "$UV_UNMANAGED_INSTALL/uv"\n')
        curl = commands / "curl"
        curl.write_text('#!/bin/sh\ncp "$GPU_TEST_INSTALLER" "$4"\n')
        curl.chmod(0o755)
        result = subprocess.run([shutil.which("sh"), str(project / "start_gpu_server.sh")], cwd=self.root,
                                env={"PATH": str(commands), "GPU_TEST_INSTALLER": str(installer)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((project / ".gpu-tools" / "uv").is_file())
        self.assertEqual(result.stdout.splitlines()[1:7], ["run", "--no-project", "--no-config", "--python", "3.11", "-m"])


if __name__ == "__main__":
    unittest.main()
