"""Read-only execution boundary shared by v1 and future MCP tools."""

from __future__ import annotations

from typing import Any

from src.config import settings
from src.sql.guard import validate_readonly


def run_query(sql: str, client: Any = None) -> list[dict[str, Any]]:
    """Validate before client creation/submission; injected clients remain testable."""
    validate_readonly(sql, dataset=settings.bigquery_dataset, project=settings.gcp_project_id)
    if client is None:
        from google.cloud import bigquery

        client = bigquery.Client(project=settings.gcp_project_id)
        config = bigquery.QueryJobConfig(
            use_legacy_sql=False, maximum_bytes_billed=10_000_000,
        )
        job = client.query(sql, job_config=config, timeout=10)
        rows = [dict(row) for row in job.result(timeout=30, max_results=1001)]
        if len(rows) > 1000:
            raise ValueError("Query result exceeds 1000 rows; refusing partial evidence")
        return rows
    job = client.query(sql)
    return [dict(row) for row in job.result()]
