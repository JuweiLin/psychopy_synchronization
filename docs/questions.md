# Article titles and questions

Each article CSV's first record is its title. It appears centered on its own
page. Press Space to proceed to that article's 1500 ms baseline and body. The
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
handled in the importer; no fuzzy answer matching is used. Pilot feedback/rating
fields are not presented. Source attribution is OneStopQA / STARC, Berzak,
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
questions do not enter reading-speed or TTS duration calculations. The existing
TTS speed policy is unchanged by this feature.
