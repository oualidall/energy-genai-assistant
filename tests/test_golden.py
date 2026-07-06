"""Tests for the golden-questions eval set.

These guard the ground truth: every question must reference a real table and its
SQL must only touch columns that exist in the schema — so a schema change that
breaks the eval set fails loudly here.
"""

from __future__ import annotations

import re

from src.data.schema import get_table, table_names
from src.eval.golden import load_golden_questions

GOLDEN = load_golden_questions()


def test_has_a_meaningful_number_of_questions() -> None:
    assert len(GOLDEN) >= 10


def test_ids_are_unique() -> None:
    ids = [q.id for q in GOLDEN]
    assert len(ids) == len(set(ids))


def test_every_question_is_well_formed() -> None:
    for q in GOLDEN:
        assert q.question.strip().endswith("?"), f"{q.id}: question should end with '?'"
        assert q.table in table_names(), f"{q.id}: unknown table {q.table}"
        assert q.table in q.sql, f"{q.id}: SQL does not reference its table"
        assert q.sql.upper().startswith("SELECT"), f"{q.id}: SQL must be a SELECT"


def test_every_table_is_covered() -> None:
    covered = {q.table for q in GOLDEN}
    assert covered == set(table_names()), "some tables have no golden question"


def _identifiers(sql: str) -> set[str]:
    # drop single-quoted string / date literals so they aren't read as columns
    sql = re.sub(r"'[^']*'", "", sql)
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", sql.lower()))
    keywords = {
        "select", "from", "where", "group", "by", "order", "desc", "asc", "limit",
        "as", "and", "or", "count", "sum", "avg", "min", "max", "between", "on",
    }
    return tokens - keywords


def test_sql_only_references_known_columns() -> None:
    for q in GOLDEN:
        table = get_table(q.table)
        # aliases defined with AS may be referenced again (e.g. in ORDER BY)
        aliases = set(re.findall(r"\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)", q.sql, flags=re.IGNORECASE))
        known = set(table.column_names()) | {q.table} | aliases
        unknown = _identifiers(q.sql) - known
        assert not unknown, f"{q.id}: SQL references unknown identifiers {unknown}"
