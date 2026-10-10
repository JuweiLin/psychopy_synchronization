# Reading Experiment

EyeLink calibration → Condition 1 reading → personal reading speed → Condition 2 sentence audio preparation.

## Start

Double-click the entry for the experiment computer:

- **Windows:** [Start Experiment.bat](Start%20Experiment.bat)
- **macOS:** [Start Experiment.command](Start%20Experiment.command)

Keep the whole project folder together when copying it to another computer. Enter a participant ID such as `S001`, then click **Start Experiment**. No name or password is collected. No terminal commands need to be typed; a terminal/console window opens only to launch the application.

The launcher looks for a project `.venv` / `venv` and an installed PsychoPy application. Dummy mode requires only PsychoPy and wxPython. Real recording also requires SR Research PyLink (`pylink`) and `EyeLinkCoreGraphicsPsychoPy`. Missing components are shown before the experiment starts. Windows discovery checks common PsychoPy installation folders under Program Files and Local AppData/Programs. If automatic launch fails, a file chooser lets you select `python.exe` inside the PsychoPy installation folder. This choice is saved under `data/launcher_logs/windows-python.txt` for future launches. If PsychoPy is not installed, install PsychoPy Standalone first. Opening the `.py` file directly depends on Windows file associations; use the `.bat` entry. The Windows chooser has not been tested on a Windows computer yet.

## Configure

Edit only [config.py](config.py) in the project root before launching. It contains five settings:

```python
dummy_mode = True
condition1_count = 2
condition2_count = 2
eyelink_ip = "100.1.1.1"
tts_server_url = ""
```

Dummy mode is currently enabled. It skips the EyeLink connection, calibration, recording, package checks and EDF transfer. It keeps article selection, reading, flip timestamps, WPM, CSV logs and sentence audio preparation. Change it to `False` before testing the real EyeLink setup. The login and ready screen identify dummy mode in English.

The two counts control how many articles are sampled for each condition. Set `eyelink_ip` to the tracker address for real recording. Leave `tts_server_url` empty until the GPU address is known, then fill in its origin, such as `"http://192.168.1.20:8765"`. Save the file and reopen the launcher after changes. Internal display defaults and validation remain in `psychopy_sync/config.py`.

Put one article in each `assets/articles/<article_id>.csv`. Each CSV has one column: the first cell is the title; each following nonempty cell is one sentence/page. Quote cells containing commas or line breaks. IDs use 1–32 ASCII letters, digits, underscores or hyphens. The article pool must contain at least the combined article count. The supplied four articles are sample text.

Both conditions are sampled without replacement at startup. The seed, article order and stimulus snapshots are saved. Space starts an article, advances a page and ends the last page. Escape stops the session.

## Data

- `data/users.csv`: participant IDs and first registration times.
- `data/reading_speed.csv`: reading speed for each participant/session.
- `data/<participant_id>/<session_id>/`: `condition1.csv`, `condition2.csv`, `user_logs.csv`, `session.json`, `stimuli/` and `eyelink.edf`.
- `assets/TTS/<participant_id>/<session_id>/`: `tts_index.csv`, requests, manifest and sentence WAVs inside article folders.
- `data/launcher_logs/`: startup and experiment diagnostics.

Dummy sessions save their registry, reading-speed table and session directories under `data/dummy/`, keeping them separate from real sessions. Session metadata and the TTS manifest contain `dummy_mode: true`; local event rows use `marker_status=disabled_dummy`. Dummy mode produces no eye samples or EDF file. TTS still follows `tts_server_url`; dummy mode does not disable a configured GPU service.

Reading speed is `60 × total words / sum of article reading seconds`. Each article's interval runs from the flip that displays its first page to the flip that removes its last page. Waiting between articles is excluded. In real mode, EyeLink recording remains continuous after calibration, including article waits and audio preparation.

After all Condition 1 articles are completed, each Condition 2 sentence is submitted at the participant's measured WPM. Without a GPU URL, requests and the sentence index are saved as `not_configured`; no WAVs are generated.

**Condition 2 presentation and audio playback are not implemented yet.** Hardware recording, EDF transfer and real F5-TTS still require verification on the experiment setup.

## Details

[Experiment flow and timing](docs/condition1.md) · [GPU audio service](docs/network-audio.md) · [Module map](docs/module-map.md)

For developers, hardware-free checks run with `python3 -m unittest discover -s tests -v`.
