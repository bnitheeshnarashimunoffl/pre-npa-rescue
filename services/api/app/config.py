"""Settings from environment variables (A11), via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    as_of_month: str = "2026-09"
    data_dir: Path = REPO_ROOT / "data" / "generated"
    model_dir: Path = REPO_ROOT / "packages" / "models" / "artifacts"
    policy_path: Path = REPO_ROOT / "packages" / "rules" / "policies" / "bank_policy.yaml"
    contracts_dir: Path = REPO_ROOT / "contracts"
    database_url: str = "postgresql+psycopg://npa:npa@localhost:5432/npa"
    jwt_secret: str = "change-me-dev-only"
    jwt_expire_minutes: int = 120
    cors_origins: str = ""
    llm_provider: str = "mock"
    llm_model: str = "claude-sonnet-5-5"
    tz_business: str = "Asia/Kolkata"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        extra = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["http://localhost:3000", *extra]


@lru_cache
def get_settings() -> Settings:
    return Settings()
