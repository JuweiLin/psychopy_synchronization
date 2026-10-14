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
hard line breaks. The title is not displayed or synthesized as body text. A page
may contain several sentences and produces one WAV. Pilot questions, answer
choices and feedback fields have not been imported.

`stimulus_import.json` records original file hashes, exported CSV hashes, word
counts and the original Screen IDs/Excel row numbers for each body page. The
experiment needs only these exported assets, not the source Office files.
`scripts/import_study_materials.py` can reproduce the import from those files.

The pilot workbook attributes the source texts to OneStopQA / STARC,
Berzak, Malmaud & Levy (2020), and states CC BY-SA 4.0:
https://aclanthology.org/2020.acl-main.507/. This import changes the file format
and omits the pilot form fields; it preserves the title and body Screen text.
