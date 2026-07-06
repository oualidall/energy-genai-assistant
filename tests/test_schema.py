"""Tests for the canonical RTE schema."""

from __future__ import annotations

from src.data.schema import (
    CANONICAL_TYPES,
    TABLES,
    get_table,
    render_schema_prompt,
    table_names,
)


def test_tables_have_unique_names() -> None:
    names = table_names()
    assert len(names) == len(set(names))
    assert names == ["consommation_journaliere", "mix_energetique_hebdomadaire", "solde_echanges_journalier"]


def test_every_column_has_a_known_type() -> None:
    for table in TABLES:
        assert table.columns, f"{table.name} has no columns"
        for col in table.columns:
            assert col.type in CANONICAL_TYPES, f"{table.name}.{col.name}: bad type {col.type}"
            assert col.description, f"{table.name}.{col.name} missing description"


def test_column_names_unique_within_table() -> None:
    for table in TABLES:
        cols = table.column_names()
        assert len(cols) == len(set(cols)), f"duplicate column in {table.name}"


def test_get_table_roundtrip_and_error() -> None:
    assert get_table("consommation_journaliere").name == "consommation_journaliere"
    try:
        get_table("does_not_exist")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for unknown table")


def test_render_schema_prompt_mentions_all_tables_and_columns() -> None:
    prompt = render_schema_prompt()
    for table in TABLES:
        assert table.name in prompt
        for col in table.columns:
            assert col.name in prompt
