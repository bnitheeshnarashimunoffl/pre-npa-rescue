"""Affordability assessment and capacity confirmation for WS4 Chatbot (Task 4.2).

Collects income, essential expenses, and dependants; calculates surplus capacity
via estimate_affordability; and confirms the affordable monthly payment in the
borrower's language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from npa_chat.i18n import get_string
from npa_chat.nlu import NLUResult, parse_amount_paise
from npa_chat.state import ChatState, ConversationState
from npa_contracts.models import Affordability, QuickReply
from npa_contracts.money import format_inr


@dataclass
class AffordabilityTurnResult:
    """Outcome of processing an affordability turn."""

    reply_text: str
    quick_replies: list[QuickReply] = field(default_factory=list)
    next_state: ChatState = ChatState.AFFORDABILITY
    affordability: Affordability | None = None
    flags: list[str] = field(default_factory=list)


def estimate_affordability(
    customer_id: str,
    declared_income_paise: int,
    declared_expenses_paise: int,
    dependants: int = 0,
    source: Literal["declared", "estimated"] = "declared",
) -> Affordability:
    """Calculate surplus payment capacity as declared income minus essential expenses.

    If income <= expenses or income is 0, surplus is 0 (zero-capacity path).
    """
    surplus = max(0, declared_income_paise - declared_expenses_paise)
    return Affordability(
        customer_id=customer_id,
        declared_income_paise=declared_income_paise,
        declared_expenses_paise=declared_expenses_paise,
        dependants=dependants,
        max_monthly_payment_paise=surplus,
        source=source,
    )


def extract_dependants(text: str) -> int | None:
    """Extract number of dependants from text."""
    lower = text.lower()
    # Pattern: '1 dependant', '2 kids', '3 children', '4 members', etc.
    match = re.search(
        r"(\d+)\s*(?:dependant|dependent|child|children|kid|member|person|சார்ந்த)", lower
    )
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    # Simple word digits with word boundary
    words = set(re.findall(r"\b\w+\b", lower))
    if "one" in words or "ஒரு" in lower or "एक" in words:
        return 1
    if "two" in words or "இரண்டு" in lower or "दो" in words:
        return 2
    if "three" in words or "மூன்று" in lower or "तीन" in words:
        return 3

    return None


def handle_affordability_turn(
    state: ConversationState,
    text: str,
    nlu_result: NLUResult | None = None,
) -> AffordabilityTurnResult:
    """Process an incoming turn in the AFFORDABILITY state.

    Collects income -> expenses -> dependants and confirms capacity.
    """
    lang = state.lang
    lower = text.lower().strip()

    # Step 3: Handle confirmation of already-calculated affordability
    if "affordability_confirming" in state.flags and state.max_monthly_payment_paise is not None:
        confirm_words = ["yes", "works", "fine", "correct", "agree", "ஆம்", "சரி", "हाँ", "ठीक"]
        rejection_words = ["no", "change", "wrong", "different", "இல்லை", "மாற்ற", "नहीं", "गलत"]

        if any(w in lower for w in confirm_words) and not any(w in lower for w in rejection_words):
            # Borrower confirmed affordability
            affordability = estimate_affordability(
                customer_id=state.customer_id,
                declared_income_paise=state.declared_income_paise or 0,
                declared_expenses_paise=state.declared_expenses_paise or 0,
                dependants=state.dependants or 0,
            )
            state.flags.remove("affordability_confirming")
            return AffordabilityTurnResult(
                reply_text="",  # engine will transition to OPTIONS
                next_state=ChatState.OPTIONS,
                affordability=affordability,
                flags=["affordability_confirmed"],
            )

        if any(w in lower for w in rejection_words):
            # Reset and ask income again
            state.flags.remove("affordability_confirming")
            state.declared_income_paise = None
            state.declared_expenses_paise = None
            prompt = get_string("affordability_income_prompt", lang)
            quick_replies = [
                QuickReply(id="inc_0", label=get_string("affordability_quick_0", lang)),
                QuickReply(id="inc_10k", label=get_string("affordability_quick_10k", lang)),
                QuickReply(id="inc_25k", label=get_string("affordability_quick_25k", lang)),
                QuickReply(id="inc_50k", label=get_string("affordability_quick_50k", lang)),
            ]
            return AffordabilityTurnResult(
                reply_text=prompt,
                quick_replies=quick_replies,
                next_state=ChatState.AFFORDABILITY,
                flags=["affordability_reset"],
            )

    # Quick reply ID mapping for income ranges
    quick_income_map: dict[str, int] = {
        "inc_0": 0,
        "inc_10k": 1000000,
        "inc_25k": 2500000,
        "inc_50k": 5000000,
    }
    quick_amount = quick_income_map.get(text.strip())

    parsed_amount: int | None = None
    if quick_amount is not None:
        parsed_amount = quick_amount
    elif nlu_result and nlu_result.slots.get("amount_paise") is not None:
        parsed_amount = int(nlu_result.slots["amount_paise"])
    else:
        parsed_amount = parse_amount_paise(text)

    # Check for zero-capacity signal (e.g. "can't pay anything", "0 rupees", Ravi demo)
    is_zero_capacity = (
        parsed_amount == 0
        or (nlu_result and nlu_result.slots.get("zero_capacity") is True)
        or any(k in lower for k in ["cannot pay", "can't pay", "no money", "முடியாது", "कुछ नहीं"])
    )

    if is_zero_capacity and state.declared_income_paise is None:
        state.declared_income_paise = 0
        state.declared_expenses_paise = 2000000  # realistic baseline
        state.max_monthly_payment_paise = 0
        affordability = estimate_affordability(
            customer_id=state.customer_id,
            declared_income_paise=0,
            declared_expenses_paise=2000000,
            dependants=state.dependants or 1,
        )
        return AffordabilityTurnResult(
            reply_text="",
            next_state=ChatState.ZERO_CAPACITY,
            affordability=affordability,
            flags=["zero_capacity", "zero_capacity_detected"],
        )

    # Check for direct capacity declaration (e.g. "I can pay 2000",
    # "மாதம் 2000 ரூபாய் என்னால் செலுத்த முடியும்", "मैं हर महीने 2000 रुपये दे सकता हूँ")
    direct_capacity_keywords = [
        "can pay",
        "able to pay",
        "can afford",
        "செலுத்த முடியும்",
        "தர முடியும்",
        "கொடுக்க முடியும்",
        "दे सकता",
        "दे सकती",
        "सकता हूँ",
        "सकती हूँ",
    ]
    if (
        parsed_amount is not None
        and parsed_amount > 0
        and any(k in lower for k in direct_capacity_keywords)
        and state.declared_income_paise is None
    ):
        state.declared_income_paise = parsed_amount
        state.declared_expenses_paise = 0
        state.max_monthly_payment_paise = parsed_amount
        affordability = estimate_affordability(
            customer_id=state.customer_id,
            declared_income_paise=parsed_amount,
            declared_expenses_paise=0,
            dependants=state.dependants or 1,
        )
        return AffordabilityTurnResult(
            reply_text="",
            next_state=ChatState.OPTIONS,
            affordability=affordability,
            flags=["affordability_assessed", "affordability_confirmed"],
        )

    # Step 1: Collecting income
    if state.declared_income_paise is None:
        if parsed_amount is not None:
            state.declared_income_paise = parsed_amount
            # Check if text also contains expenses
            expense_match = re.search(
                r"expense[s]?\s*(?:is|are|of)?\s*([0-9.,kK\s]+)", text, re.IGNORECASE
            )
            if expense_match:
                exp_paise = parse_amount_paise(expense_match.group(1))
                if exp_paise is not None:
                    state.declared_expenses_paise = exp_paise
            dependants = extract_dependants(text)
            if dependants is not None:
                state.dependants = dependants

        if state.declared_expenses_paise is None:
            # Prompt for expenses & dependants
            prompt = get_string("affordability_expenses_prompt", lang)
            return AffordabilityTurnResult(
                reply_text=prompt,
                next_state=ChatState.AFFORDABILITY,
                flags=["income_recorded"],
            )

    # Step 2: Collecting expenses & dependants
    if state.declared_expenses_paise is None:
        if parsed_amount is not None:
            state.declared_expenses_paise = parsed_amount
        else:
            # Fallback default reasonable living expenses if customer just entered a number
            state.declared_expenses_paise = 0

        dependants = extract_dependants(text)
        if dependants is not None:
            state.dependants = dependants
        elif state.dependants is None:
            state.dependants = 1

    # Both income and expenses now present: compute capacity
    income = state.declared_income_paise or 0
    expenses = state.declared_expenses_paise or 0
    dependants = state.dependants or 1

    affordability = estimate_affordability(
        customer_id=state.customer_id,
        declared_income_paise=income,
        declared_expenses_paise=expenses,
        dependants=dependants,
    )
    surplus = affordability.max_monthly_payment_paise
    state.max_monthly_payment_paise = surplus

    if surplus == 0:
        return AffordabilityTurnResult(
            reply_text="",
            next_state=ChatState.ZERO_CAPACITY,
            affordability=affordability,
            flags=["zero_capacity", "zero_capacity_detected"],
        )

    # Prompt borrower to confirm calculated monthly capacity
    formatted_amount = format_inr(surplus)
    confirm_text = get_string("affordability_confirm", lang, amount=formatted_amount)
    quick_replies = [
        QuickReply(id="aff_yes", label=get_string("affordability_confirm_yes", lang)),
        QuickReply(id="aff_no", label=get_string("affordability_confirm_no", lang)),
    ]
    state.add_flag("affordability_confirming")
    return AffordabilityTurnResult(
        reply_text=confirm_text,
        quick_replies=quick_replies,
        next_state=ChatState.AFFORDABILITY,
        affordability=affordability,
        flags=["affordability_confirming"],
    )
