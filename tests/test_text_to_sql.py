"""Tests for the text-to-SQL chain — guardrail, parsing, qualification, mocked LLM."""

from __future__ import annotations

import pytest

from src.sql import text_to_sql as t2s


class _FakeLLM:
    """Returns a canned response with a ``.content`` attribute, like a chat model."""

    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, _prompt: str):
        return type("Msg", (), {"content": self._content})()


# ── guardrail ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT total_mwh FROM consommation_journaliere",
        "select date, export_mwh from solde_echanges_journalier order by export_mwh desc limit 1",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "SELECT total_mwh FROM consommation_journaliere;",  # trailing ; tolerated
    ],
)
def test_is_safe_sql_accepts_selects(sql: str) -> None:
    assert t2s.is_safe_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM consommation_journaliere",
        "DROP TABLE consommation_journaliere",
        "INSERT INTO consommation_journaliere VALUES (1)",
        "UPDATE consommation_journaliere SET total_mwh = 0",
        "SELECT 1; DROP TABLE t",  # multiple statements
        "SELECT * INTO backup FROM consommation_journaliere",
        "",
    ],
)
def test_is_safe_sql_rejects_dangerous(sql: str) -> None:
    assert not t2s.is_safe_sql(sql)


# ── fence stripping ───────────────────────────────────────────────────────────

def test_strip_fences_removes_sql_block() -> None:
    raw = "```sql\nSELECT 1\n```"
    assert t2s.strip_fences(raw) == "SELECT 1"


def test_strip_fences_plain_passthrough() -> None:
    assert t2s.strip_fences("  SELECT 1  ") == "SELECT 1"


# ── qualification ─────────────────────────────────────────────────────────────

def test_qualify_tables_prefixes_dataset() -> None:
    out = t2s.qualify_tables(
        "SELECT total_mwh FROM consommation_journaliere", dataset="rte_energy"
    )
    assert "rte_energy.consommation_journaliere" in out


def test_qualify_tables_is_idempotent() -> None:
    once = t2s.qualify_tables("SELECT 1 FROM mix_energetique_hebdomadaire", dataset="rte_energy")
    twice = t2s.qualify_tables(once, dataset="rte_energy")
    assert once == twice
    assert twice.count("rte_energy.mix_energetique_hebdomadaire") == 1


# ── generate_sql (mocked LLM) ─────────────────────────────────────────────────

def test_generate_sql_parses_and_returns() -> None:
    llm = _FakeLLM("```sql\nSELECT MAX(pic_mw) FROM consommation_journaliere\n```")
    sql = t2s.generate_sql("Quel est le pic max ?", llm=llm)
    assert sql == "SELECT MAX(pic_mw) FROM consommation_journaliere"


def test_generate_sql_rejects_unsafe_model_output() -> None:
    llm = _FakeLLM("DROP TABLE consommation_journaliere")
    with pytest.raises(ValueError):
        t2s.generate_sql("supprime tout", llm=llm)


def test_build_prompt_includes_schema_and_question() -> None:
    prompt = t2s.build_prompt("ma question")
    assert "consommation_journaliere" in prompt
    assert "ma question" in prompt
