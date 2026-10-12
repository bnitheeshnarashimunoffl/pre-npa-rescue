"""What the harness attacks (task 7.1).

A :class:`Target` hides whether cases run in **library mode** (Python providers called
in-process: fast, used in CI) or **API mode** (the real HTTP API, phase 2). Suites only talk
to this protocol.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from npa_contracts.constants import AS_OF_MONTH
from npa_contracts.enums import Actor, Channel, Lang
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
from npa_redteam.cases import ContactSetup
from npa_redteam.fakes import (
    FixtureChatEngine,
    FixtureComplianceProvider,
    FixtureNBAProvider,
    FixturePolicyProvider,
)
from npa_redteam.variants import PersonaRegistry, Profile

__all__ = [
    "ApiResponse",
    "LibraryTarget",
    "ScenarioCompliance",
    "ScenarioScheduler",
    "Target",
    "UnsupportedCaseError",
]


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

    def api_request(
        self, method: str, path: str, *, as_user: str, body: dict[str, Any] | None = None
    ) -> ApiResponse:
        """One call to ``/api/v1`` as a demo user. Library targets raise
        :class:`UnsupportedCaseError`."""
        ...

    def check_contact(
        self,
        customer_id: str,
        channel: Channel,
        at: datetime,
        actor: Actor,
        setup: ContactSetup,
    ) -> ComplianceDecision:
        """Compliance pre-check for a contact, with the account state in ``setup``."""
        ...

    def available_slots(
        self, customer_id: str, day: date, setup: ContactSetup
    ) -> list[tuple[datetime, datetime]]:
        """Callback slots the scheduler would offer on ``day``."""
        ...


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    text: str


class ScenarioCompliance(Protocol):
    """A compliance provider that can be set up with a customer's flags, quiet times and
    contact log. The WS3 adapter (``ComplianceGuard`` with injected ``contact_history`` and
    ``accounts``) implements this once ``npa_rules`` is merged."""

    def with_setup(self, customer_id: str, setup: ContactSetup) -> ComplianceProvider: ...


class ScenarioScheduler(Protocol):
    def available_slots(
        self, customer_id: str, day: date, setup: ContactSetup
    ) -> list[tuple[datetime, datetime]]: ...


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
        scheduler: ScenarioScheduler | None = None,
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
        self._scheduler = scheduler
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

    def api_request(
        self, method: str, path: str, *, as_user: str, body: dict[str, Any] | None = None
    ) -> ApiResponse:
        raise UnsupportedCaseError("API probes need API mode (phase 2)")

    def check_contact(
        self,
        customer_id: str,
        channel: Channel,
        at: datetime,
        actor: Actor,
        setup: ContactSetup,
    ) -> ComplianceDecision:
        provider: ComplianceProvider = self._compliance
        if not setup.empty:
            with_setup = getattr(self._compliance, "with_setup", None)
            if with_setup is None:
                raise UnsupportedCaseError(
                    f"target {self.name} cannot set flags, quiet times or contact history"
                )
            provider = with_setup(customer_id, setup)
        return provider.check_contact(customer_id, channel, at, actor)

    def available_slots(
        self, customer_id: str, day: date, setup: ContactSetup
    ) -> list[tuple[datetime, datetime]]:
        if self._scheduler is None:
            raise UnsupportedCaseError(f"target {self.name} has no callback scheduler")
        return self._scheduler.available_slots(customer_id, day, setup)
