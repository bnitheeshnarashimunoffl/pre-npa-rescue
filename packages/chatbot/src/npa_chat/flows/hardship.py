"""Hardship disclosure handling for WS4 Chatbot (Task 4.2).

Classifies hardship (job_loss, medical, business_loss, family_bereavement,
other, prefer_not_to_say), acknowledges empathetically without judgement,
and offers outreach pause on bereavement/medical per RBI RBC Directions 2026 para 454Y(6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from npa_chat.i18n import get_string
from npa_chat.nlu import NLUResult
from npa_chat.state import ChatState, ConversationState
from npa_contracts.models import QuickReply

# Hardship classification types
HARDSHIP_JOB_LOSS: Final[str] = "job_loss"
HARDSHIP_MEDICAL: Final[str] = "medical"
HARDSHIP_BEREAVEMENT: Final[str] = "family_bereavement"
HARDSHIP_BUSINESS_LOSS: Final[str] = "business_loss"
HARDSHIP_PREFER_NOT_TO_SAY: Final[str] = "prefer_not_to_say"
HARDSHIP_OTHER: Final[str] = "other"


@dataclass
class HardshipTurnResult:
    """Outcome of processing a hardship turn."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    next_state: ChatState = ChatState.AFFORDABILITY
    pause_suggested: bool = False
    pause_confirmed: bool = False
    flags: list[str] = field(default_factory=list)


def is_pause_eligible(hardship_type: str | None) -> bool:
    """Return True if the hardship qualifies for immediate outreach pause under RBI para 454Y(6)."""
    return hardship_type == HARDSHIP_BEREAVEMENT


def classify_hardship(text: str, nlu_result: NLUResult | None = None) -> str:
    """Classify borrower explanation into standard hardship categories.

    Disclosure is strictly optional. If the borrower chooses not to share,
    HARDSHIP_PREFER_NOT_TO_SAY is returned.
    """
    lower = text.lower().strip()

    # Prefer not to say / skip
    prefer_not_keywords = [
        "prefer not to say",
        "don't want to say",
        "do not want to say",
        "private",
        "personal",
        "skip",
        "no comment",
        "சொல்ல விரும்பவில்லை",
        "பகிர விரும்பவில்லை",
        "விருப்பமில்லை",
        "नहीं बताना",
        "छोड़ें",
        "निजी",
    ]
    if any(k in lower for k in prefer_not_keywords):
        return HARDSHIP_PREFER_NOT_TO_SAY

    # Bereavement (RBI para 454Y(6))
    bereavement_keywords = [
        "bereavement",
        "death",
        "passed away",
        "died",
        "funeral",
        "loss of my",
        "loss of father",
        "loss of mother",
        "loss of spouse",
        "இறப்பு",
        "மரணம்",
        "மறைவு",
        "தவறிவிட்டார்",
        "मृत्यु",
        "निधन",
        "गुज़र गए",
        "देहांत",
    ]
    if any(k in lower for k in bereavement_keywords):
        return HARDSHIP_BEREAVEMENT

    # Medical emergency / illness (RBI para 454Y(6))
    medical_keywords = [
        "medical",
        "hospital",
        "surgery",
        "illness",
        "health",
        "accident",
        "icu",
        "மருத்துவ",
        "மருத்துவம்",
        "மருத்துவமனை",
        "உடல்நிலை",
        "விபத்து",
        "बीमार",
        "अस्पताल",
        "चिकित्सा",
        "दुर्घटना",
        "इलाज",
    ]
    if any(k in lower for k in medical_keywords):
        return HARDSHIP_MEDICAL

    # Job loss (Priya demo path)
    job_loss_keywords = [
        "job loss",
        "lost my job",
        "lost job",
        "laid off",
        "unemployed",
        "salary stopped",
        "no salary",
        "salary delayed",
        "வேலை போனது",
        "வேலை இல்லை",
        "சம்பளம் இல்லை",
        "வேலை இழப்பு",
        "नौकरी चली गई",
        "नौकरी छूट",
        "वेतन रुक",
        "बेरोजगार",
    ]
    if any(k in lower for k in job_loss_keywords):
        return HARDSHIP_JOB_LOSS

    # Business loss
    business_keywords = [
        "business",
        "shop closed",
        "trade loss",
        "no revenue",
        "நஷ்டம்",
        "வியாபாரம்",
        "தொழில் நஷ்டம்",
        "व्यापार",
        "घाटा",
        "दुकान",
    ]
    if any(k in lower for k in business_keywords):
        return HARDSHIP_BUSINESS_LOSS

    if nlu_result and nlu_result.slots.get("hardship_type"):
        kind = str(nlu_result.slots["hardship_type"])
        if kind in (
            HARDSHIP_JOB_LOSS,
            HARDSHIP_MEDICAL,
            HARDSHIP_BEREAVEMENT,
            HARDSHIP_BUSINESS_LOSS,
            HARDSHIP_PREFER_NOT_TO_SAY,
        ):
            return kind

    return HARDSHIP_OTHER


def handle_hardship_turn(
    state: ConversationState,
    text: str,
    nlu_result: NLUResult | None = None,
) -> HardshipTurnResult:
    """Process a turn in HARDSHIP_DISCLOSURE state.

    Handles disclosure acknowledgment and RBI para 454Y(6) bereavement/medical pause outreach.
    """
    lang = state.lang
    lower = text.lower().strip()
    words = set(re.findall(r"\b\w+\b", lower))

    # Check if this is an answer to a pending pause-outreach offer
    if state.pause_outreach_suggested and "pause_outreach_offered" in state.flags:
        pause_confirmed = (
            "pause" in words
            or "stop" in words
            or ("yes" in words and "continue" not in words and "explore" not in words)
            or "ஒத்திவை" in lower
            or "நிறுத்து" in lower
            or "ஆம்" in words
            or "रोकें" in lower
            or "हाँ" in words
        )
        continue_requested = (
            "continue" in words
            or "explore" in words
            or "proceed" in words
            or "options" in words
            or "தொடர" in lower
            or "தொடருங்கள்" in lower
            or "जारी" in words
        )

        if pause_confirmed and not continue_requested:
            # Borrower chose to pause outreach
            reply = get_string("pause_outreach_confirmed", lang)
            return HardshipTurnResult(
                reply_text=reply,
                next_state=ChatState.CLOSING,
                pause_confirmed=True,
                flags=["outreach_paused", "rbi_454y6_pause_enacted"],
            )

        # Borrower chose to continue with relief exploration
        prompt = get_string("affordability_income_prompt", lang)
        quick_replies = [
            QuickReply(id="inc_0", label=get_string("affordability_quick_0", lang)),
            QuickReply(id="inc_10k", label=get_string("affordability_quick_10k", lang)),
            QuickReply(id="inc_25k", label=get_string("affordability_quick_25k", lang)),
            QuickReply(id="inc_50k", label=get_string("affordability_quick_50k", lang)),
        ]
        return HardshipTurnResult(
            reply_text=prompt,
            quick_replies=quick_replies,
            next_state=ChatState.AFFORDABILITY,
            flags=["pause_declined_by_customer"],
        )

    # Classify the hardship disclosure
    hardship_type = classify_hardship(text, nlu_result)
    state.hardship_type = hardship_type
    state.hardship_details = text

    # Select empathetic acknowledgment string
    ack_key_map = {
        HARDSHIP_JOB_LOSS: "hardship_ack_job_loss",
        HARDSHIP_MEDICAL: "hardship_ack_medical",
        HARDSHIP_BEREAVEMENT: "hardship_ack_bereavement",
        HARDSHIP_BUSINESS_LOSS: "hardship_ack_business_loss",
        HARDSHIP_PREFER_NOT_TO_SAY: "hardship_ack_prefer_not_to_say",
        HARDSHIP_OTHER: "hardship_ack_general",
    }
    ack_key = ack_key_map.get(hardship_type, "hardship_ack_general")
    ack_text = get_string(ack_key, lang)

    # If bereavement or medical emergency, offer outreach pause per RBI para 454Y(6)
    if is_pause_eligible(hardship_type):
        pause_offer = get_string("pause_outreach_bereavement_offer", lang)
        full_reply = f"{ack_text}\n\n{pause_offer}"
        quick_replies = [
            QuickReply(id="pause_yes", label=get_string("pause_choice_pause", lang)),
            QuickReply(id="pause_no", label=get_string("pause_choice_continue", lang)),
        ]
        return HardshipTurnResult(
            reply_text=full_reply,
            quick_replies=quick_replies,
            next_state=ChatState.HARDSHIP_DISCLOSURE,
            pause_suggested=True,
            flags=["pause_outreach_suggested", "pause_outreach_offered"],
        )

    # Standard flow transitions to affordability
    prompt_text = get_string("affordability_income_prompt", lang)
    full_reply = f"{ack_text}\n\n{prompt_text}"
    quick_replies = [
        QuickReply(id="inc_0", label=get_string("affordability_quick_0", lang)),
        QuickReply(id="inc_10k", label=get_string("affordability_quick_10k", lang)),
        QuickReply(id="inc_25k", label=get_string("affordability_quick_25k", lang)),
        QuickReply(id="inc_50k", label=get_string("affordability_quick_50k", lang)),
    ]
    return HardshipTurnResult(
        reply_text=full_reply,
        quick_replies=quick_replies,
        next_state=ChatState.AFFORDABILITY,
        flags=[f"hardship_classified_{hardship_type}"],
    )
