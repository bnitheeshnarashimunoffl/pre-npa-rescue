"""Plan offer presentation and acceptance flow for WS4 Chatbot (Task 4.3).

Fetches permitted relief options from PolicyProvider, formats truthful summaries
and mandatory disclosures, and orchestrates plan acceptance per RBI regulations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from npa_chat.i18n import get_string
from npa_chat.nlu import Intent, NLUResult
from npa_chat.state import ChatState, ConversationState
from npa_contracts.constants import AS_OF_MONTH
from npa_contracts.enums import Actor, Lang, OfferStatus, ReliefType
from npa_contracts.models import Affordability, Offer, QuickReply, ReliefOption
from npa_contracts.money import format_inr
from npa_contracts.providers import PolicyProvider, RiskProvider

# Truthful regulatory & policy disclosures mapped by key suffix (supporting disc.* and disclosure.*)
_DISCLOSURES: Final[dict[str, dict[Lang, str]]] = {
    "emi_conversion.interest_breakdown": {
        Lang.EN: (
            "Interest is charged transparently on reducing balance; unpaid charges are never "
            "capitalised (RBI Credit Card Directions 2025)."
        ),
        Lang.TA: (
            "வட்டி குறைந்துவரும் நிலுவைத்தொகையின் மீது வெளிப்படையாக கணக்கிடப்படுகிறது; "
            "வட்டிக்கு வட்டி விதிக்கப்படாது (RBI Credit Card Directions 2025)."
        ),
        Lang.HI: (
            "ब्याज घटती शेष राशि पर पारदर्शी रूप से लगाया जाता है; "
            "ब्याज का पूंजीकरण नहीं किया जाएगा (RBI Credit Card Directions 2025)।"
        ),
    },
    "fee_waiver.scope": {
        Lang.EN: (
            "Late fees and penal charges waived under board-approved policy; regular principal "
            "and future instalments remain payable."
        ),
        Lang.TA: (
            "வங்கியின் கொள்கைப்படி தாமதக் கட்டணம் தள்ளுபடி செய்யப்படுகிறது; "
            "அசல் மற்றும் வழக்கமான மாதத் தவணை செலுத்தப்பட வேண்டும்."
        ),
        Lang.HI: (
            "बोर्ड-अनुमोदित नीति के तहत विलंब शुल्क माफ किया जाता है; मूलधन और भविष्य की किश्तें देय रहेंगी।"
        ),
    },
    "missed_instalment.consequence": {
        Lang.EN: (
            "If an EMI instalment is missed, standard recovery procedures resume "
            "and late charges may apply."
        ),
        Lang.TA: ("மாதத் தவணை தவறினால், வழக்கமான மீட்பு நடைமுறை தொடரும் மற்றும் தாமதக் கட்டணங்கள் பொருந்தலாம்."),
        Lang.HI: (
            "यदि कोई ईएमआई किस्त छूट जाती है, तो मानक प्रक्रिया पुनः आरंभ होगी और विलंब शुल्क लग सकता है।"
        ),
    },
    "restructuring.npa_downgrade": {
        Lang.EN: (
            "Under RBI Prudential Framework (2019), restructured standard accounts are downgraded "
            "to NPA and reported to credit bureaus."
        ),
        Lang.TA: (
            "ரிசர்வ் வங்கி ஒழுங்குமுறை கட்டமைப்பு (2019) படி, கடன் மாற்றியமைக்கப்பட்டால் "
            "கணக்கு NPA ஆக தரமிறக்கப்படும் மற்றும் கிரெடிட் பீரோவில் பதிவாகும்."
        ),
        Lang.HI: (
            "आरबीआई प्रूडेंशियल फ्रेमवर्क (2019) के तहत, पुनर्गठित खातों को एनपीए में डाउनग्रेड "
            "किया जाता है और यह क्रेडिट ब्यूरो को रिपोर्ट किया जाएगा।"
        ),
    },
    "settlement.cooling_period": {
        Lang.EN: (
            "Under RBI Compromise Settlements Framework (2023), compromise settlements carry a "
            "minimum 12-month cooling period before new credit can be granted."
        ),
        Lang.TA: (
            "ரிசர்வ் வங்கி சமரசத் தீர்வு கட்டமைப்பு (2023) படி, சமரசத் தீர்வை ஏற்றுக்கொண்டால் "
            "புதிய கடன் பெற குறைந்தபட்சம் 12 மாத கால அவகாசம் பொருந்தும்."
        ),
        Lang.HI: (
            "आरबीआई समझौता निपटान फ्रेमवर्क (2023) के तहत, समझौता स्वीकार करने पर नया ऋण मिलने "
            "से पहले कम से कम 12 महीने की कूलिंग अवधि होगी।"
        ),
    },
}


def render_disclosure(key: str, lang: Lang) -> str:
    """Render compliant disclosure text by key (supports disc.* and disclosure.* prefixes)."""
    # Normalize key by stripping prefix
    normalized = key
    if normalized.startswith("disclosure."):
        normalized = normalized[len("disclosure.") :]
    elif normalized.startswith("disc."):
        normalized = normalized[len("disc.") :]

    entry = _DISCLOSURES.get(normalized)
    if entry:
        return entry.get(lang, entry[Lang.EN])

    # Dynamic fallback if an unmapped disclosure key appears
    return f"[Disclosure: {key}]"


def format_option_summary(option: ReliefOption, lang: Lang, index: int = 1) -> str:
    """Format clear, honest summary of a ReliefOption object in the requested language."""
    if option.type in (ReliefType.EMI_CONVERSION, "emi_conversion"):
        amount_str = format_inr(option.monthly_amount_paise) if option.monthly_amount_paise else ""
        tenure = option.tenure_months or 0
        if option.waiver_paise:
            waiver_str = format_inr(option.waiver_paise)
            summary = get_string(
                "offer_item_emi_waiver",
                lang,
                index=index,
                amount=amount_str,
                tenure=tenure,
                waiver=waiver_str,
            )
        else:
            summary = get_string(
                "offer_item_emi",
                lang,
                index=index,
                amount=amount_str,
                tenure=tenure,
            )
    elif option.type in (ReliefType.FEE_WAIVER, "fee_waiver"):
        waiver_str = format_inr(option.waiver_paise) if option.waiver_paise else ""
        summary = get_string("offer_item_fee_waiver", lang, index=index, waiver=waiver_str)
    else:
        # Fallback for restructuring or settlement
        summary = f"Plan {index}: {option.type} ({option.eligibility_reason})"

    if option.requires_human_approval:
        human_note = get_string("offer_item_human_review", lang)
        summary = f"{summary} {human_note}"

    return summary


@dataclass
class OfferTurnResult:
    """Outcome of processing an offer turn."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    next_state: ChatState = ChatState.OPTIONS
    offers: list[Offer] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def present_relief_options(
    customer_id: str,
    account_id: str,
    affordability: Affordability,
    policy_provider: PolicyProvider,
    lang: Lang,
) -> tuple[str, list[Offer], list[QuickReply]]:
    """Fetch relief options from PolicyProvider and construct truthful presentation."""
    raw_options = policy_provider.relief_options(customer_id, affordability)
    # Present at most 3 options
    selected_options = raw_options[:3]

    offers: list[Offer] = []
    now = datetime.now(UTC)
    lines: list[str] = [get_string("offer_intro", lang)]

    for idx, opt in enumerate(selected_options, start=1):
        offer_id = f"OFFER-{uuid.uuid4()}"
        offer = Offer(
            offer_id=offer_id,
            customer_id=customer_id,
            account_id=account_id,
            option=opt,
            status=(
                OfferStatus.PRESENTED if not opt.requires_human_approval else OfferStatus.PROPOSED
            ),
            proposed_by=Actor.BOT,
            approved_by=None,
            created_at=now,
            expires_at=now + timedelta(days=7),
        )
        offers.append(offer)

        opt_summary = format_option_summary(opt, lang, index=idx)
        lines.append(f"\n• {opt_summary}")

        # Render each disclosure key attached to the option
        for disc_key in opt.disclosure_keys:
            disc_text = render_disclosure(disc_key, lang)
            lines.append(f"   ℹ️ {disc_text}")

    full_text = "\n".join(lines)
    quick_replies = [
        QuickReply(id="accept_offer", label=get_string("offer_accept_btn", lang)),
        QuickReply(id="reject_offer", label=get_string("offer_reject_btn", lang)),
        QuickReply(id="speak_officer", label=get_string("offer_officer_btn", lang)),
    ]

    return full_text, offers, quick_replies


def handle_why_contacted(
    account_id: str,
    risk_provider: RiskProvider | None,
    lang: Lang,
) -> str:
    """Explain why the cardholder was contacted using RiskScore reason codes."""
    if not risk_provider:
        return get_string("why_contacted_intro", lang)

    try:
        risk = risk_provider.risk(account_id, AS_OF_MONTH)
        reasons = risk.reasons
    except Exception:
        reasons = []

    lines = [get_string("why_contacted_intro", lang)]
    for idx, r in enumerate(reasons, start=1):
        text = r.text.get(lang, r.text.get(Lang.EN, r.code))
        lines.append(f"{idx}. {text}")

    lines.append(f"\n{get_string('why_contacted_outro', lang)}")
    return "\n".join(lines)


def handle_offer_turn(
    state: ConversationState,
    text: str,
    nlu_result: NLUResult | None,
    policy_provider: PolicyProvider,
    risk_provider: RiskProvider | None = None,
) -> OfferTurnResult:
    """Process customer response in the OPTIONS state."""
    lang = state.lang
    lower = text.lower().strip()

    # 1. Why contacted query
    if (
        (nlu_result and nlu_result.intent == Intent.ASK_WHY_CONTACTED)
        or "why" in lower
        or "reason" in lower
        or "ஏன்" in lower
        or "क्यों" in lower
    ):
        acct_id = (
            str(state.history[0].get("account_id", state.customer_id))
            if state.history
            else state.customer_id
        )
        explanation = handle_why_contacted(
            account_id=acct_id,
            risk_provider=risk_provider,
            lang=lang,
        )
        quick_replies = [
            QuickReply(id="accept_offer", label=get_string("offer_accept_btn", lang)),
            QuickReply(id="reject_offer", label=get_string("offer_reject_btn", lang)),
            QuickReply(id="speak_officer", label=get_string("offer_officer_btn", lang)),
        ]
        return OfferTurnResult(
            reply_text=explanation,
            quick_replies=quick_replies,
            next_state=ChatState.OPTIONS,
            offers=state.presented_offers,
            flags=["why_contacted_explained"],
        )

    # 2. Offer Acceptance
    accept_triggers = [
        "accept",
        "accept_offer",
        "agree",
        "yes",
        "take this",
        "ஏற்றுக்கொள்கிறேன்",
        "சரி",
        "स्वीकार",
        "मंजूर",
    ]
    is_accept = (nlu_result and nlu_result.intent == Intent.ACCEPT_OPTION) or any(
        t in lower for t in accept_triggers
    )
    if is_accept:
        # Pick first presented offer or fallback
        chosen_offer = state.presented_offers[0] if state.presented_offers else None
        if chosen_offer:
            state.selected_offer_id = chosen_offer.offer_id
            chosen_offer.status = OfferStatus.ACCEPTED
            # Formal proposal through PolicyProvider
            policy_provider.propose_offer(
                state.customer_id, chosen_offer.option.option_id, Actor.BOT
            )
            opt = chosen_offer.option
            amount_str = format_inr(opt.monthly_amount_paise) if opt.monthly_amount_paise else "₹0"
            tenure_str = f"{opt.tenure_months} months" if opt.tenure_months else ""
            plan_summary = f"{amount_str}/month for {tenure_str}" if tenure_str else amount_str
        else:
            plan_summary = "Custom plan"
            amount_str = "₹2,000"

        due_date = (datetime.now(UTC) + timedelta(days=30)).strftime("%d-%m-%Y")
        confirm_body = get_string(
            "offer_accepted_confirm",
            lang,
            plan_summary=plan_summary,
            amount=amount_str,
            due_date=due_date,
        )

        grievance = policy_provider.grievance_officer()
        footer = get_string(
            "grievance_footer",
            lang,
            name=grievance.name,
            email=grievance.email,
            phone=grievance.phone,
            address=grievance.address,
        )
        full_confirm = f"{confirm_body}\n\n{footer}"

        return OfferTurnResult(
            reply_text=full_confirm,
            next_state=ChatState.ACCEPTED,
            offers=state.presented_offers,
            flags=["offer_accepted", "rbi_454aa_grievance_attached"],
        )

    # 3. Offer Rejection
    reject_triggers = [
        "reject",
        "reject_offer",
        "decline",
        "no",
        "don't want",
        "வேண்டாம்",
        "நிராகரி",
        "அதிகாரியுடன்",
        "अस्वीकार",
        "नहीं चाहिए",
    ]
    is_reject = (nlu_result and nlu_result.intent == Intent.REJECT_OPTION) or any(
        t in lower for t in reject_triggers
    )
    if is_reject:
        reject_reply = get_string("offer_rejected_response", lang)
        quick_replies = [
            QuickReply(id="speak_officer", label=get_string("offer_officer_btn", lang)),
            QuickReply(id="accept_offer", label=get_string("offer_accept_btn", lang)),
        ]
        return OfferTurnResult(
            reply_text=reject_reply,
            quick_replies=quick_replies,
            next_state=ChatState.OPTIONS,
            offers=state.presented_offers,
            flags=["offer_rejected"],
        )

    # Fallback in options state
    reply_text = get_string("fallback_safe", lang)
    return OfferTurnResult(
        reply_text=reply_text,
        next_state=ChatState.OPTIONS,
        offers=state.presented_offers,
    )
