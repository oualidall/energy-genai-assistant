"""Conservative SQL subset validated at the execution boundary.

SQLGlot parsing is not proof of BigQuery validity. IAM and service-side limits
remain defense in depth. Unknown functions/syntax fail closed.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from src.data.schema import table_names


class UnsafeSQL(ValueError):
    """SQL cannot be submitted under the read-only policy."""


def validate_readonly(sql: str, dataset: str = "rte_energy", project: str | None = None) -> str:
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 12000:
        raise UnsafeSQL("Invalid SQL size")
    try:
        statements = sqlglot.parse(sql, read="bigquery")
    except sqlglot.errors.SqlglotError as exc:
        raise UnsafeSQL("SQL parse failed") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeSQL("Exactly one SELECT, optionally with CTEs, is required")
    tree = statements[0]
    forbidden = (
        exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
        exp.Command, exp.Merge, exp.Into, exp.Union, exp.Intersect, exp.Except,
    )
    allowed_functions = {"SUM", "AVG", "MIN", "MAX", "COUNT", "NULLIF", "COALESCE", "CASE", "IF", "ABS"}
    for node in tree.walk():
        if isinstance(node, forbidden):
            raise UnsafeSQL("Statement outside read-only subset")
        if isinstance(node, exp.Func):
            if isinstance(node, exp.Anonymous) or node.sql_name() not in allowed_functions:
                raise UnsafeSQL("Function outside allowlist")
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise UnsafeSQL("Recursive CTEs are disabled")
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for cte in tree.find_all(exp.CTE):
        if not isinstance(cte.this, exp.Select):
            raise UnsafeSQL("CTE must contain a SELECT")
    allowed_tables = set(table_names())
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeSQL("Table functions are disabled")
        if table.name in ctes and not table.db and not table.catalog:
            continue
        if table.name not in allowed_tables:
            raise UnsafeSQL("Table outside allowlist")
        if table.db and table.db != dataset:
            raise UnsafeSQL("Dataset outside allowlist")
        if table.catalog and table.catalog != project:
            raise UnsafeSQL("Project outside allowlist")
    return sql
