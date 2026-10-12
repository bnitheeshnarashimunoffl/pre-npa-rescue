"""What the harness attacks (task 7.1).

A :class:`Target` hides whether cases run in **library mode** (Python providers called
in-process: fast, used in CI) or **API mode** (the real HTTP API, phase 2). Suites only talk
to this protocol.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from typing import Protocol

from npa_contracts.enums import Lang
from npa_contracts.models import (
    Affordability,
    BotReply,
    ChatTurnRequest,
    ComplianceDecision,
    GrievanceOfficer,
    ReliefOption,
)
from npa_contracts.providers import ChatEngineProtocol, ComplianceProvider, PolicyProvider
from npa_redteam.fakes import (
    FixtureChatEngine,
    FixtureComplianceProvider,
    FixturePolicyProvider,
)

__all__ = ["LibraryTarget", "Target"]


class Target(Protocol):
    """The system under attack, as seen by the suites."""

    name: str

    def start_session(self, customer_id: str) -> str: ...

    def send(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply: ...

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        """The system's own harsh-language filter (RBI RBC Directions para 454Z)."""
        ...

    def allowed_options(self, customer_id: str) -> list[ReliefOption]:
        """Every relief option the bank policy would issue to this customer."""
        ...

    def grievance_officer(self) -> GrievanceOfficer: ...


def _no_declared_affordability(customer_id: str) -> Affordability:
    return Affordability(
        customer_id=customer_id,
        declared_income_paise=None,
        declared_expenses_paise=None,
        dependants=None,
        max_monthly_payment_paise=0,
        source="estimated",
    )


class LibraryTarget:
    """In-process target over A7.5 providers.

    ``affordability`` tells :meth:`allowed_options` which affordability to ask the policy
    about; the default is "nothing declared".
    """

    def __init__(
        self,
        engine: ChatEngineProtocol,
        policy: PolicyProvider,
        compliance: ComplianceProvider,
        *,
        name: str = "library",
        seed: int = 42,
        affordability: Callable[[str], Affordability] = _no_declared_affordability,
    ) -> None:
        self.name = name
        self._engine = engine
        self._policy = policy
        self._compliance = compliance
        self._affordability = affordability
        self._rng = random.Random(seed)

    @classmethod
    def from_fixtures(cls, *, seed: int = 42) -> LibraryTarget:
        """Target built from ``contracts/fixtures/`` fakes (see :mod:`npa_redteam.fakes`)."""
        return cls(
            FixtureChatEngine(),
            FixturePolicyProvider(),
            FixtureComplianceProvider(),
            name="library:fixtures",
            seed=seed,
        )

    def start_session(self, customer_id: str) -> str:
        # Seeded, so a replayed run produces the same session IDs.
        return f"SESS-{uuid.UUID(int=self._rng.getrandbits(128), version=4)}"

    def send(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply:
        return self._engine.handle(session_id, customer_id, req)

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        return self._compliance.check_text(text, lang)

    def allowed_options(self, customer_id: str) -> list[ReliefOption]:
        return self._policy.relief_options(customer_id, self._affordability(customer_id))

    def grievance_officer(self) -> GrievanceOfficer:
        return self._policy.grievance_officer()
