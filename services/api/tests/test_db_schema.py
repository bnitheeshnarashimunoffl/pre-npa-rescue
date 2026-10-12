"""Task 5.2: migrations match the ORM; constraints hold."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app import orm
from tests.conftest import API_DIR, alembic_config


def test_upgrade_creates_every_table(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert set(orm.Base.metadata.tables) <= tables
    assert len(orm.Base.metadata.tables) == 18


def test_migrations_match_orm(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), orm.Base.metadata)
    assert diff == []


def test_downgrade_to_base(db_url: str, engine: Engine) -> None:
    command.downgrade(alembic_config(db_url), "base")
    engine.dispose()
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}


def _customer(session: Session, cid: str = "CUST-1") -> None:
    session.add(
        orm.Customer(
            customer_id=cid,
            account_id=cid.replace("CUST", "ACC"),
            full_name="Test",
            language_pref="en",
        )
    )
    session.flush()


def test_enum_check_rejects_unknown_value(engine: Engine) -> None:
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO customers (customer_id, account_id, full_name, language_pref) "
                "VALUES ('C', 'A', 'x', 'fr')"
            )
        )


def test_negative_money_rejected(engine: Engine) -> None:
    with Session(engine) as s, pytest.raises(IntegrityError):
        s.add(
            orm.Customer(
                customer_id="C",
                account_id="A",
                full_name="x",
                language_pref="en",
                card_limit_paise=-1,
            )
        )
        s.flush()


def test_enum_validated_in_python(engine: Engine) -> None:
    with Session(engine) as s, pytest.raises(StatementError):
        s.add(orm.Customer(customer_id="C", account_id="A", full_name="x", language_pref="fr"))
        s.flush()


@pytest.mark.parametrize(("role", "customer_id"), [("customer", None), ("collector", "CUST-1")])
def test_user_customer_link_must_match_role(
    engine: Engine, role: str, customer_id: str | None
) -> None:
    with Session(engine) as s:
        _customer(s)
        s.add(orm.User(username="u", password_hash="h", role=role, customer_id=customer_id))
        with pytest.raises(IntegrityError):
            s.flush()


def test_callback_slot_must_be_ordered(engine: Engine) -> None:
    start = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)
    with Session(engine) as s:
        _customer(s)
        s.add(
            orm.Callback(
                callback_id="CB-1",
                customer_id="CUST-1",
                role="hardship_officer",
                slot_start=start,
                slot_end=start - timedelta(minutes=1),
                summary="x",
            )
        )
        with pytest.raises(IntegrityError):
            s.flush()


def test_timestamps_round_trip_timezone_aware(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("SQLite has no timezone-aware timestamp type")
    start = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)
    with Session(engine) as s:
        _customer(s)
        s.add(
            orm.Callback(
                callback_id="CB-1",
                customer_id="CUST-1",
                role="hardship_officer",
                slot_start=start,
                slot_end=start + timedelta(minutes=30),
                summary="x",
            )
        )
        s.commit()
        cb = s.get(orm.Callback, "CB-1")
        assert cb is not None and cb.slot_start.utcoffset() is not None
        assert cb.slot_start == start


def test_no_router_touches_protected_attributes() -> None:
    """A3 / RBI para 454O: no API route may expose protected attributes."""
    for path in (API_DIR / "app" / "routers").glob("*.py"):
        names = {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Name | ast.Attribute)
        }
        assert "ProtectedAttributes" not in names, path.name
        assert "protected_attributes" not in Path(path).read_text(encoding="utf-8"), path.name
