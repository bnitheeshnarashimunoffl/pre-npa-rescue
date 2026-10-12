"""Complaint capture and grievance redressal per IS/ISO 10002:2018 and RBI RBC Directions 2026.

Handles global complaint interrupts, category classification (harassment, wrong charges,
privacy/DPDP, service, other), priority harassment escalation, 30-day SLA enforcement,
RBI Ombudsman escalation guidance (cms.rbi.org.in / 14448), and Grievance Officer details.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from npa_chat.i18n import get_string
from npa_chat.state import ChatState, ConversationState
from npa_contracts.models import GrievanceOfficer, QuickReply
from npa_contracts.providers import ComplaintSink, PolicyProvider

logger = logging.getLogger(__name__)


class ComplaintCategory(StrEnum):
    """Complaint categories per IS/ISO 10002:2018 and RBI RBC Directions 2026."""

    HARASSMENT = "harassment"
    WRONG_CHARGES = "wrong_charges"
    PRIVACY = "privacy"
    SERVICE = "service"
    OTHER = "other"


# Keywords for classification across English, Tamil, and Hindi
_HARASSMENT_KEYWORDS: Final[list[str]] = [
    # English
    "harass",
    "threat",
    "threaten",
    "abuse",
    "abusive",
    "rude",
    "yelling",
    "shouting",
    "odd hours",
    "night call",
    "unreasonable hour",
    "family",
    "relatives",
    "employer",
    "workplace",
    "intimidat",
    "calling repeatedly",
    # Tamil
    "துன்புறுத்த",
    "அச்சுறுத்த",
    "மிரட்ட",
    "தவறான நடத்தை",
    "திட்டுகிறார்",
    "இரவு அழைப்பு",
    "குடும்பத்தினரிடம்",
    # Hindi
    "प्रताड़ना",
    "धमकी",
    "धमकाना",
    "गाली",
    "अनुचित व्यवहार",
    "डराना",
    "परेशान करना",
    "रात में कॉल",
    "परिवार को कॉल",
]

_WRONG_CHARGES_KEYWORDS: Final[list[str]] = [
    # English
    "wrong charge",
    "incorrect charge",
    "extra charge",
    "unexpected charge",
    "penalty",
    "penalties",
    "hidden fee",
    "excess interest",
    "unauthorized fee",
    "overcharged",
    "overcharge",
    "wrong fee",
    "charges",
    "fees",
    # Tamil
    "தவறான கட்டணம்",
    "கட்டணம்",
    "அபராதம்",
    "அதிக வட்டி",
    "கூடுதல் கட்டணம்",
    # Hindi
    "गलत चार्ज",
    "जुर्माना",
    "अतिरिक्त ब्याज",
    "अवैध शुल्क",
    "ज्यादा चार्ज",
    "चार्ज",
]

_PRIVACY_KEYWORDS: Final[list[str]] = [
    # English
    "privacy",
    "dpdp",
    "data breach",
    "data protection",
    "leak",
    "unauthorized access",
    "shared my data",
    "confidentiality",
    # Tamil
    "தனிஉரிமை",
    "தரவு பாதுகாப்பு",
    "ரகசியத்தன்மை",
    # Hindi
    "गोपनीयता",
    "डेटा सुरक्षा",
    "डेटा लीक",
    "व्यक्तिगत जानकारी",
]

_SERVICE_KEYWORDS: Final[list[str]] = [
    # English
    "delay",
    "no response",
    "poor service",
    "waiting",
    "bad service",
    "unhelpful",
    "rude staff",
    # Tamil
    "தாமதம்",
    "மோசமான சேவை",
    "பதில் இல்லை",
    # Hindi
    "देरी",
    "खराब सेवा",
    "कोई जवाब नहीं",
    "सेवा में कमी",
]


def classify_complaint_category(text: str) -> tuple[ComplaintCategory, bool]:
    """Classify complaint text into category and determine if harassment is reported."""
    lower = text.lower()

    # Priority 1: Harassment
    if any(kw in lower for kw in _HARASSMENT_KEYWORDS):
        return ComplaintCategory.HARASSMENT, True

    # Priority 2: Privacy / DPDP
    if any(kw in lower for kw in _PRIVACY_KEYWORDS):
        return ComplaintCategory.PRIVACY, False

    # Priority 3: Wrong charges / penalties
    if any(kw in lower for kw in _WRONG_CHARGES_KEYWORDS):
        return ComplaintCategory.WRONG_CHARGES, False

    # Priority 4: Service issues
    if any(kw in lower for kw in _SERVICE_KEYWORDS):
        return ComplaintCategory.SERVICE, False

    return ComplaintCategory.OTHER, False


@dataclass
class ComplaintTurnResult:
    """Structured outcome of complaint handling."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    docket_no: str = ""
    category: ComplaintCategory = ComplaintCategory.OTHER
    is_harassment: bool = False
    flags: list[str] = field(default_factory=list)
    next_state: ChatState = ChatState.COMPLAINT


def handle_complaint_turn(
    state: ConversationState,
    text: str,
    complaint_sink: ComplaintSink,
    policy_provider: PolicyProvider,
) -> ComplaintTurnResult:
    """Handle a complaint interrupt or complaint turn.

    Registers a docket with ComplaintSink, explains 30-day SLA per IS/ISO 10002:2018
    and RBI RBC Directions 2026, details Ombudsman escalation rights, and appends
    Grievance Redressal Officer contact information.
    """
    category, is_harassment = classify_complaint_category(text)

    # Register the formal complaint
    complaint = complaint_sink.open(
        customer_id=state.customer_id,
        category=category.value,
        text=text,
        lang=state.lang,
    )

    state.complaint_docket_no = complaint.docket_no
    state.add_flag("complaint_reported")
    flags = ["complaint_reported"]
    if is_harassment:
        state.add_flag("harassment_reported")
        flags.append("harassment_reported")

    # Grievance officer details
    grievance: GrievanceOfficer = policy_provider.grievance_officer()

    footer = get_string(
        "grievance_footer",
        state.lang,
        name=grievance.name,
        email=grievance.email,
        phone=grievance.phone,
        address=grievance.address,
    )

    # Localized category name
    cat_key = f"complaint_cat_{category.value}"
    category_label = get_string(cat_key, state.lang)

    # Build response message
    main_msg = get_string(
        "complaint_registered_msg",
        state.lang,
        docket_no=complaint.docket_no,
        category=category_label,
    )

    parts: list[str] = [main_msg]

    if is_harassment:
        harass_note = get_string("complaint_harassment_note", state.lang)
        parts.append(harass_note)

    parts.append(footer)

    reply_text = "\n\n".join(parts)

    quick_replies = [
        QuickReply(
            id="complaint_continue",
            label=get_string("complaint_btn_continue", state.lang),
        ),
        QuickReply(
            id="complaint_officer",
            label=get_string("complaint_btn_officer", state.lang),
        ),
    ]

    return ComplaintTurnResult(
        reply_text=reply_text,
        quick_replies=quick_replies,
        docket_no=complaint.docket_no,
        category=category,
        is_harassment=is_harassment,
        flags=flags,
        next_state=ChatState.COMPLAINT,
    )
