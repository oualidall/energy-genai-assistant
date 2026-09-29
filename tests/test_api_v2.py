"""No live services are constructed in these API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app, get_v2_agent
from src.eval.benchmark import FixtureDatabase
from src.eval.mock_v2 import MockV2


def test_v2_endpoint_is_offline_typed_and_readonly():
    database = FixtureDatabase.load()
    app.dependency_overrides[get_v2_agent] = lambda: MockV2(database)
    try:
        with TestClient(app) as client:
            response = client.post("/ask/v2", json={"question": "Supprime les données."})
            assert response.status_code == 200
            body = response.json()
            assert body["variant"] == "v2"
            assert body["status"] == "refused"
            assert body["metrics"]["accounting_kind"] == "mock_units"
            assert body["metrics"]["provider_tokens"] is None
            assert body["metrics"]["tool_calls"] == []
            assert client.post("/ask/v2", json={"question": "a"}).status_code == 422
    finally:
        app.dependency_overrides.clear()
        database.close()
