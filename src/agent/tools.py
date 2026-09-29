"""Local implementations behind a small tool protocol, ready for MCP adapters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Protocol

from src.agent.contracts import Evidence
from src.sql.guard import validate_readonly


def evidence(kind: str, source: str, version: str, content, call_id: str,
             sql: str | None = None, truncated: bool = False) -> Evidence:
    serialized = json.dumps(content, ensure_ascii=False, sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return Evidence(
        evidence_id=f"{call_id}:{source}", kind=kind, source_id=source,
        source_version=version, content_hash=digest, content=content,
        tool_call_id=call_id, sql=sql, truncated=truncated,
    )


class Tools(Protocol):
    def search(self, question: str, call_id: str) -> list[Evidence]: ...
    def query(self, sql: str, call_id: str) -> list[Evidence]: ...


class LocalTools:
    def __init__(self, retrieve: Callable, query: Callable, corpus_version: str,
                 snapshot_version: str, dataset: str = "rte_energy",
                 project: str | None = None) -> None:
        self.retrieve_fn = retrieve
        self.query_fn = query
        self.corpus_version = corpus_version
        self.snapshot_version = snapshot_version
        self.dataset = dataset
        self.project = project

    def search(self, question: str, call_id: str) -> list[Evidence]:
        documents = self.retrieve_fn(question)
        return [
            evidence("document", document["source_id"], self.corpus_version,
                     document["content"], call_id)
            for document in documents[:3]
        ]

    def query(self, sql: str, call_id: str) -> list[Evidence]:
        validate_readonly(sql, dataset=self.dataset, project=self.project)
        rows = self.query_fn(sql)
        if not rows:
            return []
        return [evidence(
            "sql_result", "sql", self.snapshot_version, rows[:100], call_id,
            sql=sql, truncated=len(rows) > 100,
        )]
