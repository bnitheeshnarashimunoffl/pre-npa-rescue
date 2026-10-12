"""Tests for hardship disclosure, bereavement pause, and affordability flows (Task 4.2)."""

from npa_chat.distress import detect_distress, handle_distress
from npa_chat.flows import (
    ComplaintCategory,
    classify_complaint_category,
    classify_hardship,
    estimate_affordability,
    format_option_summary,
    handle_affordability_turn,
    handle_complaint_turn,
    handle_hardship_turn,
    handle_offer_turn,
    handle_zero_capacity_turn,
    present_relief_options,
    present_zero_capacity_options,
    render_disclosure,
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
from npa_chat.nlu import Intent, NLUResult
from npa_chat.state import ChatState, ConversationState
from npa_contracts.enums import Lang, OfferStatus, ReliefType
from npa_contracts.models import Affordability, ReliefOption

from .fakes import (
    FakeCallbackScheduler,
    FakeComplaintSink,
    FakeCustomerContextProvider,
    FakePolicyProvider,
    FakeRiskProvider,
)


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


def test_render_disclosure_prefixes() -> None:
    # Key with disclosure. prefix
    disc_long = render_disclosure("disclosure.fee_waiver.scope", Lang.EN)
    assert "Late fees and penal charges waived" in disc_long

    # Key with disc. prefix (upcoming WS5 fixture format)
    disc_short = render_disclosure("disc.fee_waiver.scope", Lang.EN)
    assert "Late fees and penal charges waived" in disc_short

    # Tamil localization
    disc_ta = render_disclosure("disc.emi_conversion.interest_breakdown", Lang.TA)
    assert "வட்டி" in disc_ta

    # Fallback for unknown key
    disc_unknown = render_disclosure("disc.custom.key", Lang.EN)
    assert "disc.custom.key" in disc_unknown


def test_format_option_summary() -> None:
    opt_emi_waiver = ReliefOption(
        option_id="OPT-PRIYA-EMI",
        type=ReliefType.EMI_CONVERSION,
        monthly_amount_paise=200000,
        tenure_months=6,
        waiver_paise=153400,
        settlement_amount_paise=None,
        policy_ref="bank_policy.yaml#emi_conversion.v1",
        regulatory_refs=["RBI Prudential Framework 2019"],
        disclosure_keys=["disc.emi_conversion.interest_breakdown"],
        requires_human_approval=False,
        eligibility_reason="Affordability surplus supports ₹2,000/month",
    )
    summary_en = format_option_summary(opt_emi_waiver, Lang.EN, index=1)
    assert "₹2,000" in summary_en
    assert "6 months" in summary_en
    assert "₹1,534" in summary_en

    summary_ta = format_option_summary(opt_emi_waiver, Lang.TA, index=1)
    assert "₹2,000" in summary_ta
    assert "6 மாதங்கள்" in summary_ta


def test_present_relief_options_structure() -> None:
    policy_provider = FakePolicyProvider()
    aff = Affordability(
        customer_id="CUST-DEMO-PRIYA",
        declared_income_paise=3500000,
        declared_expenses_paise=3250000,
        dependants=1,
        max_monthly_payment_paise=250000,
        source="declared",
    )

    text, offers, quick_replies = present_relief_options(
        customer_id="CUST-DEMO-PRIYA",
        account_id="ACC-PRIYA-001",
        affordability=aff,
        policy_provider=policy_provider,
        lang=Lang.TA,
    )

    assert len(offers) <= 3
    assert len(offers) > 0
    assert offers[0].status in (OfferStatus.PRESENTED, OfferStatus.PROPOSED)
    assert any(qr.id == "accept_offer" for qr in quick_replies)
    assert any(qr.id == "reject_offer" for qr in quick_replies)
    # Check disclosure bullet in rendered text
    assert "ℹ️" in text


def test_handle_offer_turn_acceptance() -> None:
    policy_provider = FakePolicyProvider()
    aff = Affordability(
        customer_id="CUST-DEMO-PRIYA",
        declared_income_paise=3500000,
        declared_expenses_paise=3250000,
        dependants=1,
        max_monthly_payment_paise=250000,
        source="declared",
    )
    _, offers, _ = present_relief_options(
        customer_id="CUST-DEMO-PRIYA",
        account_id="ACC-PRIYA-001",
        affordability=aff,
        policy_provider=policy_provider,
        lang=Lang.EN,
    )

    state = ConversationState(session_id="SESS-OFFER", customer_id="CUST-DEMO-PRIYA", lang=Lang.EN)
    state.transition_to(ChatState.OPTIONS)
    state.presented_offers = offers

    # Accept
    res = handle_offer_turn(
        state=state,
        text="I accept this plan",
        nlu_result=NLUResult(intent=Intent.ACCEPT_OPTION),
        policy_provider=policy_provider,
    )
    assert res.next_state == ChatState.ACCEPTED
    assert "offer_accepted" in res.flags
    assert "rbi_454aa_grievance_attached" in res.flags
    assert state.presented_offers[0].status == OfferStatus.ACCEPTED
    # Grievance officer contact details attached
    assert "@" in res.reply_text


def test_handle_offer_turn_rejection() -> None:
    policy_provider = FakePolicyProvider()
    state = ConversationState(session_id="SESS-REJ", customer_id="CUST-DEMO-PRIYA", lang=Lang.EN)
    state.transition_to(ChatState.OPTIONS)

    res = handle_offer_turn(
        state=state,
        text="No, I decline this offer",
        nlu_result=NLUResult(intent=Intent.REJECT_OPTION),
        policy_provider=policy_provider,
    )
    assert res.next_state == ChatState.OPTIONS
    assert "offer_rejected" in res.flags
    assert any(qr.id == "speak_officer" for qr in res.quick_replies)


def test_handle_offer_turn_why_contacted() -> None:
    policy_provider = FakePolicyProvider()
    risk_provider = FakeRiskProvider()
    state = ConversationState(session_id="SESS-WHY", customer_id="CUST-DEMO-PRIYA", lang=Lang.TA)
    state.transition_to(ChatState.OPTIONS)

    res = handle_offer_turn(
        state=state,
        text="ஏன் என்னை தொடர்பு கொள்கிறீர்கள்?",
        nlu_result=NLUResult(intent=Intent.ASK_WHY_CONTACTED),
        policy_provider=policy_provider,
        risk_provider=risk_provider,
    )
    assert "why_contacted_explained" in res.flags
    # Check risk reasons are provided in Tamil or translated
    assert len(res.reply_text) > 50
    assert any(qr.id == "accept_offer" for qr in res.quick_replies)


def test_detect_distress_rules() -> None:
    # High distress score
    assert detect_distress("I am feeling down", distress_score=0.85) is True

    # Multilingual triggers
    assert detect_distress("I want to end my life, feel hopeless") is True
    assert detect_distress("எனக்கு வாழ பிடிக்கவில்லை, தற்கொலை எண்ணம்") is True
    assert detect_distress("मैं अपनी जान देना चाहता हूँ") is True

    # Normal text
    assert detect_distress("Can you explain the options?", distress_score=0.1) is False


def test_handle_distress_flow() -> None:
    state = ConversationState(session_id="SESS-DIST", customer_id="CUST-DEMO-RAVI", lang=Lang.EN)
    res = handle_distress(state)

    assert res.next_state == ChatState.DISTRESS
    assert "distress_detected" in res.flags
    # Tele-MANAS helpline 14416
    assert "14416" in res.reply_text
    assert "well-being comes first" in res.reply_text.lower()


def test_present_zero_capacity_options_insurance_and_slots() -> None:
    policy_provider = FakePolicyProvider()
    callback_scheduler = FakeCallbackScheduler()
    ctx_provider = FakeCustomerContextProvider()
    ravi_ctx = ctx_provider.context("CUST-DEMO-RAVI")

    state = ConversationState(session_id="SESS-ZC", customer_id="CUST-DEMO-RAVI", lang=Lang.EN)
    state.transition_to(ChatState.ZERO_CAPACITY)

    res = present_zero_capacity_options(
        state=state,
        customer_context=ravi_ctx,
        policy_provider=policy_provider,
        callback_scheduler=callback_scheduler,
    )

    # 1. Stops the ask
    assert "will not ask you for payments right now" in res.reply_text

    # 2. Mentions insurance cover first (Ravi demo feature)
    assert "job_loss" in res.reply_text or "insurance" in res.reply_text.lower()
    assert "insurance_cover_referred" in res.flags

    # 3. Disclosures rendered truthfully
    assert "ℹ️" in res.reply_text

    # 4. Offers available callback slots (including 11:00 AM)
    slot_labels = [qr.label for qr in res.quick_replies]
    assert any("11:00" in lbl for lbl in slot_labels)


def test_handle_zero_capacity_turn_booking() -> None:
    policy_provider = FakePolicyProvider()
    callback_scheduler = FakeCallbackScheduler()
    ctx_provider = FakeCustomerContextProvider()
    ravi_ctx = ctx_provider.context("CUST-DEMO-RAVI")

    state = ConversationState(session_id="SESS-ZC-BOOK", customer_id="CUST-DEMO-RAVI", lang=Lang.EN)
    state.transition_to(ChatState.ZERO_CAPACITY)
    state.hardship_type = "job_loss"

    # Customer picks 11:00 AM slot
    res = handle_zero_capacity_turn(
        state=state,
        text="Please book the 11:00 AM slot",
        nlu_result=None,
        customer_context=ravi_ctx,
        policy_provider=policy_provider,
        callback_scheduler=callback_scheduler,
    )

    assert res.next_state == ChatState.HANDOFF
    assert "callback_booked" in res.flags
    assert "rbi_454aa_grievance_attached" in res.flags
    assert state.booked_callback_id is not None
    # Confirmation details
    assert "11:00 AM" in res.reply_text
    assert "@" in res.reply_text  # Grievance officer email in footer


def test_classify_complaint_category() -> None:
    # Harassment (threat, abusive words, calling at night)
    cat, is_h = classify_complaint_category("Your recovery agent is threatening my family!")
    assert cat == ComplaintCategory.HARASSMENT
    assert is_h is True

    cat_ta, is_h_ta = classify_complaint_category("கடன் வசூல் முகவர் அச்சுறுத்தல் செய்கிறார்")
    assert cat_ta == ComplaintCategory.HARASSMENT
    assert is_h_ta is True

    cat_hi, is_h_hi = classify_complaint_category("एजेंट मुझे धमकी दे रहा है और गाली दे रहा है")
    assert cat_hi == ComplaintCategory.HARASSMENT
    assert is_h_hi is True

    # Wrong charges
    cat_wc, is_h_wc = classify_complaint_category("You added wrong charges and penalty")
    assert cat_wc == ComplaintCategory.WRONG_CHARGES
    assert is_h_wc is False

    # Privacy / DPDP
    cat_dpdp, is_h_dpdp = classify_complaint_category("DPDP data breach, you shared my data")
    assert cat_dpdp == ComplaintCategory.PRIVACY
    assert is_h_dpdp is False

    # Service
    cat_srv, is_h_srv = classify_complaint_category("Terrible delay, bad service, no response")
    assert cat_srv == ComplaintCategory.SERVICE
    assert is_h_srv is False

    # Other / general
    cat_oth, is_h_oth = classify_complaint_category("I want to lodge a formal complaint")
    assert cat_oth == ComplaintCategory.OTHER
    assert is_h_oth is False


def test_handle_complaint_turn_general() -> None:
    sink = FakeComplaintSink()
    policy = FakePolicyProvider()
    state = ConversationState(session_id="SESS-CMP-GEN", customer_id="CUST-DEMO-01", lang=Lang.EN)

    res = handle_complaint_turn(
        state=state,
        text="I have a complaint about unexpected charges on my card statement",
        complaint_sink=sink,
        policy_provider=policy,
    )

    assert res.next_state == ChatState.COMPLAINT
    assert res.category == ComplaintCategory.WRONG_CHARGES
    assert res.is_harassment is False
    assert "complaint_reported" in res.flags
    assert "harassment_reported" not in res.flags
    assert len(sink.complaints) == 1
    assert sink.complaints[0].category == "wrong_charges"
    assert state.complaint_docket_no == res.docket_no
    assert res.docket_no.startswith("CMP-")

    # 30-day timeline per IS/ISO 10002:2018 and RBI RBC Directions
    assert "30 days" in res.reply_text
    assert "IS/ISO 10002:2018" in res.reply_text
    # RBI Ombudsman escalation rights
    assert "cms.rbi.org.in" in res.reply_text
    assert "14448" in res.reply_text
    # Grievance officer footer
    assert policy.grievance_officer().email in res.reply_text


def test_handle_complaint_turn_harassment_priority() -> None:
    sink = FakeComplaintSink()
    policy = FakePolicyProvider()
    state = ConversationState(session_id="SESS-CMP-HAR", customer_id="CUST-DEMO-02", lang=Lang.EN)

    res = handle_complaint_turn(
        state=state,
        text="The agent is harassing me with abusive calls at night",
        complaint_sink=sink,
        policy_provider=policy,
    )

    assert res.category == ComplaintCategory.HARASSMENT
    assert res.is_harassment is True
    assert "complaint_reported" in res.flags
    assert "harassment_reported" in res.flags
    assert "harassment_reported" in state.flags
    # Priority note present
    assert "priority review" in res.reply_text


def test_handle_complaint_turn_multilingual_tamil() -> None:
    sink = FakeComplaintSink()
    policy = FakePolicyProvider()
    state = ConversationState(session_id="SESS-CMP-TA", customer_id="CUST-PRIYA", lang=Lang.TA)

    res = handle_complaint_turn(
        state=state,
        text="முகவர் என்னை மிரட்டுகிறார், உடனடி புகார் தேவை",
        complaint_sink=sink,
        policy_provider=policy,
    )

    assert res.category == ComplaintCategory.HARASSMENT
    assert res.is_harassment is True
    assert "30" in res.reply_text
    assert "14448" in res.reply_text
    assert "cms.rbi.org.in" in res.reply_text
    assert "@" in res.reply_text
