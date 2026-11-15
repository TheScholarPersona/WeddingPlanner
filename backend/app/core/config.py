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

    # Public base URL of the web app, used for links in emails.
    app_base_url: str = "https://localhost"

    # Sessions and cookies (ADR 003).
    cookie_secure: bool = True
    session_lifetime_hours: int = 24 * 14
    reauth_window_minutes: int = 10
    max_failed_logins: int = 10
    lockout_minutes: int = 15

    # Tokens sent by email.
    invitation_lifetime_days: int = 7
    password_reset_lifetime_minutes: int = 60

    # "redis" in real environments; "memory" keeps tests self-contained.
    rate_limit_backend: Literal["redis", "memory"] = "redis"
    login_rate_limit_per_minute: int = 5

    # "queue": emails are sent by the ARQ worker; "memory": collected in-process (tests).
    email_backend: Literal["queue", "memory"] = "queue"
    email_from: str = "Wedding Planning Platform <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def session_cookie_name(self) -> str:
        return "__Host-session" if self.cookie_secure else "session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-csrf" if self.cookie_secure else "csrf"

    @property
    def docs_enabled(self) -> bool:
        return self.environment in {"local", "test", "staging"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
