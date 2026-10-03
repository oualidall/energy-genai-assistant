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
from src.eval.benchmark import (
    ROOT,
    FixtureDatabase,
    inventory,
    load_bank,
    load_difficulty,
    verify_freeze,
)
from src.eval.compare import evaluate, main, nearest_rank, rows_equal, summarize
from src.eval.judge_prompt import judge_protocol


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
    (tmp_path / "evals/bank.lock").write_bytes((ROOT / "evals/bank.lock").read_bytes())
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
                        "judge_protocol": judge_protocol(),
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
        "compare", "--variant", "v1", "--limit", "4", "--repetitions", "1", "--output", str(target),
    ])
    main()
    records = json.loads((target / "v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert len(records) == manifest["actual_attempts"] == 4
    assert all(r["answer_success"] is None for r in records)
    assert all(r["observations"]["tokens"] is None for r in records)
    assert manifest["mode"] == "mock"
    report = Path(target / "summary.md").read_text(encoding="utf-8")
    assert report.count("Measures use a synthetic snapshot in SQLite") == 2
    assert "not BigQuery under real conditions" in report
    assert "## By difficulty" in report
    assert all(r["difficulty"] in {"facile", "moyen", "difficile"} for r in records)
    assert manifest["bank_lock"]["sha256"] == verify_freeze()["files"]["evals/bank.json"]
    assert len(manifest["difficulty"]["sha256"]) == 64


def test_inventory_counts_authors_and_categories_exactly():
    result = inventory(load_bank())
    assert result["total"] == result["unique_ids"] == 40
    assert result["by_author"] == {"legacy": 12, "owner": 10, "assistant": 18}
    assert result["by_category_and_author"] == {
        "agregation_sql": {"legacy": 12, "owner": 3, "assistant": 0, "total": 15},
        "factuel_documentaire": {"legacy": 0, "owner": 2, "assistant": 7, "total": 9},
        "ambigu": {"legacy": 0, "owner": 2, "assistant": 6, "total": 8},
        "hors_perimetre": {"legacy": 0, "owner": 3, "assistant": 5, "total": 8},
    }


@pytest.mark.parametrize("failure", ["bank", "lock_hash", "missing_lock"])
def test_cli_stops_before_agent_when_bank_lock_is_invalid(tmp_path, monkeypatch, failure):
    lock = verify_freeze()
    for name in [*lock["files"], "evals/freeze.json", "evals/bank.lock"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    if failure == "bank":
        with (tmp_path / "evals/bank.json").open("ab") as handle:
            handle.write(b"\n")
    elif failure == "lock_hash":
        target = tmp_path / "evals/bank.lock"
        data = json.loads(target.read_text())
        data["sha256"] = "0" * 64
        target.write_text(json.dumps(data))
    else:
        (tmp_path / "evals/bank.lock").unlink()

    def forbidden_agent(*args, **kwargs):
        pytest.fail("Agent must not be constructed on invalid frozen inputs")

    monkeypatch.setattr("src.eval.mock_runtime.MockV1", forbidden_agent)
    monkeypatch.setattr("src.eval.compare.verify_freeze", lambda: verify_freeze(tmp_path))
    monkeypatch.setattr("sys.argv", ["compare"])
    with pytest.raises((ValueError, FileNotFoundError)):
        main()


def test_difficulty_covers_exactly_every_question():
    bank = load_bank()
    difficulty = load_difficulty(bank)
    counts = Counter(item["level"] for item in difficulty["questions"].values())
    assert counts == {"facile": 15, "moyen": 16, "difficile": 9}


@pytest.mark.parametrize("failure", ["missing", "extra", "bad_level", "empty_reason"])
def test_difficulty_invalid_mapping_fails(tmp_path, failure):
    bank = load_bank()
    data = load_difficulty(bank)
    if failure == "missing":
        del data["questions"]["H01"]
    elif failure == "extra":
        data["questions"]["unknown"] = {"level": "facile", "reason": "Not in bank"}
    elif failure == "bad_level":
        data["questions"]["H01"]["level"] = "expert"
    else:
        data["questions"]["H01"]["reason"] = ""
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/bank.json").write_bytes((ROOT / "evals/bank.json").read_bytes())
    (tmp_path / "evals/difficulty.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_difficulty(bank, tmp_path)


def test_difficulty_aggregation_keeps_denominators_and_failures():
    records = [
        {"category": "agregation_sql", "difficulty": "facile", "execution_match": True,
         "duration_ns": 10, "error": None, "observations": {"tool_calls": 1}},
        {"category": "agregation_sql", "difficulty": "facile", "execution_match": False,
         "duration_ns": 30, "error": "Timeout", "observations": {"tool_calls": 1}},
        {"category": "ambigu", "difficulty": "difficile", "execution_match": None,
         "duration_ns": 20, "error": None, "observations": {"tool_calls": 0}},
    ]
    summary = summarize(records)
    easy = summary["difficulty:facile"]
    assert easy["attempts"] == easy["latency_n"] == 2
    assert easy["errors"] == 1
    assert easy["execution_match_fraction"] == "1/2"
    assert easy["latency_p50_ns"] == 10
    assert easy["latency_p95_ns"] == 30
    assert summary["difficulty:difficile"]["execution_match_scored"] == 0


def test_paired_cli_runs_both_graphs_and_preserves_question_pairs(tmp_path, monkeypatch):
    target = tmp_path / "paired"
    monkeypatch.setattr("sys.argv", [
        "compare", "--variant", "both", "--limit", "4", "--repetitions", "2",
        "--output", str(target),
    ])
    main()
    first = json.loads((target / "v1.json").read_text(encoding="utf-8"))
    second = json.loads((target / "v2.json").read_text(encoding="utf-8"))
    assert len(first) == len(second) == 8
    assert {(r["question_id"], r["repetition"]) for r in first} == {
        (r["question_id"], r["repetition"]) for r in second
    }
    assert all(r["raw_answer"]["variant"] == "v2" for r in second)
    errors = [r["raw_answer"] for r in second if r["raw_answer"]["status"] == "error"]
    assert not errors, json.dumps(errors, ensure_ascii=False)
    assert all(r["observations"]["tokens"] is None for r in first + second)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["actual_attempts"] == 16
    assert manifest["variants"] == ["v1", "v2"]
