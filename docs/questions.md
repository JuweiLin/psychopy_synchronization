# Article titles and questions

Each article CSV's first record is its title. It appears centered on its own
page after the article's 1500 ms fixation baseline. Press Space on the title to begin the body directly. The
title is excluded from TTS, word count and reading time. Each body line is
horizontally centered; the text block is vertically centered. Word AOIs and
screenshots use the same layout.

After every completed article in both conditions, its questions appear one at a
time. The article is hidden. Click one of the four answer buttons to submit and
advance; the program does not show correctness feedback. A held mouse button
cannot automatically answer the next question. Escape stops and saves available
responses. No questions or title text are sent to TTS. Audio onset debug remains
a separate diagnostic and does not run article questions.

## Question CSVs

Place one file per article in `assets/questions/<article_id>.csv` using this
header, in this exact order:

```csv
article_id,question_id,question_order,content,OptionA,OptionB,OptionC,OptionD,CorrectAnswer
```

- `article_id` must match the article filename.
- `question_id` must be unique within the article and use 1–64 ASCII letters,
  digits, underscores or hyphens. Supplied IDs, such as `A02_P01_Q2`, include the
  article ID and preserve the pilot's original identifiers.
- `question_order` is consecutive from 1 and determines display order. Question
  and option order are not randomized again at runtime.
- `content` and the four option columns contain nonempty text.
- `CorrectAnswer` is the displayed correct letter: `A`, `B`, `C` or `D`.

Quote cells containing commas or line breaks. Any positive question count is
supported; the imported twelve files each contain six questions (72 total).
Missing/malformed files for a selected article stop preparation before recording.
When adding an article, add its matching question CSV and, for formal IDs, update
the frozen assignment schedule through the intended study procedure.

## Imported answer key

Questions and shuffled option text come from the supplied pilot review workbook.
Answers were verified using [the official OneStopQA dataset](https://github.com/berzak/onestop-qa).
Its first source answer is correct; the importer matches that answer's text to
the pilot's displayed A–D choices. Article titles are matched explicitly because
pilot IDs A28 and A29 are reversed relative to the official article ordering.

`assets/questions/import_manifest.json` stores source hashes, per-file hashes
and a question-by-question audit. Three pilot choices correct source spelling:
`irth` → `birth`, `MP3 musi` → `MP3 music`, and `given are` → `given area`. The
last correction affects the correct choice of `A30_P03_Q2` and is explicitly
handled in the importer; no fuzzy answer matching is used. Five fixed post-article feedback prompts are implemented separately in code. Source attribution is OneStopQA / STARC, Berzak,
Malmaud & Levy (2020), CC BY-SA 4.0.

## Results and eye tracking

Each session saves `question_responses.csv` with participant/session, condition,
article/question IDs, order, exact content/options/correct answer, source hash,
selected letter/text, correctness (`1`/`0`), response time and paired events.
Unpresented/unanswered items have empty responses. The response timestamp is when
the main loop observes a fresh mouse press; it is not a hardware latency measure.

`auxiliary_pages.csv` indexes title/question trials, screenshots, IAS files,
status and first/last flip timestamps. Exact question CSV snapshots and title
text are retained under `stimuli/`. Data Viewer uses `phase=title` and
`phase=question`; question trials include `question_id`, `question_order` and
`selected_answer`. Button AOIs are `option_A` through `option_D`.

Title/question onset and removal use flip callbacks. `QUESTION_RESPONSE` records
the observed answer. EyeLink recording stays continuous. Titles, baselines and
questions do not enter reading-speed or TTS duration calculations. The TTS target speed uses the root `speed_cap` setting; see the project README.

## Fixed article feedback

After the comprehension questions, every article in both conditions receives
the same five English feedback prompts, defined in `psychopy_sync/feedback.py`.
No feedback CSV needs to be added when adding an article.

1. How easy was it to follow the article across screen changes?
2. How appropriate were the six questions as a set?
3. Did any questions repeat the same point unnecessarily?
4. Was an important article idea missing from the questions?
5. Any additional screen, text, audio, or question concerns?

The first two pages have a centered question above a continuous slider. Four
ticks mark 1, 2, 3 and 4. The first scale labels its endpoints **1 very difficult**
and **4 very easy**; the second uses **1 not appropriate** and **4 very appropriate**.
Click or drag to any position, then click Continue. There is no preselected
answer or snapping to integers. The saved `rating` is the continuous 1–4 value;
the on-screen value shows two decimals.

Items 3 and 4 use No / Yes / Unsure buttons and an editable text box. Yes requires
a note; No and Unsure may also include notes. Item 3 shows the article's original
question IDs so they can be cited. Item 5 is an optional text box: blank plus
Continue records a completed response with no concern. These forms use
[PsychoPy TextBox2](https://psychopy.org/api/visual/textbox2.html) for editable text.
Nothing on these pages is sent to TTS.

`article_feedback.csv` contains one row per participant/session/condition/article
and feedback ID (`F01`–`F05`). It snapshots the exact prompt, scale anchors and
response kind, and records rating, selected answer, notes, assignment identity,
status, onset/offset timestamps, response timestamp and event IDs. For both
comprehension and feedback questions, `response_time_s` is seconds from the
first displayed question flip to the observed submission mouse press. Feedback
submission is Continue, so its time includes adjusting the slider or writing
notes. Escape retains the current partial answer and completed earlier answers.
Feedback time does not affect reading speed.

Feedback has separate Data Viewer trials with `phase=feedback`, an initial
page screenshot and control AOIs. `FEEDBACK_START F01`,
`FEEDBACK_RESPONSE F01 <value>` and `FEEDBACK_END F01` identify each interval;
the other feedback IDs follow the same pattern. Screenshots represent the blank
form, while the CSV and response event retain the submitted values and notes.
