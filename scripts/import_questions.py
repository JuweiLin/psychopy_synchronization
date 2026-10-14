"""Import the pilot workbook's selected questions and verify shuffled answers.

The official OneStopQA archive supplies answer text. Article titles, question
text and the correct answer must match. Distractor edits are retained and audited.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from zipfile import ZipFile
import xml.etree.ElementTree as ET


FIELDS = ["article_id", "question_id", "question_order", "content", "OptionA", "OptionB", "OptionC", "OptionD", "CorrectAnswer"]


def normalized(text):
    return re.sub(r"\W+", "", unicodedata.normalize("NFKC", text).casefold())


def import_questions(workbook, source_zip, output):
    with ZipFile(source_zip) as archive:
        originals = json.loads(archive.read("onestop_qa.json"))["data"]
    by_title = {normalized(article["title"]): article for article in originals}
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    exported, audit = {}, []
    with ZipFile(workbook) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(node.text or "" for node in item.findall(".//s:t", ns))
                       for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", ns)]
        relationships = {entry.attrib["Id"]: entry.attrib["Target"]
                         for entry in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", ns):
            identifier = sheet.attrib["name"]
            if not re.fullmatch(r"A[0-9]{2}", identifier):
                continue
            target = relationships[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = []
            for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", ns):
                cells = {}
                for cell in row.findall("s:c", ns):
                    value_node = cell.find("s:v", ns)
                    value = value_node.text if value_node is not None else ""
                    if cell.attrib.get("t") == "s":
                        value = strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//s:t", ns))
                    cells[re.sub(r"[0-9]", "", cell.attrib["r"])] = value
                rows.append((int(row.attrib["r"]), cells))
            title = next(cells["A"] for row_number, cells in rows if row_number == 1)
            original = by_title[normalized(title)]
            questions = []
            for row_number, cells in rows:
                match = re.fullmatch(identifier + r"_P([0-9]+)_Q([0-9]+)", cells.get("A", ""))
                if not match:
                    continue
                parts = re.split(r"(?m)^\s*([ABCD])\.\s+", cells["B"])
                if len(parts) != 9 or parts[1::2] != list("ABCD"):
                    raise ValueError(f"Could not parse four choices for {cells['A']}")
                content = parts[0].strip()
                choices = dict(zip(parts[1::2], (value.strip() for value in parts[2::2])))
                source = original["paragraphs"][int(match[1]) - 1]["qas"][int(match[2]) - 1]
                if normalized(content) != normalized(source["question"]):
                    raise ValueError(f"Question content differs from the official source: {cells['A']}")
                edited = [value for value in choices.values() if normalized(value) not in set(map(normalized, source["answers"]))]
                source_answer = source["answers"][0]
                correction = ""
                if cells["A"] == "A30_P03_Q2" and source_answer == "A program that makes drones check every surface of a given are":
                    source_answer += "a"
                    correction = "Official answer ends in 'given are'; pilot fixes the spelling to 'given area'."
                correct = [letter for letter, value in choices.items() if normalized(value) == normalized(source_answer)]
                if len(correct) != 1:
                    raise ValueError(f"Correct answer is ambiguous for {cells['A']}")
                questions.append(dict(article_id=identifier, question_id=cells["A"], question_order=len(questions) + 1,
                    content=content, **{"Option" + letter: value for letter, value in choices.items()}, CorrectAnswer=correct[0]))
                audit.append(dict(article_id=identifier, question_id=cells["A"], source_title=original["title"],
                    source_paragraph=int(match[1]), source_question=int(match[2]), source_excel_row=row_number,
                    correct_answer=correct[0], verification="stem and correct answer match; source answer 0 remapped",
                    source_answer_spelling_correction=correction,
                    edited_pilot_choices=edited,
                    unmatched_source_choices=[value for value in source["answers"] if normalized(value) not in set(map(normalized, choices.values()))]))
            if len(questions) != 6:
                raise ValueError(f"Expected six selected questions for {identifier}")
            exported[identifier] = questions
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for identifier, rows in exported.items():
        path = output / f"{identifier}.csv"
        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
        hashes[identifier] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(source_workbook=workbook.name, source_workbook_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
        source_url="https://github.com/berzak/onestop-qa/blob/master/annotations/onestop_qa.zip",
        source_zip_sha256=hashlib.sha256(source_zip.read_bytes()).hexdigest(),
        license="CC BY-SA 4.0", attribution="OneStopQA / STARC; Berzak, Malmaud & Levy (2020)",
        note="Articles matched by title, not numeric source position; pilot A28/A29 differ from the source ordering.",
        question_count=len(audit), csv_sha256=hashes, answer_audit=audit)
    (output / "import_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported and verified {len(audit)} questions across {len(exported)} article CSVs.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    import_questions(args.workbook, args.source_zip, args.output_dir)


if __name__ == "__main__":
    main()
