"""Central application configuration, loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the whole app.

    Values are read from environment variables (and a local ``.env`` in dev).
    No secret has a real default — the app fails loudly if one is missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini (Google AI Studio)
    google_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # Google Cloud / BigQuery
    gcp_project_id: str = "energy-genai-assistant"
    bigquery_dataset: str = "rte_energy"

    # Source Postgres (the upstream rte-pipeline marts) — used by export_marts only.
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = ""
    pg_password: str = ""
    pg_database: str = ""
    pg_mart_schema: str = "mart"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_project: str = "energy-genai-assistant"

    # App
    log_level: str = "INFO"


settings = Settings()
