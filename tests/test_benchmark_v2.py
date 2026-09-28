"""Offline tests for benchmark integrity; no provider calls."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.eval.annotation import agreement, export_annotations, sample_records
from src.eval.benchmark import ROOT, FixtureDatabase, load_bank, verify_freeze
from src.eval.compare import evaluate, main, nearest_rank, rows_equal, summarize


def test_frozen_bank_keeps_owner_and_legacy_questions():
    bank = load_bank()
    counts = Counter(q["category"] for q in bank["questions"])
    assert counts == {"agregation_sql": 15, "factuel_documentaire": 9,
                      "ambigu": 8, "hors_perimetre": 8}
    assert sum(q["author"] == "legacy" for q in bank["questions"]) == 12
    owner = {q["id"]: q for q in bank["questions"] if q["author"] == "owner"}
    assert "journalière" in owner["H07"]["criterion"]
    assert "avant génération SQL" in owner["H01"]["criterion"]


def test_freeze_rejects_modified_bytes(tmp_path):
    lock = verify_freeze()
    for name in lock["files"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (tmp_path / "evals/freeze.json").write_text(json.dumps(lock), encoding="utf-8")
    with (tmp_path / "evals/bank.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="Frozen input"):
        verify_freeze(tmp_path)


@pytest.mark.parametrize("sql", [
    "DELETE FROM consommation_journaliere",
    "SELECT 1; DROP TABLE consommation_journaliere",
    "WITH x AS (SELECT 1) DELETE FROM consommation_journaliere",
    "SELECT load_extension('not-a-library')",
    "SELECT * FROM sqlite_master",
])
def test_fixture_rejects_writes_multiple_statements_and_unauthorized_access(sql):
    db = FixtureDatabase.load()
    try:
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            db.query(sql)
        assert len(db.execute("SELECT * FROM consommation_journaliere")) == 62
        assert db.calls[-1]["error"] is not None
    finally:
        db.close()


def test_snapshot_requires_both_complete_months():
    snapshot = json.loads((ROOT / "evals/fixtures/snapshot.json").read_text(encoding="utf-8"))
    snapshot["tables"]["consommation_journaliere"].pop()
    with pytest.raises(ValueError, match="coverage"):
        FixtureDatabase(snapshot["tables"])


def test_all_frozen_sql_references_execute_on_synthetic_snapshot():
    db = FixtureDatabase.load()
    try:
        for q in load_bank()["questions"]:
            if q["reference_sql"]:
                assert db.execute(q["reference_sql"])
    finally:
        db.close()


def test_numeric_matching_preserves_multiplicity_and_does_not_round_to_cents():
    assert rows_equal([{"alias": 2}, {"alias": 1}], [{"x": 1}, {"x": 2}], 1e-6, 1e-9)
    assert not rows_equal([{"x": 1}, {"x": 1}], [{"x": 1}, {"x": 2}], 1e-6, 1e-9)
    assert not rows_equal([{"x": 1.001}], [{"x": 1.002}], 1e-6, 1e-9)
    assert not rows_equal([{"x": None}], [{"x": "None"}], 1e-6, 1e-9)


def test_percentile_is_nearest_rank():
    assert nearest_rank(list(range(1, 201)), 50) == 100
    assert nearest_rank(list(range(1, 201)), 95) == 190
    assert nearest_rank([], 95) is None


def test_failed_agent_attempts_are_retained():
    def fail(_question):
        raise RuntimeError("Unit fixture error")
    observations = {"sql_calls": [], "tool_calls": 0}
    agent = SimpleNamespace(answer=fail, observations=lambda: observations)
    q = {"id": "unit-only", "category": "ambigu", "question": "Unit fixture?",
         "criterion": "Ask a question", "reference_sql": None}
    db = FixtureDatabase.load()
    try:
        records = evaluate(agent, [q], db, {
            "numeric_absolute_tolerance": "0.000001",
            "numeric_relative_tolerance": "0.000000001",
        }, repetitions=2)
    finally:
        db.close()
    result = summarize(records)["all"]
    assert result["attempts"] == result["errors"] == result["latency_n"] == 2
    assert result["answer_success_rate"] is None


def fake_records():
    records = []
    for variant in ("v1", "v2"):
        for category, size in (("sql", 15), ("docs", 9), ("ambiguous", 8), ("outside", 8)):
            for question in range(size):
                for repetition in range(5):
                    records.append({
                        "record_id": f"{variant}:{category}:{question}:{repetition}",
                        "variant": variant, "category": category,
                        "question_id": f"{category}:{question}",
                        "question": "Separate annotation unit fixture?",
                        "criterion": "Unit fixture criterion",
                        "raw_answer": {"answer": "Unit fixture answer"},
                        "observations": {}, "judge_verdict": "correct",
                    })
    return records


def test_annotation_samples_twenty_percent_blinded_and_computes_agreement(tmp_path):
    records = fake_records()
    selected = sample_records(records)
    assert len(selected) == 80
    assert len({(r["variant"], r["question_id"]) for r in selected}) == 80
    target = tmp_path / "annotation"
    export_annotations(records, target)
    with (target / "answers.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert "variant" not in reader.fieldnames
        assert "judge_verdict" not in reader.fieldnames
        labels = list(reader)
    mapping = json.loads((target / "private-map.json").read_text())
    assert all(not row["verdict"] for row in labels)
    for row in labels:
        row["verdict"] = "correct"
    labels[0]["verdict"] = "incorrect"
    report = agreement(records, mapping, labels)
    assert report["agreement_fraction"] == "79/80"
    assert report["judge_validated"]
    labels[0]["verdict"] = "incertain"
    labels[0]["commentaire"] = "Insufficient evidence"
    report = agreement(records, mapping, labels)
    assert report["uncertain"] == 1
    assert not report["judge_validated"]


def test_live_mode_is_blocked_before_any_agent_construction(monkeypatch):
    monkeypatch.setattr("sys.argv", ["compare", "--mode", "live"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_cli_smoke_writes_observed_results_and_null_quality(tmp_path, monkeypatch):
    target = tmp_path / "run"
    monkeypatch.setattr("sys.argv", [
        "compare", "--limit", "4", "--repetitions", "1", "--output", str(target),
    ])
    main()
    records = json.loads((target / "v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert len(records) == manifest["actual_attempts"] == 4
    assert all(r["answer_success"] is None for r in records)
    assert all(r["observations"]["tokens"] is None for r in records)
    assert manifest["mode"] == "mock"
    assert Path(target / "summary.md").exists()
