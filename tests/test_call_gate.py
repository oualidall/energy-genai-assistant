"""No network: fake transport and fake clock prove pre-call enforcement."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.eval.call_gate import (
    BudgetLimitError,
    CallGate,
    Quota,
    RateLimitError,
    ResumeBlockedError,
    UsageContractError,
    cost,
)

MODEL = "gemini-2.5-flash-lite"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 30, 6, 59, 59, tzinfo=UTC).timestamp()
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        assert 0 < seconds <= 30
        self.sleeps.append(seconds)
        self.now += seconds


def gate(path, clock, cap=1000000, quota=None):
    return CallGate(path, {"bank": "unit-fixture", "mode": "mock"},
                    {MODEL: quota or Quota(100, 100000, 1000)}, cap,
                    clock.time, clock.sleep)


class Transport:
    def __init__(self):
        self.calls = 0

    def __call__(self, model, payload, maximum):
        self.calls += 1
        return {"output": {"answer": "unit"}, "usage": {"input_tokens": 10, "output_tokens": 10}}


def invoke(g, fn, key="first", **kwargs):
    return g.call(key, "response-" + key, MODEL, {"question": "unit"}, 10, 10, fn, **kwargs)


def test_budget_exceeded_blocks_transport_before_first_call(tmp_path):
    clock, fn = Clock(), Transport()
    g = gate(tmp_path / "budget.db", clock, cap=cost(MODEL, 10, 10) - 1)
    with pytest.raises(BudgetLimitError, match="Campaign budget"):
        invoke(g, fn)
    assert fn.calls == 0
    assert g.report()["calls"] == []
    g.close()


def test_cumulative_budget_blocks_next_call_and_persists(tmp_path):
    clock, fn = Clock(), Transport()
    path = tmp_path / "budget.db"
    g = gate(path, clock, cap=9000)
    invoke(g, fn)
    assert g.report()["used_or_reserved_nanoeur"] == 6000
    g.close()
    g = gate(path, clock, cap=9000)
    with pytest.raises(BudgetLimitError):
        invoke(g, fn, "second")
    assert fn.calls == 1
    g.close()


@pytest.mark.parametrize("limits", [
    {"max_tokens": 19}, {"max_outputs": 9},
])
def test_request_token_budget_blocks_transport(tmp_path, limits):
    fn = Transport()
    g = gate(tmp_path / "budget.db", Clock())
    with pytest.raises(BudgetLimitError, match="Request token"):
        invoke(g, fn, **limits)
    assert fn.calls == 0
    g.close()


def test_completed_call_replays_without_transport(tmp_path):
    path, clock, fn = tmp_path / "resume.db", Clock(), Transport()
    g = gate(path, clock)
    expected = invoke(g, fn)
    g.close()
    g = gate(path, clock)
    assert invoke(g, fn) == expected
    assert fn.calls == 1
    assert g.report()["billed_cost_eur"] is None
    g.close()


def test_changed_prompt_cannot_reuse_call_id(tmp_path):
    fn = Transport()
    g = gate(tmp_path / "resume.db", Clock())
    invoke(g, fn)
    with pytest.raises(ResumeBlockedError, match="identity"):
        g.call("first", "response-first", MODEL, {"question": "changed"}, 10, 10, fn)
    assert fn.calls == 1
    g.close()


def test_changed_campaign_cannot_resume(tmp_path):
    path = tmp_path / "resume.db"
    g = gate(path, Clock())
    g.close()
    with pytest.raises(ResumeBlockedError, match="configuration"):
        CallGate(path, {"bank": "different"}, {MODEL: Quota(100, 100000, 1000)})


def test_timeout_reservation_is_kept_and_campaign_stops(tmp_path):
    clock, path, calls = Clock(), tmp_path / "resume.db", []

    def timeout(*args):
        calls.append(1)
        raise TimeoutError("No usage confirmation")

    g = gate(path, clock)
    with pytest.raises(TimeoutError):
        invoke(g, timeout)
    assert g.report()["used_or_reserved_nanoeur"] == 6000
    g.close()
    g = gate(path, clock)
    for key in ("first", "second"):
        with pytest.raises(ResumeBlockedError):
            invoke(g, timeout, key)
    assert len(calls) == 1
    g.close()


@pytest.mark.parametrize("quota", [Quota(1, 100000, 1000), Quota(100, 15, 1000)])
def test_rpm_and_tpm_wait_without_busy_loop_and_survive_restart(tmp_path, quota):
    path, clock, fn = tmp_path / "quota.db", Clock(), Transport()
    g = gate(path, clock, quota=quota)
    invoke(g, fn)
    g.close()
    g = gate(path, clock, quota=quota)
    invoke(g, fn, "second")
    assert sum(clock.sleeps) == 60
    assert fn.calls == 2
    g.close()


def test_daily_quota_waits_until_pacific_midnight(tmp_path):
    clock, fn = Clock(), Transport()
    g = gate(tmp_path / "quota.db", clock, quota=Quota(100, 100000, 1))
    invoke(g, fn)
    invoke(g, fn, "second")
    assert sum(clock.sleeps) == 1
    assert fn.calls == 2
    g.close()


def test_provider_429_retries_after_delay_with_new_reservation(tmp_path):
    clock, fn = Clock(), Transport()
    attempts = []

    def limited(*args):
        attempts.append(1)
        if len(attempts) == 1:
            raise RateLimitError(retry_after=65)
        return fn(*args)

    g = gate(tmp_path / "quota.db", clock)
    invoke(g, limited)
    assert sum(clock.sleeps) == 65
    assert len(attempts) == 2
    assert g.report()["used_or_reserved_nanoeur"] == 12000
    assert [r["state"] for r in g.report()["calls"]] == ["rate_limited", "done"]
    g.close()


def test_prompt_exceeding_tpm_fails_instead_of_waiting_forever(tmp_path):
    clock, fn = Clock(), Transport()
    g = gate(tmp_path / "quota.db", clock, quota=Quota(100, 9, 1000))
    with pytest.raises(BudgetLimitError, match="TPM"):
        invoke(g, fn)
    assert not clock.sleeps and fn.calls == 0
    g.close()


def test_usage_above_reservation_stops_campaign(tmp_path):
    g = gate(tmp_path / "usage.db", Clock())

    def invalid(*args):
        return {"output": {}, "usage": {"input_tokens": 11, "output_tokens": 10}}

    with pytest.raises(UsageContractError):
        invoke(g, invalid)
    with pytest.raises(ResumeBlockedError):
        invoke(g, Transport(), "next")
    g.close()


def test_missing_usage_never_becomes_zero_cost(tmp_path):
    g = gate(tmp_path / "usage.db", Clock())
    with pytest.raises(KeyError):
        invoke(g, lambda *args: {"output": {}})
    assert g.report()["used_or_reserved_nanoeur"] == 6000
    assert g.report()["calls"][0]["actual"] is None
    g.close()


def test_pending_reservation_is_visible_to_another_connection(tmp_path):
    path, clock = tmp_path / "race.db", Clock()
    first, second = gate(path, clock), gate(path, clock)
    fn = Transport()

    def nested(*args):
        with pytest.raises(ResumeBlockedError):
            invoke(second, fn, "second")
        assert fn.calls == 0
        return fn(*args)

    invoke(first, nested)
    assert fn.calls == 1
    first.close()
    second.close()


def test_provider_cooldown_cannot_be_bypassed_by_new_call_after_restart(tmp_path):
    path, clock = tmp_path / "cooldown.db", Clock()
    g = gate(path, clock)

    def limited(*args):
        raise RateLimitError(retry_after=65)

    with pytest.raises(ResumeBlockedError):
        invoke(g, limited, retries=0)
    g.close()
    g = gate(path, clock)
    fn = Transport()
    invoke(g, fn, "new")
    assert sum(clock.sleeps) == 65
    assert fn.calls == 1
    g.close()
