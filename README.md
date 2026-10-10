# Reading Experiment

EyeLink calibration → Condition 1 reading → personal reading speed → Condition 2 reading with sentence TTS.

## Start

Double-click the entry for the experiment computer:

- **Windows:** [Start Experiment.bat](Start%20Experiment.bat)
- **macOS:** [Start Experiment.command](Start%20Experiment.command)

Keep the whole project folder together when copying it to another computer. Enter a participant ID such as `S001`, then click **Start Experiment**. No name or password is collected. No terminal commands need to be typed; a terminal/console window opens only to launch the application.

The launcher looks for a project `.venv` / `venv` and an installed PsychoPy application. Dummy mode requires PsychoPy and wxPython; configured Condition 2 playback also requires PsychoPy's PTB (`psychtoolbox`) and `soundfile` audio dependencies. Real recording also requires SR Research PyLink (`pylink`) and `EyeLinkCoreGraphicsPsychoPy`. Missing components are shown before the experiment starts. Windows discovery checks common PsychoPy installation folders under Program Files and Local AppData/Programs. If automatic launch fails, a file chooser lets you select `python.exe` inside the PsychoPy installation folder. This choice is saved under `data/launcher_logs/windows-python.txt` for future launches. If PsychoPy is not installed, install PsychoPy Standalone first. Opening the `.py` file directly depends on Windows file associations; use the `.bat` entry. The Windows chooser has not been tested on a Windows computer yet.

## Configure

Edit only [config.py](config.py) in the project root before launching. It contains five settings:

```python
dummy_mode = True
condition1_count = 2
condition2_count = 2
eyelink_ip = "100.1.1.1"
tts_server_url = "http://192.168.137.2:8765"
```

With `dummy_mode=True`, the experiment skips the EyeLink connection, calibration, recording, package checks and EDF transfer. It keeps article selection, reading, flip timestamps, WPM, CSV logs and configured Condition 2 audio playback. Set it to `False` for the real EyeLink setup. The login and ready screen identify dummy mode in English.

The two counts control how many articles are sampled for each condition. Set `eyelink_ip` to the tracker address for real recording. Leave `tts_server_url` empty until the GPU address is known, then fill in its origin, such as `"http://192.168.1.20:8765"`. Save the file and reopen the launcher after changes. Internal display defaults and validation remain in `psychopy_sync/config.py`.

Put one article in each `assets/articles/<article_id>.csv`. Each CSV has one column: the first cell is the title; each following nonempty cell is one sentence/page. Quote cells containing commas or line breaks. IDs use 1–32 ASCII letters, digits, underscores or hyphens. The article pool must contain at least the combined article count. The supplied four articles are sample text.

Both conditions are sampled without replacement at startup. The seed, article order and stimulus snapshots are saved. Space starts each article. In Condition 1, Space advances a page and ends the last page. In Condition 2, each sentence plays its matching WAV and automatically advances when playback finishes. Escape stops the session.

## GPU server

On the GPU computer, set the reference audio and transcript paths in [gpu_config.py](gpu_config.py). On **Ubuntu/Linux**, run:

```sh
bash start_gpu_server.sh
```

The script installs uv locally if missing, obtains Python 3.11 if needed, creates or reuses `.venv-gpu`, installs [GPU requirements](gpu_service/requirements.txt), selects a CUDA PyTorch build for the installed NVIDIA driver, checks GPU execution, and starts the service. For CUDA it also installs the matching NVIDIA NPP runtime and exposes the environment's NVIDIA shared libraries to both the startup check and service. Missing FFmpeg is installed through APT on Ubuntu (sudo may ask for your password). The first model load automatically downloads model weights. Subsequent starts reuse the environment and downloaded files. The NVIDIA driver must already work (`nvidia-smi`). No manual environment activation or separate CUDA Toolkit installation is needed.

On **Windows**, `Start GPU Server.bat` still uses a manually prepared F5-TTS Python environment. `python start_gpu_server.py` is also a direct entry for an already prepared environment. Setting `GPU_PYTHON` makes the Linux script use that interpreter directly and bypass automatic setup. The GPU computer does not need PsychoPy or EyeLink packages. See [GPU setup](docs/network-audio.md) for configuration and commands.

The service loads the model and generates a short test WAV at startup. The login checks readiness in the background when opened and again before each experiment. A configured server must pass its startup audio test before the experiment can begin. Loading is retried automatically; use **Recheck** after correcting an address/network error. An empty `tts_server_url` allows the reading-only workflow. Demo silence is accepted only in dummy mode.

## Data

- `data/users.csv`: participant IDs and first registration times.
- `data/reading_speed.csv`: reading speed for each participant/session.
- `data/<participant_id>/<session_id>/`: `condition1.csv`, `condition2.csv`, `user_logs.csv`, `sentence_pages.csv`, `session.json`, `stimuli/`, `screenshots/` and `eyelink.edf`.
- `assets/TTS/<participant_id>/<session_id>/`: `tts_index.csv`, requests, manifest and sentence WAVs inside article folders.
- `data/launcher_logs/`: startup and experiment diagnostics.

Dummy sessions save their registry, reading-speed table and session directories under `data/dummy/`, keeping them separate from real sessions. Session metadata and the TTS manifest contain `dummy_mode: true`; local event rows use `marker_status=disabled_dummy`. Dummy mode produces no eye samples or EDF file. TTS still follows `tts_server_url`; dummy mode does not disable a configured GPU service.

Reading speed is `60 × total words / sum of article reading seconds`. Each article's interval runs from the flip that displays its first page to the flip that removes its last page. Waiting between articles is excluded. In real mode, EyeLink recording remains continuous after calibration, including article waits, audio preparation and Condition 2 playback.

After all Condition 1 articles are completed, each Condition 2 sentence is submitted at the participant's measured WPM. Without a GPU URL, requests and the sentence index are saved as `not_configured`; no WAVs are generated.

With a GPU URL, the first Condition 2 article is released as soon as all its sentence WAVs are downloaded, verified and preloaded. Later articles continue generating/downloading in the background. Each article starts with Space; sentences then display and play in CSV order without additional key presses. If the next article is not ready, a wait screen appears. Condition 2 timing and playback events are saved alongside Condition 1 data.

Hardware recording, EDF transfer, speaker output and real F5-TTS still require verification on the experiment setup.

For real recording, the result window shows the downloaded EDF path and byte count. EDF transfer is attempted on normal completion and Escape, retries up to three times, and publishes the file only when the received byte count matches the local file size. A failure shows the Host EDF filename for recovery. Dummy mode never produces an EDF.

Every selected sentence is captured as a full-screen PNG before calibration/recording, using the actual PsychoPy page layout (including the Condition 1 footer). `sentence_pages.csv` maps condition/article/sentence IDs to relative image paths and visible onset/offset intervals; unshown pages stay `not_presented`. Each displayed sentence is one Data Viewer trial with standard image-loading messages. Copy the complete session folder to the analysis computer and import `eyelink.edf`; then use Data Viewer's image auto-segmentation to create AOIs. The experiment does not create AOIs. See [Data Viewer output](docs/data-viewer.md).

## Details

[Experiment flow and timing](docs/condition1.md) · [Data Viewer output](docs/data-viewer.md) · [GPU audio service](docs/network-audio.md) · [Module map](docs/module-map.md)

For developers, hardware-free checks run with `python3 -m unittest discover -s tests -v`.
