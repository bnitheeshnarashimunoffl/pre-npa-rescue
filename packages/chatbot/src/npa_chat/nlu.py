"""Natural Language Understanding (NLU) for WS4 Chatbot.

Extracts intent, slots (with amount parsing to paise), sentiment, and distress detection.
"""

from __future__ import annotations

import json
import logging
import re
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, Field

from npa_chat.language import detect_language_switch_request, detect_script
from npa_contracts.enums import Lang
from npa_contracts.providers import LLMClient

logger = logging.getLogger(__name__)


class Intent(StrEnum):
    """Recognized customer intents."""

    GREET = "greet"
    EXPLAIN_HARDSHIP = "explain_hardship"
    GIVE_INCOME = "give_income"
    GIVE_EXPENSES = "give_expenses"
    GIVE_DEPENDANTS = "give_dependants"
    ASK_OPTIONS = "ask_options"
    ACCEPT_OPTION = "accept_option"
    REJECT_OPTION = "reject_option"
    ASK_HUMAN = "ask_human"
    COMPLAIN = "complain"
    CHANGE_LANGUAGE = "change_language"
    ASK_WHY_CONTACTED = "ask_why_contacted"
    OFF_TOPIC = "off_topic"
    DISTRESS = "distress"


class NLUResult(BaseModel):
    """Structured extraction from a customer message."""

    intent: str
    slots: dict[str, Any] = Field(default_factory=dict)
    lang: Lang = Lang.EN
    sentiment: str = "neutral"
    distress_score: float = Field(ge=0.0, le=1.0, default=0.0)
    raw_text: str = ""


# Severe distress keywords across languages
_DISTRESS_KEYWORDS: Final[list[str]] = [
    # English
    "suicide",
    "kill myself",
    "end my life",
    "can't live",
    "cannot live",
    "no reason to live",
    "want to die",
    "hopeless",
    "can't survive",
    # Tamil
    "தற்கொலை",
    "வாழ வழியில்லை",
    "வாழ பிடிக்கவில்லை",
    "செத்துடலாம்",
    "உயிரை மாய்த்துக்",
    # Hindi
    "आत्महत्या",
    "जान दे दूंगा",
    "जान दे दूंगी",
    "जीने की इच्छा नहीं",
    "जी नहीं सकता",
    "जी नहीं सकती",
    "मरना चाहता",
    "मरना चाहती",
]

# Zero payment capacity keywords across languages
_ZERO_CAPACITY_KEYWORDS: Final[list[str]] = [
    # English
    "cannot pay anything",
    "can't pay anything",
    "cant pay anything",
    "cannot pay even",
    "can't pay even",
    "cant pay even",
    "zero capacity",
    "no money at all",
    "pay 0",
    "0 rupees",
    # Tamil
    "எதுவும் செலுத்த முடியாது",
    "ஒரு ரூபாயும் முடியாது",
    "பணமே இல்லை",
    "கட்ட முடியாது",
    # Hindi
    "कुछ भी नहीं दे सकता",
    "कुछ नहीं दे सकता",
    "एक भी रुपया नहीं",
    "पैसे नहीं हैं",
]

# Multilingual amount parsing constants
_TAMIL_WORD_NUMBERS: Final[dict[str, int]] = {
    "ஆயிரம்": 1_000,
    "இரண்டாயிரம்": 2_000,
    "மூன்றாயிரம்": 3_000,
    "ஐந்தாயிரம்": 5_000,
    "பத்தாயிரம்": 10_000,
    "பதினைந்தாயிரம்": 15_000,
    "இருபதாயிரம்": 20_000,
    "இருபத்தைந்தாயிரம்": 25_000,
    "இலட்சம்": 100_000,
    "லட்சம்": 100_000,
}

_HINDI_WORD_NUMBERS: Final[dict[str, int]] = {
    "हज़ार": 1_000,
    "हजार": 1_000,
    "दो हज़ार": 2_000,
    "दो हजार": 2_000,
    "तीन हज़ार": 3_000,
    "पांच हज़ार": 5_000,
    "दस हज़ार": 10_000,
    "पंद्रह हज़ार": 15_000,
    "पंद्रह हजार": 15_000,
    "बीस हज़ार": 20_000,
    "पच्चीस हज़ार": 25_000,
    "लाख": 100_000,
}


def parse_amount_paise(text: str) -> int | None:
    """Parse monetary amount in free text across en/ta/hi into paise (int)."""
    cleaned = text.strip().lower()

    # Zero mentions
    if any(z in cleaned for z in ["zero", "nothing", "0", "பூஜ்ஜியம்", "शून्य"]) and re.search(
        r"\b(0|zero|nothing|பூஜ்ஜியம்|शून्य)\b", cleaned
    ):
        return 0

    # Tamil word amounts (sorted by length descending so longer phrases match first)
    sorted_tamil = sorted(_TAMIL_WORD_NUMBERS.items(), key=lambda x: len(x[0]), reverse=True)
    for word, rupee_val in sorted_tamil:
        if word in text:
            # Check for prefix multiplier e.g. "2 லட்சம்"
            m = re.search(r"(\d+(?:\.\d+)?)\s*" + re.escape(word), text)
            if m:
                return int(float(m.group(1)) * rupee_val * 100)
            return rupee_val * 100

    # Hindi word amounts (sorted by length descending so longer phrases match first)
    sorted_hindi = sorted(_HINDI_WORD_NUMBERS.items(), key=lambda x: len(x[0]), reverse=True)
    for word, rupee_val in sorted_hindi:
        if word in text:
            m = re.search(r"(\d+(?:\.\d+)?)\s*" + re.escape(word), text)
            if m:
                return int(float(m.group(1)) * rupee_val * 100)
            return rupee_val * 100

    # "15k", "20k", "2.5k" notation
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", cleaned)
    if k_match:
        return int(float(k_match.group(1)) * 1_000 * 100)

    # "1.5 lakh", "2 lakh", "2 lac" notation
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|lacs)\b", cleaned)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100_000 * 100)

    # Standard numeric pattern: e.g. ₹2,000, Rs. 15000, 2500
    num_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{3})+|\d+)", cleaned)
    if num_match:
        val_str = num_match.group(1).replace(",", "")
        try:
            return int(val_str) * 100
        except ValueError:
            return None

    return None


class NLU:
    """NLU parsing service with fast heuristics and LLM fallback."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def parse(self, text: str, current_lang: Lang = Lang.EN) -> NLUResult:
        cleaned = text.strip()
        lower = cleaned.lower()
        detected_lang = detect_script(cleaned) or current_lang

        # 1. Distress detection (highest priority)
        for keyword in _DISTRESS_KEYWORDS:
            if keyword in lower:
                return NLUResult(
                    intent=Intent.DISTRESS,
                    lang=detected_lang,
                    sentiment="distressed",
                    distress_score=1.0,
                    raw_text=text,
                )

        # 2. Language switch detection
        switch_target = detect_language_switch_request(text)
        if switch_target:
            return NLUResult(
                intent=Intent.CHANGE_LANGUAGE,
                slots={"target_lang": switch_target},
                lang=switch_target,
                raw_text=text,
            )

        # 3. Complaint detection
        if any(
            w in lower
            for w in [
                "complain",
                "complaint",
                "harass",
                "threat",
                "abuse",
                "abusive",
                "wrong charge",
                "illegal charge",
                "dpdp violation",
                "புகார்",
                "துன்புறுத்தல்",
                "அச்சுறுத்தல்",
                "शिकायत",
                "प्रताड़ना",
                "धमकी",
            ]
        ):
            return NLUResult(
                intent=Intent.COMPLAIN,
                lang=detected_lang,
                sentiment="frustrated",
                raw_text=text,
            )

        # 4. Human officer request
        if any(
            w in lower
            for w in [
                "human",
                "agent",
                "officer",
                "talk to someone",
                "person",
                "அதிகாரி",
                "மனிதர்",
                "நேரில் பேச",
                "अधिकारी",
                "बात करनी है",
                "एजेंट",
            ]
        ):
            return NLUResult(
                intent=Intent.ASK_HUMAN,
                lang=detected_lang,
                raw_text=text,
            )

        # 5. Why contacted inquiry
        if any(
            w in lower
            for w in [
                "why contacted",
                "why are you calling",
                "why messaging",
                "reason for contact",
                "ஏன் தொடர்பு",
                "ஏன் அழைக்கிறீர்கள்",
                "क्यों संपर्क",
                "क्यों कॉल",
            ]
        ):
            return NLUResult(
                intent=Intent.ASK_WHY_CONTACTED,
                lang=detected_lang,
                raw_text=text,
            )

        # 6. Offer acceptance / rejection
        accept_words = ["accept", "agree", "take this", "ஏற்றுக்கொள்கிறேன்", "சரி", "स्वीकार", "मंजूर"]
        if any(w in lower for w in accept_words):
            return NLUResult(
                intent=Intent.ACCEPT_OPTION,
                lang=detected_lang,
                raw_text=text,
            )
        reject_words = [
            "reject",
            "decline",
            "don't want",
            "வேண்டாம்",
            "நிராகரி",
            "अस्वीकार",
            "नहीं चाहिए",
        ]
        if any(w in lower for w in reject_words):
            return NLUResult(
                intent=Intent.REJECT_OPTION,
                lang=detected_lang,
                raw_text=text,
            )

        # 7. Zero capacity detection
        if any(keyword in lower for keyword in _ZERO_CAPACITY_KEYWORDS):
            return NLUResult(
                intent=Intent.GIVE_INCOME,
                slots={"amount_paise": 0, "zero_capacity": True},
                lang=detected_lang,
                raw_text=text,
            )

        # 8. Amount parsing for income / expenses
        parsed_paise = parse_amount_paise(cleaned)
        if parsed_paise is not None:
            return NLUResult(
                intent=Intent.GIVE_INCOME,
                slots={"amount_paise": parsed_paise},
                lang=detected_lang,
                raw_text=text,
            )

        # 9. Hardship explanation keywords
        if any(
            w in lower
            for w in [
                "job loss",
                "lost my job",
                "medical",
                "hospital",
                "health",
                "business loss",
                "வேலை போனது",
                "வேலை இல்லை",
                "மருத்துவம்",
                "உடல்நிலை",
                "நஷ்டம்",
                "नौकरी चली गई",
                "नौकरी छूट",
                "बीमार",
                "अस्पताल",
                "व्यापार में नुकसान",
            ]
        ):
            hardship_kind = "other"
            if any(k in lower for k in ["job", "வேலை", "नौकरी"]):
                hardship_kind = "job_loss"
            elif any(k in lower for k in ["medical", "hospital", "மருத்துவம்", "बीमार"]):
                hardship_kind = "medical"
            elif any(k in lower for k in ["business", "நஷ்டம்", "व्यापार"]):
                hardship_kind = "business_loss"
            elif any(k in lower for k in ["bereavement", "death", "இறப்பு", "मृत्यु"]):
                hardship_kind = "family_bereavement"

            return NLUResult(
                intent=Intent.EXPLAIN_HARDSHIP,
                slots={"hardship_type": hardship_kind},
                lang=detected_lang,
                raw_text=text,
            )

        # 10. Greetings
        if any(w in lower for w in ["hi", "hello", "hey", "வணக்கம்", "नमस्ते", "start"]):
            return NLUResult(
                intent=Intent.GREET,
                lang=detected_lang,
                raw_text=text,
            )

        # LLM fallback with structured schema if available
        try:
            return self._llm_fallback_parse(text, detected_lang)
        except Exception as err:
            logger.warning("LLM fallback NLU failed: %s", err)
            return NLUResult(
                intent=Intent.OFF_TOPIC,
                lang=detected_lang,
                raw_text=text,
            )

    def _llm_fallback_parse(self, text: str, lang: Lang) -> NLUResult:
        schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": [i.value for i in Intent]},
                "amount_paise": {"type": ["integer", "null"]},
                "sentiment": {"type": "string"},
                "distress_score": {"type": "number"},
            },
            "required": ["intent", "distress_score"],
        }
        raw_json = self.llm_client.complete(
            system=(
                "You are an NLU parser for a bank hardship chatbot. "
                "Classify intent and slots accurately."
            ),
            messages=[{"role": "user", "content": text}],
            json_schema=schema,
        )
        parsed = json.loads(raw_json)
        intent = parsed.get("intent", Intent.OFF_TOPIC)
        slots: dict[str, Any] = {}
        if parsed.get("amount_paise") is not None:
            slots["amount_paise"] = parsed["amount_paise"]

        return NLUResult(
            intent=intent,
            slots=slots,
            lang=lang,
            sentiment=parsed.get("sentiment", "neutral"),
            distress_score=float(parsed.get("distress_score", 0.0)),
            raw_text=text,
        )
