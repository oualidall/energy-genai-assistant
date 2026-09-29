"""Frozen benchmark inputs and a read-only synthetic SQL fixture."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = {"agregation_sql", "factuel_documentaire", "ambigu", "hors_perimetre"}


def verify_freeze(root: Path = ROOT) -> dict[str, Any]:
    """Fail closed before answers are generated when any frozen byte changes."""
    lock = json.loads((root / "evals/freeze.json").read_text(encoding="utf-8"))
    bank_lock = json.loads((root / "evals/bank.lock").read_text(encoding="utf-8"))
    expected = bank_lock["sha256"]
    if (bank_lock["algorithm"] != "sha256" or bank_lock["path"] != "evals/bank.json"
            or expected != lock["files"]["evals/bank.json"]):
        raise ValueError("bank.lock disagrees with the original freeze")
    date.fromisoformat(bank_lock["frozen_date"])
    date.fromisoformat(bank_lock["published_date"])
    actual = hashlib.sha256((root / "evals/bank.json").read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError("Frozen input changed: evals/bank.json (bank.lock)")
    for name, expected in lock["files"].items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Frozen input changed: {name}")
    return lock


def load_bank(root: Path = ROOT) -> dict[str, Any]:
    verify_freeze(root)
    bank = json.loads((root / "evals/bank.json").read_text(encoding="utf-8"))
    questions = bank["questions"]
    ids = [q["id"] for q in questions]
    if len(questions) != 40 or len(set(ids)) != 40:
        raise ValueError("Expected exactly 40 unique questions")
    if {q["category"] for q in questions} != CATEGORIES:
        raise ValueError("Invalid categories")
    owners = [q for q in questions if q["author"] == "owner"]
    if len(owners) != 10 or sum(q["category"] == "hors_perimetre" for q in owners) < 3:
        raise ValueError("Owner contribution contract violated")
    for q in questions:
        if not q["question"].strip() or not q["criterion"].strip():
            raise ValueError("Empty question or criterion")
        if (q["category"] == "agregation_sql") != bool(q["reference_sql"]):
            raise ValueError("SQL references must match SQL category")
    return bank


def inventory(bank: dict[str, Any]) -> dict[str, Any]:
    """Compute counts from records, never from the bank's display name."""
    rows = {}
    authors = ("legacy", "owner", "assistant")
    for category in sorted(CATEGORIES):
        selected = [q for q in bank["questions"] if q["category"] == category]
        rows[category] = {author: sum(q["author"] == author for q in selected)
                          for author in authors}
        rows[category]["total"] = len(selected)
    return {
        "total": len(bank["questions"]),
        "unique_ids": len({q["id"] for q in bank["questions"]}),
        "by_category_and_author": rows,
        "by_author": {author: sum(q["author"] == author for q in bank["questions"])
                      for author in authors},
    }


def load_difficulty(bank: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """External task-complexity labels; never changes frozen question records."""
    data = json.loads((root / "evals/difficulty.json").read_text(encoding="utf-8"))
    bank_hash = hashlib.sha256((root / "evals/bank.json").read_bytes()).hexdigest()
    if data["bank_sha256"] != bank_hash:
        raise ValueError("Difficulty metadata targets a different bank")
    levels = {"facile", "moyen", "difficile"}
    if set(data["levels"]) != levels or any(not s.strip() for s in data["levels"].values()):
        raise ValueError("Missing difficulty-level justifications")
    expected_ids = {q["id"] for q in bank["questions"]}
    if set(data["questions"]) != expected_ids:
        raise ValueError("Difficulty IDs must match every frozen question exactly")
    for item in data["questions"].values():
        if item["level"] not in levels or not item["reason"].strip():
            raise ValueError("Invalid difficulty or missing justification")
    return data


def _validate_snapshot(tables: dict[str, list[dict]]) -> None:
    daily = tables["consommation_journaliere"]
    required = {(date(2026, 7, 1) + timedelta(days=i)).isoformat() for i in range(62)}
    counts = Counter(r["date"] for r in daily)
    if any(counts[d] != 1 for d in required):
        raise ValueError("July/August coverage is incomplete or duplicated")
    if any(r["total_mwh"] is None for r in daily):
        raise ValueError("Null consumption")
    august = sum(r["total_mwh"] for r in daily if r["date"].startswith("2026-08"))
    if august <= 0:
        raise ValueError("August denominator must be positive")
    exchange = tables["solde_echanges_journalier"]
    if len(exchange) < 5 or len({r["date"] for r in exchange}) != len(exchange):
        raise ValueError("Exchange rows insufficient or duplicated")
    balances = sorted(r["solde_mwh"] for r in exchange)
    if len(balances) > 5 and balances[4] == balances[5]:
        raise ValueError("Tied cutoff requires a tie-aware validator")
    nuclear = [r["part_pct"] for r in tables["mix_energetique_hebdomadaire"]
               if r["filiere"] == "NUCLEAR" and r["part_pct"] is not None]
    if not nuclear or nuclear.count(min(nuclear)) != 1:
        raise ValueError("Nuclear minimum missing or tied")


class FixtureDatabase:
    """SQLite fixture only; never a BigQuery emulator or a live connection."""

    def __init__(self, tables: dict[str, list[dict]]) -> None:
        _validate_snapshot(tables)
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("ATTACH DATABASE ':memory:' AS rte_energy")
        self.table_names = set(tables)
        for name, rows in tables.items():
            # Identifiers come from the frozen fixture; reject malformed names.
            if not name.replace("_", "").isalnum() or not rows:
                raise ValueError("Invalid fixture table")
            columns = list(rows[0])
            if any(not c.replace("_", "").isalnum() for c in columns):
                raise ValueError("Invalid fixture column")
            self.connection.execute(
                f"CREATE TABLE rte_energy.{name} ({', '.join(columns)})"
            )
            marks = ", ".join("?" for _ in columns)
            self.connection.executemany(
                f"INSERT INTO rte_energy.{name} VALUES ({marks})",
                [tuple(row[c] for c in columns) for row in rows],
            )
        self.connection.commit()
        self.connection.set_authorizer(self._authorize)
        self.calls: list[dict[str, Any]] = []

    def _authorize(self, action, arg1, arg2, database, _trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return (sqlite3.SQLITE_OK if database == "rte_energy" and arg1 in self.table_names
                    else sqlite3.SQLITE_DENY)
        if action == sqlite3.SQLITE_FUNCTION and arg2 in {"sum", "avg", "min", "max", "count", "nullif"}:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    @classmethod
    def load(cls, root: Path = ROOT) -> FixtureDatabase:
        verify_freeze(root)
        data = json.loads((root / "evals/fixtures/snapshot.json").read_text(encoding="utf-8"))
        return cls(data["tables"])

    def execute(self, sql: str) -> list[dict]:
        """Single read-only statement, bounded CPU, fresh authorization each call."""
        if not sql.strip().upper().startswith(("SELECT ", "WITH ")):
            raise ValueError("Read-only SELECT/WITH required")
        ticks = 0

        def progress():
            nonlocal ticks
            ticks += 1
            return int(ticks > 1000)

        self.connection.set_progress_handler(progress, 1000)
        try:
            cursor = self.connection.execute(sql)
            rows = cursor.fetchmany(1001)
            if len(rows) > 1000:
                raise ValueError("Fixture result exceeds 1000 rows")
            return [dict(row) for row in rows]
        finally:
            self.connection.set_progress_handler(None, 0)

    def query(self, sql: str):
        """Minimal injectable client interface used by the unchanged v1."""
        entry: dict[str, Any] = {"sql": sql, "rows": None, "error": None}
        self.calls.append(entry)
        try:
            entry["rows"] = self.execute(sql)
        except Exception as exc:
            entry["error"] = type(exc).__name__
            raise

        class Job:
            def result(self):
                return entry["rows"]

        return Job()

    def close(self) -> None:
        self.connection.close()


if __name__ == "__main__":
    bank = load_bank()
    report = inventory(bank)
    difficulty = load_difficulty(bank)
    report["by_difficulty"] = dict(Counter(
        item["level"] for item in difficulty["questions"].values()
    ))
    print(json.dumps(report, ensure_ascii=False, indent=2))
