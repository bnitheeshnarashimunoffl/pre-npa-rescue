"""Provider interfaces (contract A7.5).

Packages depend on these protocols, never on each other's internals. The API (WS5) wires
concrete implementations together in ``services/api/app/deps.py``.
"""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any, Protocol

from npa_contracts.enums import Actor, Channel, Lang, Role
from npa_contracts.models import (
    Affordability,
    BotReply,
    Callback,
    ChatTurnRequest,
    Complaint,
    ComplianceDecision,
    ContactEvent,
    GrievanceOfficer,
    NextBestAction,
    Offer,
    ReliefOption,
    RiskScore,
    SegmentResult,
    UpliftResult,
)


class RiskProvider(Protocol):
    """Implemented by WS2 ``npa_models.provider``."""

    def risk(self, account_id: str, as_of_month: str) -> RiskScore: ...

    def segment(self, account_id: str, as_of_month: str) -> SegmentResult: ...

    def uplift(self, account_id: str, as_of_month: str) -> UpliftResult: ...

    def score_batch(
        self, as_of_month: str
    ) -> Iterator[tuple[RiskScore, SegmentResult, UpliftResult]]: ...


class PolicyProvider(Protocol):
    """Implemented by WS3 ``npa_rules.policy_engine``."""

    def relief_options(
        self, customer_id: str, affordability: Affordability
    ) -> list[ReliefOption]: ...

    def propose_offer(self, customer_id: str, option_id: str, actor: Actor) -> Offer: ...

    def grievance_officer(self) -> GrievanceOfficer: ...


class ComplianceProvider(Protocol):
    """Implemented by WS3 ``npa_rules.compliance_guard``."""

    def check_contact(
        self, customer_id: str, channel: Channel, at: datetime, actor: Actor
    ) -> ComplianceDecision: ...

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        """Harsh/misleading language filter (RBI RBC Directions para 454Z)."""
        ...


class NBAProvider(Protocol):
    """Implemented by WS3 ``npa_rules.nba``."""

    def next_best_action(self, account_id: str, as_of_month: str) -> NextBestAction: ...


class ContactLogger(Protocol):
    """Implemented by WS5 ``app.audit`` (RBI RBC Directions para 454P)."""

    def log(self, event: ContactEvent) -> None: ...


class ComplaintSink(Protocol):
    """Implemented by WS5 (IS/ISO 10002:2018)."""

    def open(self, customer_id: str, category: str, text: str, lang: Lang) -> Complaint: ...


class CallbackScheduler(Protocol):
    """Implemented by WS5; uses ComplianceProvider for slots (RBI para 454Y(4))."""

    def available_slots(self, customer_id: str, day: date) -> list[tuple[datetime, datetime]]: ...

    def book(
        self, customer_id: str, slot_start: datetime, role: Role, summary: str
    ) -> Callback: ...


class CustomerContextProvider(Protocol):
    """Implemented by WS5 (reads the DB). Minimised profile; never protected attributes."""

    def context(self, customer_id: str) -> dict[str, Any]: ...


class LLMClient(Protocol):
    """Implemented by WS4 ``npa_chat.llm_client`` (AnthropicLLMClient, MockLLMClient)."""

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str: ...


class ChatEngineProtocol(Protocol):
    """Public surface of WS4's ``ChatEngine`` as called by the API."""

    def handle(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply: ...
