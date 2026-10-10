# Module map

The experiment measures Condition 1 reading speed, then presents Condition 2 sentence text with matching generated audio.

| Module | Responsibility |
| --- | --- |
| `Start Experiment.bat`, `Start Experiment.command` | Double-click entries for Windows and macOS; open the login without typed commands |
| `launch_experiment.py` | Calls runtime discovery |
| `psychopy_sync/launcher_bootstrap.py` | Finds the PsychoPy/wx environment, including common Windows and macOS standalone installations |
| `psychopy_sync/windows_python_picker.ps1` | Windows fallback file chooser and saved interpreter path |
| `psychopy_sync/launcher.py` | English ID form, asynchronous GPU checks on opening/before starting, dependency checks and results |
| `psychopy_sync/server_check.py` | Bounded readiness requests, protocol/mode checks and readable connection failures |
| `psychopy_sync/desktop_runner.py` | Runs the experiment in a separate process and returns its outcome to the form |
| `config.py` | Five editable settings: dummy mode, condition counts, tracker IP and GPU URL |
| `psychopy_sync/config.py` | Loads root settings; keeps internal defaults and validation |
| `psychopy_sync/experiment.py` | Calibration → continuous recording → Condition 1 → speed → background TTS → Condition 2 playback → cleanup |
| `psychopy_sync/articles.py` | Loads article CSVs, preserves pages, counts words and samples disjoint conditions |
| `psychopy_sync/reading_display.py` | Prepares pages, handles keys, binds events to flips, waits per article and schedules PTB sentence playback |
| `psychopy_sync/condition1.py` | Runs articles, pairs onset/end events and saves complete reading speed |
| `psychopy_sync/condition2.py` | Waits/preloads each article, presents sentence text/audio and saves complete/partial presentation timing |
| `psychopy_sync/reading_speed.py` | Calculates speed from total words and summed article reading durations |
| `psychopy_sync/event_log.py` | ID registry, session tables, snapshots, timestamped events and EyeLink messages |
| `psychopy_sync/eyelink.py` | Real connection/calibration/recording/EDF transfer; an SDK-free dummy controller |
| `psychopy_sync/display.py` | Creates the experiment window; verifies and preloads sentence WAVs using PTB |
| `psychopy_sync/session_audio.py` | Prepares per-sentence requests, WAV paths, metadata, manifest and `tts_index.csv` |
| `psychopy_sync/audio_client.py` | Background submission, polling, download and local WAV verification |
| `shared/contracts.py` | Audio request identity, target duration, checksums and PCM WAV inspection |
| `gpu_service/tts_server.py` | HTTP audio service |
| `gpu_config.py` | GPU host/port, reference files, device and demo switch |
| `start_gpu_server.sh` | Linux automatic uv/Python bootstrap; starts the managed GPU environment |
| `start_gpu_server.py`, `Start GPU Server.bat` | Direct GPU startup using a prepared F5-TTS environment |
| `gpu_service/bootstrap.py`, `gpu_service/requirements.txt` | Isolated GPU environment creation/reuse, driver-based CUDA wheel selection, dependency installation and GPU probe |
| `gpu_service/launcher.py` | Loads GPU config and validates reference paths and the Python environment |
| `gpu_service/startup_check.py` | Generates and validates a temporary test WAV before readiness |
| `gpu_service/job_queue.py` | One worker for startup testing and generation, readiness state, WAV/WPM validation and atomic publication |
| `gpu_service/f5_generator.py` | F5-TTS adapter and an explicit demo-silence generator |
| `psychopy_sync/calibration_check.py` | Separate calibration check; no experiment EDF recording |
| `tests/` | Hardware-free timing, lifecycle, CSV, HTTP and launcher checks |

The experiment computer controls text flips and scheduled PTB audio starts. Audio cache completion is logged separately from playback events. Hardware timing needs validation on the experiment setup. The GPU service never controls stimulus onset or EyeLink.

See [experiment flow](condition1.md) and [audio service](network-audio.md) for execution and output details.
