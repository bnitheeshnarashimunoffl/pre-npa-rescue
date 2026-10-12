"""Zero-capacity path, insurance referral, and hardship officer callback booking (Task 4.4).

Implements the blueprint for cardholders who cannot make payments:
1. Stop the ask immediately — no counter-offers or pressure.
2. Acknowledge zero capacity and record disclosure.
3. Check card insurance cover (from context); present insurance referral first.
4. Present approved zero-capacity option set with truthful disclosures.
5. Fetch available slots from CallbackScheduler and book callback so the
   cardholder tells their story only once.
6. Close with the Grievance Officer details footer per RBI para 454AA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from npa_chat.flows.offer import format_option_summary, render_disclosure
from npa_chat.i18n import get_string
from npa_chat.nlu import NLUResult
from npa_chat.state import ChatState, ConversationState
from npa_contracts.enums import Actor, OfferStatus, Role
from npa_contracts.models import Affordability, Offer, QuickReply
from npa_contracts.providers import CallbackScheduler, PolicyProvider

_ZERO_AFFORDABILITY = Affordability(
    customer_id="",
    declared_income_paise=0,
    declared_expenses_paise=0,
    dependants=0,
    max_monthly_payment_paise=0,
    source="declared",
)


@dataclass
class ZeroCapacityResult:
    """Outcome of processing a turn in the zero-capacity flow."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    next_state: ChatState = ChatState.ZERO_CAPACITY
    flags: list[str] = field(default_factory=list)


def format_slot_label(start_dt: datetime, end_dt: datetime) -> str:
    """Format slot start and end time in a human-friendly format (e.g. 11:00 AM - 11:30 AM)."""
    return f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"


def present_zero_capacity_options(
    state: ConversationState,
    customer_context: dict[str, Any],
    policy_provider: PolicyProvider,
    callback_scheduler: CallbackScheduler,
) -> ZeroCapacityResult:
    """Construct initial zero-capacity response stopping payment asks and offering slots."""
    lang = state.lang
    customer_id = state.customer_id
    flags: list[str] = ["zero_capacity_acknowledged"]

    lines: list[str] = [get_string("zero_capacity_stop_ask", lang)]

    # 1. Insurance cover check (Ravi demo feature)
    has_insurance = bool(customer_context.get("has_card_insurance", False))
    if has_insurance:
        cover_type = str(customer_context.get("insurance_cover_type", "credit shield"))
        ins_msg = get_string("insurance_cover_referral", lang, cover_type=cover_type)
        lines.append(f"\n🛡️ {ins_msg}")
        flags.append("insurance_cover_referred")

    # 2. Present zero-capacity relief options from PolicyProvider
    aff = Affordability(
        customer_id=customer_id,
        declared_income_paise=state.declared_income_paise or 0,
        declared_expenses_paise=state.declared_expenses_paise or 0,
        dependants=state.dependants,
        max_monthly_payment_paise=0,
        source="declared",
    )
    raw_options = policy_provider.relief_options(customer_id, aff)
    if raw_options:
        lines.append(f"\n{get_string('zero_capacity_options_intro', lang)}")
        for idx, opt in enumerate(raw_options[:2], start=1):
            summary = format_option_summary(opt, lang, index=idx)
            lines.append(f"• {summary}")
            for disc_key in opt.disclosure_keys:
                disc_text = render_disclosure(disc_key, lang)
                lines.append(f"   ℹ️ {disc_text}")

            offer = Offer(
                offer_id=f"OFFER-ZC-{opt.option_id}",
                customer_id=customer_id,
                account_id=str(customer_context.get("account_id", customer_id)),
                option=opt,
                status=(
                    OfferStatus.PROPOSED if opt.requires_human_approval else OfferStatus.PRESENTED
                ),
                proposed_by=Actor.BOT,
                approved_by=None,
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC),
            )
            state.presented_offers.append(offer)

    # 3. Available callback slots (08:00 - 19:00 IST)
    today = datetime.now(UTC).date()
    slots = callback_scheduler.available_slots(customer_id, today)

    lines.append(f"\n{get_string('callback_slot_prompt', lang)}")
    quick_replies: list[QuickReply] = []
    for s_start, s_end in slots[:3]:
        label = format_slot_label(s_start, s_end)
        slot_id = f"slot_{s_start.strftime('%H_%M')}"
        quick_replies.append(QuickReply(id=slot_id, label=label))

    return ZeroCapacityResult(
        reply_text="\n".join(lines),
        quick_replies=quick_replies,
        next_state=ChatState.ZERO_CAPACITY,
        flags=flags,
    )


def handle_zero_capacity_turn(
    state: ConversationState,
    text: str,
    nlu_result: NLUResult | None,
    customer_context: dict[str, Any],
    policy_provider: PolicyProvider,
    callback_scheduler: CallbackScheduler,
) -> ZeroCapacityResult:
    """Process customer selection of callback slot or follow-up question."""
    lang = state.lang
    lower = text.lower().strip()
    customer_id = state.customer_id

    today = datetime.now(UTC).date()
    available_slots = callback_scheduler.available_slots(customer_id, today)

    # Check for slot selection (e.g. "11:00", "11", "slot_11_00", "3:00", "15:00")
    chosen_slot: tuple[datetime, datetime] | None = None

    if "11" in lower or "11_00" in lower or "slot_1" in lower:
        for s_start, s_end in available_slots:
            if s_start.hour == 11:
                chosen_slot = (s_start, s_end)
                break
    elif "15" in lower or "3" in lower or "03:00" in lower or "slot_2" in lower:
        for s_start, s_end in available_slots:
            if s_start.hour in (15, 3):
                chosen_slot = (s_start, s_end)
                break

    # If user selected an available slot or requested booking
    if (
        chosen_slot is None
        and available_slots
        and any(k in lower for k in ["book", "yes", "okay", "call me"])
    ):
        chosen_slot = available_slots[0]

    if chosen_slot:
        slot_start, _ = chosen_slot
        summary = (
            f"Customer declared zero repayment capacity. "
            f"Hardship: {state.hardship_type or 'unspecified'}. "
            f"Dependants: {state.dependants or 0}. "
            f"Card insurance referral noted: {customer_context.get('has_card_insurance', False)}."
        )

        callback = callback_scheduler.book(
            customer_id=customer_id,
            slot_start=slot_start,
            role=Role.HARDSHIP_OFFICER,
            summary=summary,
        )
        state.booked_callback_id = callback.callback_id

        date_str = slot_start.strftime("%d-%m-%Y")
        time_str = slot_start.strftime("%I:%M %p")
        confirm_text = get_string(
            "callback_booked_confirm",
            lang,
            time=time_str,
            date=date_str,
            callback_id=callback.callback_id,
        )

        # Append Grievance Officer details (RBI para 454AA)
        grievance = policy_provider.grievance_officer()
        footer = get_string(
            "grievance_footer",
            lang,
            name=grievance.name,
            email=grievance.email,
            phone=grievance.phone,
            address=grievance.address,
        )
        full_reply = f"{confirm_text}\n\n{footer}"

        return ZeroCapacityResult(
            reply_text=full_reply,
            quick_replies=[],
            next_state=ChatState.HANDOFF,
            flags=["callback_booked", "rbi_454aa_grievance_attached"],
        )

    # If customer says they prefer insurance referral
    if "insurance" in lower or "claim" in lower:
        ins_reply = (
            "We have recorded your interest in an insurance claim referral. "
            "Our hardship officer will verify the policy documentation during your callback."
        )
        quick_replies = [
            QuickReply(
                id=f"slot_{s_start.strftime('%H_%M')}", label=format_slot_label(s_start, s_end)
            )
            for s_start, s_end in available_slots[:3]
        ]
        return ZeroCapacityResult(
            reply_text=ins_reply,
            quick_replies=quick_replies,
            next_state=ChatState.ZERO_CAPACITY,
            flags=["insurance_interest_logged"],
        )

    # Fallback in zero capacity state
    fallback_text = get_string("callback_slot_prompt", lang)
    quick_replies = [
        QuickReply(id=f"slot_{s_start.strftime('%H_%M')}", label=format_slot_label(s_start, s_end))
        for s_start, s_end in available_slots[:3]
    ]
    return ZeroCapacityResult(
        reply_text=fallback_text,
        quick_replies=quick_replies,
        next_state=ChatState.ZERO_CAPACITY,
    )
