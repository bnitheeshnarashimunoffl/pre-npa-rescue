"""Task 5.5 / issue #83: `seed.demo_reset` restores the seeded demo state and keeps audit_log."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app import orm
from app.audit import verify_chain
from seed import seed_database
from seed.demo_reset import OPERATIONAL, demo_reset
from seed.demo_reset import main as demo_reset_main
from tests.conftest import CONTRACTS_DIR, bearer_for
from tests.test_seed import _write_parquet

PRIYA = bearer_for("customer", "CUST-DEMO-PRIYA", "priya")
RAVI = bearer_for("customer", "CUST-DEMO-RAVI", "ravi")
ADMIN = bearer_for("admin")


def _kw(tmp_path: Path, data_dir: Path | None = None) -> dict[str, Any]:
    return {
        "data_dir": data_dir or tmp_path / "no-data",
        "contracts_dir": CONTRACTS_DIR,
        "policy_path": tmp_path / "no-policy.yaml",
        "as_of_month": "2026-09",
        "bcrypt_rounds": 4,
    }


def _count(engine: Engine, model: type[orm.Base]) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def _play_demo(client: TestClient, engine: Engine) -> None:
    """Everything a demo run leaves behind."""
    sid = client.post("/api/v1/chat/sessions", headers=PRIYA, json={}).json()["session_id"]
    reply = client.post(
        f"/api/v1/chat/sessions/{sid}/messages", headers=PRIYA, json={"text": "I lost my job"}
    ).json()
    client.post(f"/api/v1/offers/{reply['offers'][0]['offer_id']}/accept", headers=PRIYA)
    client.post(
        "/api/v1/complaints", headers=RAVI, json={"category": "x", "text": "y", "lang": "en"}
    )
    policy = client.get("/api/v1/admin/policy", headers=ADMIN).json()["policy"]
    client.put(
        "/api/v1/admin/policy",
        headers=ADMIN,
        json={"policy": policy | {"version": "demo-edit"}, "change_note": "demo"},
    )
    with Session(engine) as s, s.begin():
        s.add(orm.ContactFlag(customer_id="CUST-DEMO-RAVI", flag="bereavement", source="bot"))
        s.execute(
            update(orm.Customer)
            .where(orm.Customer.customer_id == "CUST-DEMO-PRIYA")
            .values(city="Changed")
        )
        s.execute(update(orm.User).where(orm.User.username == "ravi").values(is_active=False))


def test_reset_restores_seed_state_and_keeps_audit(
    app_db: tuple[FastAPI, TestClient], engine: Engine, tmp_path: Path
) -> None:
    _, client = app_db
    _play_demo(client, engine)
    audit_before = _count(engine, orm.AuditLog)
    assert _count(engine, orm.ChatSession) and _count(engine, orm.Complaint)

    report = demo_reset(engine, **_kw(tmp_path))

    assert report.mode == "fixtures"
    for model in (
        orm.ChatTurn,
        orm.ChatSession,
        orm.Callback,
        orm.Complaint,
        orm.Offer,
        orm.ContactEvent,
        orm.ContactFlag,
        orm.RedTeamRun,
    ):
        assert _count(engine, model) == 0, model.__tablename__
    assert _count(engine, orm.Customer) == 10  # non-demo customers untouched
    with Session(engine) as s:
        priya = s.get(orm.Customer, "CUST-DEMO-PRIYA")
        assert priya is not None and priya.city == "Chennai"  # persona re-seeded
        assert s.get(orm.NBA, ("ACC-DEMO-PRIYA", "2026-09")) is not None
        assert s.get(orm.Score, ("ACC-DEMO-RAVI", "2026-09")) is not None
        users = {u.username: u.is_active for u in s.scalars(select(orm.User))}
        assert users == dict.fromkeys(
            ["priya", "ravi", "collector1", "officer1", "admin1", "auditor1"], True
        )
        versions = list(s.scalars(select(orm.PolicyVersion.version)))
        assert len(versions) == 1 and versions[0] != "demo-edit"
        rows = list(s.scalars(select(orm.AuditLog).order_by(orm.AuditLog.id)))
        assert len(rows) == audit_before + 1 and rows[-1].action == "demo.reset"
        assert verify_chain(s).ok
    # the demo works again straight away
    assert (
        client.post("/api/v1/auth/login", json={"username": "ravi", "password": "demo"}).status_code
        == 200
    )


def test_reset_is_idempotent(engine: Engine, tmp_path: Path) -> None:
    seed_database(engine, **_kw(tmp_path))
    first = demo_reset(engine, **_kw(tmp_path))
    second = demo_reset(engine, **_kw(tmp_path))
    assert (
        first.personas == second.personas == {"customers": 2, "accounts": 2, "scores": 2, "nba": 2}
    )
    cleared_twice = {k: v for k, v in second.cleared.items() if v}
    assert cleared_twice == {"policy_versions": 1, "users": 6}  # re-created every run
    assert set(second.cleared) == {m.__tablename__ for m in OPERATIONAL}


def test_reset_on_empty_database_runs_full_seed(engine: Engine, tmp_path: Path) -> None:
    report = demo_reset(engine, **_kw(tmp_path))
    assert report.mode == "full-seed:fixtures"
    assert _count(engine, orm.Customer) == 10 and _count(engine, orm.User) == 6


def test_parquet_mode_reloads_only_personas(engine: Engine, tmp_path: Path) -> None:
    data = tmp_path / "generated"
    _write_parquet(data)  # skips if pyarrow cannot load
    kw = _kw(tmp_path, data) | {"scores_path": data / "scores.parquet"}
    seed_database(engine, **kw)
    with Session(engine) as s, s.begin():
        s.add(
            orm.NBA(
                account_id="ACC-DEMO-PRIYA",
                as_of_month="2026-09",
                action="chat_invite",
                priority=0.5,
                customer_name="Priya Raman",
                bucket="sma0",
                dpd=16,
                total_due_paise=10_745_200,
                payload={"k": "v"},
            )
        )
        s.execute(
            update(orm.AccountMonth)
            .where(orm.AccountMonth.account_id == "ACC-000001")
            .values(dpd=99)
        )  # non-demo data must survive untouched
        s.execute(
            update(orm.AccountMonth)
            .where(orm.AccountMonth.account_id == "ACC-DEMO-RAVI")
            .values(dpd=99)
        )
    report = demo_reset(engine, **kw)
    assert report.mode == "parquet"
    assert report.personas["customers"] == 2 and report.personas["nba"] == 1
    with Session(engine) as s:
        assert s.get(orm.AccountMonth, ("ACC-000001", "2026-09")).dpd == 99  # type: ignore[union-attr]
        assert s.get(orm.AccountMonth, ("ACC-DEMO-RAVI", "2026-09")).dpd == 45  # type: ignore[union-attr]
        assert s.get(orm.NBA, ("ACC-DEMO-PRIYA", "2026-09")) is not None
        assert s.get(orm.ProtectedAttributes, "CUST-DEMO-PRIYA") is not None
    assert _count(engine, orm.Customer) == 3


def test_cli_success_and_failure(
    db_url: str, engine: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert demo_reset_main(["--database-url", db_url, "--data-dir", str(tmp_path / "x")]) == 0
    assert capsys.readouterr().out.startswith("DEMO RESET OK")
    bad = f"sqlite:///{(tmp_path / 'missing' / 'dir' / 'db.sqlite').as_posix()}"
    assert demo_reset_main(["--database-url", bad]) == 1
    assert capsys.readouterr().out.startswith("DEMO RESET FAILED")
