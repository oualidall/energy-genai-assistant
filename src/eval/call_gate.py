"""Durable mock-tested pre-call controls. No Gemini network adapter is enabled.

Integer nano-euros avoid floating point rounding. Budget prices deliberately
include the approved planning FX (1 USD = 1 EUR) and 20% provision.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from src.eval.pilot_audit import usage_counts


class BudgetLimitError(RuntimeError):
    pass


class ResumeBlockedError(RuntimeError):
    pass


class UsageContractError(RuntimeError):
    pass


class RateLimitError(RuntimeError):
    def __init__(self, retry_after: float = 60, daily: bool = False):
        super().__init__("Provider quota exhausted")
        if retry_after < 0:
            raise ValueError("Invalid retry delay")
        self.retry_after = retry_after
        self.daily = daily


@dataclass(frozen=True)
class Quota:
    rpm: int
    tpm: int
    rpd: int

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError("Positive verified project quotas required")


# Per-token budget nano-EUR, including a 20% planning provision.
PRICES = {
    "gemini-2.5-flash-lite": (120, 480),
    "gemini-2.5-flash": (360, 3000),
}
PRICE_DATE = "2026-09-30"


def cost(model: str, inputs: int, outputs: int) -> int:
    if any(type(n) is not int or n < 0 for n in (inputs, outputs)):
        raise ValueError("Invalid token count")
    incoming, outgoing = PRICES[model]
    return inputs * incoming + outputs * outgoing


def pacific_window(now: float) -> tuple[float, float]:
    local = datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class CallGate:
    """One campaign ledger; all clients sharing it reserve atomically.

    Transport is injected and must return output + complete provider usage.
    This module alone cannot establish the billing tier of an API credential.
    """
    def __init__(self, path: Path, identity: dict, quotas: dict[str, Quota],
                 cap_nanoeur: int = 500_000_000, clock=time.time, sleep=time.sleep):
        if type(cap_nanoeur) is not int or cap_nanoeur <= 0 or not quotas:
            raise ValueError("Positive cap and verified quotas required")
        if set(quotas) - set(PRICES):
            raise ValueError("Unpriced model")
        self.clock, self.sleep = clock, sleep
        self.quotas, self.cap = quotas, cap_nanoeur
        self.lock = RLock()
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, request_id TEXT, fingerprint TEXT, model TEXT,
                state TEXT, started REAL, input_limit INTEGER, output_limit INTEGER,
                reserve INTEGER, actual INTEGER, input_used INTEGER, output_used INTEGER,
                output TEXT, retry_at REAL, error TEXT
            );
            CREATE TABLE IF NOT EXISTS forecasts (call_id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS waits (
                call_id TEXT, started REAL, duration REAL, reason TEXT
            );
        """)
        binding = canonical({
            "ledger_schema": "2", "identity": identity, "quotas": {k: asdict(v) for k, v in quotas.items()},
            "cap_nanoeur": cap_nanoeur, "prices": PRICES, "price_date": PRICE_DATE,
        })
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT OR IGNORE INTO config VALUES (1, ?)", (binding,))
                if self.db.execute("SELECT value FROM config").fetchone()[0] != binding:
                    raise ResumeBlockedError("Campaign inputs/configuration changed")
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                self.db.close()
                raise

    def close(self):
        self.db.close()

    def _wait(self, call_id: str, until: float, reason: str):
        while self.clock() < until:
            now = self.clock()
            delay = min(30.0, until - now)
            # Persist before sleeping; process interruption does not erase quota history.
            with self.lock:
                self.db.execute("INSERT INTO waits VALUES (?, ?, ?, ?)",
                                (call_id, now, delay, reason))
            self.sleep(delay)

    def _prepare(self, key, request_id, model, fingerprint, inputs, outputs,
                 max_tokens, max_outputs, max_calls):
        now = self.clock()
        quota = self.quotas[model]
        if inputs > quota.tpm:
            raise BudgetLimitError("One prompt exceeds TPM; waiting cannot fix it")
        reserve = cost(model, inputs, outputs)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                old = self.db.execute("SELECT * FROM calls WHERE id=?", (key,)).fetchone()
                if old:
                    if old["fingerprint"] != fingerprint or old["request_id"] != request_id:
                        raise ResumeBlockedError("Call identity changed")
                    result = ("old", dict(old))
                else:
                    rows = self.db.execute("SELECT * FROM calls").fetchall()
                    if any(r["state"] in {"pending", "uncertain"} for r in rows):
                        raise ResumeBlockedError("Unreconciled call blocks campaign")
                    if sum(r["actual"] if r["actual"] is not None else r["reserve"]
                           for r in rows) + reserve > self.cap:
                        raise BudgetLimitError("Campaign budget blocks provider call")
                    related = [r for r in rows if r["request_id"] == request_id]
                    used_in = sum(r["input_used"] if r["actual"] is not None
                                  else r["input_limit"] for r in related)
                    used_out = sum(r["output_used"] if r["actual"] is not None
                                   else r["output_limit"] for r in related)
                    if (len(related) >= max_calls or used_out + outputs > max_outputs
                            or used_in + used_out + inputs + outputs > max_tokens):
                        raise BudgetLimitError("Request token/call budget blocks provider call")
                    own = [r for r in rows if r["model"] == model]
                    minute = [r for r in own if r["started"] > now - 60]
                    day_start, day_end = pacific_window(now)
                    daily = [r for r in own if r["started"] >= day_start]
                    until = max([now] + [r["retry_at"] for r in own if r["retry_at"]])
                    if len(daily) >= quota.rpd:
                        until = max(until, day_end)
                    if (len(minute) >= quota.rpm
                            or sum(r["input_limit"] for r in minute) + inputs > quota.tpm):
                        until = max(until, min(r["started"] for r in minute) + 60)
                    if until > now:
                        result = ("wait", until)
                    else:
                        self.db.execute(
                            "INSERT INTO calls VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, "
                            "NULL, NULL, NULL, NULL, NULL, NULL)",
                            (key, request_id, fingerprint, model, now, inputs, outputs, reserve),
                        )
                        result = ("new", None)
                self.db.execute("COMMIT")
                return result
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def call(self, key: str, request_id: str, model: str, payload: dict,
             input_tokens: int, max_output_tokens: int, transport,
             max_tokens: int = 16384, max_outputs: int = 3072,
             max_calls: int = 10, retries: int = 3, forecast: dict | None = None):
        """Only explicit 429 errors retry; uncertain outcomes never repeat silently."""
        if model not in self.quotas:
            raise ValueError("Verified model quota missing")
        cost(model, input_tokens, max_output_tokens)
        if (max_output_tokens < 1 or max_output_tokens > 1024
                or not 0 <= retries <= 3
                or any(type(n) is not int or n < 1
                       for n in (max_tokens, max_outputs, max_calls))):
            raise ValueError("Invalid call limits")
        forecast = dict(forecast or {})
        if forecast and any(type(forecast.get(k)) is not int or forecast[k] < 0
                            for k in ("input_tokens", "output_tokens")):
            raise ValueError("Invalid pre-call forecast")
        forecast["prompt_sha256"] = hashlib.sha256(canonical(payload).encode()).hexdigest()
        fingerprint = hashlib.sha256(canonical({
            "forecast": forecast,
            "payload": payload, "model": model, "inputs": input_tokens,
            "outputs": max_output_tokens, "max_tokens": max_tokens,
            "max_outputs": max_outputs, "max_calls": max_calls,
        }).encode()).hexdigest()
        for attempt in range(retries + 1):
            call_id = f"{key}/attempt-{attempt}"
            while True:
                action, data = self._prepare(
                    call_id, request_id, model, fingerprint, input_tokens,
                    max_output_tokens, max_tokens, max_outputs, max_calls,
                )
                if action != "wait":
                    break
                self._wait(call_id, data, "configured_quota")
            if action == "old":
                if data["state"] == "done":
                    return json.loads(data["output"])["output"]
                if data["state"] == "rate_limited":
                    self._wait(call_id, data["retry_at"], "provider_429")
                    continue
                raise ResumeBlockedError("Uncertain/pending call requires reconciliation")
            with self.lock:
                self.db.execute("INSERT INTO forecasts VALUES (?, ?)", (call_id, canonical(forecast)))
            try:
                response = transport(model, payload, max_output_tokens)
                with self.lock:
                    self.db.execute("UPDATE calls SET output=? WHERE id=?",
                                    (canonical(response), call_id))
                if "usageMetadata" in response:
                    incoming, outgoing = usage_counts(response["usageMetadata"])
                else:
                    # Legacy fake transports only; pilot audit rejects missing usageMetadata.
                    usage = response["usage"]
                    incoming = usage["input_tokens"]
                    outgoing = usage["output_tokens"]
                actual = cost(model, incoming, outgoing)
                with self.lock:
                    self.db.execute("UPDATE calls SET actual=?, input_used=?, output_used=? WHERE id=?",
                                    (actual, incoming, outgoing, call_id))
                if incoming > input_tokens or outgoing > max_output_tokens:
                    raise UsageContractError("Provider usage exceeds reservation; stop campaign")
                output = canonical(response)
                with self.lock:
                    self.db.execute(
                        "UPDATE calls SET state='done', actual=?, input_used=?, output_used=?, "
                        "output=? WHERE id=?", (actual, incoming, outgoing, output, call_id),
                    )
                return response["output"]
            except RateLimitError as exc:
                until = self.clock() + max(exc.retry_after, 2 ** attempt)
                if exc.daily:
                    until = max(until, pacific_window(self.clock())[1])
                with self.lock:
                    # Keep the reservation: a quota error is not proof of zero billing.
                    self.db.execute(
                        "UPDATE calls SET state='rate_limited', retry_at=?, error=? WHERE id=?",
                        (until, "429", call_id),
                    )
                if attempt < retries:
                    self._wait(call_id, until, "provider_429")
            except BaseException as exc:
                with self.lock:
                    self.db.execute("UPDATE calls SET state='uncertain', error=? WHERE id=?",
                                    (type(exc).__name__, call_id))
                raise
        raise ResumeBlockedError("Quota retries exhausted; resume after quota verification")

    def report(self) -> dict:
        with self.lock:
            rows = [dict(r) for r in self.db.execute("SELECT * FROM calls ORDER BY started, id")]
            waits = [dict(r) for r in self.db.execute("SELECT * FROM waits")]
        for row in rows:
            saved = self.db.execute("SELECT value FROM forecasts WHERE call_id=?", (row["id"],)).fetchone()
            row["forecast"] = json.loads(saved[0]) if saved else {}
            if row["actual"] is not None:
                row["hypothetical_paid_usd"] = str(Decimal(row["actual"]) / Decimal(1200000000))
            else:
                row["hypothetical_paid_usd"] = None
        return {
            "schema_version": "1", "price_date": PRICE_DATE,
            "cost_kind": "hypothetical_paid_budget; 1 USD=1 EUR plus 20% provision",
            "billed_cost_eur": None,
            "used_or_reserved_nanoeur": sum(
                r["actual"] if r["actual"] is not None else r["reserve"] for r in rows
            ),
            "cap_nanoeur": self.cap, "calls": rows, "waits": waits,
        }
