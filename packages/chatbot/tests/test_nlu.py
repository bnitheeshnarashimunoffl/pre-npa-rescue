"""Tests for Natural Language Understanding (NLU) and amount parsing."""

from npa_chat.llm_client import MockLLMClient
from npa_chat.nlu import NLU, Intent, parse_amount_paise
from npa_contracts.enums import Lang


def test_parse_amount_paise_english() -> None:
    assert parse_amount_paise("15k") == 1_500_000
    assert parse_amount_paise("₹2,000") == 200_000
    assert parse_amount_paise("2000") == 200_000
    assert parse_amount_paise("1.5 lakh") == 15_000_000
    assert parse_amount_paise("I can pay nothing") == 0
    assert parse_amount_paise("0 rupees") == 0


def test_parse_amount_paise_tamil() -> None:
    assert parse_amount_paise("இரண்டாயிரம்") == 200_000
    assert parse_amount_paise("பதினைந்தாயிரம்") == 1_500_000
    assert parse_amount_paise("பத்தாயிரம்") == 1_000_000
    assert parse_amount_paise("2000 ரூபாய்") == 200_000


def test_parse_amount_paise_hindi() -> None:
    assert parse_amount_paise("दो हज़ार") == 200_000
    assert parse_amount_paise("पंद्रह हज़ार") == 1_500_000
    assert parse_amount_paise("15 हजार") == 1_500_000
    assert parse_amount_paise("2000 रुपये") == 200_000


def test_nlu_distress_detection_multilingual() -> None:
    mock_llm = MockLLMClient()
    nlu = NLU(mock_llm)

    en_res = nlu.parse("I feel hopeless and want to end my life")
    assert en_res.intent == Intent.DISTRESS
    assert en_res.distress_score == 1.0

    ta_res = nlu.parse("வாழ வழியில்லை தற்கொலை எண்ணம் வருகிறது")
    assert ta_res.intent == Intent.DISTRESS
    assert ta_res.distress_score == 1.0

    hi_res = nlu.parse("मुझे जीने की इच्छा नहीं है")
    assert hi_res.intent == Intent.DISTRESS
    assert hi_res.distress_score == 1.0


def test_nlu_common_intents() -> None:
    mock_llm = MockLLMClient()
    nlu = NLU(mock_llm)

    complaint_res = nlu.parse("I want to file a complaint about agent harassment")
    assert complaint_res.intent == Intent.COMPLAIN

    human_res = nlu.parse("Can I talk to a human officer please?")
    assert human_res.intent == Intent.ASK_HUMAN

    hardship_res = nlu.parse("I suffered a sudden job loss last month")
    assert hardship_res.intent == Intent.EXPLAIN_HARDSHIP
    assert hardship_res.slots.get("hardship_type") == "job_loss"


def test_nlu_llm_fallback() -> None:
    fallback_payload = (
        '{"intent": "ask_options", "amount_paise": null, '
        '"sentiment": "neutral", "distress_score": 0.0}'
    )
    mock_llm = MockLLMClient(default_response=fallback_payload)
    nlu = NLU(mock_llm)

    res = nlu.parse("Could you walk me through the relief plans?", Lang.EN)
    assert res.intent == Intent.ASK_OPTIONS
    assert len(mock_llm.calls) == 1
