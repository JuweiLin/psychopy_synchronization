# GPU audio service

After Condition 1 saves personal WPM, the display computer sends one request per selected Condition 2 sentence to the GPU service. The service generates and validates a complete WAV before publishing it. The display computer polls and downloads in a background thread, then verifies identity, checksum, file size, PCM readability and duration before caching the sentence.

The experiment's local files are `assets/TTS/<participant_id>/<session_id>/<article_id>/sentence_0001.wav`, with one JSON metadata file per WAV and a `tts_index.csv` mapping every sentence to its audio location. With `tts_server_url=""` in the root `config.py`, only requests and the index/manifest are saved. With a configured server, Condition 2 starts after the first article's entire set of WAVs is verified and preloaded. Each sentence displays with its corresponding WAV and advances automatically after playback. Later articles generate/download in the background; waiting is per article, not for the whole condition.

## Start the GPU service

Both computers need the project code. Only the GPU computer needs F5-TTS and its model dependencies. Prepare a fixed reference WAV and its exact transcript, and edit the GPU computer's root `gpu_config.py`:

```python
ref_audio = "assets/reference.wav"
ref_text_file = "assets/reference.txt"
host = "0.0.0.0"
port = 8765
device = "cuda"
demo_mode = False
```

The paths can be absolute or relative to `gpu_config.py`. The project includes the [official F5-TTS English reference sample](https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/examples/basic/basic.toml) as `assets/reference.wav` and its matching transcript as `assets/reference.txt`, so the default paths can be used directly. If you replace the recording, update the text file with its exact transcript too. Keep the server terminal open during the experiment.

### Automatic setup on Ubuntu/Linux

Install the NVIDIA driver first and confirm `nvidia-smi` works. From the project directory, run:

```sh
bash start_gpu_server.sh
```

This single entry:

1. Uses uv from PATH or installs it into `.gpu-tools/` using the [official installer](https://docs.astral.sh/uv/getting-started/installation/), without changing shell profiles. curl or wget is required for this first download.
2. Obtains Python 3.11 through uv if needed, validates the config/reference paths, and checks the NVIDIA driver.
3. Checks FFmpeg/ffprobe. If missing on Ubuntu, runs `apt-get update` and `apt-get install -y ffmpeg` (through sudo for non-root users).
4. Creates `.venv-gpu` or reuses its Python 3.11 interpreter. This environment is separate from PsychoPy and any active Conda environment.
5. Runs `uv pip install` against `gpu_service/requirements.txt`, using an explicit environment interpreter and the selected PyTorch backend. CUDA setup also installs a matching NVIDIA NPP wheel (cu128: 12.3.3.65; cu126: 12.3.1.23; cu118: 11.8.0.86). Already satisfied packages are reused; dependencies are not upgraded on every start.
6. Adds `.venv-gpu/lib/python3.11/site-packages/nvidia/*/lib` directories to the startup check and service's `LD_LIBRARY_PATH`, preserving existing entries. Imports the audio/model libraries and executes a CUDA tensor operation on the configured device before starting the HTTP service.

The requirements pin PyTorch/torchaudio 2.7.1 and TorchCodec 0.5 as a matched set, plus F5-TTS 1.1.22. CUDA mode explicitly selects matching CUDA builds of all three packages, including TorchCodec. Its `libnpp` dependency is installed separately; PyTorch supplies the matching CUDA runtime and `libnvrtc`. For NVIDIA drivers at least 570.26 the script selects `cu128`; at least 560.28.03 selects `cu126`; at least 520.61.05 selects `cu118`. Older/unreadable drivers stop setup. These are conservative Linux driver floors from [NVIDIA release notes](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html); the wheel builds are listed by [PyTorch](https://pytorch.org/get-started/previous-versions/#v271), and TorchCodec's [compatibility table](https://github.com/meta-pytorch/torchcodec#compatibility-with-torch-versions) defines its matching version. `device="cpu"` is also supported explicitly. CUDA failure never falls back silently to CPU.

If an older installation fails importing TorchCodec with `libnppicc.so.12: cannot open shared object file`, update `gpu_service/bootstrap.py` and `gpu_service/requirements.txt`, then rerun `./start_gpu_server.sh`. The bootstrap installs NPP into the existing environment and exposes its shared libraries before importing TorchCodec. No environment deletion or full CUDA Toolkit installation is needed for this fix. See TorchCodec 0.5's [CPU and CUDA installation instructions](https://github.com/meta-pytorch/torchcodec/blob/v0.5.0/README.md#installing-torchcodec).

The requirements also pin `pyarrow==23.0.1`, which supports the configured NumPy 1.26 environment ([PyArrow 23 installation requirements](https://arrow.apache.org/docs/23.0/python/install.html#dependencies)). F5-TTS imports it through `datasets` even during inference. If startup reports `pyarrow requires NumPy 2.0 or newer`, update `gpu_service/requirements.txt` and rerun the same startup script; it replaces the incompatible PyArrow package in `.venv-gpu`.

On its first real startup, F5-TTS automatically downloads the `F5TTS_v1_Base` weights and Vocos vocoder, then generates the startup test WAV. Internet access and enough disk space for Python, dependencies and models are needed for initial setup. The script does not install a driver or the full CUDA Toolkit. Existing model caches are reused by the model libraries. Errors stop startup; fix the reported cause and rerun the same command. An incomplete/incompatible `.venv-gpu` is reported and retained instead of being erased automatically. CUDA execution and real speech generation still need verification on the GPU computer; local development checks use mocks and metadata resolution.

`--config "/path with spaces/gpu_config.py"` selects a custom config. `--demo` skips model/GPU setup when Python 3 is already available; configured demo mode also skips GPU dependencies. Setting `GPU_PYTHON` explicitly bypasses automatic setup and uses that prepared Python directly.

### Prepared environments and Windows

On Windows run `Start GPU Server.bat` from an activated F5-TTS environment, or set `GPU_PYTHON` to its interpreter. `python start_gpu_server.py` is the direct cross-platform entry for an already prepared environment. It does not install dependencies. Missing reference files or F5-TTS are reported before the server is started. Manual setup follows the [official F5-TTS instructions](https://github.com/SWivid/F5-TTS#installation).

The service loads the model and generates a short temporary test WAV at startup, checking PCM readability and WPM tolerance. The test does not create participant jobs or experiment audio files. `/ready` returns HTTP 503 while loading or if the test fails, and HTTP 200 only after success. A failed startup requires fixing the cause and restarting the service; the full error is in its console. Startup testing and normal inference use the same worker, so they cannot access the model concurrently. The login checks in a background thread, automatically retries loading every three seconds, and rechecks before each session. Each network request has a three-second socket timeout. Configured servers that are offline, incompatible or unready prevent starting. The readiness check identifies the service/protocol, confirms the startup test, and rejects demo mode for real EyeLink sessions. Use **Recheck** after resolving connection failures. With no URL, the reading-only workflow is allowed.

The existing explicit command is also supported:

```sh
python -m gpu_service.tts_server \
  --host 0.0.0.0 \
  --port 8765 \
  --output-dir generated_audio \
  --ref-audio /path/to/reference.wav \
  --ref-text-file /path/to/reference.txt \
  --device cuda \
  --wpm-tolerance 0.05
```

Replace the reference paths. Set `tts_server_url` in the display computer's root `config.py` to the GPU computer's actual origin, for example `"http://192.168.1.20:8765"`, and reopen the launcher. The server defaults to loopback unless `--host` is set. This HTTP service is intended for the experiment LAN and has no account authentication.

Run from the project root in the GPU computer's F5-TTS Python environment. The equivalent single-line command works in Windows PowerShell/CMD and Linux/macOS shells (replace both reference paths):

```sh
python -m gpu_service.tts_server --host 0.0.0.0 --port 8765 --output-dir generated_audio --ref-audio "reference.wav" --ref-text-file "reference.txt" --device cuda
```

`reference.wav` is the reference voice audio; `reference.txt` is its exact transcript. Keep the server running during the experiment. From the display computer, open `http://<GPU_IP>:8765/health` to check reachability; a health response does not confirm that model inference works. The two computers must be able to reach each other on port 8765.

After its startup test, a single worker reuses the loaded model. The adapter maps target duration to F5-TTS inference duration, including reference duration in `fix_duration`. It does not pass WPM directly as relative model speed. Long tasks can be split internally and joined, but still produce one WAV for the requested sentence. See the [official inference implementation](https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/utils_infer.py).

The 5% WPM tolerance is a configurable engineering default, not a finalized experiment criterion. Duration includes generated pauses and leading/trailing silence. Content accuracy and voice quality require listening checks; automatic ASR content verification is not implemented. Real F5-TTS has not been tested on this setup.

## Request contract

The outer JSON key remains `articles` for compatibility; each item is one audio task. The experiment creates this automatically from its selected CSV pages.

```json
{
  "articles": [
    {
      "session_id": "run01",
      "participant_id": "S001",
      "article_id": "article_001",
      "sentence_index": 1,
      "text": "The first sentence goes here.",
      "word_count": 5,
      "target_wpm": 240.0
    }
  ]
}
```

The target duration above is 1.25 seconds. Word count must equal `len(text.split())`. Sentence index is a positive integer and forms part of identity with participant, session and article IDs. Duplicate identities in one batch are rejected. The API accepts 1–100 tasks per batch and at most 1 MiB of JSON; the background client splits longer lists into batches of 100.

Standalone tasks without `sentence_index` remain supported for compatibility. The experiment always uses sentence-based generation.

## API and files

| Endpoint | Result |
| --- | --- |
| `GET /health` | HTTP liveness plus nested readiness details; HTTP 200 alone does not imply model readiness |
| `GET /ready` | Service/protocol, mode, startup test state and error; 200 when verified, otherwise 503 |
| `POST /jobs/batch` | Validates and queues tasks; 503 while startup is pending or failed |
| `GET /jobs/<job_id>` | Current state and metadata |
| `GET /jobs/<job_id>/audio` | Complete WAV; unfinished audio returns HTTP 409 |

```text
generated_audio/<job_id>/
  audio.partial.wav   # unavailable while generating
  audio.wav           # published after validation
  metadata.json
```

Metadata records identity, text hash, target speed/duration, actual duration/WPM, sample rate, checksum, file size, model information and errors. Cache completion is delivered as `CachedAudio`; failures as `AudioFailure`. Cached audio has not yet been preloaded or played by PsychoPy.

Failed tasks are recorded while later tasks continue. Service restarts preserve completed jobs; unfinished jobs become failed and require resubmission. Automatic network retry is not implemented. Escape stops local polling/downloads and retains cached audio, but does not cancel accepted GPU jobs.

## Independent transport test

For HTTP/file testing without a model:

```sh
python start_gpu_server.py --demo
```

This uses the host/port in `gpu_config.py` and skips reference files/model dependencies. The launcher accepts this server only for participant ID **0** (dummy mode). An existing server must be restarted with the updated code to provide `/ready`.

In another terminal, use a `requests.json` saved by a completed Condition 1 session. Replace the placeholder path below:

```sh
python -m psychopy_sync.audio_client \
  --server http://127.0.0.1:8765 \
  --articles /path/to/session/requests.json \
  --cache-dir audio_cache
```

Demo mode produces explicitly marked silence, which the formal sound preload helper rejects unless dummy mode is explicitly enabled. It is not experimental speech. Integration tests use temporary local HTTP services for sentence identity, indexing, batching, publication, checksum validation, failure handling and restart recovery.
