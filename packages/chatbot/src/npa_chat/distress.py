"""Severe distress detection and support routing for WS4 Chatbot (Task 4.4).

Detects despair, hopelessness, or self-harm keywords across English, Tamil, and Hindi.
Halts all financial recovery dialogue, presents compassionate support, and routes
to India's national mental health helpline Tele-MANAS (14416).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from npa_chat.i18n import get_string
from npa_chat.state import ChatState, ConversationState
from npa_contracts.models import QuickReply

# Severe distress triggers across supported languages
_DISTRESS_TRIGGERS: Final[dict[str, list[str]]] = {
    "en": [
        "suicide",
        "kill myself",
        "end my life",
        "can't live",
        "cannot live",
        "want to die",
        "end it all",
        "hopeless",
        "give up on life",
        "no reason to live",
    ],
    "ta": [
        "தற்கொலை",
        "சாக வேண்டும்",
        "வாழ பிடிக்கவில்லை",
        "உயிரை விட",
        "சாக போறேன்",
        "வாழ வழியில்லை",
    ],
    "hi": [
        "आत्महत्या",
        "जान देना",
        "मर जाना चाहता",
        "जीना नहीं चाहता",
        "जिंदगी खत्म",
        "जान ले लूँगा",
    ],
}


def detect_distress(text: str, distress_score: float = 0.0) -> bool:
    """Check if message expresses severe emotional distress or self-harm."""
    if distress_score >= 0.8:
        return True

    lower = text.lower()
    for lang_triggers in _DISTRESS_TRIGGERS.values():
        for trigger in lang_triggers:
            if trigger in lower:
                return True
    return False


@dataclass
class DistressResult:
    """Outcome of distress handling."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    next_state: ChatState = ChatState.DISTRESS
    flags: list[str] = field(default_factory=lambda: ["distress_detected"])


def handle_distress(
    state: ConversationState,
) -> DistressResult:
    """Construct caring, non-financial support message with Tele-MANAS helpline."""
    lang = state.lang
    state.add_flag("distress_detected")

    distress_msg = get_string("distress_response", lang)
    helpline_msg = get_string("tele_manas_notice", lang)
    reply_text = f"{distress_msg}\n\n{helpline_msg}"

    quick_replies = [
        QuickReply(id="speak_officer", label=get_string("offer_officer_btn", lang)),
    ]

    return DistressResult(
        reply_text=reply_text,
        quick_replies=quick_replies,
        next_state=ChatState.DISTRESS,
        flags=["distress_detected"],
    )
