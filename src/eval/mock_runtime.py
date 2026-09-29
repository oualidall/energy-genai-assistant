"""Deliberately limited smoke model, independent of the bank and its references.

This exercises the actual v1 graph but is NOT a proxy for Gemini quality.
The SQL model always counts consumption rows: no question-to-answer lookup.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from src.agent.graph import EnergyAgent
from src.eval.benchmark import FixtureDatabase
from src.rag.knowledge import KNOWLEDGE


class SmokeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        if "Catégorise la question" in prompt:
            question = prompt.split("Question:", 1)[-1].lower()
            is_document = any(term in question for term in (
                "signifie", "désigne", "unité", "granularité", "fuseau", "représente",
            ))
            text = "rag" if is_document else "sql"
        elif "expert SQL BigQuery" in prompt:
            text = "SELECT COUNT(*) AS row_count FROM consommation_journaliere"
        elif "Éléments:\n" in prompt:
            text = prompt.split("Éléments:\n", 1)[1].rsplit("\nRéponse:", 1)[0]
        else:
            text = "Précisez votre question."
        return SimpleNamespace(content=text)


class SmokeRetriever:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        words = set(re.findall(r"\w+", query.lower()))
        ranked = sorted(
            enumerate(KNOWLEDGE),
            key=lambda item: (-len(words & set(re.findall(r"\w+", item[1].lower()))), item[0]),
        )[:k]
        self.calls.append([{"source_id": f"knowledge:{i}", "content": text}
                           for i, text in ranked])
        return [text for _, text in ranked]


class MockV1:
    def __init__(self, database: FixtureDatabase) -> None:
        self.database = database
        self.llm = SmokeLLM()
        self.retriever = SmokeRetriever()
        self.agent = EnergyAgent(
            llm=self.llm, retriever=self.retriever, bq_client=database,
        )

    def answer(self, question: str) -> dict:
        self.llm.calls = 0
        self.retriever.calls.clear()
        self.database.calls.clear()
        return self.agent.answer(question)

    def observations(self) -> dict:
        return {
            "llm_calls": self.llm.calls,
            "tool_calls": len(self.database.calls) + len(self.retriever.calls),
            "sql_calls": list(self.database.calls),
            "document_calls": list(self.retriever.calls),
            "critic_calls": 0,
            "revision_requests": 0,
            "tokens": None,
            "usage_reason": "Offline smoke model has no provider token usage.",
            "llm_api_cost_eur": "0",
            "total_cost_eur": None,
        }
