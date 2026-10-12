"""Tests for ChatEngine dialogue handling and initial flows."""

from npa_chat.engine import ChatEngine, build_engine
from npa_chat.llm_client import MockLLMClient
from npa_chat.state import ChatState, InMemorySessionStore
from npa_contracts.enums import Lang
from npa_contracts.models import ChatTurnRequest

from .fakes import (
    FakeCallbackScheduler,
    FakeComplaintSink,
    FakeComplianceProvider,
    FakeContactLogger,
    FakeCustomerContextProvider,
    FakePolicyProvider,
    FakeRiskProvider,
)


def _create_engine() -> tuple[ChatEngine, FakeContactLogger, FakeComplaintSink]:
    logger = FakeContactLogger()
    complaints = FakeComplaintSink()
    store = InMemorySessionStore()
    engine = build_engine(
        risk_provider=FakeRiskProvider(),
        policy_provider=FakePolicyProvider(),
        compliance_provider=FakeComplianceProvider(),
        contact_logger=logger,
        complaint_sink=complaints,
        callback_scheduler=FakeCallbackScheduler(),
        customer_context_provider=FakeCustomerContextProvider(),
        llm_client=MockLLMClient(),
        session_store=store,
    )
    return engine, logger, complaints


def test_first_turn_greeting_and_regulatory_notices() -> None:
    engine, logger, _ = _create_engine()

    req = ChatTurnRequest(text="Hi", lang=None)
    reply = engine.handle(
        session_id="SESS-TURN1-001",
        customer_id="CUST-DEMO-PRIYA",
        req=req,
    )

    # Greets by first name
    assert "Priya" in reply.text or "பிரியா" in reply.text

    # Mandatory notices (RBI para 454P recording notice + DPDP Act)
    assert "recorded" in reply.text.lower() or "பதிவு" in reply.text
    assert "dpdp" in reply.text.lower() or "தகவல்" in reply.text

    # Quick replies include the three supported languages
    reply_ids = [qr.id for qr in reply.quick_replies]
    assert "lang_en" in reply_ids
    assert "lang_ta" in reply_ids
    assert "lang_hi" in reply_ids

    # State transitions to CONSENT_NOTICE
    assert reply.state == ChatState.CONSENT_NOTICE.value

    # Contact logger recorded inbound and outbound turns
    assert len(logger.events) == 2
    assert logger.events[0].direction == "inbound"
    assert logger.events[1].direction == "outbound"
    assert logger.events[1].recorded_notice_given is True


def test_turn_two_language_switch_to_tamil() -> None:
    engine, _, _ = _create_engine()

    # Turn 1
    engine.handle(
        session_id="SESS-SWITCH-001",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="Hello", lang=Lang.EN),
    )

    # Turn 2: Switch to Tamil
    reply_ta = engine.handle(
        session_id="SESS-SWITCH-001",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="தமிழ்", lang=None),
    )

    assert reply_ta.lang == Lang.TA
    assert "language_switched" in reply_ta.flags
    assert "மாற்றப்பட்டது" in reply_ta.text or "வணக்கம்" in reply_ta.text
    assert reply_ta.state == ChatState.HARDSHIP_DISCLOSURE.value


def test_distress_interrupt_flow() -> None:
    engine, _, _ = _create_engine()

    # Turn 1
    engine.handle(
        session_id="SESS-DISTRESS-001",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="Hi"),
    )

    # Turn 2: Express distress
    distress_reply = engine.handle(
        session_id="SESS-DISTRESS-001",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(
            text="I have lost everything and feel hopeless and want to end my life"
        ),
    )

    assert "distress_detected" in distress_reply.flags
    assert distress_reply.state == ChatState.DISTRESS.value
    # Tele-MANAS helpline 14416 present
    assert "14416" in distress_reply.text


def test_complaint_interrupt_flow() -> None:
    engine, _, complaints = _create_engine()

    # Turn 1
    engine.handle(
        session_id="SESS-COMPLAINT-001",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="Hello"),
    )

    # Turn 2: Register complaint
    complaint_reply = engine.handle(
        session_id="SESS-COMPLAINT-001",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="I want to lodge a formal complaint about improper charges"),
    )

    assert "complaint_reported" in complaint_reply.flags
    assert complaint_reply.state == ChatState.COMPLAINT.value
    assert len(complaints.complaints) == 1
    docket = complaints.complaints[0].docket_no
    assert docket in complaint_reply.text


def test_engine_priya_hardship_and_affordability_flow() -> None:
    engine, _, _ = _create_engine()

    # Turn 1: Greeting
    r1 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="Hello"),
    )
    assert r1.state == ChatState.CONSENT_NOTICE.value

    # Turn 2: Switch to Tamil
    r2 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="தமிழ்"),
    )
    assert r2.state == ChatState.HARDSHIP_DISCLOSURE.value

    # Turn 3: Disclose job loss in Tamil ("வேலை போனது")
    r3 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="எனக்கு வேலை போனது, வருமானம் இல்லை"),
    )
    assert r3.state == ChatState.AFFORDABILITY.value
    assert "hardship_classified_job_loss" in r3.flags

    # Turn 4: Provide income (35000)
    r4 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="35000"),
    )
    assert r4.state == ChatState.AFFORDABILITY.value

    # Turn 5: Provide expenses (32500) and dependants
    r5 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="செலவு 32500, ஒருவர் என்னை சார்ந்துள்ளார்"),
    )
    assert "₹2,500" in r5.text or "2,500" in r5.text
    assert "affordability_confirming" in r5.flags

    # Turn 6: Confirm budget capacity -> Bot presents relief options
    r6 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="ஆம்"),
    )
    assert r6.state == ChatState.OPTIONS.value
    assert "affordability_confirmed" in r6.flags
    # Check Priya's plan is presented (₹2,000/month for 6 months and fee waiver)
    assert "2,000" in r6.text
    assert "ℹ️" in r6.text

    # Turn 7: Priya asks why contacted in Tamil
    r7 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="ஏன் என்னை தொடர்பு கொள்கிறீர்கள்?"),
    )
    assert r7.state == ChatState.OPTIONS.value
    assert "why_contacted_explained" in r7.flags

    # Turn 8: Priya accepts the offer in Tamil
    r8 = engine.handle(
        session_id="SESS-PRIYA-FULL",
        customer_id="CUST-DEMO-PRIYA",
        req=ChatTurnRequest(text="ஏற்றுக்கொள்கிறேன்"),
    )
    assert r8.state == ChatState.ACCEPTED.value
    assert "offer_accepted" in r8.flags
    assert "rbi_454aa_grievance_attached" in r8.flags
    # Confirms 30-day first instalment due date and grievance officer
    assert "@" in r8.text


def test_engine_bereavement_pause_flow() -> None:
    engine, _, _ = _create_engine()

    # Turn 1: Greeting
    engine.handle(
        session_id="SESS-BEREAVEMENT-ENGINE",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="Hi"),
    )

    # Turn 2: Consent -> Hardship
    engine.handle(
        session_id="SESS-BEREAVEMENT-ENGINE",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="English"),
    )

    # Turn 3: Bereavement report
    r3 = engine.handle(
        session_id="SESS-BEREAVEMENT-ENGINE",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="There was a bereavement in my family recently"),
    )
    assert "pause_outreach_suggested" in r3.flags
    assert "para 454Y(6)" in r3.text

    # Turn 4: Accept pause
    r4 = engine.handle(
        session_id="SESS-BEREAVEMENT-ENGINE",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="Yes pause"),
    )
    assert r4.state == ChatState.CLOSING.value
    assert "outreach_paused" in r4.flags


def test_engine_ravi_zero_capacity_full_demo_flow() -> None:
    engine, _, _ = _create_engine()

    # Turn 1: Greeting
    r1 = engine.handle(
        session_id="SESS-RAVI-DEMO",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="Hi"),
    )
    assert r1.state == ChatState.CONSENT_NOTICE.value
    assert "Ravi" in r1.text

    # Turn 2: Select English
    r2 = engine.handle(
        session_id="SESS-RAVI-DEMO",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="English"),
    )
    assert r2.state == ChatState.HARDSHIP_DISCLOSURE.value

    # Turn 3: Disclose job loss
    r3 = engine.handle(
        session_id="SESS-RAVI-DEMO",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="I lost my job 3 months ago and have zero income"),
    )
    assert r3.state == ChatState.AFFORDABILITY.value
    assert "hardship_classified_job_loss" in r3.flags

    # Turn 4: Cannot pay even ₹500 -> Zero Capacity Entry
    r4 = engine.handle(
        session_id="SESS-RAVI-DEMO",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="I can't pay even 500 rupees right now, I have zero money"),
    )
    assert r4.state == ChatState.ZERO_CAPACITY.value
    # 1. Stops the ask
    assert "will not ask you for payments right now" in r4.text
    # 2. Mentions insurance cover from context
    assert "insurance" in r4.text.lower()
    assert "insurance_cover_referred" in r4.flags
    # 3. Disclosures present
    assert "ℹ️" in r4.text
    # 4. Offers 11:00 AM slot in quick replies
    assert any("11:00" in qr.label for qr in r4.quick_replies)

    # Turn 5: Ravi books 11:00 AM slot
    r5 = engine.handle(
        session_id="SESS-RAVI-DEMO",
        customer_id="CUST-DEMO-RAVI",
        req=ChatTurnRequest(text="Please book the 11:00 AM slot with the hardship officer"),
    )
    assert r5.state == ChatState.HANDOFF.value
    assert "callback_booked" in r5.flags
    assert "rbi_454aa_grievance_attached" in r5.flags
    assert "11:00 AM" in r5.text
    assert "@" in r5.text  # Grievance officer details in footer
