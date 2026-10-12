"""Task 5.2: seeding from fixtures and from Parquet, demo users, policy."""

import json
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import orm
from app.security import verify_password
from seed import DEMO_USERS, SeedError, seed_database
from seed.__main__ import main as seed_main
from tests.conftest import CONTRACTS_DIR, alembic_config


def _seed(engine: Engine, tmp_path: Path, **kw: Any):  # type: ignore[no-untyped-def]
    defaults: dict[str, Any] = {
        "data_dir": tmp_path / "no-data",
        "contracts_dir": CONTRACTS_DIR,
        "policy_path": tmp_path / "no-policy.yaml",
        "as_of_month": "2026-09",
        "bcrypt_rounds": 4,
    }
    return seed_database(engine, **(defaults | kw))


def _count(engine: Engine, model: type[orm.Base]) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def test_fixture_seed(engine: Engine, tmp_path: Path) -> None:
    report = _seed(engine, tmp_path)
    assert report.source == "fixtures"
    assert report.counts == {
        "customers": 10,
        "accounts": 10,
        "scores": 10,
        "nba": 10,
        "users": 6,
        "policy_versions": 1,
    }
    assert any("no Parquet" in w for w in report.warnings)
    with Session(engine) as s:
        priya = s.get(orm.Customer, "CUST-DEMO-PRIYA")
        ravi = s.get(orm.Customer, "CUST-DEMO-RAVI")
        assert priya is not None and priya.language_pref == "ta"
        assert ravi is not None and ravi.has_card_insurance is True
        score = s.get(orm.Score, ("ACC-DEMO-PRIYA", "2026-09"))
        assert score is not None and score.segment == "cant_pay"
        assert score.uplift_group == "persuadable"
        assert score.reasons[0]["code"] == "SALARY_STOPPED"
        policy = s.scalars(select(orm.PolicyVersion)).one()
        assert policy.is_active and "grievance_officer" in policy.policy


def test_demo_users_are_bcrypt_hashed_and_linked(engine: Engine, tmp_path: Path) -> None:
    _seed(engine, tmp_path)
    with Session(engine) as s:
        users = {u.username: u for u in s.scalars(select(orm.User))}
    assert set(users) == {name for name, _, _ in DEMO_USERS}
    assert users["priya"].customer_id == "CUST-DEMO-PRIYA"
    assert users["officer1"].role == "hardship_officer" and users["officer1"].customer_id is None
    assert users["admin1"].password_hash.startswith("$2")
    assert verify_password("demo", users["admin1"].password_hash)
    assert not verify_password("wrong", users["admin1"].password_hash)


def test_seed_refuses_non_empty_db_and_reset_replaces(engine: Engine, tmp_path: Path) -> None:
    _seed(engine, tmp_path)
    with pytest.raises(SeedError, match="--reset"):
        _seed(engine, tmp_path)
    report = _seed(engine, tmp_path, reset=True)
    assert report.counts["customers"] == 10
    assert _count(engine, orm.User) == 6


def test_policy_from_yaml_when_present(engine: Engine, tmp_path: Path) -> None:
    policy = tmp_path / "bank_policy.yaml"
    policy.write_text("version: v7\nrelief: {}\n", encoding="utf-8")
    _seed(engine, tmp_path, policy_path=policy)
    with Session(engine) as s:
        assert s.scalars(select(orm.PolicyVersion.version)).one() == "v7"


def test_parquet_source_requires_files(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(SeedError, match=r"customers\.parquet"):
        _seed(engine, tmp_path, source="parquet")


# --- Parquet (needs pyarrow; skipped where it can't load, e.g. Windows App Control) ----------
def _write_parquet(data_dir: Path, *, drop: str | None = None) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    data_dir.mkdir()
    ids = ["CUST-DEMO-PRIYA", "CUST-DEMO-RAVI", "CUST-000001"]
    accs = [i.replace("CUST", "ACC") for i in ids]
    customers = {
        "customer_id": ids,
        "account_id": accs,
        "full_name": ["Priya Raman", "Ravi Shankar", "Asha Pillai"],
        "age": [31, 44, 27],
        "city": ["Chennai", "Coimbatore", "Kochi"],
        "language_pref": ["ta", "en", "en"],
        "card_limit_paise": [15_000_000, 20_000_000, 5_000_000],
        "has_card_insurance": [False, True, False],
        "extra_column_ignored": [1, 2, 3],
    }
    if drop:
        customers.pop(drop)
    pq.write_table(pa.table(customers), data_dir / "customers.parquet")
    pq.write_table(
        pa.table({"customer_id": ids, "gender": ["f", "m", "f"], "region": ["south"] * 3}),
        data_dir / "protected_attributes.parquet",
    )
    import datetime as dt

    pq.write_table(
        pa.table(
            {
                "account_id": accs,
                "customer_id": ids,
                "month": ["2026-09"] * 3,
                "statement_date": [dt.date(2026, 9, 1)] * 3,
                "due_date": [dt.date(2026, 9, 21)] * 3,
                "opening_balance_paise": [100] * 3,
                "purchases_paise": [0] * 3,
                "cash_advance_paise": [0] * 3,
                "payments_paise": [0] * 3,
                "payment_date": [None, None, dt.date(2026, 9, 20)],
                "total_due_paise": [1_318_000, 6_480_000, 0],
                "min_due_paise": [100] * 3,
                "interest_paise": [0] * 3,
                "late_fee_paise": [118_000, 0, 0],
                "closing_balance_paise": [100] * 3,
                "utilisation": [0.8, 0.9, 0.1],
                "dpd": [12, 45, 0],
                "bucket": ["sma0", "sma1", "current"],
            }
        ),
        data_dir / "account_months.parquet",
    )
    reason = [{"code": "SALARY_STOPPED", "weight": 0.4, "text": {"en": "x", "ta": "x", "hi": "x"}}]
    pq.write_table(
        pa.table(
            {
                "account_id": accs,
                "as_of_month": ["2026-09"] * 3,
                "p_roll_forward": [0.82, 0.91, 0.1],
                "risk_band": ["high", "high", "low"],
                "reasons": [reason, reason, []],
                "risk_model_version": ["v1"] * 3,
                "segment": ["cant_pay", "cant_pay", "not_at_risk"],
                "segment_confidence": [0.7] * 3,
                "segment_model_version": ["v1"] * 3,
                "uplift_score": [0.2, 0.0, -0.1],
                "uplift_group": ["persuadable", "lost_cause", "sleeping_dog"],
                "recommended_treatment": ["relief_offer", "agent_call", "none"],
                "uplift_model_version": ["v1"] * 3,
            }
        ),
        data_dir / "scores.parquet",
    )


def test_parquet_seed(engine: Engine, tmp_path: Path) -> None:
    data = tmp_path / "generated"
    _write_parquet(data)
    report = _seed(engine, tmp_path, data_dir=data, scores_path=data / "scores.parquet")
    assert report.source == "parquet"
    assert report.counts["customers"] == 3
    assert report.counts["accounts"] == 3
    assert report.counts["protected_attributes"] == 3
    assert report.counts["account_months"] == 3
    assert report.counts["scores"] == 3
    assert report.counts["users"] == 6
    with Session(engine) as s:
        acc = s.get(orm.Account, "ACC-000001")
        assert acc is not None and acc.limit_paise == 5_000_000
        month = s.get(orm.AccountMonth, ("ACC-DEMO-PRIYA", "2026-09"))
        assert month is not None and month.late_fee_paise == 118_000 and month.payment_date is None
        score = s.get(orm.Score, ("ACC-DEMO-PRIYA", "2026-09"))
        assert score is not None and score.reasons[0]["code"] == "SALARY_STOPPED"


def test_parquet_missing_required_column(engine: Engine, tmp_path: Path) -> None:
    data = tmp_path / "generated"
    _write_parquet(data, drop="full_name")
    with pytest.raises(SeedError, match="full_name"):
        _seed(engine, tmp_path, data_dir=data)
    assert _count(engine, orm.Customer) == 0  # one transaction: nothing half-loaded


# --- CLI ---------------------------------------------------------------------------------------
def test_cli(db_url: str, tmp_path: Path) -> None:
    command.upgrade(alembic_config(db_url), "head")
    base = ["--database-url", db_url, "--data-dir", str(tmp_path / "none")]
    assert seed_main(base) == 0
    assert seed_main(base) == 1  # already seeded
    assert seed_main([*base, "--reset"]) == 0
    assert seed_main([*base, "--source", "parquet"]) == 1


def test_fixture_queue_file_is_the_source() -> None:
    queue = json.loads((CONTRACTS_DIR / "fixtures" / "queue.json").read_text(encoding="utf-8"))
    assert len(queue["items"]) == 10
