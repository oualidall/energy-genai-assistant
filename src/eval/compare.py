"""Offline benchmark CLI; live execution stays locked pending a priced plan.

python -m src.eval.compare
V1 and v2 are interleaved with different offline fixtures; this is not a quality experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from src.eval.benchmark import ROOT, FixtureDatabase, load_bank, load_difficulty, verify_freeze

MEASUREMENT_SCOPE = (
    "Measures use a synthetic snapshot in SQLite, not BigQuery under real conditions. "
    "They cannot establish BigQuery SQL compatibility, network/service latency, "
    "BigQuery query cost, IAM enforcement, scalability, real RTE data quality, "
    "or Gemini answer quality with this offline smoke model."
)


def cell_equal(left, right, absolute: float, relative: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return math.isfinite(left) and math.isfinite(right) and math.isclose(
            left, right, abs_tol=absolute, rel_tol=relative,
        )
    return type(left) is type(right) and left == right


def rows_equal(actual: list[dict], expected: list[dict], absolute: float, relative: float) -> bool:
    """Match row multisets without rounding, preserving duplicate multiplicity.

    Alias names are ignored; column positions follow the frozen reference policy.
    Bipartite matching avoids greedy failures near a numeric tolerance boundary.
    """
    if len(actual) != len(expected):
        return False
    edges = []
    for row in actual:
        edges.append([
            i for i, ref in enumerate(expected)
            if len(row) == len(ref)
            and all(cell_equal(a, b, absolute, relative)
                    for a, b in zip(row.values(), ref.values(), strict=True))
        ])
    matches: dict[int, int] = {}

    def assign(index: int, visited: set[int]) -> bool:
        for candidate in edges[index]:
            if candidate in visited:
                continue
            visited.add(candidate)
            if candidate not in matches or assign(matches[candidate], visited):
                matches[candidate] = index
                return True
        return False

    return all(assign(i, set()) for i in range(len(actual)))


def nearest_rank(values: list[int], percent: int) -> int | None:
    if not values:
        return None
    if percent not in (50, 95):
        raise ValueError("Only p50/p95 are reported")
    ordered = sorted(values)
    return ordered[(len(ordered) * percent + 99) // 100 - 1]


def summarize(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    groups["all"] = records
    for record in records:
        groups[record["category"]].append(record)
        groups["difficulty:" + record.get("difficulty", "unclassified")].append(record)
    result = {}
    for category, items in groups.items():
        scored = [r for r in items if r["execution_match"] is not None]
        passed = sum(r["execution_match"] is True for r in scored)
        durations = [r["duration_ns"] for r in items]
        result[category] = {
            "measurement_scope": MEASUREMENT_SCOPE,
            "attempts": len(items),
            "errors": sum(r["error"] is not None for r in items),
            "execution_match_passed": passed,
            "execution_match_scored": len(scored),
            "execution_match_fraction": str(Fraction(passed, len(scored))) if scored else None,
            "answer_success_rate": None,
            "answer_success_status": "not evaluated; judge and human validation pending",
            "latency_n": len(durations),
            "latency_p50_ns": nearest_rank(durations, 50),
            "latency_p95_ns": nearest_rank(durations, 95),
            "tool_calls": sum(r["observations"]["tool_calls"] for r in items),
            "critic_coverage": str(Fraction(
                sum(r["observations"].get("critic_calls", 0) > 0 for r in items), len(items),
            )) if items else None,
            "revision_rate": str(Fraction(
                sum(r["observations"].get("revision_requests", 0) > 0 for r in items), len(items),
            )) if items else None,
        }
    return result


def evaluate(agent, questions: list[dict], reference: FixtureDatabase,
             policy: dict, repetitions: int = 5, seed: int = 42,
             variant: str = "v1") -> list[dict]:
    if repetitions < 1:
        raise ValueError("Repetitions must be positive")
    # Validate references before invoking any agent.
    expected = {}
    for q in questions:
        if q["reference_sql"]:
            expected[q["id"]] = reference.execute(q["reference_sql"])
            if not expected[q["id"]]:
                raise ValueError(f"Empty SQL reference: {q['id']}")
    absolute = float(policy["numeric_absolute_tolerance"])
    relative = float(policy["numeric_relative_tolerance"])
    ordered = list(questions)
    random.Random(seed).shuffle(ordered)
    records = []
    for repetition in range(repetitions):
        for q in ordered:
            start = time.perf_counter_ns()
            error = None
            out = {}
            try:
                out = agent.answer(q["question"])
                if not isinstance(out, dict) or not isinstance(out.get("answer"), str):
                    raise ValueError("Invalid agent answer schema")
            except Exception as exc:  # noqa: BLE001
                error = type(exc).__name__
            elapsed = time.perf_counter_ns() - start
            out = out if isinstance(out, dict) else {}
            error = error or out.get("error")
            observations = agent.observations()
            if any(call["error"] for call in observations["sql_calls"]):
                error = error or "ObservedToolError"
            match = None
            if q["reference_sql"]:
                successful = [call for call in observations["sql_calls"]
                              if call["error"] is None and call["rows"] is not None]
                match = bool(
                    not error and successful and out.get("sql")
                    and rows_equal(successful[-1]["rows"], expected[q["id"]], absolute, relative)
                )
            records.append({
                "schema_version": "1",
                "record_id": f"{variant}:{q['id']}:{repetition}",
                "variant": variant, "question_id": q["id"], "category": q["category"],
                "question": q["question"], "criterion": q["criterion"],
                "difficulty": q.get("difficulty", "unclassified"),
                "repetition": repetition, "raw_answer": out,
                "duration_ns": elapsed, "error": error,
                "observations": observations, "execution_match": match,
                "judge_verdict": None, "human_verdict": None,
                "answer_success": None,
            })
    return records



def evaluate_variants(agents: dict, questions: list[dict], reference: FixtureDatabase,
                      policy: dict, repetitions: int, seed: int = 42) -> list[dict]:
    """Interleave matched trials; never run all of v1 before all of v2."""
    if repetitions < 1:
        raise ValueError("Repetitions must be positive")
    for q in questions:
        if q["reference_sql"] and not reference.execute(q["reference_sql"]):
            raise ValueError(f"Empty SQL reference: {q['id']}")
    ordered = list(questions)
    random.Random(seed).shuffle(ordered)
    records = []
    for repetition in range(repetitions):
        for index, question in enumerate(ordered):
            variants = list(agents)
            if (repetition * len(ordered) + index) % 2:
                variants.reverse()
            for variant in variants:
                record = evaluate(
                    agents[variant], [question], reference, policy, 1, seed, variant,
                )[0]
                record["repetition"] = repetition
                record["record_id"] = f"{variant}:{question['id']}:{repetition}"
                records.append(record)
    return records


def git_state() -> dict:
    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def write_outputs(destination: Path, manifest: dict, records: list[dict]) -> None:
    destination.mkdir(parents=True, exist_ok=False)

    def save(name, data):
        (destination / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    summaries = {}
    for variant in sorted({r["variant"] for r in records}):
        selected = [r for r in records if r["variant"] == variant]
        save(f"{variant}.json", selected)
        summaries[variant] = summarize(selected)
    save("manifest.json", manifest)
    save("summary.json", {"schema_version": "2", "variants": summaries})
    lines = [
        "# Offline graph smoke run", "",
        "The two smoke model implementations differ; no Gemini or multi-agent quality gain is established.",
        "Natural-language correctness is unscored pending judge/human validation.",
        "SQL execution match does not establish final-answer correctness.",
    ]
    for title, is_difficulty in (("Overall and by category", False), ("By difficulty", True)):
        lines.extend([
            "", f"## {title}", "", MEASUREMENT_SCOPE, "",
            "| Variant | Group | Attempts | SQL matched/scored | p50 ns | p95 ns | Latency n | Critic coverage | Revision rate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for variant, summary in summaries.items():
            for group, values in summary.items():
                if group.startswith("difficulty:") != is_difficulty:
                    continue
                label = group.removeprefix("difficulty:")
                lines.append(
                    f"| {variant} | {label} | {values['attempts']} | "
                    f"{values['execution_match_passed']}/{values['execution_match_scored']} | "
                    f"{values['latency_p50_ns']} | {values['latency_p95_ns']} | "
                    f"{values['latency_n']} | {values['critic_coverage']} | {values['revision_rate']} |"
                )
    (destination / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--variant", choices=["v1", "v2", "both"], default="both")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None, help="Explicit stratified smoke subset")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode != "mock":
        parser.error("Live mode locked: dated EUR estimate and enforced 5 EUR budget required.")
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    if args.limit is not None and not 4 <= args.limit <= 40:
        parser.error("subset limit must be 4..40")
    lock = verify_freeze()
    bank = load_bank()
    difficulty = load_difficulty(bank)
    questions = [dict(q, difficulty=difficulty["questions"][q["id"]]["level"])
                 for q in bank["questions"]]
    if args.limit is not None:
        buckets = defaultdict(list)
        for q in questions:
            buckets[q["category"]].append(q)
        selected = []
        while len(selected) < args.limit:
            for category in sorted(buckets):
                if buckets[category] and len(selected) < args.limit:
                    selected.append(buckets[category].pop(0))
        questions = selected
    # Import only after the mode and frozen inputs have been checked.
    from src.eval.mock_runtime import MockV1
    from src.eval.mock_v2 import MockV2

    started = datetime.now(UTC).isoformat()
    setup_start = time.perf_counter_ns()
    variants = ["v1", "v2"] if args.variant == "both" else [args.variant]
    databases = {variant: FixtureDatabase.load() for variant in variants}
    factories = {"v1": MockV1, "v2": MockV2}
    agents = {variant: factories[variant](databases[variant]) for variant in variants}
    setup_ns = time.perf_counter_ns() - setup_start
    state = git_state()
    try:
        records = evaluate_variants(
            agents, questions, databases[variants[0]], bank["reference_policy"], args.repetitions,
        )
    finally:
        for database in databases.values():
            database.close()
    manifest = {
        "schema_version": "1", "protocol_version": "mock-smoke-3",
        "started_at": started, "finished_at": datetime.now(UTC).isoformat(),
        "git": state, "bank_id": bank["bank_id"], "frozen_inputs": lock,
        "mode": "mock", "variants": variants, "models": {"v1": "offline-smoke-v1", "v2": "offline-smoke-v2"},
        "measurement_scope": MEASUREMENT_SCOPE,
        "bank_lock": json.loads((ROOT / "evals/bank.lock").read_text(encoding="utf-8")),
        "difficulty": {
            "assigned_date": difficulty["assigned_date"], "basis": difficulty["basis"],
            "sha256": hashlib.sha256((ROOT / "evals/difficulty.json").read_bytes()).hexdigest(),
            "mapping": difficulty["questions"],
        },
        "mock_source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("src/eval/mock_runtime.py", "src/eval/mock_v2.py")
        },
        "temperature": 0, "model_seed_supported": False, "harness_seed": 42,
        "repetitions": args.repetitions, "question_ids": [q["id"] for q in questions],
        "actual_attempts": len(records), "concurrency": 1,
        "order": "seeded question order; repetition-major; alternating variant order per question", "setup_duration_ns": setup_ns,
        "latency": "monotonic ns; complete graph call; setup/scoring excluded; nearest rank",
        "tokens": None, "llm_api_cost_eur": "0", "total_cost_eur": None,
        "cost_note": "No provider calls. Host/CI cost not measured. Not a live price estimate.",
        "judge": "not run", "human_validation": "pending",
        "transport": "local injection; MCP paired transport planned in lot 3",
        "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {name: version(name) for name in
                         ("langgraph", "langchain-core", "pydantic", "numpy")},
        "limitations": [
            "Mock model always generates COUNT(*) for SQL; not representative of Gemini.",
            "No live model, pricing or judge is enabled.",
            "V1/v2 mock policies differ; this comparison tests mechanics, not architecture quality.",
            "Shared executor AST guard is stricter than the immutable historical v1 baseline.",
            "SQL match checks observed tool rows; final-answer correctness is unscored.",
        ],
    }
    output = args.output or ROOT / "evals/results" / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    )
    write_outputs(output, manifest, records)
    print(json.dumps({"output": str(output), "attempts": len(records), "mode": "mock"}))


if __name__ == "__main__":
    main()
