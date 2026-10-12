"""Conversation state machine and session persistence for WS4 Chatbot."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from npa_contracts.enums import Lang
from npa_contracts.models import Offer


class ChatState(StrEnum):
    """Conversation states per WS4 briefing B4."""

    GREETING = "GREETING"
    CONSENT_NOTICE = "CONSENT_NOTICE"
    HARDSHIP_DISCLOSURE = "HARDSHIP_DISCLOSURE"
    AFFORDABILITY = "AFFORDABILITY"
    OPTIONS = "OPTIONS"
    ACCEPTED = "ACCEPTED"
    ZERO_CAPACITY = "ZERO_CAPACITY"
    HANDOFF = "HANDOFF"
    CLOSING = "CLOSING"

    # Global interrupt states
    COMPLAINT = "COMPLAINT"
    HUMAN_REQUEST = "HUMAN_REQUEST"
    DISTRESS = "DISTRESS"
    LANGUAGE_SWITCH = "LANGUAGE_SWITCH"


class ConversationState(BaseModel):
    """Serialisable state of an active chat session."""

    session_id: str
    customer_id: str
    current_state: ChatState = ChatState.GREETING
    previous_state: ChatState | None = None
    lang: Lang = Lang.EN

    # Flags & disclosures
    recording_notice_given: bool = False
    dpdp_notice_given: bool = False
    pause_outreach_suggested: bool = False

    # Hardship information
    hardship_type: str | None = None
    hardship_details: str | None = None

    # Affordability information
    declared_income_paise: int | None = None
    declared_expenses_paise: int | None = None
    dependants: int | None = None
    max_monthly_payment_paise: int | None = None

    # Offers & decisions
    presented_offers: list[Offer] = Field(default_factory=list)
    selected_offer_id: str | None = None

    # Handoff & complaints
    booked_callback_id: str | None = None
    complaint_docket_no: str | None = None

    flags: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_flag(self, flag: str) -> None:
        if flag not in self.flags:
            self.flags.append(flag)

    def transition_to(self, new_state: ChatState) -> None:
        self.previous_state = self.current_state
        self.current_state = new_state
        self.updated_at = datetime.now(UTC)


class SessionStore(Protocol):
    """Protocol for persisting conversation state."""

    def get(self, session_id: str) -> ConversationState | None: ...

    def save(self, state: ConversationState) -> None: ...


class InMemorySessionStore:
    """In-memory session store for testing and local execution."""

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationState] = {}

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def save(self, state: ConversationState) -> None:
        self._sessions[state.session_id] = state
