"""DB fixtures: every DB test runs on SQLite, and also on Postgres when TEST_DATABASE_URL is set
(CI sets it; locally: `uv run --with pgserver python scripts/dev_postgres.py`)."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from app.config import get_settings
from app.db import make_engine
from app.ratelimit import RateLimits
from app.security import Principal, create_access_token
from npa_contracts.enums import Role

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"

_BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("TEST_DATABASE_URL") else [])


def alembic_config(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(params=_BACKENDS)
def db_url(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    """URL of an empty database (schema not migrated)."""
    if request.param == "sqlite":
        return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    url = os.environ["TEST_DATABASE_URL"]
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    """Engine on a freshly migrated database (alembic upgrade head)."""
    command.upgrade(alembic_config(db_url), "head")
    eng = make_engine(db_url)
    yield eng
    eng.dispose()


# --- auth helpers (task 5.3) ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    RateLimits.reset()
    yield
    RateLimits.reset()


def bearer_for(
    role: str, customer_id: str | None = None, username: str | None = None
) -> dict[str, str]:
    """Authorization header with a valid token for ``role`` (no DB needed)."""
    if role == "customer" and customer_id is None:
        customer_id = "CUST-DEMO-PRIYA"
    principal = Principal(username or f"test-{role}-{customer_id}", Role(role), customer_id)
    token, _ = create_access_token(principal, get_settings())
    return {"Authorization": f"Bearer {token}"}
