"""Evaluate the agent against the golden-questions set.

Two complementary metrics:

- **execution match** (objective): run the agent's SQL and the reference SQL on
  BigQuery and compare the result sets. No LLM judge, no reliance on hard-coded
  expected values — robust to the data window.
- **LLM-as-judge** (optional): ask Gemini whether the agent's natural-language
  answer is consistent with the reference result. Useful for RAG/direct answers
  that have no SQL to compare.

Everything is dependency-injected so the harness is unit-tested with fakes; the
live run (`python -m src.eval.runner`) needs BigQuery and a Gemini quota.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.eval.golden import GoldenQuestion, load_golden_questions
from src.sql.executor import run_query
from src.sql.text_to_sql import qualify_tables

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("eval")

RunQueryFn = Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class QuestionResult:
    id: str
    question: str
    route: str
    agent_sql: str | None
    exec_match: bool
    error: str = ""


@dataclass
class EvalReport:
    results: list[QuestionResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.exec_match)

    @property
    def pass_rate(self) -> float:
        return self.n_passed / self.total if self.total else 0.0


def _canonical(value: Any) -> Any:
    """Normalise a cell so equal values compare equal across SQL variants."""
    if isinstance(value, float | Decimal):
        return round(float(value), 2)
    if isinstance(value, int):
        return round(float(value), 2)
    return str(value)


def _canonical_rows(rows: list[dict[str, Any]]) -> list[tuple]:
    """Rows as an order-insensitive multiset of value-tuples (column names ignored)."""
    return sorted(tuple(_canonical(v) for v in row.values()) for row in rows)


def execution_match(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]]) -> bool:
    """True if two result sets hold the same rows (order- and alias-insensitive)."""
    return _canonical_rows(rows_a) == _canonical_rows(rows_b)


def run_eval(
    agent: Any,
    questions: list[GoldenQuestion] | None = None,
    bq_client: Any = None,
    run_query_fn: RunQueryFn = run_query,
) -> EvalReport:
    """Run every golden question through the agent and score by execution match."""
    questions = questions if questions is not None else load_golden_questions()
    report = EvalReport()

    for q in questions:
        out = agent.answer(q.question)
        agent_sql = out.get("sql")
        try:
            ref_rows = run_query_fn(qualify_tables(q.sql), client=bq_client)
            if agent_sql:
                got_rows = run_query_fn(qualify_tables(agent_sql), client=bq_client)
                match = execution_match(got_rows, ref_rows)
                error = ""
            else:
                match, error = False, "agent produced no SQL"
        except Exception as exc:  # noqa: BLE001 — a bad query scores 0, never crashes the run
            match, error = False, f"{type(exc).__name__}: {exc}"[:150]
        report.results.append(
            QuestionResult(q.id, q.question, out.get("route", ""), agent_sql, match, error)
        )
        log.info("%s %s", "PASS" if match else "FAIL", q.id)

    return report


_JUDGE_PROMPT = """Tu es un évaluateur. Réponds uniquement par OUI ou NON.
La réponse de l'assistant est-elle correcte et cohérente avec le résultat de référence ?
Question: {question}
Réponse de l'assistant: {answer}
Résultat de référence: {reference}
Verdict (OUI/NON):"""


def judge_answer(llm: Any, question: str, answer: str, reference: Any) -> bool:
    """LLM-as-judge: does the NL answer match the reference? Returns True for OUI."""
    prompt = _JUDGE_PROMPT.format(question=question, answer=answer, reference=reference)
    raw = llm.invoke(prompt)
    verdict = (raw.content if hasattr(raw, "content") else str(raw)).strip().upper()
    return verdict.startswith("OUI")


if __name__ == "__main__":
    from src.agent.graph import EnergyAgent

    report = run_eval(EnergyAgent())
    print(f"\nExecution match: {report.n_passed}/{report.total} " f"({report.pass_rate:.0%})")
    for r in report.results:
        flag = "✓" if r.exec_match else "✗"
        detail = r.error or (r.agent_sql or "")
        print(f"  {flag} [{r.route:6}] {r.id:28} {detail}")
