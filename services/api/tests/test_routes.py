"""Task 5.1: every A7.4 route against a migrated + seeded database (fixtures source), plus the
Priya and Ravi demo flows end to end. Role denial for every route is in test_auth.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import orm
from app.audit import verify_chain
from npa_contracts import CONTRACT_VERSION
from npa_contracts.api import AccountSummary, ChatTranscript, KpiReport, QueuePage
from npa_contracts.models import BotReply, Callback, Complaint, Offer, ReliefOption
from tests.conftest import bearer_for

API = "/api/v1"
COLLECTOR = bearer_for("collector")
OFFICER = bearer_for("hardship_officer")
ADMIN = bearer_for("admin")
AUDITOR = bearer_for("auditor")
PRIYA = bearer_for("customer", "CUST-DEMO-PRIYA", "priya")
RAVI = bearer_for("customer", "CUST-DEMO-RAVI", "ravi")
IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def client(app_db: tuple[FastAPI, TestClient]) -> TestClient:
    return app_db[1]


def _tomorrow_ist(hour: int, minute: int = 0) -> datetime:
    day = datetime.now(IST).date() + timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


# --- health / customers / accounts ----------------------------------------------------------------
def test_health_reports_db_and_providers(client: TestClient) -> None:
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok"
    assert body["contract_version"] == CONTRACT_VERSION
    assert set(body["providers"]) == {"risk", "policy", "compliance", "nba", "chat"}


def test_customer_profile_minimised_per_role(client: TestClient) -> None:
    own = client.get(f"{API}/customers/CUST-DEMO-RAVI", headers=RAVI).json()
    collector = client.get(f"{API}/customers/CUST-DEMO-RAVI", headers=COLLECTOR).json()
    officer = client.get(f"{API}/customers/CUST-DEMO-RAVI", headers=OFFICER).json()
    assert own["has_card_insurance"] is True and own["city"] == "Coimbatore"
    assert collector["has_card_insurance"] is None and collector["phone_masked"]
    assert officer["insurance_cover_type"] == "job_loss"
    assert client.get(f"{API}/customers/CUST-NOPE", headers=ADMIN).status_code == 404


def test_relief_options(client: TestClient) -> None:
    priya = [
        ReliefOption.model_validate(o)
        for o in client.get(f"{API}/customers/CUST-DEMO-PRIYA/relief-options", headers=PRIYA).json()
    ]
    emi = next(o for o in priya if o.type == "emi_conversion")
    assert (emi.monthly_amount_paise, emi.tenure_months) == (200_000, 6)
    other = client.get(f"{API}/customers/CUST-000117/relief-options", headers=OFFICER)
    assert other.status_code == 200 and other.json() == []
    missing = client.get(f"{API}/customers/CUST-NOPE/relief-options", headers=OFFICER)
    assert missing.status_code == 404


@pytest.mark.parametrize("kind", ["risk", "segment", "uplift", "nba"])
def test_account_outputs(client: TestClient, kind: str) -> None:
    res = client.get(f"{API}/accounts/ACC-DEMO-PRIYA/{kind}", headers=COLLECTOR)
    assert res.status_code == 200 and res.json()["account_id"] == "ACC-DEMO-PRIYA"
    assert client.get(f"{API}/accounts/ACC-NOPE/{kind}", headers=COLLECTOR).status_code == 404


def test_priya_risk_matches_demo_story(client: TestClient) -> None:
    risk = client.get(f"{API}/accounts/ACC-DEMO-PRIYA/risk", headers=OFFICER).json()
    seg = client.get(f"{API}/accounts/ACC-DEMO-PRIYA/segment", headers=OFFICER).json()
    up = client.get(f"{API}/accounts/ACC-DEMO-PRIYA/uplift", headers=OFFICER).json()
    assert risk["risk_band"] == "high" and risk["reasons"][0]["code"] == "SALARY_STOPPED"
    assert seg["segment"] == "cant_pay" and up["uplift_group"] == "persuadable"


# --- collector ------------------------------------------------------------------------------------
def test_queue_pagination_and_filters(client: TestClient) -> None:
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 4} | ({"cursor": cursor} if cursor else {})
        page = QueuePage.model_validate(
            client.get(f"{API}/collector/queue", params=params, headers=COLLECTOR).json()
        )
        seen += [i.account_id for i in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 10
    assert set(seen[:2]) == {"ACC-DEMO-PRIYA", "ACC-DEMO-RAVI"}  # demo customers lead
    sma1 = client.get(f"{API}/collector/queue", params={"bucket": "sma1"}, headers=COLLECTOR)
    assert {i["bucket"] for i in sma1.json()["items"]} == {"sma1"}
    bad = client.get(f"{API}/collector/queue", params={"cursor": "junk!"}, headers=COLLECTOR)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_CURSOR"


def test_account_summary(client: TestClient) -> None:
    res = client.get(f"{API}/collector/accounts/ACC-DEMO-PRIYA/summary", headers=OFFICER)
    summary = AccountSummary.model_validate(res.json())
    assert summary.customer_id == "CUST-DEMO-PRIYA" and summary.nba is not None
    assert summary.reasons[0].code == "SALARY_STOPPED"
    assert (
        client.get(f"{API}/collector/accounts/ACC-NOPE/summary", headers=OFFICER).status_code == 404
    )


# --- contacts -------------------------------------------------------------------------------------
def test_contact_check_window(client: TestClient) -> None:
    body = {"customer_id": "CUST-DEMO-RAVI", "channel": "call", "actor": "agent"}
    inside = client.post(
        f"{API}/contacts/check",
        headers=COLLECTOR,
        json=body | {"at": _tomorrow_ist(11).isoformat()},
    ).json()
    late = client.post(
        f"{API}/contacts/check",
        headers=COLLECTOR,
        json=body | {"at": _tomorrow_ist(21, 30).isoformat()},
    ).json()
    assert inside["allowed"] is True
    assert late["allowed"] is False and "RBI-454Y4-WINDOW" in late["rule_ids"]
    assert late["next_allowed_at"] is not None


def test_contact_log_unknown_customer(client: TestClient) -> None:
    assert (
        client.get(
            f"{API}/contacts", params={"customer_id": "CUST-DEMO-RAVI"}, headers=AUDITOR
        ).json()
        == []
    )
    assert (
        client.get(
            f"{API}/contacts", params={"customer_id": "CUST-NOPE"}, headers=AUDITOR
        ).status_code
        == 404
    )


# --- offers ---------------------------------------------------------------------------------------
def _priya_option(client: TestClient, kind: str = "emi_conversion") -> ReliefOption:
    options = client.get(f"{API}/customers/CUST-DEMO-PRIYA/relief-options", headers=PRIYA).json()
    return next(ReliefOption.model_validate(o) for o in options if o["type"] == kind)


def test_offer_lifecycle(client: TestClient, engine: Engine) -> None:
    option = _priya_option(client)
    created = client.post(
        f"{API}/offers",
        headers=OFFICER,
        json={"customer_id": "CUST-DEMO-PRIYA", "option_id": option.option_id},
    )
    assert created.status_code == 201
    offer = Offer.model_validate(created.json())
    if offer.status == "proposed":  # needs a human (IS/ISO/IEC 38507)
        approved = client.post(f"{API}/offers/{offer.offer_id}/approve", headers=OFFICER).json()
        assert approved["status"] == "approved"
        assert approved["approved_by"] == "test-hardship_officer-None"
    else:
        assert (offer.status, offer.approved_by) == ("approved", "policy_engine")
    # Ravi cannot see or accept Priya's offer
    assert client.post(f"{API}/offers/{offer.offer_id}/accept", headers=RAVI).status_code == 404
    accepted = client.post(
        f"{API}/offers/{offer.offer_id}/accept", headers=PRIYA, json={"note": "Thank you"}
    )
    assert accepted.json()["status"] == "accepted"
    again = client.post(f"{API}/offers/{offer.offer_id}/reject", headers=PRIYA)
    assert again.status_code == 409 and again.json()["error"]["code"] == "CONFLICT"
    with Session(engine) as s:
        changes = [
            r.details
            for r in s.scalars(
                select(orm.AuditLog).where(orm.AuditLog.action == "offer.status_changed")
            )
        ]
        assert changes[-1]["to"] == "accepted" and changes[-1]["note"] == "Thank you"


def test_offer_errors(client: TestClient, engine: Engine) -> None:
    assert (
        client.post(
            f"{API}/offers",
            headers=OFFICER,
            json={"customer_id": "CUST-DEMO-PRIYA", "option_id": "OPT-MADE-UP"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/offers", headers=OFFICER, json={"customer_id": "CUST-NOPE", "option_id": "x"}
        ).status_code
        == 404
    )
    assert client.post(f"{API}/offers/OFFER-nope/approve", headers=OFFICER).status_code == 404
    option = _priya_option(client)
    offer = client.post(
        f"{API}/offers",
        headers=OFFICER,
        json={"customer_id": "CUST-DEMO-PRIYA", "option_id": option.option_id},
    ).json()
    with Session(engine) as s, s.begin():
        row = s.get(orm.Offer, offer["offer_id"])
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    expired = client.post(f"{API}/offers/{offer['offer_id']}/reject", headers=PRIYA)
    assert expired.status_code == 409 and "expired" in expired.json()["error"]["message"]


# --- chat: Priya and Ravi end to end --------------------------------------------------------------
def _chat(client: TestClient, headers: dict[str, str], text: str) -> tuple[str, BotReply]:
    sid = client.post(f"{API}/chat/sessions", headers=headers, json={}).json()["session_id"]
    res = client.post(f"{API}/chat/sessions/{sid}/messages", headers=headers, json={"text": text})
    assert res.status_code == 200, res.text
    return sid, BotReply.model_validate(res.json())


def test_priya_flow(client: TestClient, engine: Engine) -> None:
    sid, reply = _chat(client, PRIYA, "நான் வேலையை இழந்துவிட்டேன்")
    assert reply.lang == "ta" and reply.offers
    offer = reply.offers[0]
    assert (offer.option.monthly_amount_paise, offer.option.tenure_months) == (200_000, 6)
    assert offer.option.waiver_paise
    accepted = client.post(f"{API}/offers/{offer.offer_id}/accept", headers=PRIYA)
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    transcript = ChatTranscript.model_validate(
        client.get(f"{API}/chat/sessions/{sid}", headers=OFFICER).json()
    )
    assert [t.actor for t in transcript.turns] == ["customer", "bot"]
    contacts = client.get(
        f"{API}/contacts", params={"customer_id": "CUST-DEMO-PRIYA"}, headers=AUDITOR
    ).json()
    assert [c["direction"] for c in contacts] == ["inbound", "outbound"]
    assert client.get(f"{API}/chat/sessions/{sid}", headers=RAVI).status_code == 404
    stream = client.get(f"{API}/chat/sessions/{sid}/stream", headers=PRIYA)
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: done" in stream.text
    with Session(engine) as s:
        assert verify_chain(s).ok


def test_ravi_flow(client: TestClient, engine: Engine) -> None:
    _, reply = _chat(client, RAVI, "I lost my job and cannot pay even Rs 500")
    assert "zero_capacity" in reply.flags and reply.offers == []
    assert reply.handoff is not None and reply.handoff.role == "hardship_officer"
    slot = _tomorrow_ist(11)
    booked = client.post(
        f"{API}/callbacks",
        headers=RAVI,
        json={
            "slot_start": slot.isoformat(),
            "role": "hardship_officer",
            "summary": "Job loss, sole earner; check job-loss insurance; agree review date.",
        },
    )
    assert booked.status_code == 201, booked.text
    cb = Callback.model_validate(booked.json())
    assert cb.slot_start == slot and cb.customer_id == "CUST-DEMO-RAVI"
    late = client.post(
        f"{API}/callbacks",
        headers=RAVI,
        json={
            "slot_start": _tomorrow_ist(20).isoformat(),
            "role": "hardship_officer",
            "summary": "x",
        },
    )
    assert late.status_code == 409  # outside 08:00-19:00 IST (RBI para 454Y(4))
    twice = client.post(
        f"{API}/callbacks",
        headers=RAVI,
        json={"slot_start": slot.isoformat(), "role": "hardship_officer", "summary": "again"},
    )
    assert twice.status_code == 409
    mine = client.get(f"{API}/callbacks", headers=RAVI).json()
    assert [c["callback_id"] for c in mine] == [cb.callback_id]
    assert client.get(f"{API}/callbacks", headers=PRIYA).json() == []
    kpis = KpiReport.model_validate(client.get(f"{API}/metrics/kpis", headers=ADMIN).json())
    assert kpis.handoff_rate == 1.0 and kpis.avg_turns_to_resolution == 2.0


def test_chat_session_errors(client: TestClient, engine: Engine) -> None:
    sid, _ = _chat(client, PRIYA, "hello")
    with Session(engine) as s, s.begin():
        row = s.get(orm.ChatSession, sid)
        assert row is not None
        row.closed_at = datetime.now(UTC)
    closed = client.post(f"{API}/chat/sessions/{sid}/messages", headers=PRIYA, json={"text": "hi"})
    assert closed.status_code == 409
    assert (
        client.post(
            f"{API}/chat/sessions/SESS-nope/messages", headers=PRIYA, json={"text": "hi"}
        ).status_code
        == 404
    )


def test_distress_flag_creates_contact_flag(
    app_db: tuple[FastAPI, TestClient], engine: Engine
) -> None:
    app, client = app_db
    engine_reply = app.state.providers.chat

    class _Distress:
        def handle(self, session_id: str, customer_id: str, req: Any) -> BotReply:
            reply = engine_reply.handle(session_id, customer_id, req)
            return reply.model_copy(update={"flags": ["distress_detected", "bereavement"]})

    app.state.providers.chat = _Distress()
    _chat(client, RAVI, "my father passed away")
    with Session(engine) as s:
        flags = {f.flag for f in s.scalars(select(orm.ContactFlag))}
    assert flags == {"distress", "bereavement"}


def test_blocked_bot_text_is_never_sent(app_db: tuple[FastAPI, TestClient], engine: Engine) -> None:
    app, client = app_db
    real = app.state.providers.compliance

    class _Strict:
        check_contact = real.check_contact

        def check_text(self, text: str, lang: Any) -> Any:
            return real.check_text(text, lang).model_copy(update={"allowed": False})

    app.state.providers.compliance = _Strict()
    _, reply = _chat(client, PRIYA, "hello")
    assert "compliance_blocked" in reply.flags and reply.offers == []
    assert "₹2,000" not in reply.text


# --- complaints -----------------------------------------------------------------------------------
def test_complaints(client: TestClient) -> None:
    res = client.post(
        f"{API}/complaints",
        headers=PRIYA,
        json={
            "category": "fees_and_charges",
            "text": "Late fee charged within grace.",
            "lang": "en",
        },
    )
    assert res.status_code == 201
    c = Complaint.model_validate(res.json())
    assert c.docket_no.startswith(f"CMP-{datetime.now(UTC):%Y%m%d}-")
    assert c.sla_due_at - c.created_at == timedelta(days=30)
    assert c.grievance_officer.email
    assert client.get(f"{API}/complaints/{c.docket_no}", headers=RAVI).status_code == 404
    assert client.get(f"{API}/complaints/{c.docket_no}", headers=AUDITOR).status_code == 200
    upd = client.patch(
        f"{API}/complaints/{c.docket_no}",
        headers=OFFICER,
        json={"status": "escalated", "escalation_level": 1, "note": "SLA risk"},
    )
    assert upd.json()["status"] == "escalated" and upd.json()["escalation_level"] == 1
    staff = client.post(
        f"{API}/complaints", headers=OFFICER, json={"category": "x", "text": "y", "lang": "en"}
    )
    assert staff.status_code == 400
    second = client.post(
        f"{API}/complaints",
        headers=OFFICER,
        json={"customer_id": "CUST-DEMO-RAVI", "category": "x", "text": "y", "lang": "hi"},
    ).json()
    assert int(second["docket_no"][-4:]) == int(c.docket_no[-4:]) + 1
    assert client.get(f"{API}/complaints/CMP-20200101-0001", headers=OFFICER).status_code == 404


# --- admin / red team / metrics / wellness --------------------------------------------------------
def test_policy_get_and_put(client: TestClient, engine: Engine) -> None:
    current = client.get(f"{API}/admin/policy", headers=ADMIN)
    assert current.status_code == 200 and "X-Data-Source" not in current.headers
    policy = current.json()["policy"] | {"version": "v99"}
    put = client.put(
        f"{API}/admin/policy", headers=ADMIN, json={"policy": policy, "change_note": "test bump"}
    )
    assert put.status_code == 200 and put.json()["version"] == "v99"
    assert client.get(f"{API}/admin/policy", headers=ADMIN).json()["version"] == "v99"
    dup = client.put(
        f"{API}/admin/policy", headers=ADMIN, json={"policy": policy, "change_note": "again"}
    )
    assert dup.status_code == 409
    invalid = client.put(
        f"{API}/admin/policy",
        headers=ADMIN,
        json={"policy": {"no": "version"}, "change_note": "bad"},
    )
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "POLICY_INVALID"
    with Session(engine) as s:
        active = s.scalars(select(orm.PolicyVersion).where(orm.PolicyVersion.is_active)).all()
        assert [p.version for p in active] == ["v99"]
        change = s.scalars(
            select(orm.AuditLog).where(orm.AuditLog.action == "policy.changed")
        ).one()
        assert change.details["new_version"] == "v99"


def test_redteam_without_harness(client: TestClient) -> None:
    start = client.post(f"{API}/redteam/runs", headers=ADMIN)
    assert start.status_code == 501 and start.json()["error"]["code"] == "REDTEAM_UNAVAILABLE"
    latest = client.get(f"{API}/redteam/scorecard/latest", headers=AUDITOR)
    assert latest.status_code == 200 and latest.headers["X-Data-Source"] == "fixture"
    assert client.get(f"{API}/redteam/runs/RT-20200101-0000", headers=AUDITOR).status_code == 404


def test_simulation_metrics_fixture_is_flagged(client: TestClient) -> None:
    res = client.get(f"{API}/metrics/simulation", headers=COLLECTOR)
    assert res.status_code == 200 and res.headers["X-Data-Source"] == "fixture"


def test_kpis_empty(client: TestClient) -> None:
    k = client.get(f"{API}/metrics/kpis", headers=COLLECTOR).json()
    assert k["in_window_share"] == 1.0 and k["complaints_open"] == 0


def test_wellness_is_illustrative_and_self_only(client: TestClient) -> None:
    res = client.post(
        f"{API}/wellness/simulate", headers=PRIYA, json={"customer_id": "CUST-DEMO-PRIYA"}
    ).json()
    assert res["illustrative"] is True
    names = {s["name"]: s for s in res["scenarios"]}
    assert names["pay_plan"]["score_band"] == "good"  # Priya is SMA-0
    assert names["reach_npa"]["months_to_recover"] > names["pay_plan"]["months_to_recover"]
    other = client.post(
        f"{API}/wellness/simulate", headers=PRIYA, json={"customer_id": "CUST-DEMO-RAVI"}
    )
    assert other.status_code == 404
