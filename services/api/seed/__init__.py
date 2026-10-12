"""Database seeding (task 5.2): WS1 Parquet (+ WS2 scores) or contracts/fixtures, demo users,
and the initial bank-policy version.

    uv run python -m seed            # load into an empty, migrated database
    uv run python -m seed --reset    # wipe all rows first

Postgres loads use COPY (target: 5 lakh customers in < 10 minutes).
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.orm import Session

from app.audit import audit
from app.orm import AuditLog, Base, Customer, PolicyVersion, User, table_of
from app.security import DEFAULT_BCRYPT_ROUNDS, hash_password
from npa_contracts.enums import Role
from seed.errors import SeedError
from seed.fixtures import load_fixtures

__all__ = ["DEMO_USERS", "SeedError", "SeedReport", "seed_database"]

log = logging.getLogger("seed")

Source = Literal["auto", "parquet", "fixtures"]

# A7.4 demo users. Password "demo" for all (synthetic demo only; never reuse).
DEMO_USERS: tuple[tuple[str, Role, str | None], ...] = (
    ("priya", Role.CUSTOMER, "CUST-DEMO-PRIYA"),
    ("ravi", Role.CUSTOMER, "CUST-DEMO-RAVI"),
    ("collector1", Role.COLLECTOR, None),
    ("officer1", Role.HARDSHIP_OFFICER, None),
    ("admin1", Role.ADMIN, None),
    ("auditor1", Role.AUDITOR, None),
)
DEMO_PASSWORD = "demo"


@dataclass
class SeedReport:
    source: str
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def reset_database(conn: Connection) -> None:
    """Delete every row (schema stays), except ``audit_log``: it is append-only (task 5.4) and
    survives resets; the reset itself is audited. Postgres: one TRUNCATE ... CASCADE."""
    tables = [t for t in Base.metadata.sorted_tables if t.name != AuditLog.__tablename__]
    if conn.dialect.name == "postgresql":
        names = ", ".join(t.name for t in tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(tables):
            conn.execute(delete(table))


def seed_demo_users(conn: Connection, *, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> list[str]:
    """Insert missing demo users (bcrypt). Returns warnings for users that could not be linked."""
    warnings: list[str] = []
    existing = set(conn.scalars(select(User.username)))
    customers = set(conn.scalars(select(Customer.customer_id)))
    rows = []
    for username, role, customer_id in DEMO_USERS:
        if username in existing:
            continue
        if customer_id is not None and customer_id not in customers:
            warnings.append(f"demo user {username}: customer {customer_id} not seeded; skipped")
            continue
        rows.append(
            {
                "username": username,
                "password_hash": hash_password(DEMO_PASSWORD, rounds=rounds),
                "role": role,
                "customer_id": customer_id,
                "is_active": True,
            }
        )
    if rows:
        conn.execute(table_of(User).insert(), rows)
    return warnings


def seed_policy(conn: Connection, policy_path: Path, contracts_dir: Path) -> str:
    """Store the initial active policy version: WS3's bank_policy.yaml, else the fixture."""
    if conn.scalar(select(func.count()).select_from(PolicyVersion)):
        return "kept existing"
    if policy_path.exists():
        policy: dict[str, Any] = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        source = policy_path.name
    else:
        doc = json.loads((contracts_dir / "fixtures" / "policy.json").read_text(encoding="utf-8"))
        policy = doc["policy"]
        source = "fixtures/policy.json"
    conn.execute(
        table_of(PolicyVersion).insert(),
        {
            "version": str(policy.get("version", "v1")),
            "policy": policy,
            "change_note": f"Initial policy loaded by seed from {source}",
            "created_by": "seed",
            "is_active": True,
        },
    )
    return source


def seed_database(
    engine: Engine,
    *,
    data_dir: Path,
    contracts_dir: Path,
    policy_path: Path,
    as_of_month: str,
    scores_path: Path | None = None,
    source: Source = "auto",
    reset: bool = False,
    bcrypt_rounds: int = DEFAULT_BCRYPT_ROUNDS,
) -> SeedReport:
    """Seed a migrated database in one transaction. Refuses a non-empty DB unless ``reset``."""
    started = time.perf_counter()
    has_parquet = (data_dir / "customers.parquet").exists()
    if source == "parquet" and not has_parquet:
        raise SeedError(f"no customers.parquet in {data_dir} (run `make data` first)")
    chosen = "parquet" if source == "parquet" or (source == "auto" and has_parquet) else "fixtures"
    report = SeedReport(source=chosen)
    if chosen == "fixtures" and source == "auto":
        report.warnings.append(f"no Parquet in {data_dir}; seeding the 10 fixture accounts")

    with engine.begin() as conn:
        if reset:
            reset_database(conn)
        elif conn.scalar(select(func.count()).select_from(Customer)):
            raise SeedError("database already has customers; re-run with --reset to replace them")
        if chosen == "parquet":
            from seed.parquet import load_parquet  # pyarrow only needed on this path

            report.counts = load_parquet(conn, data_dir, scores_path)
        else:
            report.counts = load_fixtures(conn, contracts_dir, as_of_month)
        report.warnings += seed_demo_users(conn, rounds=bcrypt_rounds)
        report.counts["users"] = conn.scalar(select(func.count()).select_from(User)) or 0
        policy_source = seed_policy(conn, policy_path, contracts_dir)
        report.counts["policy_versions"] = 1
        log.info("policy source=%s", policy_source)
        with Session(bind=conn) as session:
            audit(
                session,
                "seed.loaded",
                "seed",
                "database",
                {"source": chosen, "reset": reset, "counts": dict(report.counts)},
            )
    report.seconds = round(time.perf_counter() - started, 2)
    return report
