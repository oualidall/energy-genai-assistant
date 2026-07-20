"""Text-to-SQL: turn a natural-language question into a safe BigQuery query.

The chain is deliberately small and auditable:

    question ──► build_prompt ──► Gemini ──► strip fences ──► is_safe_sql ──► qualify

``is_safe_sql`` is a hard guardrail: the model may only ever produce a single
read-only ``SELECT``/``WITH`` statement. Anything else (DML/DDL, multiple
statements) is rejected *before* it can touch BigQuery.

The LLM is injected so tests can run without any API call.
"""

from __future__ import annotations

import re

from src.config import settings
from src.data.schema import render_schema_prompt, table_names

_PROMPT_TEMPLATE = """Tu es un expert SQL BigQuery (Standard SQL). À partir du schéma \
ci-dessous, écris UNE seule requête SQL qui répond à la question.

Règles:
- Uniquement du SELECT en lecture (jamais INSERT/UPDATE/DELETE/DDL).
- Utilise uniquement les tables et colonnes du schéma, avec leur nom tel quel (sans préfixe).
- Réponds UNIQUEMENT avec la requête SQL, sans explication ni balises Markdown.

Schéma:
{schema}

Question: {question}
SQL:"""

# Keywords that must never appear in a generated query.
_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "MERGE",
    "TRUNCATE", "GRANT", "REVOKE", "REPLACE", "CALL", "EXECUTE", "INTO",
}


def build_prompt(question: str) -> str:
    return _PROMPT_TEMPLATE.format(schema=render_schema_prompt(), question=question)


def strip_fences(text: str) -> str:
    """Remove Markdown code fences and a leading ``sql`` language tag."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def is_safe_sql(sql: str) -> bool:
    """Return True only for a single read-only SELECT/WITH statement."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False
    # reject multiple statements
    if ";" in cleaned:
        return False
    upper = cleaned.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False
    words = set(re.findall(r"[A-Z_]+", upper))
    return not (words & _FORBIDDEN)


def qualify_tables(sql: str, dataset: str | None = None) -> str:
    """Prefix bare table names with the dataset (``rte_energy.<table>``)."""
    dataset = dataset or settings.bigquery_dataset
    out = sql
    for name in table_names():
        # match the table name when not already preceded by a dot or word char
        out = re.sub(rf"(?<![.\w]){re.escape(name)}\b", f"{dataset}.{name}", out)
    return out


def get_llm():
    """Build the Gemini chat model (temperature 0 for deterministic SQL)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=settings.gemini_model, temperature=0)


def generate_sql(question: str, llm=None) -> str:
    """Generate a SQL query for ``question``. Raises ValueError if it is unsafe."""
    llm = llm or get_llm()
    raw = llm.invoke(build_prompt(question))
    text = raw.content if hasattr(raw, "content") else str(raw)
    sql = strip_fences(text)
    if not is_safe_sql(sql):
        raise ValueError(f"refused unsafe or non-SELECT SQL: {sql!r}")
    return sql


if __name__ == "__main__":
    import sys

    from src.sql.executor import run_query

    question = " ".join(sys.argv[1:]) or "Quel jour la France a-t-elle le plus exporté ?"
    sql = generate_sql(question)
    print("Question:", question)
    print("SQL     :", sql)
    print("Résultat:", run_query(qualify_tables(sql)))
