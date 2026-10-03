"""Pilot audit uses provider-shaped synthetic metadata, never real measurements."""
from __future__ import annotations

import hashlib
import json

import pytest

from src.eval.annotation import agreement
from src.eval.call_gate import CallGate, Quota, ResumeBlockedError, UsageContractError
from src.eval.judge_prompt import judge_protocol, prepare_judge
from src.eval.pilot_audit import MetadataError, audit, delta, usage_counts, write_report


def test_usage_metadata_counts_thinking_without_double_counting_cache():
    assert usage_counts({
        "promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 5,
        "cachedContentTokenCount": 30, "totalTokenCount": 125,
    }) == (100, 25)


@pytest.mark.parametrize("metadata", [
    None, {}, {"promptTokenCount": True},
    {"promptTokenCount": 10, "candidatesTokenCount": 3, "totalTokenCount": 99},
    {"promptTokenCount": 10, "candidatesTokenCount": 3, "totalTokenCount": 13,
     "toolUsePromptTokenCount": 1},
])
def test_missing_or_inconsistent_metadata_cannot_be_scored(metadata):
    with pytest.raises(MetadataError):
        usage_counts(metadata)


def test_exact_percentage_and_zero_denominator():
    assert delta(4, 3) == "100/3"
    assert delta(15, 10) == "50"
    assert delta(5, 10) == "-50"
    assert delta(0, 0) == "0"
    assert delta(1, 0) is None


def test_overrun_keeps_raw_usage_and_stops_subsequent_calls(tmp_path):
    model = "gemini-2.5-flash-lite"
    gate = CallGate(tmp_path / "audit.db", {"test": True}, {model: Quota(10, 10000, 100)})
    calls = []

    def provider(*args):
        calls.append(1)
        return {
            "output": "unit",
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 3, "totalTokenCount": 14},
            "modelVersion": "unit-version", "responseId": "unit-id",
        }

    with pytest.raises(UsageContractError):
        gate.call("one", "v2:H07:0", model, {"question": "unit"}, 10, 10, provider,
                  forecast={"role": "synthesis", "input_tokens": 8, "output_tokens": 2})
    with pytest.raises(ResumeBlockedError):
        gate.call("two", "v2:H08:0", model, {}, 10, 10, provider)
    assert len(calls) == 1
    report = audit(gate.report())
    row = report["rows"][0]
    assert row["api_input"] == 11 and row["input_delta_percent"] == "75/2"
    assert row["api_output_including_thoughts"] == 3 and row["output_delta_percent"] == "50"
    assert row["reservation_exceeded"]
    assert row["usageMetadata"]["totalTokenCount"] == 14
    assert row["modelVersion"] == "unit-version"
    assert report["forecast_underestimation"] and not report["campaign_authorized"]
    write_report(gate.report(), tmp_path / "report")
    assert "75/2" in (tmp_path / "report/calls.md").read_text()
    gate.close()


def test_judge_does_not_truncate_when_input_exceeds_2000():
    record = {"question": "Q", "criterion": "C", "raw_answer": {"answer": "A"}, "observations": {}}
    assert prepare_judge(record, lambda _: 2000)["judge_protocol"] == judge_protocol()
    with pytest.raises(ValueError, match="2000"):
        prepare_judge(record, lambda _: 2001)


@pytest.mark.parametrize("old", [True, False])
def test_human_agreement_is_not_transferable_from_old_judge(old):
    protocol = dict(judge_protocol())
    if old:
        protocol["version"] = "old-4000"
    records = [{"record_id": "v1:unit:0", "judge_verdict": "correct", "judge_protocol": protocol}]
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False, allow_nan=False)
    mapping = {"record_sha256": hashlib.sha256(payload.encode()).hexdigest(),
               "mapping": {"A0001": "v1:unit:0"}}
    labels = [{"annotation_id": "A0001", "verdict": "correct", "commentaire": ""}]
    report = agreement(records, mapping, labels)
    assert report["agreement_fraction"] == "1"
    assert report["judge_validated"] is (not old)
    assert report["judge_protocol_matches"] is (not old)
