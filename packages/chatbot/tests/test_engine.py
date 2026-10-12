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
