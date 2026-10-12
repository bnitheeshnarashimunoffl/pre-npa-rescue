"""Tests for conversation state and session storage."""

from npa_chat.state import ChatState, ConversationState, InMemorySessionStore
from npa_contracts.enums import Lang


def test_conversation_state_lifecycle() -> None:
    state = ConversationState(
        session_id="SESS-1234",
        customer_id="CUST-DEMO-PRIYA",
        lang=Lang.TA,
    )
    assert state.current_state == ChatState.GREETING
    assert state.previous_state is None
    assert state.lang == Lang.TA
    assert not state.recording_notice_given

    state.add_flag("distress_detected")
    state.add_flag("distress_detected")  # idempotent
    assert state.flags == ["distress_detected"]

    state.transition_to(ChatState.HARDSHIP_DISCLOSURE)
    assert state.previous_state == ChatState.GREETING
    assert state.current_state == ChatState.HARDSHIP_DISCLOSURE


def test_conversation_state_json_roundtrip() -> None:
    state = ConversationState(
        session_id="SESS-5678",
        customer_id="CUST-DEMO-RAVI",
        declared_income_paise=1500000,
        max_monthly_payment_paise=0,
    )
    json_data = state.model_dump_json()
    reloaded = ConversationState.model_validate_json(json_data)

    assert reloaded.session_id == state.session_id
    assert reloaded.customer_id == state.customer_id
    assert reloaded.declared_income_paise == 1500000
    assert reloaded.max_monthly_payment_paise == 0


def test_in_memory_session_store() -> None:
    store = InMemorySessionStore()
    assert store.get("non-existent") is None

    state = ConversationState(session_id="SESS-001", customer_id="CUST-001")
    store.save(state)

    retrieved = store.get("SESS-001")
    assert retrieved is not None
    assert retrieved.customer_id == "CUST-001"

    retrieved.transition_to(ChatState.CONSENT_NOTICE)
    store.save(retrieved)
    assert store.get("SESS-001") is not None
    assert store.get("SESS-001").current_state == ChatState.CONSENT_NOTICE  # type: ignore[union-attr]
