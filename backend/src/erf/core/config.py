"""Application settings loaded from environment variables (prefix ``ERF_``) or an ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ERF_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "Engineering Resource Requests"
    base_url: str = "http://localhost:5173"
    """Public URL of the web UI, used for links in emails."""

    database_url: str = "sqlite:///./data/erf.db"
    timezone: str = "Asia/Singapore"
    """Business time zone used for working-day calculations."""

    # Sessions and security
    session_cookie_name: str = "erf_session"
    csrf_cookie_name: str = "erf_csrf"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # Background jobs
    run_scheduler: bool = True
    """Run background jobs inside the API process. Set to false when a separate worker runs them."""

    # Mail
    mail_backend: Literal["log", "smtp"] = "log"
    mail_from: str = "Engineering Resource Requests <no-reply@example.com>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 20
    mail_redirect_to: str | None = None
    """Demo installations: deliver email for placeholder addresses such as @example.com to this mailbox.
    Real addresses are not affected."""

    # Static frontend (optional; in production Caddy serves it)
    frontend_dist: Path | None = None

    log_level: str = "INFO"
    log_json: bool = Field(default=False, description="Emit logs as JSON lines.")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
