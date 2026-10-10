# Module map

The current implementation ends after Condition 1 reading-speed measurement and Condition 2 sentence audio preparation.

| Module | Responsibility |
| --- | --- |
| `Start Experiment.bat`, `Start Experiment.command` | Double-click entries for Windows and macOS; open the login without typed commands |
| `launch_experiment.py` | Calls runtime discovery |
| `psychopy_sync/launcher_bootstrap.py` | Finds the PsychoPy/wx environment, including common Windows and macOS standalone installations |
| `psychopy_sync/windows_python_picker.ps1` | Windows fallback file chooser and saved interpreter path |
| `psychopy_sync/launcher.py` | English participant ID form, mode-aware dependency checks, experiment launch and results |
| `psychopy_sync/desktop_runner.py` | Runs the experiment in a separate process and returns its outcome to the form |
| `config.py` | Five editable settings: dummy mode, condition counts, tracker IP and GPU URL |
| `psychopy_sync/config.py` | Loads root settings; keeps internal defaults and validation |
| `psychopy_sync/experiment.py` | Calibration → continuous recording → Condition 1 → speed → sentence audio → cleanup |
| `psychopy_sync/articles.py` | Loads article CSVs, preserves pages, counts words and samples disjoint conditions |
| `psychopy_sync/reading_display.py` | Prepares pages, handles keys, binds events to flips and shows the audio wait screen |
| `psychopy_sync/condition1.py` | Runs articles, pairs onset/end events and saves complete reading speed |
| `psychopy_sync/reading_speed.py` | Calculates speed from total words and summed article reading durations |
| `psychopy_sync/event_log.py` | ID registry, session tables, snapshots, timestamped events and EyeLink messages |
| `psychopy_sync/eyelink.py` | Real connection/calibration/recording/EDF transfer; an SDK-free dummy controller |
| `psychopy_sync/display.py` | Creates the experiment window; also contains an audio preload helper for future playback |
| `psychopy_sync/session_audio.py` | Prepares per-sentence requests, WAV paths, metadata, manifest and `tts_index.csv` |
| `psychopy_sync/audio_client.py` | Background submission, polling, download and local WAV verification |
| `shared/contracts.py` | Audio request identity, target duration, checksums and PCM WAV inspection |
| `gpu_service/tts_server.py` | HTTP audio service |
| `gpu_service/job_queue.py` | One generation worker, WAV/WPM validation and atomic publication |
| `gpu_service/f5_generator.py` | F5-TTS adapter and an explicit demo-silence generator |
| `psychopy_sync/calibration_check.py` | Separate calibration check; no experiment EDF recording |
| `tests/` | Hardware-free timing, lifecycle, CSV, HTTP and launcher checks |

Condition 2 presentation, audio playback and text/audio synchronization are not implemented. Audio cache completion is not a playback event. The GPU service never controls stimulus onset or EyeLink.

See [experiment flow](condition1.md) and [audio service](network-audio.md) for execution and output details.
