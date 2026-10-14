# Reading Experiment

EyeLink calibration → Condition 1 reading → personal reading speed → Condition 2 reading with sentence TTS.

## Start

Double-click the entry for the experiment computer:

- **Windows:** [Start Experiment.bat](Start%20Experiment.bat)
- **macOS:** [Start Experiment.command](Start%20Experiment.command)

Keep the whole project folder together when copying it to another computer. Enter a whole-number participant ID from `0` to `200`, then click **Start Experiment**. Other inputs show an error. Leading zeros are removed, so `001` uses ID `1`. No name or password is collected. No terminal commands need to be typed; a terminal/console window opens only to launch the application.

Enter **0** for a dummy session or **1–200** for a real EyeLink session. There is no mode checkbox or config switch. Each ID 0 session randomly selects **one Condition 1 article and two Condition 2 articles**, without overlap, skips calibration/eye tracking, and saves under `data/dummy/`. It does not claim a formal slot. Changing between 0 and a formal ID rechecks GPU readiness and applies the corresponding dependency checks. Configured TTS still uses the GPU service in either mode.

With ID **0**, **Audio Onset Debug...** opens a separate WPM test interface. Choose an article/page or edit the text, enter speeds such as `100, 150, 200, 250, 300, 400`, and set plays per speed. It bypasses Condition 1, generates one real F5-TTS WAV per speed, and uses Condition 2's PTB playback. After each play, press **C** for complete first words, **M** for a missing beginning, **U** for unsure, or **R** to replay that same WAV. Escape saves and stops. WAVs, metadata, `audio_index.csv`, `onset_results.csv` and playback logs are saved under `data/dummy/audio_debug/<run>/`. Open the saved WAV separately to compare its content with in-app playback. See [audio debug](docs/audio-debug.md).

The launcher looks for a project `.venv` / `venv` and an installed PsychoPy application. Dummy mode requires PsychoPy and wxPython; configured Condition 2 playback also requires PsychoPy's PTB (`psychtoolbox`) and `soundfile` audio dependencies. Real recording also requires SR Research PyLink (`pylink`) and `EyeLinkCoreGraphicsPsychoPy`. Missing components are shown before the experiment starts. Windows discovery checks common PsychoPy installation folders under Program Files and Local AppData/Programs. If automatic launch fails, a file chooser lets you select `python.exe` inside the PsychoPy installation folder. This choice is saved under `data/launcher_logs/windows-python.txt` for future launches. If PsychoPy is not installed, install PsychoPy Standalone first. Opening the `.py` file directly depends on Windows file associations; use the `.bat` entry. The Windows chooser has not been tested on a Windows computer yet.

PsychoPy-managed packages are loaded in the runtime check, login and experiment processes. On Windows the launcher uses `%APPDATA%/psychopy3/packages/PythonXY/site-packages`, where `XY` matches the selected interpreter (for example, `Python310` for Python 3.10). If **Missing components** still appears, the scrollable status box shows the missing module names, the actual Python executable/version and the searched package directories. Copy that text when reporting the error; packages installed for another Python version are not reused.

## Configure

Edit only [config.py](config.py) in the project root before launching. It contains four settings:

```python
condition1_count = 4
condition2_count = 4
eyelink_ip = "100.1.1.1"
tts_server_url = "http://192.168.137.2:8765"
```

With ID **0**, the experiment skips the EyeLink connection, calibration, recording, package checks and EDF transfer. It keeps reading, flip timestamps, WPM, CSV logs and configured Condition 2 audio playback. IDs **1–200** use the real EyeLink setup. The login and ready screen identify dummy mode in English.

The imported frozen schedule requires both formal article counts to remain **4**; changing them requires a matching new schedule. ID 0 overrides these counts to **1 and 2** automatically. Set `eyelink_ip` to the tracker address for real recording. Leave `tts_server_url` empty for a reading-only session, or fill in the GPU service origin. Audio onset debug requires a configured, ready F5-TTS server and rejects demo silence. Save the file and reopen the launcher after changes. Internal display defaults and validation remain in `psychopy_sync/config.py`.

The twelve study articles are in `assets/articles/<article_id>.csv` (`A02`, `A03`, `A05`, `A08`, `A09`, `A12`, `A15`, `A19`, `A20`, `A28`, `A29`, `A30`). Each CSV has one column: the first cell is the title and each following cell is one body Screen from the pilot workbook, preserving its hard line breaks. A Screen can contain several sentences; the program does not split it further. The title is displayed on its own centered page; Space starts the pre-article baseline and then the body. It is excluded from word count, reading duration and TTS. Every body line is horizontally centered, with the text block vertically centered; word AOIs use those exact positions. `assets/stimulus_import.json` records source hashes, page-to-Screen mapping and word counts.

After each article in either condition, its questions appear one at a time with four clickable answer buttons. The article is hidden, and clicking one answer submits it and advances; correctness feedback is not displayed. Questions keep their CSV order and option order. `assets/questions/<article_id>.csv` stores one file per article, with columns `article_id, question_id, question_order, content, OptionA, OptionB, OptionC, OptionD, CorrectAnswer`. The supplied twelve files contain six questions each (72 total), extracted from the pilot workbook. Correct letters were matched to the official OneStopQA answer text after the workbook's option shuffling; source spelling differences and the A28/A29 source-order difference are documented in `assets/questions/import_manifest.json`. Pilot rating/feedback forms are not part of the experiment. See [question files and responses](docs/questions.md).

`assets/user_assignments.csv` freezes the 200 assignments from planning document version 4.0 (seed 20261013). ID 1 uses R001, ID 2 uses R002, and so on. Each row contains SYNC/FLEX, its list ID, and four article IDs in order for each condition. No new draw is made at login. Reusing an ID preserves its assigned list; a changed schedule for an already registered ID raises an error. Group membership is saved for analysis; the full group-specific instruction wording is not supplied yet, so both groups currently use the existing common reading/listening prompt. Space starts each article. In Condition 1, Space advances a page and ends the last page. In Condition 2, each page plays its matching WAV and automatically advances when playback finishes. Escape stops the session.

After Space starts an article, a central white `+` appears on the same black background for a target of **1500 ms**, then switches directly to the first sentence. This happens once per article in both conditions; sentences within an article advance directly. The cross has a separate AOI and Data Viewer baseline trial (`phase=baseline`, `sentence_index=0`), linked to the article ID. Sentence trials use `phase=reading`. Actual baseline start/end flips, duration and status are saved in the corresponding condition CSV. Baseline time is excluded from reading speed. Display timing is quantized to refresh cycles; use the recorded timestamps to check actual durations.

## GPU server

On the GPU computer, set the reference audio and transcript paths in [gpu_config.py](gpu_config.py). On **Ubuntu/Linux**, run:

```sh
bash start_gpu_server.sh
```

The script installs uv locally if missing, obtains Python 3.11 if needed, creates or reuses `.venv-gpu`, installs [GPU requirements](gpu_service/requirements.txt), selects a CUDA PyTorch build for the installed NVIDIA driver, checks GPU execution, and starts the service. For CUDA it also installs the matching NVIDIA NPP runtime and exposes the environment's NVIDIA shared libraries to both the startup check and service. Missing FFmpeg is installed through APT on Ubuntu (sudo may ask for your password). The first model load automatically downloads model weights. Subsequent starts reuse the environment and downloaded files. The NVIDIA driver must already work (`nvidia-smi`). No manual environment activation or separate CUDA Toolkit installation is needed.

On **Windows**, `Start GPU Server.bat` still uses a manually prepared F5-TTS Python environment. `python start_gpu_server.py` is also a direct entry for an already prepared environment. Setting `GPU_PYTHON` makes the Linux script use that interpreter directly and bypass automatic setup. The GPU computer does not need PsychoPy or EyeLink packages. See [GPU setup](docs/network-audio.md) for configuration and commands.

The service loads the model and generates a short test WAV at startup. The login checks readiness in the background when opened and again before each experiment. A configured server must pass its startup audio test before the experiment can begin. Loading is retried automatically; use **Recheck** after correcting an address/network error. An empty `tts_server_url` allows the reading-only workflow. Demo silence is accepted only in dummy mode.

## Data

- `assets/user_assignments.csv`: fixed assignments for IDs 1–200; not a completion log.
- `data/users.csv`: registered IDs, first registration times, slots, instruction groups, list IDs and schedule provenance.
- `data/reading_speed.csv`: reading speed for each participant/session.
- `data/<participant_id>/<session_id>/`: `condition1.csv`, `condition2.csv`, `user_logs.csv`, `sentence_pages.csv`, `word_aois.csv`, `session.json`, `stimuli/`, `screenshots/`, `interest_areas/`, `aoi_previews/` and `eyelink.edf`.
- `data/<participant_id>/<session_id>/question_responses.csv`: question/option snapshots, selected answers, correctness, observed response times and assignment identity.
- `data/<participant_id>/<session_id>/auxiliary_pages.csv`: title/question screenshots, AOIs, presentation status and paired flip events.
- `assets/TTS/<participant_id>/<session_id>/`: `tts_index.csv`, requests, manifest and sentence WAVs inside article folders.
- `data/launcher_logs/`: startup and experiment diagnostics.

Dummy sessions save their registry, reading-speed table and session directories under `data/dummy/`, keeping them separate from real sessions. Session metadata and the TTS manifest contain `dummy_mode: true`; local event rows use `marker_status=disabled_dummy`. Dummy mode produces no eye samples or EDF file. TTS still follows `tts_server_url`; dummy mode does not disable a configured GPU service.

Reading speed is `60 × total words / sum of article reading seconds`. Each article's interval runs from the flip that displays its first page to the flip that removes its last page. Waiting between articles is excluded. In real mode, EyeLink recording remains continuous after calibration, including article waits, audio preparation and Condition 2 playback.

Title pages, questions and baselines are excluded from reading speed. EyeLink recording remains continuous through all of them. Each title/question is a separate Data Viewer trial (`phase=title` or `phase=question`) with its actual screenshot and AOIs; answer buttons have AOI labels `option_A` through `option_D`.

After all Condition 1 articles are completed, each Condition 2 sentence is submitted at the participant's measured WPM. Without a GPU URL, requests and the sentence index are saved as `not_configured`; no WAVs are generated.

With a GPU URL, the first Condition 2 article is released as soon as all its sentence WAVs are downloaded, verified and preloaded. Later articles continue generating/downloading in the background. Each article starts with Space; sentences then display and play in CSV order without additional key presses. If the next article is not ready, a wait screen appears. Condition 2 timing and playback events are saved alongside Condition 1 data.

Hardware recording, EDF transfer, speaker output and real F5-TTS still require verification on the experiment setup.

For real recording, the result window shows the downloaded EDF path and byte count. EDF transfer is attempted on normal completion and Escape, retries up to three times, and publishes the file only when the received byte count matches the local file size. A failure shows the Host EDF filename for recovery. Dummy mode never produces an EDF.

Every selected sentence is captured as a full-screen PNG before calibration/recording, using the actual PsychoPy page layout (including the Condition 1 footer). Words are measured and positioned individually; those same positions generate word AOI files under `interest_areas/`. `word_aois.csv` records each word and its screen rectangle; `aoi_previews/` contains screenshot copies with red AOI outlines for inspection. `sentence_pages.csv` maps each sentence to its image/IAS files and visible interval; unshown pages stay `not_presented`. Each displayed sentence is one Data Viewer trial with image and `!V IAREA FILE` messages. Copy the complete session folder and import `eyelink.edf` to load the prepared word AOIs. Inspect their alignment; Data Viewer image auto-segmentation is not needed. The new word layout can change line wrapping/spacing compared with earlier sessions and does not retrofit old EDFs. See [Data Viewer output](docs/data-viewer.md).

## Details

For continuous pupil values in Data Viewer, enable **Inspector → Preferences → Data Loading → Load Samples**, then remove and re-import the EDF before exporting a **Sample Report**. Include timestamps, pupil values, gaze, eye identity and trial variables `condition`, `article_id`, `sentence_index`, `phase`. A Fixation Report contains fixation averages rather than every recorded sample. See the [official sample-loading instructions](https://www.sr-research.com/support/thread-169.html) and [pupil/report guide](docs/data-viewer.md). Existing EDFs may already contain samples; newly added baselines and markers apply only to new sessions.

[Experiment flow and timing](docs/condition1.md) · [Data Viewer output](docs/data-viewer.md) · [GPU audio service](docs/network-audio.md) · [Module map](docs/module-map.md)

For developers, hardware-free checks run with `python3 -m unittest discover -s tests -v`.
