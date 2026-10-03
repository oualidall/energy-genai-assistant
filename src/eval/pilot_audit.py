"""Exact per-call pilot audit. No API calls and no campaign authorization."""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path


class MetadataError(ValueError):
    pass


def usage_counts(metadata: dict) -> tuple[int, int]:
    if not isinstance(metadata, dict):
        raise MetadataError("Missing usageMetadata")
    for name in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount"):
        if type(metadata.get(name)) is not int or metadata[name] < 0:
            raise MetadataError(f"Missing/invalid {name}")
    for name in ("thoughtsTokenCount", "toolUsePromptTokenCount", "cachedContentTokenCount"):
        if type(metadata.get(name, 0)) is not int or metadata.get(name, 0) < 0:
            raise MetadataError(f"Invalid {name}")
    incoming = metadata["promptTokenCount"]
    outgoing = metadata["candidatesTokenCount"] + metadata.get("thoughtsTokenCount", 0)
    if metadata.get("toolUsePromptTokenCount", 0):
        raise MetadataError("Unexpected provider-side tool tokens")
    if metadata.get("cachedContentTokenCount", 0) > incoming:
        raise MetadataError("Cached tokens exceed prompt")
    if metadata["totalTokenCount"] != incoming + outgoing:
        raise MetadataError("Unreconciled totalTokenCount")
    # Cache tokens are already part of prompt; no discount is assumed in the theoretical estimate.
    return incoming, outgoing


def delta(actual: int | None, expected: int | None):
    if actual is None or expected is None:
        return None
    if expected == 0:
        return "0" if actual == 0 else None
    return str(Fraction(100 * (actual - expected), expected))


def audit(ledger: dict) -> dict:
    rows = []
    for call in ledger["calls"]:
        response = json.loads(call["output"]) if call.get("output") else {}
        raw = response.get("usageMetadata")
        issue = None
        incoming = outgoing = None
        try:
            incoming, outgoing = usage_counts(raw)
        except MetadataError as exc:
            issue = str(exc)
        forecast = call.get("forecast", {})
        expected_in = forecast.get("input_tokens")
        expected_out = forecast.get("output_tokens")
        if any(type(n) is not int or n < 0 for n in (expected_in, expected_out)):
            issue = issue or "Missing pre-call forecast"
            expected_in = expected_out = None
        overflow = incoming is not None and (
            incoming > call["input_limit"] or outgoing > call["output_limit"]
        )
        row = {
            "call_id": call["id"], "request_id": call["request_id"],
            "role": forecast.get("role"), "model": call["model"],
            "state": call["state"], "estimated_input": expected_in,
            "api_input": incoming, "input_delta_percent": delta(incoming, expected_in),
            "estimated_output": expected_out, "api_output_including_thoughts": outgoing,
            "output_delta_percent": delta(outgoing, expected_out),
            "reserved_input": call["input_limit"], "reserved_output": call["output_limit"],
            "reservation_exceeded": bool(overflow),
            "usageMetadata": raw, "modelVersion": response.get("modelVersion"),
            "responseId": response.get("responseId"),
            "prompt_sha256": forecast.get("prompt_sha256"),
            "issue": issue,
        }
        rows.append(row)
    return {
        "schema_version": "1", "rows": rows,
        "all_calls_auditable": bool(rows) and all(not r["issue"] for r in rows),
        "reservation_exceeded": any(r["reservation_exceeded"] for r in rows),
        "forecast_underestimation": any(
            r["estimated_input"] is not None and r["api_input"] is not None
            and (r["api_input"] > r["estimated_input"]
                 or r["api_output_including_thoughts"] > r["estimated_output"])
            for r in rows
        ),
        "campaign_authorized": False,
        "note": "Forecasts differ from hard reservations. Fractions are exact percentages; null is unknown.",
    }


def write_report(ledger: dict, destination: Path):
    report = audit(ledger)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "calls.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    lines = [
        "# Pilot per-call token audit", "",
        "Synthetic SQLite snapshot. No BigQuery or real RTE inference.",
        "Percentages are exact signed fractions; unknown is not zero. All attempts are retained.",
        "Any amount is a theoretical cost in paid mode, not free-tier expenditure.", "",
        "| Call | Role | Estimated in | API in | Difference % | Estimated out | API out incl. thoughts | Difference % | Reserved in/out | Exceeded | Issue |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        values = [
            row["call_id"], row["role"], row["estimated_input"], row["api_input"],
            row["input_delta_percent"], row["estimated_output"],
            row["api_output_including_thoughts"], row["output_delta_percent"],
            f'{row["reserved_input"]}/{row["reserved_output"]}',
            row["reservation_exceeded"], row["issue"],
        ]
        lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ")
                                       if v is not None else "unknown" for v in values) + " |")
    (destination / "calls.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_report(json.loads(args.ledger_json.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
