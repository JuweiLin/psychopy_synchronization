#!/bin/sh
set -eu
gpu_project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$gpu_project_root"
if [ -n "${GPU_PYTHON:-}" ]; then
    exec "$GPU_PYTHON" "$gpu_project_root/start_gpu_server.py" "$@"
fi
# Transport-only tests do not need uv, model packages or an NVIDIA GPU.
for gpu_argument in "$@"; do
    if [ "$gpu_argument" = "--demo" ] && command -v python3 >/dev/null 2>&1; then
        exec python3 "$gpu_project_root/start_gpu_server.py" "$@"
    fi
done
if command -v uv >/dev/null 2>&1; then
    gpu_uv=$(command -v uv)
elif [ -x "$gpu_project_root/.gpu-tools/uv" ]; then
    gpu_uv="$gpu_project_root/.gpu-tools/uv"
else
    echo "Installing uv locally for the GPU service..."
    gpu_installer=$(mktemp)
    trap 'rm -f "$gpu_installer"' EXIT HUP INT TERM
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh -o "$gpu_installer"
    elif command -v wget >/dev/null 2>&1; then
        wget -q https://astral.sh/uv/install.sh -O "$gpu_installer"
    else
        echo "curl or wget is required to install uv. On Ubuntu: sudo apt install curl" >&2
        exit 1
    fi
    UV_UNMANAGED_INSTALL="$gpu_project_root/.gpu-tools" sh "$gpu_installer"
    rm -f "$gpu_installer"
    trap - EXIT HUP INT TERM
    gpu_uv="$gpu_project_root/.gpu-tools/uv"
fi
# uv supplies Python 3.11 too, even if only Ubuntu's system Python is installed.
exec "$gpu_uv" run --no-project --no-config --python 3.11 \
    -m gpu_service.bootstrap --uv "$gpu_uv" "$@"
