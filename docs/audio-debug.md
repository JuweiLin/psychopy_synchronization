# Audio onset debug

Enter participant ID **0** in the normal login and click **Audio Onset Debug...**.
This opens a separate diagnostic run without reading Condition 1, connecting to
EyeLink or changing formal assignments. The normal **Start Dummy Session** button
still runs one random Condition 1 article followed by two distinct random
Condition 2 articles.

1. Select an article and body page, then click **Load page**. The text can also be
   edited, for example to isolate a sentence whose first words are being lost.
   The editor scrolls vertically for long pasted text. The settings area also
   scrolls when the window is small; Cancel and Generate remain at the bottom.
2. Enter positive WPM values separated by commas or spaces. They are tested in
   the entered order. The default is `100, 150, 200, 250, 300, 400`.
3. Set **Plays per speed** (default 2), then click **Generate and listen**. A real
   F5-TTS server must be ready at `tts_server_url`; silent demo generation is
   rejected for this diagnostic.
4. Press Space to play. After playback, press **C** if the first words are
   complete, **M** if the beginning is missing, **U** if unsure, or **R** to replay
   the same file before moving on. Escape stops and saves the available results.

The diagnostic plays in a window with a scrollable text preview. During playback,
use the mouse wheel, drag the right-hand scrollbar, or press Up/Down,
Page Up/Page Down, Home or End to navigate. Each play starts at the beginning of
the text. Long input is no longer passed through the formal experiment's
single-page height validation; the entire original input is still sent to TTS
and saved in the manifest. The preview wraps text for display only. Formal
experiment pages keep their existing size checks and layout.

Each speed requests one WAV of the same text using the normal target-duration
calculation. Repetitions and R replays reuse that exact WAV rather than generating
another sample. Requests run in the background, with playback starting when the
next requested file is ready. A generation failure at one speed is recorded and
does not prevent later speeds from being checked.

Playback calls the same `ReadingDisplay.play_page` used by Condition 2: verified
local WAV, PTB preloading, start scheduled against the next display flip, and
completion observed through PTB. The debug path does not add leading silence or
an audio warmup. One speaker device is shared across speeds. The diagnostic uses
manual per-clip start prompts rather than the experiment's automatic page chain;
it checks isolated onsets and replays, not the timing of uninterrupted page-to-page
transitions. Report the first play and later repetitions separately if they differ.

Each run saves under `data/dummy/audio_debug/<run>/`:

| File | Contents |
| --- | --- |
| `manifest.json` | Exact text, requested speeds/repetitions, source page reference, server and run status |
| `audio_index.csv` | Target WPM, actual duration/WPM, job ID, WAV path/checksum and per-speed generation status |
| `onset_results.csv` | Each play's speed, repetition, replay attempt, manual onset rating and paired playback events/timestamps |
| `user_logs.csv` | PTB scheduling details, flip onset, observed audio end/abort and generation events |
| `wavs/speed_XXX/sentence_0001.wav` and `.json` | Original verified server output and generation metadata |

Open a saved WAV in another player and listen to the beginning. If the first
words are absent there too, the downloaded audio already lacks them. If they are
present in the file but missing during this diagnostic, investigate playback or
the output device. The software records your judgments; it does not automatically
recognize words, detect a clipping threshold or measure physical speaker onset.
WPM shown in the request is the target rate; inspect actual WPM/duration too.

Debug runs do not append to the participant registry or the reading-speed table.
Escape stops local playback and further polling; jobs already accepted by the
GPU server may finish there. Previously cached files and ratings are retained.
