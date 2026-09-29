"""Offline v2 smoke adapter; no golden-bank/reference-answer access."""

from __future__ import annotations

import hashlib
import json

from src.agent.multi_agent import MultiAgent, normalized
from src.agent.tools import LocalTools
from src.eval.benchmark import ROOT, FixtureDatabase, verify_freeze
from src.eval.mock_runtime import SmokeRetriever


class V2SmokeModel:
    offline = True
    accounting_kind = "mock_units"

    def count_units(self, text: str) -> int:
        # A deterministic test unit, NOT a Gemini tokenizer or provider usage.
        return (len(text.encode("utf-8")) + 3) // 4

    def generate(self, role: str, payload: dict, max_output_units: int) -> str:
        data = payload["data"]
        text = normalized(data["question"])
        if role == "supervisor":
            if any(word in text for word in ("allemagne", "prix", "carbone", "recette",
                                             "appartement", "billet", "gateau")):
                output = {"route": "refuse", "message":
                          "Mon périmètre couvre les volumes historiques RTE français, pas cette demande."}
            elif any(word in text for word in ("meilleure", "derniere", "cette annee")):
                output = {"route": "clarify", "message":
                          "Quelle période, quelle filière et quelle mesure souhaitez-vous préciser ?"}
            else:
                document = any(word in text for word in (
                    "signifie", "designe", "unite", "granularite", "fuseau", "represente",
                ))
                output = {"route": "rag" if document else "sql"}
        elif role == "sql":
            output = {"sql": "SELECT COUNT(*) AS row_count FROM rte_energy.consommation_journaliere"}
        elif role == "synthesis":
            items = data["untrusted_evidence"]
            output = {
                "answer": "\n".join(json.dumps(e["content"], ensure_ascii=False) for e in items),
                "citations": [e["evidence_id"] for e in items],
            }
        elif role == "critique":
            output = {"verdict": "accept", "reason": "Smoke fixture only; no semantic judgment.",
                      "evidence_ids": data["draft"]["citations"]}
        else:
            raise ValueError("Unknown role")
        raw = json.dumps(output, ensure_ascii=False)
        if self.count_units(raw) > max_output_units:
            raise ValueError("Mock output exceeds reserved cap")
        return raw


class MockV2:
    def __init__(self, database: FixtureDatabase, limits=None) -> None:
        lock = verify_freeze()
        self.retriever = SmokeRetriever()

        def retrieve(question):
            self.retriever.retrieve(question)
            return self.retriever.calls[-1]

        tools = LocalTools(
            retrieve=retrieve, query=database.execute,
            corpus_version=lock["files"]["src/rag/knowledge.py"],
            snapshot_version=lock["files"]["evals/fixtures/snapshot.json"],
        )
        self.agent = MultiAgent(V2SmokeModel(), tools, limits)
        self.last = None

    def answer(self, question: str) -> dict:
        self.last = None
        self.retriever.calls.clear()
        self.last = self.agent.answer(question)
        return self.last

    def observations(self) -> dict:
        metrics = self.last["metrics"] if self.last else {
            "model_calls": [], "tool_calls": [], "critic_calls": 0, "revision_requests": 0,
        }
        sql_calls = []
        doc_calls = []
        for call in metrics["tool_calls"]:
            if call["name"] == "query_readonly":
                rows = [row for item in call["evidence"] for row in item["content"]]
                sql_calls.append({"sql": call["sql"], "rows": rows, "error": call["error"]})
            else:
                doc_calls.append([{"source_id": e["source_id"], "content": e["content"]}
                                  for e in call["evidence"]])
        return {
            "llm_calls": len(metrics["model_calls"]), "tool_calls": len(metrics["tool_calls"]),
            "sql_calls": sql_calls, "document_calls": doc_calls,
            "critic_calls": metrics["critic_calls"],
            "revision_requests": metrics["revision_requests"],
            "tokens": None, "usage_reason": "Offline mock units are not provider tokens.",
            "mock_budget": metrics, "llm_api_cost_eur": "0", "total_cost_eur": None,
            "source_sha256": hashlib.sha256(
                (ROOT / "src/eval/mock_v2.py").read_bytes()
            ).hexdigest(),
        }
