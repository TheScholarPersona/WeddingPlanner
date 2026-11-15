"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Runtime connection: role `app_user` (no BYPASSRLS), subject to row-level security.
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://app_user:app_user@localhost:5432/weddingplanner")
    )
    # Migration connection: the schema owner. Never used by request handlers.
    migration_database_url: PostgresDsn = Field(
        default=PostgresDsn(
            "postgresql+asyncpg://wedding_owner:wedding_owner@localhost:5432/weddingplanner"
        )
    )
    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))

    # Origins allowed to call the API from a browser (only needed outside the Caddy proxy).
    cors_origins: list[str] = []

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.environment in {"local", "test", "staging"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
