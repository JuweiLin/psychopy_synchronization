# Experiment flow and timing

## Before a session

1. Install PsychoPy and wxPython. For real recording (participant IDs 1–200), also install SR Research PyLink (`pylink`) and `EyeLinkCoreGraphicsPsychoPy`.
2. For real recording, connect the EyeLink Host and verify `eyelink_ip` in the root `config.py` (currently `100.1.1.1`).
3. The display defaults to screen 0, fullscreen and 1920 × 1080. The formal experiment measures refresh rate; it does not use the calibration check's assumed 60 Hz. Advanced display defaults remain in `psychopy_sync/config.py`.
4. Keep `condition1_count = 4` and `condition2_count = 4` for the frozen schedule. Confirm that `assets/articles/` contains all twelve study CSVs and `assets/user_assignments.csv` is present.
5. Leave `tts_server_url=""` for a recording-only test, or set the GPU service origin for audio generation. Save changes and reopen the launcher.

Double-click `Start Experiment.bat` on Windows or `Start Experiment.command` on macOS, enter a participant ID and click **Start Experiment**. The terminal window is a launch helper; no command input is required. The login and experiment prompts are in English. The launcher checks only the modules required by the configured mode before starting; real tracker connectivity is checked by the experiment process. When a GPU URL is configured, the login checks `/ready` in the background and again before each session. Loading is retried automatically. An offline, incompatible or failed server prevents starting; **Recheck** retries after a correction. The empty-URL reading-only workflow remains available.

## Dummy mode

Enter **0** in the login window, then click **Start Dummy Session**. There is no mode checkbox or dummy-mode setting in the root config. The launcher and experiment process derive the mode from the participant ID. ID 0 randomly draws one Condition 1 article and two Condition 2 articles without overlap, using a fresh seed each session. It does not claim a formal assignment. Dummy-mode session preflight does not require or probe `pylink` or `EyeLinkCoreGraphicsPsychoPy`, does not connect to a tracker, and skips calibration and all recording/EDF operations. It shows a dummy ready screen before Condition 1. PsychoPy and wxPython are still required for the display and login.

ID 0 also exposes **Audio Onset Debug...**, a separate direct WPM sweep that skips Condition 1. It tests one editable text at several generated speeds and records manual onset ratings alongside saved WAVs and PTB playback logs. See [audio debug](audio-debug.md).

Article selection, sentence pages, keyboard controls, flip timestamps, WPM calculation, event logs and configured Condition 2 playback run normally. Condition 2 requires PsychoPy's PTB and soundfile dependencies even in dummy mode. `tts_server_url` still controls whether audio is generated; dummy mode does not disable the GPU service. A demo-silence server can pass the readiness check only in dummy mode; real EyeLink sessions require a verified F5-TTS server when a URL is configured.

Dummy session files and global tables are stored under `data/dummy/`. Session metadata records `dummy_mode=true`, `edf_status=disabled_dummy`, an empty Host EDF filename and no EyeLink configuration. Local events use `marker_status=disabled_dummy`, not `sent`. No synthetic eye data or EDF is created. The TTS manifest also records the mode.

Use an ID from **1–200** for real device testing. The remaining recording sequence and EDF recovery details below describe real mode.

## Articles and selection

Each `assets/articles/<article_id>.csv` has one column. Its first cell is the title; each following nonempty cell is one sentence/page. CSV quoting preserves commas and embedded newlines. Empty cells are skipped. The code does not split sentences or repaginate the supplied pages.

Article IDs are filename stems: 1–32 ASCII letters, digits, `_` or `-`. Case-insensitive duplicate IDs are rejected; duplicate titles are allowed. The first CSV cell is displayed as a separate centered title page after the baseline. It does not count toward reading word count/duration or TTS. Every body line is horizontally centered, and the complete text block is vertically centered. Screenshots and word AOIs follow the same positions.

Formal IDs map directly to the frozen rows of `assets/user_assignments.csv`: 1 → R001 through 200 → R200. Every row contains an instruction group (SYNC/FLEX), list ID and four ordered article IDs for each condition. The program loads that order without another random draw. Each formal participant has eight different articles and two low/two high readability articles per condition. ID 0 uses the separate smaller random draw described above. Group-specific instruction text is pending; both groups currently use the common prompt and the same playback behavior.

`assets/articles/` contains the twelve articles extracted from the pilot workbook. The original body Screen boundaries and hard line breaks are preserved; a page is not necessarily a single sentence. The title Screen becomes the CSV header. Six selected questions per article are now in `assets/questions/<article_id>.csv`; five fixed feedback prompts follow the comprehension questions. `assets/stimulus_import.json` records source checksums and the Screen-to-page mapping; `assets/questions/import_manifest.json` documents answer verification. The study still estimates speed from Condition 1; this import does not add the planning document's separate pre-block VO speed calibration.

## Session sequence

1. Create a new session under the participant ID, register the ID if needed, and save article selection and both conditions' stimulus snapshots.
2. Connect to EyeLink, open the PsychoPy window and prepare the pages for both conditions. Oversized pages fail validation rather than being split. Capture every selected page to a full-screen PNG in the back buffer before calibration/recording.
3. Configure and run EyeLink calibration. The default is HV9 with automatic calibration start and 1000 ms pacing.
4. Open the Host EDF and start one continuous recording. Calibration itself is outside this EDF recording.
5. Show the operator confirmation screen. Verify calibration/validation on the Host before pressing Space.
6. Run Condition 1. Show one central `+` baseline for 1500 ms, then the title until Space, followed directly by the first body page. Space advances each page and ends the last page. Pages within the article have no additional baselines. After the body ends, present that article's questions in order with four mouse-click answer buttons, without showing the article or correctness feedback. Then collect five fixed article feedback answers.
7. After all Condition 1 articles, comprehension questions and feedback are completed, compute and save reading speed.
8. Create the participant/session TTS directory and submit every selected Condition 2 sentence in background HTTP batches of at most 100. GPU generation is queued in article/sentence order.
9. Wait only for the next article's complete set of verified local WAVs, then preload them on the main thread. Show one 1500 ms `+` baseline, then its title until Space, then display its first body page and schedule the matching WAV using PTB. Automatically advance subsequent pages after audio completion, without extra baselines. Ask the article's button questions and then five fixed feedback questions after the body ends. Later articles continue generating/downloading in the background. Repeat for each Condition 2 article.
10. Stop recording after both conditions, close and download the EDF in real mode, and close the experiment window. The login window returns with the reading speed, data directory and verified EDF path/byte count or recovery filename.

With no service URL, Condition 2 is explicitly skipped, its article rows remain `not_presented`, and requests/index files are saved as `not_configured`.

## Timing and messages

Each article has one fixed-duration baseline before its title, in both real and dummy mode. The white cross uses the reading screen's black background. This keeps the background/color scheme constant; it does not equalize total screen luminance between a cross and text. The baseline is a timed display, with no gaze-contingent fixation gate. Space cannot shorten it; Escape can stop the session. The actual duration is bounded by refresh timing and processing, and both ends are saved from real flips.

`BASELINE_START` occurs on the cross's first flip. `BASELINE_END`, `PASSAGE_START` and the first `SENTENCE_START` occur on the flip that replaces the cross with the first sentence. `SENTENCE_END` occurs on the flip that replaces that sentence. `PASSAGE_END` occurs on the final removal flip, before closing its Data Viewer trial. `CONDITION_START`/`CONDITION_END` identify the conditions. `SENTENCE_ONSET`/`SENTENCE_OFFSET` are retained as aliases. Baseline, passage, sentence and audio markers are unprefixed for Data Viewer message-based analysis; identity is available in trial variables and the local log columns.

- `ARTICLE_ONSET`: bound to the flip that displays the first page.
- `PAGE_ONSET` / `PAGE_END`: bound to every sentence's display/removal flip in both conditions.
- `ARTICLE_END`: bound to the flip that removes the last page.
- Condition 2 also logs every `PAGE_ONSET` and `PAGE_END`, plus `AUDIO_START`, `AUDIO_END` and interrupted playback (`AUDIO_ABORT`). `AUDIO_START` records the display flip and requested PTB start time, job ID and WAV path. `AUDIO_END` records when the main loop observes PTB completion. These are software playback events, not measured acoustic onset/offset. Verify physical audiovisual timing on the experiment hardware; see [PsychoPy scheduling](https://psychopy.org/api/sound/playback.html#preschedule-your-sound).

Each local log row includes an event ID, condition, article ID, page and timestamp. Data Viewer protocol messages and named analysis markers are sent unprefixed; other experiment markers retain the local event prefix. The Host stores its own message reception timestamp; online reading speed uses the display flip timestamps, not subtraction of Host reception times.

```text
sentence_reading_s = PAGE_END.timestamp_s - PAGE_ONSET.timestamp_s
article_reading_s = sum(sentence_reading_s)
total_reading_s = sum(article_reading_s)
WPM = 60 * total_word_count / total_reading_s
```

English words are counted using whitespace-separated tokens. `reading_duration_s` sums the visible sentence intervals and excludes the pre-article baseline and between-article waits. `elapsed_duration_s` is the first-sentence-onset to last-sentence-offset interval. `baseline_duration_s` and paired baseline timestamps are saved separately in the condition table. Condition 2 reading durations never contribute to Condition 1 WPM. The final speed uses total words divided by total effective reading time, not the mean of individual article speeds.

Titles and question intervals are also excluded. `question_responses.csv` records selected letters/text, correctness and response time from the question's first flip to the observed fresh mouse press. `auxiliary_pages.csv` records title/question visible intervals and image/AOI associations. Completed reading intervals stay completed if the participant subsequently stops during questions; unanswered questions retain their own status. See [question schema and responses](questions.md).

The five fixed article feedback pages are also excluded. `article_feedback.csv`
records each continuous rating, No/Yes/Unsure answer, typed note and response time
from that feedback page's first flip to the observed Continue click. Feedback
uses separate `phase=feedback` trials, initial-form screenshots and control AOIs.
`FEEDBACK_START`, `FEEDBACK_RESPONSE` and `FEEDBACK_END` carry IDs F01–F05.

Eye samples, including gaze and pupil area, are stored in EDF. `user_logs.csv` contains events, not individual eye samples. Continuous recording includes the confirmation screen, article waits, reading, configured TTS preparation and Condition 2 playback. Holding Space across screens does not automatically advance the next screen.

## Output and identity

Only participant ID is collected. The desktop login accepts whole numbers from `0` to `200`, inclusive, and shows an English error for other inputs. Leading zeros are removed (`001` becomes `1`). `users.csv` contains `participant_id`, `created_at_utc`, `allocation_slot`, `instruction_group`, `list_id`, `schedule_version` and `assignment_sha256`. Older registries gain these columns while retaining IDs and dates and dropping legacy names. Reusing an ID creates a new session with the same frozen assignment and keeps earlier sessions; changing an already bound schedule raises an error. Numeric login validation does not rename or delete existing sessions with older ID formats. Assigned slots and completed article/session statuses are separate records.

| Output | Contents |
| --- | --- |
| `data/users.csv` | Participant registry |
| `data/reading_speed.csv` | Participant/session reading speed and totals |
| `data/<id>/<session>/condition1.csv` | Selected articles, order, status, event IDs, timestamps and durations |
| `data/<id>/<session>/condition2.csv` | Selected articles, presentation timing/status and aggregate audio preparation state |
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

A nonempty CSV sentence/page corresponds to one WAV. Numbering starts at 1 and matches page order. Repeated text at different sentence indices is kept as separate requests/files. Each target duration is `60 × sentence word count / target WPM`. Target WPM is the measured reading speed limited by root `speed_cap`: True = 210, False = no cap, or a positive numeric WPM limit. Raw reading speed is preserved. `reading_speed.csv`, the TTS index and manifest record the target and whether it was capped. Audio onset debug uses its explicitly requested speeds without this cap.

The sentence index contains participant/session/article IDs, sentence index, source CSV record number, exact sentence text, word count, target WPM/duration, audio status, actual WAV path, planned WAV path, job ID, actual duration/WPM, checksum and error. `audio_path` stays empty until a WAV is successfully downloaded and verified. `planned_audio_path` does not assert file existence.

Without a service URL, requests, manifest and index are saved as `not_configured`; no placeholder WAV is produced. With a URL, HTTP requests run in a background thread. All batches are submitted before waiting on jobs; downloaded audio events are saved at article boundaries and during wait screens so file writes do not interrupt sentence display. Each verified sentence is saved individually, and batches are limited to 100 requests per HTTP call. A failed sentence does not prevent other sentences from finishing. An article becomes `cached` only after all its sentences are cached. The display waits for each article separately; ready first-article audio does not wait on later articles. Its `audio_index_path` links the sentence table; individual job IDs live there.

## Exit and recovery

Escape or an exception triggers cleanup and data saving, with an attempted EDF download in real mode. A partially completed Condition 1 does not publish a complete reading speed or start TTS. Exiting during TTS or Condition 2 playback preserves saved speed, cached files and partial presentation logs; active audio is stopped. It stops further local polling/downloads but does not cancel jobs already accepted by the GPU.

EDF transfer first writes `.partial.edf`, retries up to three times, and publishes `eyelink.edf` only after the received byte count matches a nonempty local file. Transfer failure records `edf_status=recovery_required` and the Host EDF filename for manual recovery; the login also displays the recovery name. Forced termination or power loss can lose locally buffered events; inspect the Host recording for recovery.

Data Viewer trials are per article baseline and body page, with relative screenshot paths sent via `!V IMGLOAD FILL`. Participant ID, instruction group, allocation slot and list ID are included as trial variables. This does not interrupt continuous recording or change article-level WPM. `sentence_pages.csv` retains its existing filename/index fields for the supplied pages. Word AOIs and the cross AOI are exported automatically; see [EDF and sentence images](data-viewer.md).

One experiment process should own an output directory. Global CSV tables do not support concurrent writers. Hardware and real model behavior still need testing on the experiment computers.
