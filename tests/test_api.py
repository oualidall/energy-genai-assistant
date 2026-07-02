"""Smoke tests for the Phase 0 API surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "llm_configured" in body


def test_ask_echoes_question() -> None:
    resp = client.post("/ask", json={"question": "Consommation moyenne en janvier ?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "direct"
    assert "janvier" in body["answer"]


def test_ask_rejects_short_question() -> None:
    resp = client.post("/ask", json={"question": "a"})
    assert resp.status_code == 422
