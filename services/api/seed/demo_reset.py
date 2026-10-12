"""Deterministic demo reset (task 5.5, issue #83): ``uv run python -m seed.demo_reset``.

Puts the database back into its freshly seeded state in seconds, without reloading the whole
dataset (5 lakh customers take minutes):

1. clears everything the demo creates: chat sessions and turns, callbacks, complaints, offers,
   contact events and flags, red-team runs, policy versions and users;
2. re-seeds the demo personas (Priya, Ravi) from the same seed source as ``python -m seed``
   (WS1 Parquet if present, else contracts/fixtures), restoring their profile, statements,
   scores and queue entry;
3. restores the demo users (password ``demo``) and the seed bank policy.

``audit_log`` is kept (append-only evidence); the reset itself is audited. Safe to run any
number of times; on an empty (migrated) database it runs the full seed instead.
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, delete, func, select
from sqlalchemy.orm import Session

from app import orm
from app.audit import audit
from app.config import get_settings
from app.db import make_engine
from app.orm import table_of
from app.security import DEFAULT_BCRYPT_ROUNDS
from seed import SeedError, seed_database, seed_demo_users, seed_policy
from seed.fixtures import load_fixtures

log = logging.getLogger("seed.demo_reset")

DEMO_CUSTOMERS = frozenset({"CUST-DEMO-PRIYA", "CUST-DEMO-RAVI"})

# Cleared completely (child tables first). Nothing here exists right after a seed except the
# policy version and users, which are re-created below.
OPERATIONAL = (
    orm.ChatTurn,
    orm.ChatSession,
    orm.Callback,
    orm.Complaint,
    orm.Offer,
    orm.ContactEvent,
    orm.ContactFlag,
    orm.RedTeamResult,
    orm.RedTeamRun,
    orm.PolicyVersion,
    orm.User,
)


@dataclass
class DemoResetReport:
    mode: str
    cleared: dict[str, int] = field(default_factory=dict)
    personas: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0


def _persona_accounts() -> set[str]:
    return {c.replace("CUST-", "ACC-", 1) for c in DEMO_CUSTOMERS}


def _delete_personas(conn: Connection) -> list[dict[str, Any]]:
    """Delete persona reference rows; returns their ``nba`` rows (restored in Parquet mode,
    where the NBA cache is not part of the seed files)."""
    accounts = _persona_accounts()
    nba_rows = [
        dict(r._mapping)
        for r in conn.execute(select(table_of(orm.NBA)).where(orm.NBA.account_id.in_(accounts)))
    ]
    for model, col in (
        (orm.NBA, orm.NBA.account_id),
        (orm.Score, orm.Score.account_id),
        (orm.AccountMonth, orm.AccountMonth.account_id),
    ):
        conn.execute(delete(model).where(col.in_(accounts)))
    conn.execute(delete(orm.Account).where(orm.Account.customer_id.in_(DEMO_CUSTOMERS)))
    conn.execute(
        delete(orm.ProtectedAttributes).where(
            orm.ProtectedAttributes.customer_id.in_(DEMO_CUSTOMERS)
        )
    )
    conn.execute(delete(orm.Customer).where(orm.Customer.customer_id.in_(DEMO_CUSTOMERS)))
    return nba_rows


def demo_reset(
    engine: Engine,
    *,
    data_dir: Path,
    contracts_dir: Path,
    policy_path: Path,
    as_of_month: str,
    scores_path: Path | None = None,
    bcrypt_rounds: int = DEFAULT_BCRYPT_ROUNDS,
) -> DemoResetReport:
    started = time.perf_counter()
    with engine.connect() as probe:
        seeded = bool(probe.scalar(select(func.count()).select_from(orm.Customer)))
    if not seeded:
        seed_report = seed_database(
            engine,
            data_dir=data_dir,
            contracts_dir=contracts_dir,
            policy_path=policy_path,
            as_of_month=as_of_month,
            scores_path=scores_path,
            bcrypt_rounds=bcrypt_rounds,
        )
        return DemoResetReport(
            mode=f"full-seed:{seed_report.source}",
            personas=seed_report.counts,
            seconds=round(time.perf_counter() - started, 2),
        )

    parquet = (data_dir / "customers.parquet").exists()
    report = DemoResetReport(mode="parquet" if parquet else "fixtures")
    with engine.begin() as conn:
        for model in OPERATIONAL:
            report.cleared[model.__tablename__] = conn.execute(delete(model)).rowcount or 0
        nba_rows = _delete_personas(conn)
        if parquet:
            from seed.parquet import load_parquet  # pyarrow only needed on this path

            report.personas = load_parquet(
                conn, data_dir, scores_path, only_customers=set(DEMO_CUSTOMERS)
            )
            if nba_rows:
                conn.execute(table_of(orm.NBA).insert(), nba_rows)
                report.personas["nba"] = len(nba_rows)
        else:
            report.personas = load_fixtures(
                conn, contracts_dir, as_of_month, only_customers=set(DEMO_CUSTOMERS)
            )
        missing = DEMO_CUSTOMERS - set(
            conn.scalars(
                select(orm.Customer.customer_id).where(orm.Customer.customer_id.in_(DEMO_CUSTOMERS))
            )
        )
        if missing:
            raise SeedError(f"seed source has no persona rows for {sorted(missing)}")
        warnings = seed_demo_users(conn, rounds=bcrypt_rounds)
        if warnings:
            raise SeedError("; ".join(warnings))
        seed_policy(conn, policy_path, contracts_dir)
        with Session(bind=conn) as session:
            audit(
                session,
                "demo.reset",
                "seed",
                "database",
                {"mode": report.mode, "cleared": report.cleared, "personas": report.personas},
            )
    report.seconds = round(time.perf_counter() - started, 2)
    return report


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m seed.demo_reset", description=__doc__)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--data-dir", type=Path, default=settings.data_dir)
    args = parser.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    scores = next(
        (
            p
            for p in (args.data_dir / "scores.parquet", settings.model_dir / "scores.parquet")
            if p.exists()
        ),
        None,
    )
    try:
        report = demo_reset(
            make_engine(args.database_url),
            data_dir=args.data_dir,
            contracts_dir=settings.contracts_dir,
            policy_path=settings.policy_path,
            as_of_month=settings.as_of_month,
            scores_path=scores,
        )
    except Exception as exc:  # one clear failure line for the demo operator
        sys.stdout.write(f"DEMO RESET FAILED: {exc.__class__.__name__}: {exc}\n")
        return 1
    cleared = sum(report.cleared.values())
    sys.stdout.write(
        f"DEMO RESET OK ({report.mode}, {report.seconds}s): cleared {cleared} rows; "
        f"personas {report.personas}; audit_log kept\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
