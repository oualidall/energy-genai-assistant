"""Export the RTE dbt *mart* tables from Postgres to local CSVs.

This is the bridge from the upstream `rte-pipeline` project (whose dbt models
materialise into a Postgres ``mart`` schema) to this project: it writes one CSV
per table into ``data/``, which :mod:`src.data.load_bigquery` then loads.

Run (with the rte-pipeline Postgres reachable and PG_* set in ``.env``):

    python -m src.data.export_marts

Kept separate from the BigQuery loader so the two halves (source read / warehouse
write) can be run and tested independently.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from src.config import settings
from src.data.schema import TABLES, Table

logging.basicConfig(
    level=settings.log_level,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")

# Target table name -> source table name in the Postgres ``mart`` schema.
SOURCE_TABLE = {
    "consommation_journaliere": "mart_consommation_journaliere",
    "mix_energetique_hebdomadaire": "mart_mix_energetique_hebdomadaire",
    "solde_echanges_journalier": "mart_solde_echanges_journalier",
}


def _engine():
    url = (
        f"postgresql+psycopg2://{settings.pg_user}:{settings.pg_password}"
        f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_database}"
    )
    return create_engine(url)


def export_query(table: Table) -> str:
    """Build the SELECT that pulls exactly the target columns, in order."""
    cols = ", ".join(table.column_names())
    source = f"{settings.pg_mart_schema}.{SOURCE_TABLE[table.name]}"
    return f"SELECT {cols} FROM {source} ORDER BY 1"


def export_all(data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Export every mart table to ``data/<table>.csv``. Returns {table: rows}."""
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = _engine()
    counts: dict[str, int] = {}
    for table in TABLES:
        frame = pd.read_sql(export_query(table), engine)
        out = data_dir / f"{table.name}.csv"
        frame.to_csv(out, index=False)
        counts[table.name] = len(frame)
        logger.info("exported %s rows -> %s", len(frame), out)
    logger.info("export complete: %s", counts)
    return counts


if __name__ == "__main__":
    export_all()
