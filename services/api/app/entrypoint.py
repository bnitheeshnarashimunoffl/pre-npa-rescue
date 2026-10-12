"""Container entrypoint (task 5.5): ``python -m app.entrypoint``.

1. wait for the database (up to ``WAIT_FOR_DB_SECONDS``, default 60);
2. ``alembic upgrade head`` unless ``RUN_MIGRATIONS=false``;
3. if ``SEED_ON_START=true`` and the database has no customers, run the seed (WS1 Parquet when
   mounted, else the fixture accounts); an already-seeded database is left alone;
4. replace this process with uvicorn on ``PORT`` (default 8000; Render sets it).

``WEB_CONCURRENCY`` sets uvicorn workers (default 1: the login/chat rate limits are per process).

Any other command is run as given, without the steps above, so one image serves the web
service and one-off jobs: ``python -m app.entrypoint python -m app.retention`` (Render cron),
``... python -m seed.demo_reset``.
"""

import logging
import os
import sys
import time
from collections.abc import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.db import make_engine
from app.orm import Customer

log = logging.getLogger("entrypoint")

TRUE = {"1", "true", "yes", "on"}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in TRUE


def wait_for_db(
    engine: Engine,
    timeout_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout_seconds
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if clock() >= deadline:
                raise
            log.info("database not ready; retrying")
            sleep(2)


def run_migrations(settings: Settings) -> None:
    cfg = Config(str(settings.alembic_config))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def seed_if_empty(engine: Engine, settings: Settings) -> bool:
    """Seed an empty database; returns True if it seeded."""
    with engine.connect() as conn:
        if conn.scalar(select(func.count()).select_from(Customer)):
            log.info("database already seeded; skipping seed")
            return False
    from seed import seed_database  # imported lazily: only needed on first start

    candidates = (settings.data_dir / "scores.parquet", settings.model_dir / "scores.parquet")
    report = seed_database(
        engine,
        data_dir=settings.data_dir,
        contracts_dir=settings.contracts_dir,
        policy_path=settings.policy_path,
        as_of_month=settings.as_of_month,
        scores_path=next((p for p in candidates if p.exists()), None),
    )
    log.info("seeded source=%s counts=%s", report.source, report.counts)
    return True


def uvicorn_argv() -> list[str]:
    return [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        os.environ.get("PORT", "8000"),
        "--workers",
        os.environ.get("WEB_CONCURRENCY", "1"),
        "--proxy-headers",
        "--forwarded-allow-ips",
        "*",
        "--no-server-header",
    ]


def main(
    argv: list[str] | None = None, exec_fn: Callable[[str, list[str]], object] | None = None
) -> int:
    """Prepare the database, then exec uvicorn (``exec_fn`` is injectable for tests)."""
    args = sys.argv[1:] if argv is None else argv
    if args and args != ["serve"]:
        (exec_fn or os.execvp)(args[0], args)  # one-off job: run it as given
        return 0
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    engine = make_engine(settings.database_url)
    try:
        wait_for_db(engine, float(os.environ.get("WAIT_FOR_DB_SECONDS", "60")))
        if _flag("RUN_MIGRATIONS", True):
            run_migrations(settings)
            log.info("migrations applied")
        if _flag("SEED_ON_START", False):
            seed_if_empty(engine, settings)
    except Exception:
        log.exception("startup failed")
        return 1
    finally:
        engine.dispose()
    argv = uvicorn_argv()
    (exec_fn or os.execvp)(argv[0], argv)
    return 0  # only reached when exec_fn returns (tests)


if __name__ == "__main__":
    sys.exit(main())
