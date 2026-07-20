"""LangGraph agent that answers energy questions.

The graph routes each question, then produces a natural-language answer:

        ┌──────────┐   sql    ┌─────┐
        │  router  ├─────────►│ sql │────┐
        │          │   rag    ├─────┤    ▼
question│          ├─────────►│ rag │──►│ synthesize │──► answer
        │          │  direct  ├─────┤    ▲
        │          ├─────────►│direct│───┘
        └──────────┘          └─────┘

- **sql**    : the question needs figures → text-to-SQL on BigQuery.
- **rag**    : the question is about vocabulary/definitions → knowledge retrieval.
- **direct** : greeting / off-topic → answer directly.

All external dependencies (LLM, retriever, BigQuery client) are injected, so the
whole agent runs in tests against fakes with no network access.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from src.rag.knowledge import Retriever
from src.sql.executor import run_query
from src.sql.text_to_sql import generate_sql, get_llm, qualify_tables

Route = Literal["sql", "rag", "direct"]

_ROUTER_PROMPT = """Catégorise la question en un seul mot :
- "sql" : elle demande un chiffre, une donnée ou une statistique sur l'électricité \
(consommation, production, filières, échanges, dates, records...).
- "rag" : elle demande une définition, la signification d'un terme ou d'une filière, \
une explication du vocabulaire.
- "direct" : salutation ou question générale sans rapport avec les données.
Réponds UNIQUEMENT par un mot : sql, rag ou direct.
Question: {question}
Catégorie:"""

_SYNTH_PROMPT = """Réponds en français, de façon concise et factuelle, à la question \
en t'appuyant UNIQUEMENT sur les éléments fournis. Si les éléments sont vides, dis \
que la donnée n'est pas disponible.
Question: {question}
Éléments:
{evidence}
Réponse:"""

_DIRECT_PROMPT = """Tu es un assistant sur les données électriques françaises (RTE). \
Réponds brièvement en français à la question.
Question: {question}
Réponse:"""


class AgentState(TypedDict, total=False):
    question: str
    route: Route
    sql: str | None
    rows: list[dict[str, Any]]
    context: list[str]
    answer: str


def _content(msg: Any) -> str:
    return msg.content if hasattr(msg, "content") else str(msg)


class EnergyAgent:
    """Routing agent over the RTE energy data."""

    def __init__(self, llm: Any = None, retriever: Retriever | None = None, bq_client: Any = None) -> None:
        self.llm = llm or get_llm()
        self._retriever = retriever
        self.bq_client = bq_client
        self.graph = self._build()

    # ── nodes ──────────────────────────────────────────────────────────────────

    def _route_node(self, state: AgentState) -> AgentState:
        raw = _content(self.llm.invoke(_ROUTER_PROMPT.format(question=state["question"]))).lower()
        route: Route = "sql"  # default: most useful when unsure
        for candidate in ("sql", "rag", "direct"):
            if candidate in raw:
                route = candidate  # type: ignore[assignment]
                break
        return {"route": route}

    def _sql_node(self, state: AgentState) -> AgentState:
        try:
            sql = generate_sql(state["question"], llm=self.llm)
            rows = run_query(qualify_tables(sql), client=self.bq_client)
            return {"sql": sql, "rows": rows}
        except Exception:  # noqa: BLE001 — surface as "no data" rather than crash the API
            return {"sql": None, "rows": []}

    def _rag_node(self, state: AgentState) -> AgentState:
        docs = self._get_retriever().retrieve(state["question"], k=3)
        return {"context": docs}

    def _direct_node(self, state: AgentState) -> AgentState:
        answer = _content(self.llm.invoke(_DIRECT_PROMPT.format(question=state["question"])))
        return {"answer": answer.strip()}

    def _synthesize_node(self, state: AgentState) -> AgentState:
        if state.get("route") == "sql":
            evidence = "\n".join(str(r) for r in state.get("rows", [])) or "(aucune ligne)"
        else:  # rag
            evidence = "\n".join(state.get("context", [])) or "(aucun élément)"
        prompt = _SYNTH_PROMPT.format(question=state["question"], evidence=evidence)
        return {"answer": _content(self.llm.invoke(prompt)).strip()}

    # ── wiring ─────────────────────────────────────────────────────────────────

    def _get_retriever(self) -> Retriever:
        if self._retriever is None:
            from src.rag.knowledge import build_default_retriever

            self._retriever = build_default_retriever()
        return self._retriever

    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("router", self._route_node)
        g.add_node("sql_tool", self._sql_node)
        g.add_node("rag_tool", self._rag_node)
        g.add_node("direct_answer", self._direct_node)
        g.add_node("synthesize", self._synthesize_node)

        g.set_entry_point("router")
        g.add_conditional_edges(
            "router",
            lambda s: s["route"],
            {"sql": "sql_tool", "rag": "rag_tool", "direct": "direct_answer"},
        )
        g.add_edge("sql_tool", "synthesize")
        g.add_edge("rag_tool", "synthesize")
        g.add_edge("direct_answer", END)  # direct already produced the answer
        g.add_edge("synthesize", END)
        return g.compile()

    # ── public API ─────────────────────────────────────────────────────────────

    def answer(self, question: str) -> dict[str, Any]:
        """Run the graph and return {answer, route, sql}."""
        final: AgentState = self.graph.invoke({"question": question})
        return {
            "answer": final.get("answer", ""),
            "route": final.get("route", "direct"),
            "sql": final.get("sql"),
        }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--qfile":
        q = Path(args[1]).read_text(encoding="utf-8").strip()
    else:
        q = " ".join(args) or "C'est quoi la filière NUCLEAR ?"
    result = EnergyAgent().answer(q)
    print("Question:", q)
    print("Route   :", result["route"])
    if result["sql"]:
        print("SQL     :", result["sql"])
    print("Réponse :", result["answer"])
