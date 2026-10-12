"""Tests for fixture-backed provider fakes."""

from datetime import UTC, date, datetime, timedelta

from npa_contracts.constants import COMPLAINT_SLA_DAYS
from npa_contracts.enums import Actor, Channel, Lang, Role
from npa_contracts.models import Affordability, ContactEvent
from npa_contracts.providers import (
    CallbackScheduler,
    ComplaintSink,
    ComplianceProvider,
    ContactLogger,
    CustomerContextProvider,
    PolicyProvider,
    RiskProvider,
)

from .fakes import (
    FakeCallbackScheduler,
    FakeComplaintSink,
    FakeComplianceProvider,
    FakeContactLogger,
    FakeCustomerContextProvider,
    FakePolicyProvider,
    FakeRiskProvider,
    _get_ist_tz,
)


def test_fake_risk_provider_protocol_conformance() -> None:
    provider: RiskProvider = FakeRiskProvider()
    risk = provider.risk("ACC-DEMO-PRIYA", "2026-09")
    assert risk.account_id == "ACC-DEMO-PRIYA"
    assert risk.risk_band == "high"

    segment = provider.segment("ACC-DEMO-PRIYA", "2026-09")
    assert segment.account_id == "ACC-DEMO-PRIYA"

    uplift = provider.uplift("ACC-DEMO-PRIYA", "2026-09")
    assert uplift.account_id == "ACC-DEMO-PRIYA"

    batch = list(provider.score_batch("2026-09"))
    assert len(batch) == 1


def test_fake_policy_provider_priya_and_ravi() -> None:
    provider: PolicyProvider = FakePolicyProvider()

    # Priya capacity
    aff_priya = Affordability(
        customer_id="CUST-DEMO-PRIYA",
        declared_income_paise=3500000,
        declared_expenses_paise=3250000,
        dependants=1,
        max_monthly_payment_paise=250000,
        source="declared",
    )
    priya_options = provider.relief_options("CUST-DEMO-PRIYA", aff_priya)
    assert len(priya_options) >= 2
    assert any(opt.monthly_amount_paise == 200000 for opt in priya_options)

    # Ravi zero capacity
    aff_ravi = Affordability(
        customer_id="CUST-DEMO-RAVI",
        declared_income_paise=0,
        declared_expenses_paise=2000000,
        dependants=3,
        max_monthly_payment_paise=0,
        source="declared",
    )
    ravi_options = provider.relief_options("CUST-DEMO-RAVI", aff_ravi)
    assert len(ravi_options) >= 1
    assert any(opt.type == "insurance_referral" for opt in ravi_options)

    # Grievance officer
    officer = provider.grievance_officer()
    assert officer.name
    assert officer.email


def test_fake_compliance_and_contact_logger() -> None:
    comp: ComplianceProvider = FakeComplianceProvider()
    now = datetime.now(UTC)
    dec = comp.check_contact("CUST-DEMO-PRIYA", Channel.CHAT, now, Actor.BOT)
    assert dec.allowed

    logger: ContactLogger = FakeContactLogger()
    event = ContactEvent(
        event_id="EVT-001",
        customer_id="CUST-DEMO-PRIYA",
        account_id="ACC-DEMO-PRIYA",
        channel=Channel.CHAT,
        direction="outbound",
        actor=Actor.BOT,
        ts=now,
        content="Hello Priya",
        lang=Lang.TA,
        recorded_notice_given=True,
        compliance=dec,
        outcome=None,
    )
    logger.log(event)
    assert len(logger.events) == 1  # type: ignore[attr-defined]


def test_fake_complaint_and_callback() -> None:
    complaint_sink: ComplaintSink = FakeComplaintSink()
    complaint = complaint_sink.open(
        "CUST-DEMO-PRIYA", "fees_and_charges", "Late fee dispute", Lang.EN
    )
    assert complaint.docket_no.startswith("CMP-")
    assert complaint.status == "open"
    # Verify Complaint SLA delta is exactly 30 days
    assert complaint.sla_due_at == complaint.created_at + timedelta(days=COMPLAINT_SLA_DAYS)
    assert (complaint.sla_due_at - complaint.created_at).days == 30

    # Month-boundary case (e.g. created on Jan 31 or Oct 31)
    boundary_dt = datetime(2026, 1, 31, 10, 0, tzinfo=UTC)
    complaint_boundary = complaint_sink.open(  # type: ignore[call-arg]
        "CUST-DEMO-PRIYA", "fees_and_charges", "Late fee dispute", Lang.EN, at=boundary_dt
    )
    assert complaint_boundary.sla_due_at == boundary_dt + timedelta(days=COMPLAINT_SLA_DAYS)
    assert (complaint_boundary.sla_due_at - boundary_dt).days == 30

    scheduler: CallbackScheduler = FakeCallbackScheduler()
    today = date(2026, 10, 15)
    slots = scheduler.available_slots("CUST-DEMO-RAVI", today)
    assert len(slots) >= 1
    # Check slots are in IST 08:00 to 19:00
    tz = _get_ist_tz()
    slot_start, _ = slots[0]
    assert 8 <= slot_start.astimezone(tz).hour < 19

    cb = scheduler.book("CUST-DEMO-RAVI", slot_start, Role.HARDSHIP_OFFICER, "Summary")
    assert cb.customer_id == "CUST-DEMO-RAVI"
    # Assert slot_end > slot_start and duration is exactly 30 minutes
    assert cb.slot_end > cb.slot_start
    assert cb.slot_end - cb.slot_start == timedelta(minutes=30)


def test_fake_customer_context_provider() -> None:
    context_provider: CustomerContextProvider = FakeCustomerContextProvider()
    priya_ctx = context_provider.context("CUST-DEMO-PRIYA")
    assert priya_ctx["language_pref"] == "ta"
    assert priya_ctx["has_card_insurance"] is False

    ravi_ctx = context_provider.context("CUST-DEMO-RAVI")
    assert ravi_ctx["language_pref"] == "en"
    assert ravi_ctx["has_card_insurance"] is True
