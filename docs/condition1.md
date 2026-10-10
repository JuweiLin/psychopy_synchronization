# Experiment flow and timing

## Before a session

1. Install PsychoPy and wxPython. For real recording (`dummy_mode=False`), also install SR Research PyLink (`pylink`) and `EyeLinkCoreGraphicsPsychoPy`.
2. For real recording, connect the EyeLink Host and verify `eyelink_ip` in the root `config.py` (currently `100.1.1.1`).
3. The display defaults to screen 0, fullscreen and 1920 × 1080. The formal experiment measures refresh rate; it does not use the calibration check's assumed 60 Hz. Advanced display defaults remain in `psychopy_sync/config.py`.
4. Set `condition1_count` and `condition2_count` in the root `config.py`. Confirm that `assets/articles/` contains enough article CSVs.
5. Leave `tts_server_url=""` for a recording-only test, or set the GPU service origin for audio generation. Save changes and reopen the launcher.

Double-click `Start Experiment.bat` on Windows or `Start Experiment.command` on macOS, enter a participant ID and click **Start Experiment**. The terminal window is a launch helper; no command input is required. The login and experiment prompts are in English. The launcher checks only the modules required by the configured mode before starting; real tracker connectivity is checked by the experiment process.

## Dummy mode

`dummy_mode` in the root `config.py` is currently `True`. This mode does not require or probe `pylink` or `EyeLinkCoreGraphicsPsychoPy`, does not connect to a tracker, and skips calibration and all recording/EDF operations. It shows a dummy ready screen before Condition 1. PsychoPy and wxPython are still required for the display and login.

Article selection, sentence pages, keyboard controls, flip timestamps, WPM calculation, event logs and TTS preparation run normally. `tts_server_url` still controls whether audio is generated; dummy mode does not disable the GPU service.

Dummy session files and global tables are stored under `data/dummy/`. Session metadata records `dummy_mode=true`, `edf_status=disabled_dummy`, an empty Host EDF filename and no EyeLink configuration. Local events use `marker_status=disabled_dummy`, not `sent`. No synthetic eye data or EDF is created. The TTS manifest also records the mode.

Set `dummy_mode=False` before real device testing. The remaining recording sequence and EDF recovery details below describe real mode.

## Articles and selection

Each `assets/articles/<article_id>.csv` has one column. Its first cell is the title; each following nonempty cell is one sentence/page. CSV quoting preserves commas and embedded newlines. Empty cells are skipped. The code does not split sentences or repaginate the supplied pages.

Article IDs are filename stems: 1–32 ASCII letters, digits, `_` or `-`. Case-insensitive duplicate IDs are rejected; duplicate titles are allowed. The title does not count toward reading word count and is not displayed as body text.

At startup, the code randomly selects `condition1_count + condition2_count` distinct articles, then assigns the first group to Condition 1 and the remainder to Condition 2. Order is randomized within this selection. The internal default `random_seed=None` creates a new seed; the actual seed, pool IDs and selected order are saved. A fixed integer supplied programmatically reproduces selection for the same file pool and implementation. This does not implement cross-participant counterbalancing.

## Session sequence

1. Create a new session under the participant ID, register the ID if needed, and save article selection and both conditions' stimulus snapshots.
2. Connect to EyeLink, open the PsychoPy window and prepare the Condition 1 pages. Oversized pages fail validation rather than being split.
3. Configure and run EyeLink calibration. The default is HV9 with automatic calibration start and 1000 ms pacing.
4. Open the Host EDF and start one continuous recording. Calibration itself is outside this EDF recording.
5. Show the operator confirmation screen. Verify calibration/validation on the Host before pressing Space.
6. Run Condition 1. Space starts an article, advances each sentence/page and ends the last page. Each article has a separate start prompt.
7. After every Condition 1 article is completed, compute and save reading speed.
8. Create the participant/session TTS directory and prepare one request per selected Condition 2 sentence. With a configured service, wait for generation, download and verification while EyeLink continues recording.
9. End this phase, stop recording, close and download the EDF in real mode, and close the experiment window. The login window returns with the reading speed and data directory.

Condition 2 text presentation and audio playback have not started at step 8; its article rows remain `not_presented`.

## Timing and messages

- `ARTICLE_ONSET`: bound to the flip that displays the first page.
- `PAGE_ONSET`: bound to each subsequent page's first flip.
- `ARTICLE_END`: bound to the flip that removes the last page.

Each marker includes a local event ID, condition, article ID, page and display timestamp. The same event is stored in `user_logs.csv` and sent to EyeLink. The Host stores its own message reception timestamp; online reading speed uses the display flip timestamps, not subtraction of Host reception times.

```text
article_reading_s = ARTICLE_END.timestamp_s - ARTICLE_ONSET.timestamp_s
total_reading_s = sum(article_reading_s)
WPM = 60 * total_word_count / total_reading_s
```

English words are counted using whitespace-separated tokens. Article intervals include within-article page transitions and exclude waits between articles. The final speed uses total words divided by total effective time, not the mean of individual article speeds.

Eye samples, including gaze and pupil area, are stored in EDF. `user_logs.csv` contains events, not individual eye samples. Continuous recording includes the confirmation screen, article waits, reading and configured TTS preparation. Holding Space across screens does not automatically advance the next screen.

## Output and identity

Only participant ID is collected. `users.csv` contains `participant_id` and `created_at_utc`. Loading an older registry removes its legacy name column while preserving IDs and registration times. Reusing an ID creates a new session and keeps earlier sessions.

| Output | Contents |
| --- | --- |
| `data/users.csv` | Participant registry |
| `data/reading_speed.csv` | Participant/session reading speed and totals |
| `data/<id>/<session>/condition1.csv` | Selected articles, order, status, event IDs, timestamps and durations |
| `data/<id>/<session>/condition2.csv` | Selected articles and aggregate audio preparation state |
| `data/<id>/<session>/user_logs.csv` | Timestamped session, condition, article, page and audio events |
| `data/<id>/<session>/eyelink.edf` | Continuous eye samples and messages |
| `data/<id>/<session>/session.json` | Configuration, sampling seed, selections, session/EDF state and TTS location |
| `data/<id>/<session>/stimuli/` | Full-text and page snapshots for both conditions |

## Sentence audio

```text
assets/TTS/<participant_id>/<session_id>/
  requests.json
  manifest.json
  tts_index.csv
  <article_id>/
    sentence_0001.wav
    sentence_0001.json
    sentence_0002.wav
    sentence_0002.json
```

A nonempty CSV sentence/page corresponds to one WAV. Numbering starts at 1 and matches page order. Repeated text at different sentence indices is kept as separate requests/files. Each target duration is `60 × sentence word count / participant WPM`.

The sentence index contains participant/session/article IDs, sentence index, source CSV record number, exact sentence text, word count, target WPM/duration, audio status, actual WAV path, planned WAV path, job ID, actual duration/WPM, checksum and error. `audio_path` stays empty until a WAV is successfully downloaded and verified. `planned_audio_path` does not assert file existence.

Without a service URL, requests, manifest and index are saved as `not_configured`; no placeholder WAV is produced. With a URL, HTTP requests run in a background thread. Each verified sentence is saved individually, and batches are limited to 100 requests per HTTP call. A failed sentence does not prevent other sentences from finishing. An article becomes `cached` only after all its sentences are cached. Its `audio_index_path` links the sentence table; individual job IDs live there.

## Exit and recovery

Escape or an exception triggers cleanup and data saving, with an attempted EDF download in real mode. A partially completed Condition 1 does not publish a complete reading speed or start TTS. Exiting during TTS preserves saved speed and cached files; it stops further local polling/downloads but does not cancel jobs already accepted by the GPU.

EDF transfer first writes `.partial.edf` and publishes `eyelink.edf` only after success. Transfer failure records `edf_status=recovery_required` and the Host EDF filename for manual recovery. Forced termination or power loss can lose locally buffered events; inspect the Host recording for recovery.

One experiment process should own an output directory. Global CSV tables do not support concurrent writers. Hardware and real model behavior still need testing on the experiment computers.
