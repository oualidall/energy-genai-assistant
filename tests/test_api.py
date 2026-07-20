"""API tests for the Phase 3 surface (agent dependency overridden with a fake)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_agent


class _FakeAgent:
    """Stands in for EnergyAgent; returns a fixed result without any LLM call."""

    def answer(self, question: str) -> dict:
        return {
            "answer": f"Réponse de test pour : {question}",
            "route": "sql",
            "sql": "SELECT 1",
        }


@pytest.fixture()
def client():
    app.dependency_overrides[get_agent] = lambda: _FakeAgent()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_healthz_returns_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "llm_configured" in body


def test_ask_returns_agent_answer(client: TestClient) -> None:
    resp = client.post("/ask", json={"question": "Quel est le pic de consommation ?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "sql"
    assert body["sql"] == "SELECT 1"
    assert "Réponse de test" in body["answer"]


def test_ask_rejects_short_question(client: TestClient) -> None:
    resp = client.post("/ask", json={"question": "a"})
    assert resp.status_code == 422  # Pydantic validation, never reaches the agent
