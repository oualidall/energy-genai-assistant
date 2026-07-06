"""Tests for the BigQuery loader — pure logic + a fully mocked client (no network)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data import load_bigquery
from src.data.schema import CONSOMMATION, MIX


def test_build_bq_schema_maps_types() -> None:
    fields = load_bigquery.build_bq_schema(CONSOMMATION)
    by_name = {f.name: f for f in fields}

    assert [f.name for f in fields] == CONSOMMATION.column_names()
    assert by_name["date"].field_type == "DATE"
    assert by_name["total_mwh"].field_type == "FLOAT64"
    assert by_name["nb_pics"].field_type == "INT64"
    # descriptions are carried through
    assert by_name["date"].description


def test_build_bq_schema_handles_string_column() -> None:
    fields = load_bigquery.build_bq_schema(MIX)
    filiere = next(f for f in fields if f.name == "filiere")
    assert filiere.field_type == "STRING"


def test_load_table_raises_when_csv_missing(tmp_path: Path) -> None:
    client = MagicMock()
    with pytest.raises(FileNotFoundError):
        load_bigquery.load_table(client, CONSOMMATION, data_dir=tmp_path)


def test_load_table_loads_and_returns_rowcount(tmp_path: Path) -> None:
    # minimal CSV with the right header
    csv = tmp_path / f"{CONSOMMATION.name}.csv"
    csv.write_text(
        "date,total_mwh,moyenne_mw,pic_mw,creux_mw,nb_pics\n"
        "2025-01-15,1234.5,51000.0,62000.0,40000.0,20\n",
        encoding="utf-8",
    )

    client = MagicMock()
    job = MagicMock()
    client.load_table_from_file.return_value = job
    client.get_table.return_value = MagicMock(num_rows=1)

    rows = load_bigquery.load_table(client, CONSOMMATION, data_dir=tmp_path)

    assert rows == 1
    client.load_table_from_file.assert_called_once()
    job.result.assert_called_once()  # we wait for the load to finish


def test_ensure_dataset_is_idempotent() -> None:
    client = MagicMock()
    load_bigquery.ensure_dataset(client)
    client.create_dataset.assert_called_once()
    # exists_ok must be set so re-runs don't error
    _, kwargs = client.create_dataset.call_args
    assert kwargs.get("exists_ok") is True
