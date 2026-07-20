"""Load the RTE energy tables into BigQuery.

Pipeline: ``export_marts`` writes one CSV per table into ``data/``; this module
creates the dataset + tables (from :mod:`src.data.schema`) and loads those CSVs.

Run (once GCP is configured and the CSVs exist):

    python -m src.data.load_bigquery

Idempotent: the dataset is created if missing and each table is overwritten
(``WRITE_TRUNCATE``) so re-running always yields a clean, deterministic state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.cloud import bigquery

from src.config import settings
from src.data.schema import TABLES, Table

logging.basicConfig(
    level=settings.log_level,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")

# Canonical type -> BigQuery Standard-SQL type.
_BQ_TYPE = {
    "DATE": "DATE",
    "FLOAT": "FLOAT64",
    "INT": "INT64",
    "STRING": "STRING",
}


def build_bq_schema(table: Table) -> list[bigquery.SchemaField]:
    """Map a canonical :class:`~src.data.schema.Table` to BigQuery SchemaFields."""
    return [
        bigquery.SchemaField(
            name=col.name,
            field_type=_BQ_TYPE[col.type],
            mode="NULLABLE",
            description=col.description,
        )
        for col in table.columns
    ]


def dataset_ref() -> str:
    return f"{settings.gcp_project_id}.{settings.bigquery_dataset}"


def ensure_dataset(client: bigquery.Client) -> None:
    """Create the dataset if it does not already exist."""
    dataset = bigquery.Dataset(dataset_ref())
    dataset.location = "EU"
    client.create_dataset(dataset, exists_ok=True)
    logger.info("dataset ready: %s", dataset_ref())


def load_table(client: bigquery.Client, table: Table, data_dir: Path = DATA_DIR) -> int:
    """Load ``data/<table>.csv`` into BigQuery. Returns the number of rows loaded."""
    csv_path = data_dir / f"{table.name}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} not found. Run `python -m src.data.export_marts` first."
        )

    table_id = f"{dataset_ref()}.{table.name}"
    job_config = bigquery.LoadJobConfig(
        schema=build_bq_schema(table),
        skip_leading_rows=1,
        source_format=bigquery.SourceFormat.CSV,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with csv_path.open("rb") as fh:
        job = client.load_table_from_file(fh, table_id, job_config=job_config)
    job.result()  # wait for completion

    loaded = client.get_table(table_id).num_rows
    logger.info("loaded %s rows into %s", loaded, table_id)
    return loaded


def main(data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Create the dataset and load every table. Returns {table: rows}."""
    client = bigquery.Client(project=settings.gcp_project_id)
    ensure_dataset(client)
    counts = {t.name: load_table(client, t, data_dir) for t in TABLES}
    logger.info("load complete: %s", counts)
    return counts


if __name__ == "__main__":
    main()
