"""Runtime settings loaded from environment variables (never hard-coded).

Each database role has its own connection URL so that every process gets
only the privileges it needs:

* ``DATABASE_URL``           - read-only role used by the public API
* ``WRITER_DATABASE_URL``    - analysis writer used by ``customerpulse persist``
* ``MIGRATOR_DATABASE_URL``  - schema owner used by Alembic
* ``ADMIN_DATABASE_URL``     - only for ``customerpulse setup-roles``
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from customerpulse.config import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str | None = None
    writer_database_url: str | None = None
    migrator_database_url: str | None = None
    admin_database_url: str | None = None
    cors_origins: str = Field(default="http://localhost:5173")
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def normalise_url(url: str) -> str:
    """Use the psycopg 3 driver regardless of how the URL was written."""
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise ValueError("Database URL must be a PostgreSQL URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
