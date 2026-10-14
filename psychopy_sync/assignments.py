"""Frozen participant assignments exported from the study planning document."""

import csv
from dataclasses import asdict, dataclass, replace
import hashlib
import io
from pathlib import Path

from .event_log import validate_login_participant_id


@dataclass(frozen=True)
class ParticipantAssignment:
    participant_id: str
    allocation_slot: str
    instruction_group: str
    list_id: str
    schedule_version: str
    seed: int
    condition1_articles: tuple
    condition2_articles: tuple
    source_sha256: str
    preview_of: str = ""

    def metadata(self):
        return asdict(self)


def load_assignment(config, participant_id):
    participant_id = validate_login_participant_id(participant_id)
    path = Path(config.assets_dir) / "user_assignments.csv"
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    article_fields = {condition: [f"{condition}_article_{index}" for index in range(1, 5)]
                      for condition in ("condition1", "condition2")}
    required = {"participant_id", "allocation_slot", "instruction_group", "list_id", "schedule_version", "seed"}
    required.update(name for names in article_fields.values() for name in names)
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("The participant assignment table is missing required columns")
    rows = {}
    for row in reader:
        identifier = validate_login_participant_id(row["participant_id"])
        if identifier == "0" or identifier in rows or row["participant_id"] != identifier:
            raise ValueError("The assignment table requires unique participant IDs from 1 to 200")
        groups = {condition: tuple(row[name] for name in names) for condition, names in article_fields.items()}
        if (row["allocation_slot"] != f"R{int(identifier):03d}" or row["instruction_group"] not in ("SYNC", "FLEX")
                or len(set(groups["condition1"] + groups["condition2"])) != 8
                or any(not article for articles in groups.values() for article in articles)):
            raise ValueError(f"Invalid frozen assignment for participant {identifier}")
        rows[identifier] = ParticipantAssignment(
            participant_id=identifier, allocation_slot=row["allocation_slot"], instruction_group=row["instruction_group"],
            list_id=row["list_id"], schedule_version=row["schedule_version"], seed=int(row["seed"]),
            condition1_articles=groups["condition1"], condition2_articles=groups["condition2"],
            source_sha256=hashlib.sha256(raw).hexdigest())
    if set(rows) != {str(index) for index in range(1, 201)}:
        raise ValueError("The frozen assignment table must contain all participant IDs from 1 to 200")
    if (config.condition1_count, config.condition2_count) != (4, 4):
        raise ValueError("The frozen study schedule requires condition1_count = 4 and condition2_count = 4")
    if participant_id == "0":
        # Preview the first list without claiming a formal allocation slot.
        return replace(rows["1"], participant_id="0", allocation_slot="", preview_of=rows["1"].allocation_slot)
    return rows[participant_id]
