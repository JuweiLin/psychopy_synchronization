# EDF and sentence images

Clear **Dummy mode (no EyeLink)** in the login window and connect a real EyeLink Host. Dummy mode produces local logs and sentence images, but no eye samples or EDF. The separate calibration check is not an experiment recording.

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
  stimuli/
  screenshots/
    condition1/<article_id>/sentence_0001.png
    condition1/<article_id>/sentence_0002.png
    condition2/<article_id>/sentence_0001.png
  interest_areas/
    condition1/<article_id>/sentence_0001.ias
    condition2/<article_id>/sentence_0001.ias
  aoi_previews/
    condition1/<article_id>/sentence_0001.png
    condition2/<article_id>/sentence_0001.png
```

Every selected CSV page is rendered and captured once before calibration/recording. No sentence image is flipped to the participant during this preparation. Captures use the same TextStim objects and drawing code as reading. Condition 1 includes its keyboard footer; Condition 2 shows only the sentence. Each PNG covers the entire window and must have the same dimensions as EyeLink's `DISPLAY_COORDS`. A mismatch stops preparation instead of silently changing the coordinate system.

Legacy OpenGL TextStim rendering on macOS Retina displays applies an extra 2x pixel scale. Text height, wrap width and footer position are compensated together so they still refer to the framebuffer pixels used by EyeLink. Standard Windows and newer OpenGL rendering retain their normal scale.

`sentence_pages.csv` contains the condition, article ID, sentence index, source CSV record number, exact text, trial ID, relative PNG path, image checksum/dimensions, presentation status, start/end event IDs, local flip timestamps and duration. Images can exist for pages that were never presented; their status remains `not_presented`. An aborted/failed page is flagged separately. A connection/flip failure without a confirmed offset leaves an open interval marked `interrupted`.

## Data Viewer import

Each page is now laid out as individual word TextStim objects. The program measures the chosen font, places words from left to right, and wraps between whitespace tokens when the configured width is reached. Explicit line breaks are retained. The text block is vertically centered and starts at the left edge of the configured text area. This replaces whole-sentence TextStim wrapping, so line breaks and spacing can differ from earlier sessions. Each CSV page remains one trial; oversized words and overflowing pages fail preparation rather than creating additional pages.

The same positions generate word AOI rectangles. Each whitespace token is one AOI, including attached punctuation (`don't`, `sentence.`). IDs restart at 1 per page; repeated words have distinct IDs. Labels contain the word index and text, with non-ASCII characters escaped. `word_aois.csv` retains the exact word, line number, ID/label, zero-based/end-exclusive character offsets, coordinates and links to the trial, screenshot and IAS file. Coordinates are integer framebuffer pixels with an upper-left origin and inclusive right/bottom edges. Two-pixel padding is limited at the midpoint of each adjacent word gap to avoid overlap. Keyboard instructions have no AOIs.

`sentence_pages.csv` also records the IAS path, hash, status and word count; `session.json` records the layout version and coordinate convention. `aoi_previews/` contains screenshot copies with red AOI rectangles for inspection, never shown to participants. All images, layouts and IAS files are prepared before calibration/recording.

1. Copy the **whole session folder**, preserving the EDF, `screenshots/` and `interest_areas/` hierarchy.
2. Import `eyelink.edf` into EyeLink Data Viewer. Images are referenced relative to that EDF's location. If the software asks for an image directory, point it to the copied session folder and keep the relative hierarchy intact.
3. Each sentence is a separate trial. Trial variables `condition`, `article_id` and `sentence_index` identify its place in the experiment. Use them to group results by article or condition.
4. Inspect the background screenshot and gaze overlay. Confirm text and gaze use the same screen coordinates.
5. Word AOIs load through the trial's `!V IAREA FILE` message. Enable interest-area outlines in the Spatial Overlay view and inspect them against the words. There is no need to use **Auto Segment Image into Interest Areas**. Compare `aoi_previews/` and `word_aois.csv` if anything looks misplaced. Older EDFs without the IAS message still need manual association of compatible AOI files or Data Viewer's segmentation tools; updating the program does not add AOIs to old recordings.
6. Export the required fixation, interest-area or sample reports from Data Viewer. These reports are analysis outputs; the experiment itself saves the raw EDF and event/page tables.

The EDF contains unprefixed Data Viewer commands, for example:

```text
TRIALID c1_A_s0001
!V TRIAL_VAR condition condition1
!V TRIAL_VAR article_id A
!V TRIAL_VAR sentence_index 1
!V IMGLOAD FILL screenshots/condition1/A/sentence_0001.png
!V IAREA FILE interest_areas/condition1/A/sentence_0001.ias
SENTENCE_ONSET
...
SENTENCE_OFFSET
TRIAL_RESULT 0
```

Trial start/image/AOI/onset messages are sent in the first-flip callback. The previous sentence's offset/result is sent on the same flip that replaces it with the next sentence, before starting the next trial. The final sentence ends on the blank flip at article end. Interrupted trials use `TRIAL_RESULT 1` when an offset can still be recorded. Recording remains continuous across all these analysis trials; no per-sentence stop/start is performed.

`user_logs.csv` saves the exact message strings, including Data Viewer commands, alongside local event IDs and flip timestamps. EDF timestamps are EyeLink message-reception times; local reading durations use PsychoPy flip timestamps. Software messages do not measure physical screen/speaker latency. Validate overlays and audiovisual timing on the acquisition hardware before formal collection.

Protocol reference: [SR Research Data Viewer integration messages](https://www.sr-research.com/support/thread-83.html). Segmentation reference: [SR Research text interest areas](https://www.sr-research.com/support/thread-167-post-167.html).

## EDF verification and recovery

`session.json` records `edf_status`, `edf_path`, `edf_bytes` and `host_edf_name`.

- `downloaded`: a nonempty local `eyelink.edf` was saved and the transfer return count matched its byte size.
- `disabled_dummy`: no tracker recording or EDF was requested.
- `not_opened`: the experiment failed or stopped before opening an EDF.
- `recovery_required`: a close/download/verification error occurred. Read `edf_error` and `cleanup_errors`, and recover `host_edf_name` from the EyeLink Host using SR Research's file-transfer tools.

Downloads use `eyelink.partial.edf` as a staging file, with up to three attempts. An incomplete transfer is never published as `eyelink.edf`. Byte-count verification does not replace opening the EDF in Data Viewer to confirm the recorded samples. A forced process kill, power loss or network failure can prevent automatic transfer; keep the Host file until the local file has been checked.
