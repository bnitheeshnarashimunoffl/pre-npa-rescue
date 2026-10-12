"""Task 5.5: container entrypoint (migrate -> optional seed -> exec uvicorn) and settings."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import entrypoint, orm
from app.config import Settings, get_settings
from app.db import make_engine


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, db_url: str, tmp_path: Path) -> str:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "no-data"))
    monkeypatch.setenv("POLICY_PATH", str(tmp_path / "no-policy.yaml"))
    monkeypatch.setenv("WAIT_FOR_DB_SECONDS", "1")
    get_settings.cache_clear()
    yield db_url  # type: ignore[misc]
    get_settings.cache_clear()


def _exec_recorder() -> tuple[list[list[str]], object]:
    calls: list[list[str]] = []
    return calls, lambda file, argv: calls.append(list(argv))


def test_migrates_seeds_and_execs_uvicorn(env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_ON_START", "true")
    monkeypatch.setenv("PORT", "10000")
    calls, fake_exec = _exec_recorder()
    assert entrypoint.main([], exec_fn=fake_exec) == 0  # type: ignore[arg-type]
    engine = make_engine(env)
    assert "audit_log" in inspect(engine).get_table_names()
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(orm.Customer)) == 10
    argv = calls[0]
    assert argv[:2] == ["uvicorn", "app.main:app"]
    assert argv[argv.index("--port") + 1] == "10000" and argv[argv.index("--workers") + 1] == "1"
    # second start: already seeded -> left alone, still execs
    assert entrypoint.main([], exec_fn=fake_exec) == 0  # type: ignore[arg-type]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(orm.User)) == 6
    assert len(calls) == 2


def test_no_seed_by_default_and_migrations_can_be_skipped(
    env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _calls, fake_exec = _exec_recorder()
    monkeypatch.setenv("RUN_MIGRATIONS", "false")
    assert entrypoint.main([], exec_fn=fake_exec) == 0  # type: ignore[arg-type]
    assert "customers" not in inspect(make_engine(env)).get_table_names()
    monkeypatch.setenv("RUN_MIGRATIONS", "true")
    assert entrypoint.main([], exec_fn=fake_exec) == 0  # type: ignore[arg-type]
    with Session(make_engine(env)) as s:
        assert s.scalar(select(func.count()).select_from(orm.Customer)) == 0


def test_startup_failure_does_not_exec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = f"sqlite:///{(tmp_path / 'missing' / 'x.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", bad)
    monkeypatch.setenv("WAIT_FOR_DB_SECONDS", "0")
    get_settings.cache_clear()
    calls, fake_exec = _exec_recorder()
    try:
        assert entrypoint.main([], exec_fn=fake_exec) == 1  # type: ignore[arg-type]
    finally:
        get_settings.cache_clear()
    assert calls == []


def test_wait_for_db_retries_then_gives_up(tmp_path: Path) -> None:
    engine: Engine = make_engine(f"sqlite:///{(tmp_path / 'no' / 'x.db').as_posix()}")
    now = [0.0]
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    with pytest.raises(OperationalError):
        entrypoint.wait_for_db(engine, 5, sleep=fake_sleep, clock=lambda: now[0])
    assert sleeps == [2, 2, 2]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u@h/db", "postgresql+psycopg://u@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_database_url_normalised_for_psycopg(raw: str, expected: str) -> None:
    assert Settings(database_url=raw).database_url == expected


def test_other_commands_run_as_given_without_startup_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/none")
    monkeypatch.setenv("WAIT_FOR_DB_SECONDS", "0")
    get_settings.cache_clear()
    calls, fake_exec = _exec_recorder()
    cmd = ["python", "-m", "app.retention", "--dry-run"]
    assert entrypoint.main(cmd, exec_fn=fake_exec) == 0  # type: ignore[arg-type]
    assert calls == [cmd]  # no DB wait/migration attempted for one-off jobs
    calls.clear()
    try:
        assert entrypoint.main(["serve"], exec_fn=fake_exec) == 1  # serve needs the (dead) DB
    finally:
        get_settings.cache_clear()
