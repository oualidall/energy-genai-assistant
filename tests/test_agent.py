"""Tests for the LangGraph agent — routing, nodes and end-to-end, all mocked."""

from __future__ import annotations

from src.agent.graph import EnergyAgent


class _FakeLLM:
    """Dispatches a canned response based on which prompt it receives."""

    def __init__(self, route: str = "sql", sql: str = "", answer: str = "réponse") -> None:
        self.route = route
        self.sql = sql
        self.answer = answer

    def invoke(self, prompt: str):
        if "expert SQL BigQuery" in prompt:
            content = self.sql
        elif "Catégorise" in prompt:
            content = self.route
        else:  # synthesis or direct
            content = self.answer
        return type("Msg", (), {"content": content})()


class _FakeClient:
    """Fake BigQuery client returning fixed rows."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def query(self, _sql: str):
        rows = self._rows
        return type("Job", (), {"result": lambda self: rows})()


class _FakeRetriever:
    def retrieve(self, _query: str, k: int = 3) -> list[str]:
        return ["NUCLEAR = nucléaire", "SOLAR = solaire"][:k]


def _agent(route="sql", sql="", answer="réponse", rows=None, retriever=None):
    return EnergyAgent(
        llm=_FakeLLM(route=route, sql=sql, answer=answer),
        retriever=retriever or _FakeRetriever(),
        bq_client=_FakeClient(rows or []),
    )


def test_routes_sql_question_and_answers_from_rows() -> None:
    agent = _agent(
        route="sql",
        sql="SELECT MAX(pic_mw) AS pic FROM consommation_journaliere",
        answer="Le pic est de 59537 MW.",
        rows=[{"pic": 59537.0}],
    )
    out = agent.answer("Quel est le pic de consommation ?")
    assert out["route"] == "sql"
    assert out["sql"].startswith("SELECT")
    assert "59537" in out["answer"]


def test_routes_rag_question_to_definitions() -> None:
    agent = _agent(route="rag", answer="NUCLEAR désigne le nucléaire.")
    out = agent.answer("Que veut dire la filière NUCLEAR ?")
    assert out["route"] == "rag"
    assert out["sql"] is None
    assert "nucléaire" in out["answer"].lower()


def test_routes_direct_question() -> None:
    agent = _agent(route="direct", answer="Bonjour ! Comment puis-je aider ?")
    out = agent.answer("Bonjour")
    assert out["route"] == "direct"
    assert out["answer"]


def test_sql_node_falls_back_gracefully_on_unsafe_sql() -> None:
    # model returns non-SELECT -> generate_sql raises -> node returns empty rows
    agent = _agent(route="sql", sql="DROP TABLE consommation_journaliere", answer="Donnée indisponible.")
    out = agent.answer("supprime tout")
    assert out["route"] == "sql"
    assert out["sql"] is None
