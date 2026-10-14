"""Load one question CSV per article, keeping its fixed question/option order."""

import csv
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re


QUESTION_FIELDS = ["article_id", "question_id", "question_order", "content", "OptionA", "OptionB", "OptionC", "OptionD", "CorrectAnswer"]


@dataclass(frozen=True)
class Question:
    article_id: str
    question_id: str
    question_order: int
    content: str
    options: tuple
    correct_answer: str
    source_path: str
    source_sha256: str


def load_question_sets(config, articles):
    root = Path(config.assets_dir).resolve()
    folder = root / "questions"
    result = {}
    for article in articles:
        if article.article_id in result:
            continue
        path = folder / f"{article.article_id}.csv"
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Missing question CSV inside assets/questions: {article.article_id}.csv")
        raw = path.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if reader.fieldnames != QUESTION_FIELDS:
            raise ValueError(f"Question columns must be {', '.join(QUESTION_FIELDS)}: {path.name}")
        questions, seen = [], set()
        for row in reader:
            identifier = row["question_id"]
            if (row["article_id"] != article.article_id or not isinstance(identifier, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier in seen):
                raise ValueError(f"Invalid or duplicate question identity in {path.name}")
            if any(not isinstance(row.get(field), str) or not row[field].strip()
                   for field in ("content", "OptionA", "OptionB", "OptionC", "OptionD")):
                raise ValueError(f"Question text/options must be nonempty: {identifier}")
            if not isinstance(row["CorrectAnswer"], str) or row["CorrectAnswer"] not in ("A", "B", "C", "D"):
                raise ValueError(f"CorrectAnswer must be A, B, C or D: {identifier}")
            try:
                order = int(row["question_order"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid question_order: {identifier}") from exc
            seen.add(identifier)
            questions.append(Question(article.article_id, identifier, order, row["content"],
                tuple(row["Option" + letter] for letter in "ABCD"), row["CorrectAnswer"],
                str(path.relative_to(root)), hashlib.sha256(raw).hexdigest()))
        questions.sort(key=lambda question: question.question_order)
        if not questions or [question.question_order for question in questions] != list(range(1, len(questions) + 1)):
            raise ValueError(f"Question order must be consecutive from 1: {path.name}")
        result[article.article_id] = questions
    return result
