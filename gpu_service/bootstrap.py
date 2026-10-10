"""Prepare an isolated Linux GPU environment with uv, then launch the service."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .launcher import PROJECT_ROOT, main as launch, server_arguments


# NPP releases shipped with CUDA 12.8, 12.6 and 11.8 respectively.
# PyTorch already supplies the matching CUDA runtime and NVRTC packages.
NPP_REQUIREMENTS = {
    "cu128": "nvidia-npp-cu12==12.3.3.65",
    "cu126": "nvidia-npp-cu12==12.3.1.23",
    "cu118": "nvidia-npp-cu11==11.8.0.86",
}


def runtime_environment(python, device):
    """Expose this managed Python 3.11 environment's NVIDIA shared libraries."""
    environment = os.environ.copy()
    if device.startswith("cuda"):
        site_packages = Path(python).parent.parent / "lib" / "python3.11" / "site-packages"
        libraries = [str(path) for path in sorted((site_packages / "nvidia").glob("*/lib"))
                     if path.is_dir()]
        existing = [path for path in environment.get("LD_LIBRARY_PATH", "").split(os.pathsep) if path]
        paths = list(dict.fromkeys(libraries + existing))
        if paths:
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    return environment


def torch_backend(driver_versions):
    """Use published PyTorch 2.7.1 builds and conservative NVIDIA driver floors."""
    versions = []
    for line in driver_versions.splitlines():
        value = line.strip()
        if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
            raise ValueError(f"Unexpected NVIDIA driver version: {value!r}")
        parts = tuple(int(part) for part in value.split("."))
        versions.append(parts + (0,) * (3 - len(parts)))
    if not versions:
        raise ValueError("No NVIDIA GPU was reported by nvidia-smi")
    driver = min(versions)
    for minimum, backend in (((570, 26, 0), "cu128"),
                             ((560, 28, 3), "cu126"),
                             ((520, 61, 5), "cu118")):
        if driver >= minimum:
            return backend
    raise ValueError("The NVIDIA driver is too old. Update it, reboot, and rerun this script.")


def ensure_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    if not shutil.which("apt-get"):
        raise ValueError("Install FFmpeg and ffprobe using your system package manager, then rerun.")
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    if prefix and not shutil.which("sudo"):
        raise ValueError("FFmpeg is missing. Ask an administrator to run: apt-get install ffmpeg")
    print("Installing FFmpeg using apt; sudo may ask for your password.", flush=True)
    subprocess.run(prefix + ["apt-get", "update"], check=True)
    subprocess.run(prefix + ["apt-get", "install", "-y", "ffmpeg"], check=True)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg installation did not make ffmpeg and ffprobe available on PATH")


GPU_PROBE = """
import sys
import torch
import torchaudio
from torchcodec.decoders import AudioDecoder
from f5_tts.api import F5TTS
device = sys.argv[1]
if device.startswith('cuda'):
    if not torch.cuda.is_available():
        raise RuntimeError('PyTorch cannot use CUDA. Check the NVIDIA driver and reboot after installing it.')
    # Exercise the selected device, including a CUDA kernel, before loading models.
    value = (torch.ones(1, device=device) + 1).item()
    print('GPU:', torch.cuda.get_device_name(torch.device(device)))
    print('PyTorch:', torch.__version__, 'CUDA runtime:', torch.version.cuda)
print('GPU environment check passed.', flush=True)
"""


def prepare_environment(uv, device, root=PROJECT_ROOT):
    if sys.platform != "linux":
        raise ValueError("Automatic GPU setup supports Linux. Use start_gpu_server.py with a prepared environment on other systems.")
    backend = "cpu"
    if device.startswith("cuda"):
        if shutil.which("nvidia-smi") is None:
            raise ValueError("nvidia-smi was not found. Install the NVIDIA driver and reboot first.")
        result = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                check=True, capture_output=True, text=True, timeout=15)
        backend = torch_backend(result.stdout)
        print(f"NVIDIA driver: {result.stdout.strip()}; PyTorch backend: {backend}", flush=True)
    elif device != "cpu":
        raise ValueError("Automatic setup supports device='cuda', 'cuda:N', or 'cpu'")
    ensure_ffmpeg()
    environment = Path(root) / ".venv-gpu"
    python = environment / "bin" / "python"
    if environment.exists():
        if not python.is_file():
            raise ValueError(f"Incomplete environment: {environment}. Rename it and rerun to create a fresh one.")
        subprocess.run([str(python), "-c",
                        "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 'The GPU environment requires Python 3.11. Rename .venv-gpu and rerun.')"],
                       check=True)
        print(f"Reusing GPU environment: {environment}", flush=True)
    else:
        print(f"Creating GPU environment: {environment}", flush=True)
        subprocess.run([uv, "venv", "--no-config", "--python", "3.11", str(environment)], check=True)
    print("Checking and installing GPU requirements...", flush=True)
    # Exact local versions also replace an existing CPU/different CUDA build.
    wheels = [f"torch==2.7.1+{backend}", f"torchaudio==2.7.1+{backend}"]
    if backend == "cpu":
        wheels.append("torchcodec===0.5")  # CPU TorchCodec has no +cpu suffix.
    else:
        wheels.extend([f"torchcodec==0.5+{backend}", NPP_REQUIREMENTS[backend]])
    subprocess.run([uv, "pip", "install", "--no-config", "--python", str(python),
                    "--torch-backend", backend, "--requirements", str(Path(root) / "gpu_service" / "requirements.txt"),
                    *wheels],
                   check=True)
    # LD_LIBRARY_PATH must be set before the child starts, including the probe.
    subprocess.run([str(python), "-c", GPU_PROBE, device], check=True,
                   env=runtime_environment(python, device))
    return python


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "gpu_config.py"))
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    try:
        # Fail on missing references/config before installing large dependencies.
        arguments = server_arguments(args.config, args.demo)
        if "--demo" in arguments:
            launch(["--config", args.config, "--demo"])
            return
        device = arguments[arguments.index("--device") + 1]
        python = prepare_environment(args.uv, device)
    except subprocess.CalledProcessError as exc:
        print(f"GPU setup failed (exit {exc.returncode}). See the command output above, fix the cause and rerun.", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        raise SystemExit(exc.returncode or 1) from exc
    except (OSError, ValueError, KeyError, SyntaxError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    # An explicit interpreter is equivalent to activation and cannot select a
    # PsychoPy/Conda Python accidentally. exec also preserves Ctrl+C/shutdown.
    os.execve(str(python), [str(python), str(PROJECT_ROOT / "start_gpu_server.py"), "--config", args.config],
              runtime_environment(python, device))


if __name__ == "__main__":
    main()
