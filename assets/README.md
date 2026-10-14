# Study materials

`user_assignments.csv` contains the frozen 200-slot schedule from the supplied
planning document, version 4.0 dated 13 October 2026, seed 20261013. Participant
IDs 1–200 map to R001–R200. The eight numbered article columns give presentation
order: four visual-only pagesets followed by four TTS pagesets. SYNC/FLEX is a
participant-level instruction group. Full group-specific instruction wording
has not yet been supplied; the experiment currently retains its common prompt.

ID 0 randomly draws one Condition 1 article and two Condition 2 articles for
each dummy session, without overlap or a formal allocation slot. Its results
stay under `data/dummy/`. The frozen table records assignments;
completed readings are recorded separately in each session's condition tables.

`articles/` contains one UTF-8 CSV per study article. The first cell is the title
and subsequent cells are the workbook's body Screens, preserving page order and
hard line breaks. The title appears as its own centered title page, followed by
the 1500 ms baseline and body pages. It is excluded from WPM and TTS. A body page
may contain several sentences and produces one WAV. Body lines are centered and
their text block is vertically centered.

`questions/<article_id>.csv` contains each article's selected pilot questions,
one file per article. The nine columns are `article_id`, `question_id`,
`question_order`, `content`, `OptionA`, `OptionB`, `OptionC`, `OptionD`,
`CorrectAnswer`. Order numbers start at 1; the correct answer is a displayed
letter A–D. Original IDs such as `A02_P01_Q2` already include the article ID.
The supplied twelve files have six questions each. Add a matching question CSV
when adding an article. `questions/import_manifest.json` records answer-key
provenance and source/pilot spelling differences. Pilot feedback fields are
omitted. Questions are shown after each article, with mouse-click answer buttons.

`stimulus_import.json` records original file hashes, exported CSV hashes, word
counts and the original Screen IDs/Excel row numbers for each body page. The
experiment needs only these exported assets, not the source Office files.
`scripts/import_study_materials.py` can reproduce the import from those files.

The pilot workbook attributes the source texts to OneStopQA / STARC,
Berzak, Malmaud & Levy (2020), and states CC BY-SA 4.0:
https://aclanthology.org/2020.acl-main.507/. This import changes the file format
and omits the pilot form fields; it preserves the title and body Screen text.
