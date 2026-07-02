"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness / readiness probe payload."""

    status: str = Field(examples=["ok"])
    llm_configured: bool = Field(description="True when a Gemini API key is present.")


class AskRequest(BaseModel):
    """A natural-language question about the energy data."""

    question: str = Field(
        min_length=3,
        max_length=1000,
        examples=["Quelle a été la consommation électrique moyenne en janvier ?"],
    )


class AskResponse(BaseModel):
    """The assistant's answer plus a bit of provenance."""

    answer: str
    route: str = Field(description="Which tool answered: 'rag', 'sql' or 'direct'.")
    sql: str | None = Field(default=None, description="Generated SQL, if the SQL route was used.")
