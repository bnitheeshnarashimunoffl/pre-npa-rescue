"""Tests for hardship disclosure, bereavement pause, and affordability flows (Task 4.2)."""

from npa_chat.flows import (
    classify_hardship,
    estimate_affordability,
    handle_affordability_turn,
    handle_hardship_turn,
)
from npa_chat.flows.affordability import extract_dependants
from npa_chat.flows.hardship import (
    HARDSHIP_BEREAVEMENT,
    HARDSHIP_BUSINESS_LOSS,
    HARDSHIP_JOB_LOSS,
    HARDSHIP_MEDICAL,
    HARDSHIP_OTHER,
    HARDSHIP_PREFER_NOT_TO_SAY,
)
from npa_chat.state import ChatState, ConversationState
from npa_contracts.enums import Lang


def test_classify_hardship_multilingual() -> None:
    # Job loss
    assert classify_hardship("I lost my job last month") == HARDSHIP_JOB_LOSS
    assert classify_hardship("வேலை போனது, வருமானம் இல்லை") == HARDSHIP_JOB_LOSS
    assert classify_hardship("मेरी नौकरी चली गई") == HARDSHIP_JOB_LOSS

    # Medical emergency
    assert classify_hardship("Hospital bills and medical emergency") == HARDSHIP_MEDICAL
    assert classify_hardship("மருத்துவமனை செலவு அதிகம்") == HARDSHIP_MEDICAL
    assert classify_hardship("परिवार में कोई बीमार है, अस्पताल में भर्ती") == HARDSHIP_MEDICAL

    # Bereavement (RBI para 454Y(6))
    assert classify_hardship("Death in family, bereavement") == HARDSHIP_BEREAVEMENT
    assert classify_hardship("தந்தை இறப்பு, இறுதி சடங்கு") == HARDSHIP_BEREAVEMENT
    assert classify_hardship("परिवार में किसी का निधन हो गया") == HARDSHIP_BEREAVEMENT

    # Business loss
    assert classify_hardship("My business suffered huge losses") == HARDSHIP_BUSINESS_LOSS
    assert classify_hardship("தொழிலில் நஷ்டம்") == HARDSHIP_BUSINESS_LOSS
    assert classify_hardship("दुकान में बहुत घाटा हुआ") == HARDSHIP_BUSINESS_LOSS

    # Prefer not to say (optional disclosure)
    assert classify_hardship("I prefer not to say, it's private") == HARDSHIP_PREFER_NOT_TO_SAY
    assert classify_hardship("சொல்ல விரும்பவில்லை") == HARDSHIP_PREFER_NOT_TO_SAY
    assert classify_hardship("नहीं बताना चाहता") == HARDSHIP_PREFER_NOT_TO_SAY

    # General / Other
    assert classify_hardship("Lots of sudden expenses came up") == HARDSHIP_OTHER


def test_hardship_flow_bereavement_pause_enacted() -> None:
    state = ConversationState(session_id="SESS-BEREAVEMENT", customer_id="CUST-001", lang=Lang.EN)
    state.transition_to(ChatState.HARDSHIP_DISCLOSURE)

    # 1. Customer discloses bereavement
    res = handle_hardship_turn(state, "There was a death in the family recently")
    assert res.pause_suggested is True
    assert "pause_outreach_suggested" in res.flags
    assert len(res.quick_replies) == 2
    assert "para 454Y(6)" in res.reply_text

    # 2. Customer confirms they want outreach paused
    state.pause_outreach_suggested = True
    state.add_flag("pause_outreach_offered")
    res_pause = handle_hardship_turn(state, "Yes, please pause messages for now")
    assert res_pause.pause_confirmed is True
    assert res_pause.next_state == ChatState.CLOSING
    assert "outreach_paused" in res_pause.flags


def test_hardship_flow_bereavement_pause_declined() -> None:
    state = ConversationState(session_id="SESS-CONT", customer_id="CUST-001", lang=Lang.EN)
    state.transition_to(ChatState.HARDSHIP_DISCLOSURE)

    # Offer pause
    state.pause_outreach_suggested = True
    state.add_flag("pause_outreach_offered")

    # Customer declines pause and wants to explore options
    res = handle_hardship_turn(state, "No, continue exploring relief options")
    assert res.next_state == ChatState.AFFORDABILITY
    assert len(res.quick_replies) > 0


def test_hardship_flow_prefer_not_to_say_optional() -> None:
    state = ConversationState(session_id="SESS-OPT", customer_id="CUST-001", lang=Lang.EN)
    state.transition_to(ChatState.HARDSHIP_DISCLOSURE)

    res = handle_hardship_turn(state, "Prefer not to say")
    assert res.next_state == ChatState.AFFORDABILITY
    assert state.hardship_type == HARDSHIP_PREFER_NOT_TO_SAY
    assert "optional" in res.reply_text.lower()


def test_estimate_affordability_priya_and_ravi() -> None:
    # Priya demo figures: income ₹35k, expenses ₹32.5k, dependants 1 -> surplus ₹2.5k
    aff_priya = estimate_affordability(
        customer_id="CUST-DEMO-PRIYA",
        declared_income_paise=3500000,
        declared_expenses_paise=3250000,
        dependants=1,
    )
    assert aff_priya.max_monthly_payment_paise == 250000
    assert aff_priya.customer_id == "CUST-DEMO-PRIYA"

    # Ravi zero capacity: income 0, expenses ₹20k -> surplus 0
    aff_ravi = estimate_affordability(
        customer_id="CUST-DEMO-RAVI",
        declared_income_paise=0,
        declared_expenses_paise=2000000,
        dependants=3,
    )
    assert aff_ravi.max_monthly_payment_paise == 0

    # Negative surplus bounded at 0
    aff_neg = estimate_affordability(
        customer_id="CUST-002",
        declared_income_paise=1000000,
        declared_expenses_paise=1500000,
    )
    assert aff_neg.max_monthly_payment_paise == 0


def test_affordability_flow_multi_turn() -> None:
    state = ConversationState(session_id="SESS-AFF", customer_id="CUST-DEMO-PRIYA", lang=Lang.EN)
    state.transition_to(ChatState.AFFORDABILITY)

    # 1. Provide income
    res1 = handle_affordability_turn(state, "35000")
    assert state.declared_income_paise == 3500000
    assert "expenses" in res1.reply_text.lower()

    # 2. Provide expenses & dependants
    res2 = handle_affordability_turn(state, "Expenses are 32500, 1 dependant")
    assert state.declared_expenses_paise == 3250000
    assert state.dependants == 1
    assert "affordability_confirming" in state.flags
    assert "₹2,500" in res2.reply_text

    # 3. Confirm capacity
    res3 = handle_affordability_turn(state, "Yes, that works")
    assert res3.next_state == ChatState.OPTIONS
    assert res3.affordability is not None
    assert res3.affordability.max_monthly_payment_paise == 250000


def test_affordability_flow_zero_capacity_ravi() -> None:
    state = ConversationState(session_id="SESS-RAVI", customer_id="CUST-DEMO-RAVI", lang=Lang.EN)
    state.transition_to(ChatState.AFFORDABILITY)

    res = handle_affordability_turn(state, "I cannot pay anything right now")
    assert res.next_state == ChatState.ZERO_CAPACITY
    assert state.max_monthly_payment_paise == 0


def test_extract_dependants() -> None:
    assert extract_dependants("I have 2 kids and my spouse") == 2
    assert extract_dependants("1 dependant") == 1
    assert extract_dependants("ஒருவர் என்னை சார்ந்துள்ளார்") == 1
    assert extract_dependants("no dependants mentioned") is None
