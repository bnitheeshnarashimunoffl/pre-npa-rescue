"""Task 5.4: hash-chained append-only audit log, contact logging, retention purge."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app import orm
from app.audit import (
    GENESIS_HASH,
    DbContactLogger,
    audit,
    audit_offer_transition,
    audit_policy_change,
    verify_chain,
)
from app.retention import main as retention_main
from app.retention import purge_expired
from npa_contracts.models import ComplianceDecision, ContactEvent
from seed import seed_database
from tests.conftest import CONTRACTS_DIR, bearer_for

T0 = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)


def _rows(engine: Engine) -> list[orm.AuditLog]:
    with Session(engine) as s:
        return list(s.scalars(select(orm.AuditLog).order_by(orm.AuditLog.id)))


def _append(engine: Engine, n: int = 3) -> None:
    with Session(engine) as s, s.begin():
        for i in range(n):
            audit(
                s,
                "test.event",
                "tester",
                f"thing:{i}",
                {"i": i, "nested": {"b": 2, "a": 1}},
                now=T0 + timedelta(seconds=i),
            )


def _disable_guard(engine: Engine) -> None:
    """Simulate an attacker with DDL rights (to prove verify_chain still catches tampering)."""
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update_delete"))
        else:
            conn.execute(text("DROP TRIGGER audit_log_no_update"))
            conn.execute(text("DROP TRIGGER audit_log_no_delete"))


# --- chain ------------------------------------------------------------------------------------
def test_chain_links_and_verifies(engine: Engine) -> None:
    _append(engine)
    rows = _rows(engine)
    assert rows[0].prev_hash == GENESIS_HASH
    assert [r.prev_hash for r in rows[1:]] == [r.row_hash for r in rows[:-1]]
    assert len({r.row_hash for r in rows}) == 3
    with Session(engine) as s:
        check = verify_chain(s)
    assert (check.ok, check.rows_checked, check.first_bad_id) == (True, 3, None)


def test_empty_log_verifies(engine: Engine) -> None:
    with Session(engine) as s:
        assert verify_chain(s).ok


@pytest.mark.parametrize("statement", ["UPDATE audit_log SET actor = 'x'", "DELETE FROM audit_log"])
def test_database_rejects_update_and_delete(engine: Engine, statement: str) -> None:
    _append(engine, 1)
    with pytest.raises((IntegrityError, DBAPIError)), engine.begin() as conn:
        conn.execute(text(statement))
    assert len(_rows(engine)) == 1


def test_database_rejects_truncate_on_postgres(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("TRUNCATE is Postgres-only")
    _append(engine, 1)
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("TRUNCATE audit_log"))


def test_tampered_content_is_detected(engine: Engine) -> None:
    _append(engine)
    _disable_guard(engine)
    second = _rows(engine)[1].id
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET actor = 'mallory' WHERE id = :i"), {"i": second})
    with Session(engine) as s:
        check = verify_chain(s)
    assert (check.ok, check.first_bad_id) == (False, second)
    assert check.reason == "row content does not match row_hash"


def test_deleted_row_is_detected(engine: Engine) -> None:
    _append(engine)
    _disable_guard(engine)
    rows = _rows(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE id = :i"), {"i": rows[1].id})
    with Session(engine) as s:
        check = verify_chain(s)
    assert (check.ok, check.first_bad_id) == (False, rows[2].id)
    assert check.reason == "prev_hash does not match previous row"


# --- domain events -------------------------------------------------------------------------------
def _seeded(engine: Engine, tmp_path: Path) -> None:
    seed_database(
        engine,
        data_dir=tmp_path,
        contracts_dir=CONTRACTS_DIR,
        policy_path=tmp_path / "none.yaml",
        as_of_month="2026-09",
        bcrypt_rounds=4,
    )


def _event(event_id: str, ts: datetime) -> ContactEvent:
    return ContactEvent(
        event_id=event_id,
        customer_id="CUST-DEMO-RAVI",
        account_id="ACC-DEMO-RAVI",
        channel="chat",
        direction="inbound",
        actor="customer",
        ts=ts,
        content="I lost my job and cannot pay anything now.",
        lang="en",
        recorded_notice_given=True,
        compliance=ComplianceDecision(
            allowed=True,
            rule_ids=["RBI-454Y4-WINDOW"],
            next_allowed_at=None,
            explanation="inside window",
        ),
        outcome=None,
    )


def test_contact_logger_stores_event_and_audits_without_content(
    engine: Engine, tmp_path: Path
) -> None:
    _seeded(engine, tmp_path)
    with Session(engine) as s, s.begin():
        DbContactLogger(s).log(_event("EVT-1", T0))
    with Session(engine) as s:
        stored = s.get(orm.ContactEvent, "EVT-1")
        assert stored is not None and stored.allowed and stored.content.startswith("I lost")
        row = s.scalars(select(orm.AuditLog).where(orm.AuditLog.action == "contact.logged")).one()
        assert row.details["event_id"] == "EVT-1" and row.details["rule_ids"] == [
            "RBI-454Y4-WINDOW"
        ]
        assert "content" not in row.details and "lost my job" not in str(row.details)
        assert verify_chain(s).ok


def test_offer_and_policy_changes_are_audited(engine: Engine) -> None:
    with Session(engine) as s, s.begin():
        audit_offer_transition(s, "OFFER-1", "proposed", "approved", "officer1", "officer1")
        audit_policy_change(s, "admin1", "v1", "v2", "raise waiver cap")
    rows = _rows(engine)
    assert rows[0].details == {"from": "proposed", "to": "approved", "approved_by": "officer1"}
    assert (rows[1].action, rows[1].details["old_version"], rows[1].details["new_version"]) == (
        "policy.changed",
        "v1",
        "v2",
    )


def test_seed_is_audited_and_reset_keeps_the_log(engine: Engine, tmp_path: Path) -> None:
    _seeded(engine, tmp_path)
    seed_database(
        engine,
        data_dir=tmp_path,
        contracts_dir=CONTRACTS_DIR,
        policy_path=tmp_path / "none.yaml",
        as_of_month="2026-09",
        bcrypt_rounds=4,
        reset=True,
    )
    rows = _rows(engine)
    assert [r.action for r in rows] == ["seed.loaded", "seed.loaded"]
    assert rows[1].details["reset"] is True and rows[1].details["counts"]["customers"] == 10
    with Session(engine) as s:
        assert verify_chain(s).ok


# --- login audit + verify endpoint ------------------------------------------------------------
def test_logins_are_audited(app_db: tuple[FastAPI, TestClient], engine: Engine) -> None:
    _, client = app_db
    client.post("/api/v1/auth/login", json={"username": "officer1", "password": "demo"})
    client.post("/api/v1/auth/login", json={"username": "officer1", "password": "nope"})
    actions = [(r.action, r.actor) for r in _rows(engine) if r.action.startswith("auth.")]
    assert actions == [("auth.login", "officer1"), ("auth.login_failed", "officer1")]
    assert all("demo" not in str(r.details) and "nope" not in str(r.details) for r in _rows(engine))


def test_verify_endpoint(app_db: tuple[FastAPI, TestClient], engine: Engine) -> None:
    _, client = app_db
    ok = client.get("/api/v1/admin/audit/verify", headers=bearer_for("auditor"))
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert ok.json()["rows_checked"] >= 1
    _disable_guard(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET details = '{}'"))
    bad = client.get("/api/v1/admin/audit/verify", headers=bearer_for("admin")).json()
    assert bad["ok"] is False and bad["first_bad_id"] is not None
    denied = client.get("/api/v1/admin/audit/verify", headers=bearer_for("collector"))
    assert denied.status_code == 404


# --- retention (RBI para 454P: 180 days) --------------------------------------------------------
def _old_and_new_records(engine: Engine, tmp_path: Path, now: datetime) -> None:
    _seeded(engine, tmp_path)
    old, recent = now - timedelta(days=200), now - timedelta(days=10)
    with Session(engine) as s, s.begin():
        logger = DbContactLogger(s)
        logger.log(_event("EVT-OLD", old))
        logger.log(_event("EVT-NEW", recent))
        s.add_all(
            [
                orm.ChatSession(
                    session_id="SESS-OLD", customer_id="CUST-DEMO-RAVI", lang="en", created_at=old
                ),
                orm.ChatSession(
                    session_id="SESS-MIXED", customer_id="CUST-DEMO-RAVI", lang="en", created_at=old
                ),
            ]
        )
        s.flush()
        s.add_all(
            [
                orm.ChatTurn(
                    session_id="SESS-OLD",
                    seq=1,
                    actor="customer",
                    text="x",
                    lang="en",
                    flags=[],
                    ts=old,
                ),
                orm.ChatTurn(
                    session_id="SESS-MIXED",
                    seq=1,
                    actor="customer",
                    text="x",
                    lang="en",
                    flags=[],
                    ts=old,
                ),
                orm.ChatTurn(
                    session_id="SESS-MIXED",
                    seq=2,
                    actor="bot",
                    text="y",
                    lang="en",
                    flags=[],
                    ts=recent,
                ),
            ]
        )


def _count(engine: Engine, model: type[orm.Base]) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def test_retention_dry_run_then_purge(engine: Engine, tmp_path: Path) -> None:
    now = datetime(2026, 10, 12, tzinfo=UTC)
    _old_and_new_records(engine, tmp_path, now)
    with Session(engine) as s, s.begin():
        dry = purge_expired(s, now=now, dry_run=True)
    assert (dry.contact_events, dry.chat_turns, dry.chat_sessions) == (1, 2, 1)
    assert _count(engine, orm.ContactEvent) == 2
    with Session(engine) as s, s.begin():
        report = purge_expired(s, now=now)
    assert (report.contact_events, report.chat_turns, report.chat_sessions) == (1, 2, 1)
    with Session(engine) as s:
        assert {e.event_id for e in s.scalars(select(orm.ContactEvent))} == {"EVT-NEW"}
        assert {c.session_id for c in s.scalars(select(orm.ChatSession))} == {"SESS-MIXED"}
        assert _count(engine, orm.ChatTurn) == 1
        purges = s.scalars(
            select(orm.AuditLog).where(orm.AuditLog.action == "retention.purge")
        ).all()
        assert [p.details["dry_run"] for p in purges] == [True, False]
        assert verify_chain(s).ok


def test_retention_cannot_be_shortened(engine: Engine) -> None:
    with Session(engine) as s, pytest.raises(ValueError, match="180"):
        purge_expired(s, days=30)


def test_retention_cli(db_url: str, engine: Engine) -> None:
    assert retention_main(["--database-url", db_url, "--dry-run"]) == 0
    assert retention_main(["--database-url", db_url, "--days", "7"]) == 1
