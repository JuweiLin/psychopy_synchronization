"""Extract article CSVs and the frozen schedule without importing pilot questions.

Uses only the Python standard library. The workbook and planning document are
read-only inputs; the experiment subsequently uses the exported assets alone.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET


def workbook_articles(path):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    articles = {}
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(node.text or "" for node in item.findall(".//s:t", ns))
                      for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", ns)]
        relationships = {entry.attrib["Id"]: entry.attrib["Target"]
                         for entry in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall("s:sheets/s:sheet", ns):
            identifier = sheet.attrib["name"]
            if not re.fullmatch(r"A[0-9]{2}", identifier):
                continue
            target = relationships[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            screens = []
            for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", ns):
                cells = {}
                for cell in row.findall("s:c", ns):
                    value_node = cell.find("s:v", ns)
                    value = value_node.text if value_node is not None else ""
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//s:t", ns))
                    cells[re.sub(r"[0-9]", "", cell.attrib["r"])] = value
                match = re.fullmatch(identifier + r"Screen([0-9]+)", cells.get("A", ""))
                if match:
                    if not cells.get("B", "").strip():
                        raise ValueError(f"Empty article screen: {cells['A']}")
                    screens.append((int(match[1]), cells["A"], cells["B"], int(row.attrib["r"])))
            if [screen[0] for screen in screens] != list(range(1, len(screens) + 1)) or len(screens) < 2:
                raise ValueError(f"Article screens are missing or out of order: {identifier}")
            articles[identifier] = dict(title=screens[0][2], pages=[screen[2] for screen in screens[1:]],
                                       source_screen_ids=[screen[1] for screen in screens[1:]],
                                       source_excel_rows=[screen[3] for screen in screens[1:]])
    return articles


def document_schedule(path):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    rows = []
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    for row in root.findall(".//w:tbl/w:tr", ns):
        cells = ["".join(node.text or "" for node in cell.findall(".//w:t", ns)) for cell in row.findall("w:tc", ns)]
        if len(cells) != 6 or not re.fullmatch(r"R[0-9]{3}", cells[0]):
            continue
        if cells[2] != "VO → TTS" or cells[1] not in ("SYNC", "FLEX"):
            raise ValueError(f"Unexpected mode order or group in {cells[0]}")
        result = dict(participant_id=str(int(cells[0][1:])), allocation_slot=cells[0],
                      instruction_group=cells[1], list_id=cells[5], schedule_version="4.0-2026-10-13",
                      seed="20261013")
        for condition, cell in (("condition1", cells[3]), ("condition2", cells[4])):
            identifiers = [identifier.strip() for identifier in cell.split("·")]
            if len(identifiers) != 4:
                raise ValueError(f"Expected four articles per condition in {cells[0]}")
            result.update({f"{condition}_article_{index}": identifier for index, identifier in enumerate(identifiers, 1)})
        rows.append(result)
    if [row["participant_id"] for row in rows] != [str(index) for index in range(1, 201)]:
        raise ValueError("Expected the complete R001–R200 schedule in order")
    return rows


def write_csv(path, rows, fields=None):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        if fields is None:
            csv.writer(stream).writerows(rows)
        else:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--schedule-document", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    args = parser.parse_args()
    articles = workbook_articles(args.workbook)
    schedule = document_schedule(args.schedule_document)
    article_fields = [f"condition{condition}_article_{index}" for condition in (1, 2) for index in range(1, 5)]
    used = {row[field] for row in schedule for field in article_fields}
    if len(articles) != 12 or used != articles.keys():
        raise ValueError("The workbook and schedule must contain the same twelve articles")
    for row in schedule:
        if len({row[field] for field in article_fields}) != 8:
            raise ValueError(f"Repeated article in {row['allocation_slot']}")
    folder = args.assets_dir / "articles"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = dict(source_workbook=args.workbook.name, source_document=args.schedule_document.name,
                    source_workbook_sha256=hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
                    source_document_sha256=hashlib.sha256(args.schedule_document.read_bytes()).hexdigest(),
                    source_text_attribution="OneStopQA / STARC, Berzak, Malmaud & Levy (2020)",
                    source_text_url="https://aclanthology.org/2020.acl-main.507/",
                    source_text_license="CC BY-SA 4.0, as stated in the pilot workbook",
                    schedule_version="4.0-2026-10-13", schedule_seed=20261013,
                    title_handling="CSV header only; excluded from reading and TTS",
                    page_handling="Preserve each body Screen cell and its hard line breaks",
                    questions_imported=False, articles={})
    for identifier, article in articles.items():
        path = folder / f"{identifier}.csv"
        write_csv(path, [[article["title"]]] + [[page] for page in article["pages"]])
        manifest["articles"][identifier] = dict(
            title=article["title"], body_page_count=len(article["pages"]),
            word_count=sum(len(page.split()) for page in article["pages"]),
            source_screen_ids=article["source_screen_ids"], source_excel_rows=article["source_excel_rows"],
            csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assignment_path = args.assets_dir / "user_assignments.csv"
    write_csv(assignment_path, schedule, list(schedule[0]))
    manifest["assignment_sha256"] = hashlib.sha256(assignment_path.read_bytes()).hexdigest()
    (args.assets_dir / "stimulus_import.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Imported {len(articles)} articles and {len(schedule)} participant assignments. No questions imported.")


if __name__ == "__main__":
    main()
