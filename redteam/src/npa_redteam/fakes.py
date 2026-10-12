"""Fixture-backed stand-ins for library mode (task 7.1, briefing B4).

Until WS3's ``npa_rules`` and WS4's ``npa_chat`` are merged, library mode runs against these
fakes built from ``contracts/fixtures/``. They are **not** the system under test: the chat
engine replays the persona's fixture reply on every turn and makes no attempt to pass any case.
A scorecard produced against them only proves the harness works; its notes say
``target=library:fixtures``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from npa_contracts.constants import BUSINESS_TZ, CONTACT_WINDOW
from npa_contracts.enums import Actor, Channel, Lang
from npa_contracts.models import (
    Affordability,
    BotReply,
    ChatTurnRequest,
    ComplianceDecision,
    GrievanceOfficer,
    Offer,
    ReliefOption,
)

__all__ = [
    "PERSONAS",
    "FixtureChatEngine",
    "FixtureComplianceProvider",
    "FixturePolicyProvider",
    "UnknownPersonaError",
    "contracts_dir",
    "load_fixture",
]

# customer_id -> (relief options fixture, bot reply fixture)
PERSONAS: dict[str, tuple[str, str]] = {
    "CUST-DEMO-PRIYA": ("relief_options_priya.json", "bot_reply_offer.json"),
    "CUST-DEMO-RAVI": ("relief_options_ravi.json", "bot_reply_zero_capacity.json"),
}


class UnknownPersonaError(LookupError):
    """The target has no data for this customer; the harness skips the case."""


def contracts_dir() -> Path:
    """``$CONTRACTS_DIR`` (A11) or ``contracts/`` at the repository root."""
    env = os.environ.get("CONTRACTS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "contracts"


@cache
def _read_fixture(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fixture(name: str) -> Any:
    """Parsed JSON of ``contracts/fixtures/<name>``."""
    return _read_fixture(contracts_dir() / "fixtures" / name)


def _persona(customer_id: str) -> tuple[str, str]:
    try:
        return PERSONAS[customer_id]
    except KeyError:
        raise UnknownPersonaError(f"no fixture data for {customer_id}") from None


class FixtureChatEngine:
    """``ChatEngineProtocol`` that replays the persona's fixture ``BotReply``."""

    def handle(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply:
        _, reply_file = _persona(customer_id)
        reply = BotReply.model_validate(load_fixture(reply_file))
        return reply.model_copy(update={"session_id": session_id})


class FixturePolicyProvider:
    """``PolicyProvider`` serving ``relief_options_<persona>.json`` whatever the affordability."""

    def relief_options(self, customer_id: str, affordability: Affordability) -> list[ReliefOption]:
        options_file, _ = _persona(customer_id)
        return [ReliefOption.model_validate(o) for o in load_fixture(options_file)]

    def propose_offer(self, customer_id: str, option_id: str, actor: Actor) -> Offer:
        raise NotImplementedError("the fixture policy provider does not create offers")

    def grievance_officer(self) -> GrievanceOfficer:
        officer = load_fixture("policy.json")["policy"]["grievance_officer"]
        return GrievanceOfficer.model_validate(officer)


class FixtureComplianceProvider:
    """``ComplianceProvider`` with only the contact window and no text lexicon.

    Real rules (preferences, occasions, caps, lexicon) come from WS3's ``ComplianceGuard``.
    """

    def check_contact(
        self, customer_id: str, channel: Channel, at: datetime, actor: Actor
    ) -> ComplianceDecision:
        # RBI RBC Directions para 454Y(4): outbound contact only 08:00-19:00 IST.
        local = at.astimezone(ZoneInfo(BUSINESS_TZ)).time()
        start, end = CONTACT_WINDOW
        if actor is Actor.CUSTOMER or start <= local < end:
            return ComplianceDecision(
                allowed=True, rule_ids=[], next_allowed_at=None, explanation="fixture fake"
            )
        return ComplianceDecision(
            allowed=False,
            rule_ids=["RBI-454Y4-WINDOW"],
            next_allowed_at=None,
            explanation="fixture fake: outside 08:00-19:00 IST",
        )

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        return ComplianceDecision(
            allowed=True, rule_ids=[], next_allowed_at=None, explanation="fixture fake: no lexicon"
        )
