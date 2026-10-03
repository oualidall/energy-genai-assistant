"""Offline recorder tests; fabricated responses never become published demos."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.demo_guardrail import ROOT, generate, sync_readme
from scripts.demo_run import (
    MAX_CALLS,
    MeteredLLM,
    ReadOnlyBigQuery,
    run_demo,
)
from src.agent.graph import AgentExecutionAborted


def test_generated_guardrail_is_current(tmp_path):
    output = tmp_path / "guardrail.md"
    generate(output)
    assert output.read_bytes() == (ROOT / "docs/demo/guardrail.md").read_bytes()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    actual = readme.split("<!-- demo:guardrail:start -->\n")[1].split("<!-- demo:guardrail:end -->")[0]
    assert actual == output.read_text(encoding="utf-8")


def response(text, usage=True):
    result = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    if usage:
        result["usageMetadata"] = {"promptTokenCount": 7, "candidatesTokenCount": 3, "totalTokenCount": 10}
    return result


def test_eleventh_call_never_reaches_transport():
    sent = []
    llm = MeteredLLM(lambda prompt: sent.append(prompt) or response("sql"))
    for _ in range(MAX_CALLS):
        llm.invoke("route")
    with pytest.raises(AgentExecutionAborted, match="10 appels"):
        llm.invoke("blocked")
    assert len(sent) == len(llm.calls) == MAX_CALLS


def test_failed_attempt_reserves_call_and_unknown_usage():
    def fail(_):
        raise OSError("offline")
    llm = MeteredLLM(fail)
    with pytest.raises(AgentExecutionAborted):
        llm.invoke("question")
    assert len(llm.calls) == 1
    assert llm.calls[0]["usageMetadata"] is None


def test_oversized_prompt_never_reaches_transport():
    sent = []
    llm = MeteredLLM(lambda prompt: sent.append(prompt))
    with pytest.raises(AgentExecutionAborted, match="24000"):
        llm.invoke("a" * 24001)
    assert not sent
    assert not llm.calls


class FakeClient:
    def __init__(self):
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        return SimpleNamespace(result=lambda: [{"fixture": 42}])


class FakeRetriever:
    def retrieve(self, question, k=3):
        return ["Solde = export - import (test fixture)."]


def test_actual_graph_partial_transcript_keeps_guard_error_and_usage(tmp_path):
    def transport(prompt):
        if "Catégorise" in prompt:
            return response("rag" if "signifie" in prompt else "sql")
        if "expert SQL BigQuery" in prompt:
            return response("DELETE FROM consommation_journaliere" if "Supprime" in prompt else "SELECT 42")
        return response("Réponse de test.")
    output = tmp_path / "transcript.md"
    client = FakeClient()
    result = run_demo(transport, bq_client=client, retriever=FakeRetriever(),
                      output=output, metadata={"mode": "test fixture"})
    assert result["stopped"]
    assert len(result["calls"]) == 10
    assert len(client.queries) == 2
    assert result["records"][-1]["route"] == "sql"
    assert "refused unsafe" in result["records"][-1]["error"]
    text = output.read_text(encoding="utf-8")
    assert "DELETE FROM consommation_journaliere" in text
    assert "non obtenue" in text
    assert "Jetons totaux rapportés par l'API : 100." in text
    assert '"fixture": 42' in text


def test_complete_direct_run_and_missing_usage_are_not_fabricated(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("<!-- demo:conversation:start -->\nPending\n<!-- demo:conversation:end -->", encoding="utf-8")
    result = run_demo(lambda p: response("direct" if "Catégorise" in p else "Réponse.", usage=False),
                      bq_client=FakeClient(), retriever=FakeRetriever(),
                      output=tmp_path / "transcript.md", metadata={"mode": "test"}, readme=readme)
    assert not result["stopped"]
    assert len(result["records"]) == 4
    assert len(result["calls"]) == 8
    text = readme.read_text(encoding="utf-8")
    assert "inconnus" in text
    assert "Pending" not in text
    assert "refused unsafe" not in text


def test_readonly_adapter_blocks_write_before_bigquery():
    client = FakeClient()
    with pytest.raises(ValueError, match="refused unsafe"):
        ReadOnlyBigQuery(client).query("DELETE FROM consommation_journaliere")
    assert client.queries == []


def test_readme_sync_requires_explicit_markers(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("unchanged", encoding="utf-8")
    with pytest.raises(ValueError, match="markers"):
        sync_readme(path, "conversation", "test")
    assert path.read_text(encoding="utf-8") == "unchanged"


def test_budget_cancellation_in_sql_node_is_not_swallowed(tmp_path):
    sent = []
    def transport(prompt):
        sent.append(prompt)
        return response("sql" if "Catégorise" in prompt else "SELECT 1")
    result = run_demo(transport, bq_client=FakeClient(), retriever=FakeRetriever(),
                      output=tmp_path / "partial.md", metadata={"mode": "test"})
    assert len(sent) == 10
    assert result["stopped"]
    assert "answer" not in result["records"][-1]
    assert result["records"][-1]["route"] == "sql"
