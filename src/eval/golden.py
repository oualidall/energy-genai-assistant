"""Loader for the golden-questions evaluation set.

The golden set is the ground truth used (from Phase 5) to score the agent: each
entry pairs a natural-language question with the SQL that answers it. Keeping it
as JSON makes it trivial to grow and to push to a LangSmith dataset later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_GOLDEN_PATH = Path(__file__).with_name("golden_questions.json")


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    question: str
    table: str
    sql: str
    note: str = ""


def load_golden_questions(path: Path = _GOLDEN_PATH) -> list[GoldenQuestion]:
    """Load and parse the golden-questions eval set."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenQuestion(**item) for item in raw]


if __name__ == "__main__":
    for q in load_golden_questions():
        print(f"[{q.id}] {q.question}\n    {q.sql}\n")
