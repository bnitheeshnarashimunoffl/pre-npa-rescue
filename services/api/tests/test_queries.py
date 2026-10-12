"""Task 5.2: collector queue keyset pagination."""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.queries import InvalidCursorError, QueueCursor, queue_page
from app.security import hash_password, verify_password
from npa_contracts.enums import Bucket, NextAction
from seed import seed_database
from tests.conftest import CONTRACTS_DIR


@pytest.fixture
def seeded(engine: Engine, tmp_path: Path) -> Engine:
    seed_database(
        engine,
        data_dir=tmp_path,
        contracts_dir=CONTRACTS_DIR,
        policy_path=tmp_path / "none.yaml",
        as_of_month="2026-09",
        bcrypt_rounds=4,
    )
    return engine


def test_walk_all_pages_in_priority_order(seeded: Engine) -> None:
    seen, cursor = [], None
    with Session(seeded) as s:
        while True:
            rows, cursor = queue_page(s, "2026-09", limit=3, cursor=cursor)
            seen += rows
            if cursor is None:
                break
    assert len(seen) == 10
    assert len({r.account_id for r in seen}) == 10
    assert [r.priority for r in seen] == sorted((r.priority for r in seen), reverse=True)
    assert seen[0].account_id == "ACC-DEMO-PRIYA"


def test_exact_page_has_no_next_cursor(seeded: Engine) -> None:
    with Session(seeded) as s:
        rows, cursor = queue_page(s, "2026-09", limit=10)
    assert len(rows) == 10 and cursor is None


def test_filters_and_other_month(seeded: Engine) -> None:
    with Session(seeded) as s:
        sma1, _ = queue_page(s, "2026-09", limit=50, bucket=Bucket.SMA1)
        reminders, _ = queue_page(s, "2026-09", limit=50, action=NextAction.REMINDER)
        empty, cursor = queue_page(s, "2026-08", limit=50)
    assert {r.bucket for r in sma1} == {"sma1"} and len(sma1) == 3
    assert {r.action for r in reminders} == {"reminder"}
    assert empty == [] and cursor is None


def test_ties_broken_by_account_id() -> None:
    a, b = QueueCursor(0.5, "ACC-1"), QueueCursor(0.5, "ACC-2")
    assert QueueCursor.decode(a.encode()) == a
    assert a.encode() != b.encode()


@pytest.mark.parametrize(
    "bad", ["", "not-base64!", "WzEsMiwzXQ", "WyJ4IiwiQUNDIl0", "W3RydWUsIkEiXQ"]
)
def test_invalid_cursor(bad: str) -> None:
    with pytest.raises(InvalidCursorError):
        QueueCursor.decode(bad)


def test_limit_bounds(seeded: Engine) -> None:
    with Session(seeded) as s:
        for limit in (0, 201):
            with pytest.raises(ValueError, match="limit"):
                queue_page(s, "2026-09", limit=limit)


def test_password_hashing() -> None:
    h = hash_password("demo", rounds=4)
    assert verify_password("demo", h)
    assert not verify_password("Demo", h)
    assert not verify_password("demo", "not-a-bcrypt-hash")
