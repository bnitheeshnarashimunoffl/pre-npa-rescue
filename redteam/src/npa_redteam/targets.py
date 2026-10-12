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

from npa_contracts.constants import AS_OF_MONTH
from npa_contracts.enums import Lang
from npa_contracts.models import (
    Affordability,
    BotReply,
    ChatTurnRequest,
    ComplianceDecision,
    GrievanceOfficer,
    NextBestAction,
    ReliefOption,
)
from npa_contracts.providers import (
    ChatEngineProtocol,
    ComplianceProvider,
    NBAProvider,
    PolicyProvider,
)
from npa_redteam.fakes import (
    FixtureChatEngine,
    FixtureComplianceProvider,
    FixtureNBAProvider,
    FixturePolicyProvider,
)
from npa_redteam.variants import PersonaRegistry, Profile

__all__ = ["LibraryTarget", "Target", "UnsupportedCaseError"]


class UnsupportedCaseError(Exception):
    """The target cannot run this case (for example no NBA provider); the case is skipped."""


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

    def clone_customer(self, base_customer_id: str, profile: Profile) -> str:
        """A synthetic customer with the base's account data and a new name and protected
        attributes (bias swaps). Returns the new customer_id."""
        ...

    def next_best_action(self, customer_id: str) -> NextBestAction:
        """NBA for the customer's account; raises :class:`UnsupportedCaseError` if unavailable."""
        ...


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

    ``registry`` must be the same :class:`PersonaRegistry` the providers use to resolve
    bias-swap clones. ``affordability`` tells :meth:`allowed_options` which affordability to ask
    the policy about; the default is "nothing declared".
    """

    def __init__(
        self,
        engine: ChatEngineProtocol,
        policy: PolicyProvider,
        compliance: ComplianceProvider,
        *,
        nba: NBAProvider | None = None,
        registry: PersonaRegistry | None = None,
        name: str = "library",
        seed: int = 42,
        affordability: Callable[[str], Affordability] = _no_declared_affordability,
        as_of_month: str = AS_OF_MONTH,
    ) -> None:
        self.name = name
        self.registry = registry or PersonaRegistry()
        self._engine = engine
        self._policy = policy
        self._compliance = compliance
        self._nba = nba
        self._affordability = affordability
        self._as_of_month = as_of_month
        self._rng = random.Random(seed)

    @classmethod
    def from_fixtures(cls, *, seed: int = 42) -> LibraryTarget:
        """Target built from ``contracts/fixtures/`` fakes (see :mod:`npa_redteam.fakes`)."""
        registry = PersonaRegistry()
        return cls(
            FixtureChatEngine(registry),
            FixturePolicyProvider(registry),
            FixtureComplianceProvider(),
            nba=FixtureNBAProvider(registry),
            registry=registry,
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

    def clone_customer(self, base_customer_id: str, profile: Profile) -> str:
        return self.registry.clone(base_customer_id, profile)

    def next_best_action(self, customer_id: str) -> NextBestAction:
        if self._nba is None:
            raise UnsupportedCaseError(f"target {self.name} has no NBA provider")
        account_id = PersonaRegistry.account_of(customer_id)
        return self._nba.next_best_action(account_id, self._as_of_month)
