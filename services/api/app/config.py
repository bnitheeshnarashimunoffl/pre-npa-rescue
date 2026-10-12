"""Settings from environment variables (A11), via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    as_of_month: str = "2026-09"
    data_dir: Path = REPO_ROOT / "data" / "generated"
    model_dir: Path = REPO_ROOT / "packages" / "models" / "artifacts"
    policy_path: Path = REPO_ROOT / "packages" / "rules" / "policies" / "bank_policy.yaml"
    contracts_dir: Path = REPO_ROOT / "contracts"
    reports_dir: Path = REPO_ROOT / "packages" / "models" / "reports"  # WS2 committed reports
    api_base_url: str = "http://localhost:8000/api/v1"  # used by the red-team harness
    # WS7 harness mode: "library" (in-process providers) or "api" (this API over HTTP)
    redteam_mode: Literal["library", "api"] = "library"
    alembic_config: Path = REPO_ROOT / "services" / "api" / "alembic.ini"
    database_url: str = "postgresql+psycopg://npa:npa@localhost:5432/npa"
    # Dev default only; >= 32 bytes for HS256 (RFC 7518). Set a random secret anywhere shared.
    jwt_secret: str = "change-me-dev-only-0123456789abcdef"
    jwt_expire_minutes: int = 120
    login_rate_per_minute: int = 10
    chat_rate_per_minute: int = 30
    cors_origins: str = ""
    llm_provider: str = "mock"
    llm_model: str = "claude-sonnet-5-5"
    tz_business: str = "Asia/Kolkata"
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres (e.g. Render) hands out ``postgres://`` / ``postgresql://`` URLs;
        SQLAlchemy needs the psycopg 3 driver named explicitly."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        extra = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["http://localhost:3000", *extra]


@lru_cache
def get_settings() -> Settings:
    return Settings()
