"""Scan one CSV per article; the filename stem is the experimental article ID."""

import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import random
import re
import secrets


def count_units(text, mode):
    if mode == "words":
        return len(text.split())
    if mode == "hanzi":
        return sum(1 for c in text if (0x3400 <= ord(c) <= 0x4DBF
                   or 0x4E00 <= ord(c) <= 0x9FFF or 0x20000 <= ord(c) <= 0x323AF))
    raise ValueError("Unknown count mode")


@dataclass(frozen=True)
class Article:
    article_id: str
    condition: str
    title: str
    path: str
    text: str
    text_sha256: str
    unit_count: int
    count_mode: str
    pages: tuple
    pages_sha256: str
    source_rows: tuple
    sampling_seed: int
    source_sha256: str
    pool_article_ids: tuple


def load_experiment_articles(config, assignment=None):
    root = Path(config.assets_dir).resolve()
    folder = (root / config.articles_folder).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Articles folder must be inside assets_dir")
    if not folder.is_dir():
        raise ValueError(f"Articles folder does not exist: {folder}")
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".csv"
                    and not p.name.startswith(".")), key=lambda p: (p.stem.casefold(), p.name))
    seen = set()
    for path in files:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", path.stem):
            raise ValueError(f"Invalid article ID in filename {path.name}: use 1–32 letters/digits/_/-")
        if path.stem.casefold() in seen:
            raise ValueError(f"Duplicate article ID in filename: {path.name}")
        seen.add(path.stem.casefold())
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Article CSV must be inside assets_dir: {path.name}")
    required = config.condition1_count + config.condition2_count
    if len(files) < required:
        raise ValueError(f"Article pool requires {required} distinct articles "
                         f"(condition1={config.condition1_count}, condition2={config.condition2_count}); found {len(files)}")
    seed = assignment.seed if assignment is not None else (
        config.random_seed if config.random_seed is not None else secrets.randbits(64))
    pool_ids = tuple(path.stem for path in files)
    pool = []
    for path in files:
        raw = path.read_bytes()
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            header = next(reader, [])
            if len(header) != 1 or not header[0].strip():
                raise ValueError("CSV requires one column with a nonempty article title in the first row")
            title = header[0].strip()
            pages, source_rows = [], []
            for row_number, row in enumerate(reader, 2):
                if len(row) > 1:
                    raise ValueError(f"row {row_number} has more than one column; quote sentences containing commas")
                if row and row[0].strip():
                    pages.append(row[0])
                    source_rows.append(row_number)
            text = "\n".join(pages)
            if not pages or not count_units(text, config.count_mode):
                raise ValueError("article has no countable pages")
        except (ValueError, UnicodeDecodeError, csv.Error) as exc:
            raise ValueError(f"Invalid article CSV {path.name}: {exc}") from exc
        pool.append(dict(
            article_id=path.stem, title=title, path=str(path.relative_to(root)), text=text,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            unit_count=count_units(text, config.count_mode), count_mode=config.count_mode,
            pages=tuple(pages), pages_sha256=hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode("utf-8")).hexdigest(),
            source_rows=tuple(source_rows), sampling_seed=seed,
            source_sha256=hashlib.sha256(raw).hexdigest(), pool_article_ids=pool_ids,
        ))
    if assignment is not None:
        assigned = {"condition1": assignment.condition1_articles, "condition2": assignment.condition2_articles}
        by_id = {article["article_id"]: article for article in pool}
        missing = sorted({identifier for ids in assigned.values() for identifier in ids} - by_id.keys())
        if missing:
            raise ValueError("Assigned article CSVs are missing: " + ", ".join(missing))
        if any(len(ids) != getattr(config, condition + "_count") for condition, ids in assigned.items()):
            raise ValueError("Configured article counts differ from the frozen assignment")
        return {condition: [Article(condition=condition, **by_id[identifier]) for identifier in ids]
                for condition, ids in assigned.items()}
    # Internal random-pool API retained for callers without a frozen assignment.
    drawn = random.Random(seed).sample(pool, required)
    selected = {"condition1": [], "condition2": []}
    for position, article in enumerate(drawn):
        condition = "condition1" if position < config.condition1_count else "condition2"
        selected[condition].append(Article(condition=condition, **article))
    return selected
