"""Collector queue at scale (Postgres only): keyset pages and filters are served by indexes, and
GET /collector/queue meets a p95 latency budget on a large queue.

QUEUE_SCALE_ROWS (default 200000; the demo target is 500000) and QUEUE_P95_BUDGET_MS (default
300, the A5.5 target for non-chat routes) can be raised or lowered per machine.
"""

import json
import os
import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.main import create_app
from app.queries import QueueCursor, queue_page
from tests.conftest import CONTRACTS_DIR, bearer_for

ROWS = int(os.environ.get("QUEUE_SCALE_ROWS", "200000"))
BUDGET_MS = float(os.environ.get("QUEUE_P95_BUDGET_MS", "300"))
MONTH = "2026-09"
COLLECTOR = bearer_for("collector")
BUCKETS = ["current", "sma0", "sma1", "sma2", "npa"]
ACTIONS = [
    "no_contact",
    "reminder",
    "chat_invite",
    "agent_call",
    "hardship_officer",
    "firm_process",
]


@pytest.fixture
def big_queue(engine: Engine) -> Iterator[Engine]:
    if engine.dialect.name != "postgresql":
        pytest.skip("scale test needs Postgres (set TEST_DATABASE_URL)")
    payload = json.loads((CONTRACTS_DIR / "fixtures" / "nba.json").read_text(encoding="utf-8"))
    with engine.begin() as conn:
        conn.execute(text("SELECT setseed(0.42)"))
        conn.execute(
            text("""
            INSERT INTO customers (customer_id, account_id, full_name, language_pref)
            SELECT 'CUST-' || lpad(g::text, 7, '0'), 'ACC-' || lpad(g::text, 7, '0'),
                   'Customer ' || g, 'en'
            FROM generate_series(1, :n) AS g"""),
            {"n": ROWS},
        )
        conn.execute(
            text("""
            INSERT INTO accounts (account_id, customer_id)
            SELECT account_id, customer_id FROM customers""")
        )
        conn.execute(
            text("""
            INSERT INTO nba (account_id, as_of_month, action, channel, priority, customer_name,
                             bucket, dpd, total_due_paise, payload, created_at)
            SELECT c.account_id, :month,
                   (CAST(:actions AS text[]))[1 + (g % 6)], 'chat',
                   round(random()::numeric, 4)::float8,
                   c.full_name, (CAST(:buckets AS text[]))[1 + (g % 5)], g % 120, (g % 997) * 10000,
                   CAST(:payload AS jsonb), now()
            FROM customers c
            JOIN generate_series(1, :n) AS g ON c.customer_id = 'CUST-' || lpad(g::text, 7, '0')
        """),
            {
                "month": MONTH,
                "n": ROWS,
                "payload": json.dumps(payload),
                "actions": ACTIONS,
                "buckets": BUCKETS,
            },
        )
        conn.execute(text("ANALYZE customers, accounts, nba"))
    yield engine


def _plan(engine: Engine, **kw: Any) -> str:
    """EXPLAIN of the exact SQL queue_page runs (captured, then explained)."""
    with Session(engine) as s:
        captured: list[tuple[str, Any]] = []

        def grab(conn: Any, cursor: Any, statement: str, params: Any, *a: Any) -> None:
            if "FROM nba" in statement and not captured:
                captured.append((statement, params))

        from sqlalchemy import event

        event.listen(s.get_bind(), "before_cursor_execute", grab)
        try:
            queue_page(s, MONTH, limit=50, **kw)
        finally:
            event.remove(s.get_bind(), "before_cursor_execute", grab)
        statement, params = captured[0]
        raw = s.connection().connection.driver_connection
        assert raw is not None
        with raw.cursor() as cur:
            cur.execute("EXPLAIN (FORMAT JSON) " + statement, params)
            return json.dumps(cur.fetchone()[0])


def _deep_cursor(engine: Engine) -> str:
    """A cursor ~90% of the way down the queue."""
    with engine.connect() as conn:
        p, a = conn.execute(
            text(
                "SELECT priority, account_id FROM nba WHERE as_of_month = :m "
                "ORDER BY priority DESC, account_id DESC OFFSET :o LIMIT 1"
            ),
            {"m": MONTH, "o": int(ROWS * 0.9)},
        ).one()
    return QueueCursor(p, a).encode()


def test_queue_at_scale(big_queue: Engine) -> None:
    """One seeded queue (seeding dominates the runtime): plans, then the latency budget."""
    deep = _deep_cursor(big_queue)
    variants: dict[str, dict[str, Any]] = {
        "first": {},
        "deep": {"cursor": deep},
        "bucket": {"bucket": "sma1"},
        "action": {"action": "hardship_officer"},
        "bucket+deep": {"bucket": "sma1", "cursor": deep},
    }
    for name, kw in variants.items():
        plan = _plan(big_queue, **kw)
        assert "Seq Scan" not in plan, (name, plan)
        assert '"Node Type": "Sort"' not in plan, (name, plan)
        assert "ix_nba_queue" in plan, (name, plan)
        assert "Index Cond" in plan, (name, plan)

    client = TestClient(create_app(engine=big_queue))
    url = "/api/v1/collector/queue"

    def call(**params: Any) -> tuple[float, dict[str, Any]]:
        t0 = time.perf_counter()
        res = client.get(url, params=params, headers=COLLECTOR)
        elapsed = (time.perf_counter() - t0) * 1000
        assert res.status_code == 200, res.text
        return elapsed, res.json()

    call()  # warm-up (connections, caches)
    timings: list[float] = []
    cursor = None
    for _ in range(15):  # walk 15 pages
        ms, body = call(limit=50, **({"cursor": cursor} if cursor else {}))
        timings.append(ms)
        assert len(body["items"]) == 50
        cursor = body["next_cursor"]
    for params in (
        {"cursor": deep},
        {"bucket": "sma2"},
        {"action": "agent_call"},
        {"bucket": "npa", "cursor": deep},
        {"limit": 200},
    ):
        for _ in range(3):
            timings.append(call(**params)[0])
    p95 = statistics.quantiles(timings, n=20)[-1]
    print(f"\nqueue p95={p95:.1f} ms max={max(timings):.1f} ms, {len(timings)} calls, {ROWS} rows")
    assert p95 < BUDGET_MS, f"p95 {p95:.1f} ms over {len(timings)} calls on {ROWS} rows"
