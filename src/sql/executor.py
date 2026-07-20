"""Execute a (already validated) SQL query against BigQuery."""

from __future__ import annotations

from typing import Any

from src.config import settings


def run_query(sql: str, client: Any = None) -> list[dict[str, Any]]:
    """Run ``sql`` on BigQuery and return rows as a list of dicts.

    ``client`` is injectable so tests can pass a fake and avoid any network call.
    Only pass SQL that has already been checked by ``is_safe_sql``.
    """
    if client is None:
        from google.cloud import bigquery

        client = bigquery.Client(project=settings.gcp_project_id)
    job = client.query(sql)
    return [dict(row) for row in job.result()]
