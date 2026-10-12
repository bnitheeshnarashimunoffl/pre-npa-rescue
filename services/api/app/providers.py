"""Provider wiring (task 5.1, B4 dependency injection).

``build_providers`` runs once per app. Every slot gets the real ``npa_*`` implementation when it
is installed and usable, otherwise a fallback from ``app.services.fallbacks``; fallbacks log a
warning and are reported as ``"fixture"`` by ``GET /health``. Real WS2/WS3/WS4 providers are
wired in the phase-2 integration PR (``ws5/feat/integration-real-providers``) once those
packages are merged; until then every model/rules/chat slot is a fallback.
"""

import logging
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.fallbacks import (
    CachedNBAProvider,
    FixtureChatEngine,
    FixturePolicyProvider,
    ScoresRiskProvider,
    WindowComplianceProvider,
)
from app.services.records import DbCallbackScheduler, DbComplaintSink, DbCustomerContext
from npa_contracts.providers import (
    ChatEngineProtocol,
    ComplianceProvider,
    NBAProvider,
    PolicyProvider,
    RiskProvider,
)

log = logging.getLogger(__name__)

Kind = Literal["real", "fixture"]


@dataclass
class Providers:
    risk: RiskProvider
    policy: PolicyProvider
    compliance: ComplianceProvider
    nba: NBAProvider
    chat: ChatEngineProtocol
    complaints: DbComplaintSink
    callbacks: DbCallbackScheduler
    context: DbCustomerContext
    kinds: dict[str, Kind] = field(default_factory=dict)


def build_providers(settings: Settings, sessions: sessionmaker[Session]) -> Providers:
    risk = ScoresRiskProvider(sessions)
    policy = FixturePolicyProvider(settings.contracts_dir)
    compliance = WindowComplianceProvider(settings.tz_business)
    nba = CachedNBAProvider(sessions)
    chat = FixtureChatEngine(settings.contracts_dir)
    kinds: dict[str, Kind] = {
        "risk": "fixture",
        "policy": "fixture",
        "compliance": "fixture",
        "nba": "fixture",
        "chat": "fixture",
    }
    for name, kind in kinds.items():
        if kind == "fixture":
            log.warning("provider=%s using fallback (real package not wired yet)", name)
    return Providers(
        risk=risk,
        policy=policy,
        compliance=compliance,
        nba=nba,
        chat=chat,
        complaints=DbComplaintSink(sessions, policy),
        callbacks=DbCallbackScheduler(sessions, compliance, tz=settings.tz_business),
        context=DbCustomerContext(sessions),
        kinds=kinds,
    )


def get_providers(request: Request) -> Providers:
    providers: Providers = request.app.state.providers
    return providers


Deps = Annotated[Providers, Depends(get_providers)]
