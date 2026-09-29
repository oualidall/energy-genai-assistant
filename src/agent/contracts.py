"""Versioned shared-state contracts; no model/provider initialization."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limits(Contract):
    max_tokens: int = Field(default=32768, ge=1, le=100000)
    max_model_calls: int = Field(default=10, ge=1, le=20)
    max_tool_calls: int = Field(default=6, ge=0, le=12)
    max_revisions: int = Field(default=2, ge=0, le=2)
    max_steps: int = Field(default=18, ge=1, le=24)
    max_output_tokens: int = Field(default=2048, ge=1, le=4096)


class Plan(Contract):
    route: Literal["rag", "sql", "mixed", "clarify", "refuse"]
    message: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def terminal_message(self):
        if self.route in {"clarify", "refuse"} and not self.message.strip():
            raise ValueError("Terminal plan requires an explanation")
        return self


class SQLProposal(Contract):
    sql: str = Field(min_length=1, max_length=12000)


class Draft(Contract):
    answer: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=20)


class Critique(Contract):
    verdict: Literal["accept", "revise"]
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class Evidence(Contract):
    evidence_id: str
    kind: Literal["document", "sql_result"]
    source_id: str
    source_version: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: Any
    tool_call_id: str
    sql: str | None = None
    truncated: bool = False


class Metrics(Contract):
    duration_ns: int = Field(ge=0)
    accounting_kind: Literal["provider_tokens", "mock_units"]
    reserved_units: int = Field(ge=0)
    used_units: int = Field(ge=0)
    model_calls: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    critic_calls: int = Field(ge=0)
    revision_requests: int = Field(ge=0)
    steps: int = Field(ge=0)
    provider_tokens: int | None = None
    estimated_cost_eur: str | None = None


class AnswerResult(Contract):
    schema_version: Literal["1"] = "1"
    variant: Literal["v2"] = "v2"
    request_id: str
    answer: str
    route: Literal["rag", "sql", "mixed", "direct", "unknown"]
    status: Literal[
        "answered", "clarification_required", "refused",
        "budget_exhausted", "unsubstantiated", "error",
    ]
    sql: str | None = None
    citations: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    metrics: Metrics
    error: str | None = None

    @model_validator(mode="after")
    def citations_resolve(self):
        available = {e.evidence_id for e in self.evidence}
        if len(available) != len(self.evidence):
            raise ValueError("Duplicate evidence IDs")
        if not set(self.citations) <= available:
            raise ValueError("Unresolved citation")
        if self.status == "answered" and self.route != "direct" and not self.citations:
            raise ValueError("Grounded answer requires citations")
        return self
