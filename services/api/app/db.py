"""Engine and session factory (task 5.2).

Nothing connects at import time: the API must start (and serve fixtures) even when Postgres
is down. Connections are opened lazily on first use.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

CONNECT_TIMEOUT_SECONDS = 5  # fail fast (503) instead of hanging when Postgres is unreachable


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, committed by the caller."""
    with get_sessionmaker()() as session:
        yield session
