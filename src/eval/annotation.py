"""Human annotation export/import; never generates human judgments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

VERDICTS = {"correct", "incorrect", "incertain"}
FIELDS = ["annotation_id", "question", "categorie", "reponse", "critere_attendu",
          "preuves", "verdict", "commentaire"]


def sample_records(records: list[dict], seed: int = 42) -> list[dict]:
    groups = defaultdict(list)
    ids = [r["record_id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate record IDs")
    for record in records:
        groups[(record["variant"], record["category"])].append(record)
    rng = random.Random(seed)
    selected = []
    for key in sorted(groups):
        items = groups[key]
        by_question = defaultdict(list)
        for item in items:
            by_question[item["question_id"]].append(item)
        keys = sorted(by_question)
        rng.shuffle(keys)
        ordered = []
        for question in keys:
            rng.shuffle(by_question[question])
            ordered.append(by_question[question].pop())
        remainder = [item for bucket in by_question.values() for item in bucket]
        rng.shuffle(remainder)
        ordered.extend(remainder)
        selected.extend(ordered[:(len(items) + 4) // 5])
    rng.shuffle(selected)
    return selected


def safe_cell(value: str) -> str:
    """Escape spreadsheet formulas; preserve ordinary text."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_annotations(records: list[dict], destination: Path) -> None:
    selected = sample_records(records)
    destination.mkdir(parents=True, exist_ok=False)
    mapping = {}
    with (destination / "answers.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for i, record in enumerate(selected):
            blind_id = f"A{i + 1:04d}"
            observations = record["observations"]
            evidence = {
                "documents": observations.get("document_calls", []),
                "sql": observations.get("sql_calls", []),
            }
            mapping[blind_id] = record["record_id"]
            writer.writerow({
                "annotation_id": blind_id,
                "question": safe_cell(record["question"]),
                "categorie": record["category"],
                "reponse": safe_cell(record["raw_answer"].get("answer", "")),
                "critere_attendu": safe_cell(record["criterion"]),
                "preuves": safe_cell(json.dumps(evidence, ensure_ascii=False)),
                "verdict": "", "commentaire": "",
            })
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False, allow_nan=False)
    (destination / "private-map.json").write_text(
        json.dumps({"record_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                    "seed": 42, "mapping": mapping}, indent=2) + "\n",
        encoding="utf-8",
    )


def agreement(records: list[dict], mapping: dict, labels: list[dict]) -> dict:
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if hashlib.sha256(payload.encode()).hexdigest() != mapping["record_sha256"]:
        raise ValueError("Annotation source results changed")
    by_id = {r["record_id"]: r for r in records}
    seen = set()
    annotated = definite = uncertain = paired = matches = invalid_judge = 0
    matrix = {h: {j: 0 for j in ("correct", "incorrect")} for h in ("correct", "incorrect")}
    for row in labels:
        blind_id = row["annotation_id"]
        if blind_id in seen or blind_id not in mapping["mapping"]:
            raise ValueError("Unknown or duplicate annotation ID")
        seen.add(blind_id)
        verdict = row["verdict"].strip()
        if not verdict:
            continue
        if verdict not in VERDICTS:
            raise ValueError(f"Invalid human verdict: {verdict}")
        annotated += 1
        if verdict == "incertain":
            if not row["commentaire"].strip():
                raise ValueError("Uncertain verdict requires a comment")
            uncertain += 1
            continue
        definite += 1
        record = by_id[mapping["mapping"][blind_id]]
        judge = record.get("judge_verdict")
        if judge not in ("correct", "incorrect"):
            invalid_judge += 1
            continue
        paired += 1
        matches += judge == verdict
        matrix[verdict][judge] += 1
    total = len(records)
    return {
        "total_responses": total, "sampled": len(mapping["mapping"]),
        "annotated": annotated, "definite": definite, "uncertain": uncertain,
        "valid_pairs": paired, "matches": matches,
        "agreement_fraction": str(Fraction(matches, paired)) if paired else None,
        "invalid_or_missing_judge_on_definite_labels": invalid_judge,
        "human_coverage_fraction": str(Fraction(annotated, total)) if total else None,
        "definite_coverage_fraction": str(Fraction(definite, total)) if total else None,
        "confusion_matrix": matrix,
        "judge_validated": bool(total and definite * 5 >= total
                                and paired == definite and paired > 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "agreement"])
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for path in args.results:
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    if args.action == "export":
        export_annotations(records, args.directory)
    else:
        mapping = json.loads((args.directory / "private-map.json").read_text(encoding="utf-8"))
        with (args.directory / "answers.csv").open(encoding="utf-8-sig", newline="") as handle:
            labels = list(csv.DictReader(handle))
        print(json.dumps(agreement(records, mapping, labels), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
