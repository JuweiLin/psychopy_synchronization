# EDF and sentence images

Enter a participant ID from **1–200** in the login window and connect a real EyeLink Host. ID **0** selects dummy mode and produces local logs and page images, but no eye samples or EDF. The separate calibration check is not an experiment recording.

Launch using **Start Experiment**, enter the participant ID, complete calibration/validation and run the reading conditions. Leave the application running while the final **Saving session data. Please wait.** screen is shown. Normal completion and Escape both attempt to stop recording, close the Host EDF and download it before disconnecting. The result window reports the saved EDF path and byte count, or the Host filename to recover if transfer fails.

## Session files

```text
data/<participant_id>/<session_id>/
  eyelink.edf
  session.json
  condition1.csv
  condition2.csv
  user_logs.csv
  sentence_pages.csv
  word_aois.csv
  auxiliary_pages.csv
  question_responses.csv
  stimuli/
  screenshots/
    baseline.png
    condition1/<article_id>/sentence_0001.png
    condition1/<article_id>/sentence_0002.png
    condition2/<article_id>/sentence_0001.png
  interest_areas/
    baseline.ias
    condition1/<article_id>/sentence_0001.ias
    condition2/<article_id>/sentence_0001.ias
  aoi_previews/
    baseline.png
    condition1/<article_id>/sentence_0001.png
    condition2/<article_id>/sentence_0001.png
```

Every selected CSV page is rendered and captured once before calibration/recording. No sentence image is flipped to the participant during this preparation. Captures use the same TextStim objects and drawing code as reading. Condition 1 includes its keyboard footer; Condition 2 shows only the sentence. Each PNG covers the entire window and must have the same dimensions as EyeLink's `DISPLAY_COORDS`. A mismatch stops preparation instead of silently changing the coordinate system.

Legacy OpenGL TextStim rendering on macOS Retina displays applies an extra 2x pixel scale. Text height, wrap width and footer position are compensated together so they still refer to the framebuffer pixels used by EyeLink. Standard Windows and newer OpenGL rendering retain their normal scale.

`sentence_pages.csv` contains the condition, article ID, sentence index, source CSV record number, exact text, trial ID, relative PNG path, image checksum/dimensions, presentation status, start/end event IDs, local flip timestamps and duration. Images can exist for pages that were never presented; their status remains `not_presented`. An aborted/failed page is flagged separately. A connection/flip failure without a confirmed offset leaves an open interval marked `interrupted`.

In both conditions, each article starts with one central white `+` on the same black background for a target of 1500 ms. Sentences within the article follow directly, without further baselines. The cross screenshot and its rectangular AOI are prepared once and reused. The article rows in `condition1.csv` and `condition2.csv` contain the baseline trial ID, image/IAS paths, status, paired event IDs and flip timestamps, target duration and actual duration. Baseline time is excluded from reading speed; `reading_duration_s` sums the visible sentence intervals.

## Data Viewer import

Each body/title page is laid out as individual word TextStim objects. The program measures the chosen font, places words from left to right, and wraps between whitespace tokens when the configured width is reached. Explicit line breaks are retained. Each line is horizontally centered, and the text block is vertically centered. The same positions generate its AOIs. This layout is recorded as `centered_word_textstim_v2`; older sessions keep their original screenshots and coordinates. Each body CSV cell remains one trial; oversized words and overflowing pages fail preparation rather than creating additional pages.

An article now has a separate title trial before its baseline, and question trials after its body. `phase=title` displays the CSV header without audio; `phase=question` displays one question and four answer buttons, with `question_id`, `question_order` and `selected_answer` trial variables. `TITLE_START`/`TITLE_END` and `QUESTION_START <id>`/`QUESTION_END <id>` mark their visible intervals. `QUESTION_RESPONSE <id> <letter>` marks the observed mouse response. `auxiliary_pages.csv` maps these trials to their screenshots, IAS files and timing. Question IAS files contain four button AOIs labelled `option_A`–`option_D`. Filter by `phase` for reading/pupil analyses; neither titles nor questions enter reading-speed calculations.

The same positions generate word AOI rectangles. Each whitespace token is one AOI, including attached punctuation (`don't`, `sentence.`). IDs restart at 1 per page; repeated words have distinct IDs. Labels contain the word index and text, with non-ASCII characters escaped. `word_aois.csv` retains the exact word, line number, ID/label, zero-based/end-exclusive character offsets, coordinates and links to the trial, screenshot and IAS file. Coordinates are integer framebuffer pixels with an upper-left origin and inclusive right/bottom edges. Two-pixel padding is limited at the midpoint of each adjacent word gap to avoid overlap. Keyboard instructions have no AOIs.

`sentence_pages.csv` also records the IAS path, hash, status and word count; `session.json` records the layout version and coordinate convention. `aoi_previews/` contains screenshot copies with red AOI rectangles for inspection, never shown to participants. All images, layouts and IAS files are prepared before calibration/recording.

1. Copy the **whole session folder**, preserving the EDF, `screenshots/` and `interest_areas/` hierarchy.
2. Import `eyelink.edf` into EyeLink Data Viewer. Images are referenced relative to that EDF's location. If the software asks for an image directory, point it to the copied session folder and keep the relative hierarchy intact.
3. Each article has one baseline trial followed by one trial per body page. Trial variables `condition`, `article_id`, `sentence_index` and `phase` identify each trial; the existing `sentence_index` names the supplied page even when it contains multiple sentences. Baselines have `phase=baseline` and `sentence_index=0`; pages have `phase=reading`. `participant_id`, `instruction_group`, `allocation_slot` and `list_id` record the frozen assignment. Join baseline and reading results within participant/session by condition and article ID.
4. Inspect the background screenshot and gaze overlay. Confirm text and gaze use the same screen coordinates.
5. Word AOIs load through the trial's `!V IAREA FILE` message. Enable interest-area outlines in the Spatial Overlay view and inspect them against the words. There is no need to use **Auto Segment Image into Interest Areas**. Compare `aoi_previews/` and `word_aois.csv` if anything looks misplaced. Older EDFs without the IAS message still need manual association of compatible AOI files or Data Viewer's segmentation tools; updating the program does not add AOIs to old recordings.
6. Export the required fixation, interest-area or sample reports from Data Viewer. These reports are analysis outputs; the experiment itself saves the raw EDF and event/page tables.

The EDF contains unprefixed Data Viewer commands, for example:

```text
TRIALID c1_A_baseline
!V TRIAL_VAR condition condition1
!V TRIAL_VAR article_id A
!V TRIAL_VAR sentence_index 0
!V TRIAL_VAR phase baseline
!V IMGLOAD FILL screenshots/baseline.png
!V IAREA FILE interest_areas/baseline.ias
BASELINE_START
...
BASELINE_END
TRIAL_RESULT 0
TRIALID c1_A_s0001
!V TRIAL_VAR condition condition1
!V TRIAL_VAR article_id A
!V TRIAL_VAR sentence_index 1
!V TRIAL_VAR phase reading
!V IMGLOAD FILL screenshots/condition1/A/sentence_0001.png
!V IAREA FILE interest_areas/condition1/A/sentence_0001.ias
PASSAGE_START condition1 A
SENTENCE_START
SENTENCE_ONSET
...
SENTENCE_OFFSET
SENTENCE_END
TRIAL_RESULT 0
```

Trial start/image/AOI/onset messages are sent in the first-flip callback. `BASELINE_END` is sent on the first sentence's flip, before starting its reading trial. The previous sentence's offset/result is sent on the same flip that replaces it with the next sentence, before starting the next trial. The final sentence ends on the blank flip at article end, with `PASSAGE_END condition1 A` before its trial result. Interrupted trials use `TRIAL_RESULT 1` when an offset can still be recorded. Recording remains continuous across all these analysis trials; no per-sentence stop/start is performed. Condition markers and Condition 2 audio markers (`AUDIO_START`, `AUDIO_END`, or `AUDIO_ABORT`) are also recorded.

For Data Viewer interest periods, use `BASELINE_START` to `BASELINE_END` within baseline trials and `SENTENCE_START` to `SENTENCE_END` within reading trials. Passage start and end belong to different sentence trials in a multi-sentence article; aggregate those trials by article for passage-level analysis.

`user_logs.csv` saves the exact message strings, including Data Viewer commands, alongside local event IDs and flip timestamps. EDF timestamps are EyeLink message-reception times; local reading durations use PsychoPy flip timestamps. Software messages do not measure physical screen/speaker latency. Validate overlays and audiovisual timing on the acquisition hardware before formal collection.

Protocol reference: [SR Research Data Viewer integration messages](https://www.sr-research.com/support/thread-83.html). Segmentation reference: [SR Research text interest areas](https://www.sr-research.com/support/thread-167-post-167.html).

## Continuous pupil samples

Real EyeLink sessions save continuous samples to the EDF using `file_sample_data = LEFT,RIGHT,GAZE,AREA,GAZERES,STATUS,INPUT`. Event configuration includes fixation, saccade, blink and message events, with `file_event_data = GAZE,GAZERES,AREA,VELOCITY,STATUS`. There is no Python sample polling loop. The sampling rate and pupil measurement mode remain those configured on the EyeLink Host; the experiment does not assume 500 Hz or convert pupil values to millimetres. See [SR Research file data commands](https://www.sr-research.com/download/dispdoc/cmds7.html).

To export the continuous pupil series, enable **Load Samples** under **Inspector Preferences → Data Loading** before importing the EDF. If already imported without samples, remove that recording from the Data Viewer session and reimport it. Generate a **Sample Report**, including sample timestamps, pupil values, gaze/eye information and the trial variables above. A **Fixation Report** contains fixation-level pupil summaries rather than the continuous series. See [SR Research pupil sample reporting instructions](https://www.sr-research.com/support/thread-169.html).

The experiment saves raw pupil data and the baseline intervals; it does not automatically remove blinks, interpolate missing samples or compute baseline-corrected pupil values. Those steps belong to subsequent analysis. Use the article's baseline trial for its reading trials, and check sample validity before calculating a baseline. Updating the program cannot add baseline periods or new event markers to an earlier EDF; an earlier EDF may already contain pupil samples that can be loaded and reported.

## EDF verification and recovery

`session.json` records `edf_status`, `edf_path`, `edf_bytes` and `host_edf_name`.

- `downloaded`: a nonempty local `eyelink.edf` was saved and the transfer return count matched its byte size.
- `disabled_dummy`: no tracker recording or EDF was requested.
- `not_opened`: the experiment failed or stopped before opening an EDF.
- `recovery_required`: a close/download/verification error occurred. Read `edf_error` and `cleanup_errors`, and recover `host_edf_name` from the EyeLink Host using SR Research's file-transfer tools.

Downloads use `eyelink.partial.edf` as a staging file, with up to three attempts. An incomplete transfer is never published as `eyelink.edf`. Byte-count verification does not replace opening the EDF in Data Viewer to confirm the recorded samples. A forced process kill, power loss or network failure can prevent automatic transfer; keep the Host file until the local file has been checked.
