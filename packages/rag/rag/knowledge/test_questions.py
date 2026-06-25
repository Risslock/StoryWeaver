"""TestQuestion Pydantic model and JSONL loader for RAG evaluation."""

from __future__ import annotations

import json

from pydantic import BaseModel


class TestQuestion(BaseModel):
    question: str
    keywords: list[str]
    reference_answer: str
    category: str


def load_test_questions(file_path: str) -> list[TestQuestion]:
    """Load TestQuestion objects from a JSONL file, one object per line.

    Returns an empty list for an empty file.
    Raises ValueError for missing required fields.
    Propagates json.JSONDecodeError for malformed JSON lines.
    """
    questions: list[TestQuestion] = []
    required_fields = {"question", "keywords", "reference_answer", "category"}

    with open(file_path, encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            data: dict[str, object] = json.loads(line)
            missing = required_fields - data.keys()
            if missing:
                field = next(iter(sorted(missing)))
                raise ValueError(f"Row {line_no}: missing field '{field}'")
            questions.append(TestQuestion(
                question=str(data["question"]),
                keywords=list(data["keywords"]),  # type: ignore[arg-type]
                reference_answer=str(data["reference_answer"]),
                category=str(data["category"]),
            ))

    return questions
