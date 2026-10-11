"""REST request/response models for ``/api/v1`` (contract A7.4).

These complement the shared objects in :mod:`npa_contracts.models` with the envelopes the
API needs (login, errors, pagination, summaries). ``contracts/openapi.yaml`` is generated
from the API routes that use them.
"""

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from npa_contracts.enums import (
    Actor,
    Bucket,
    Channel,
    ComplaintStatus,
    Lang,
    Role,
)
from npa_contracts.models import (
    ChatTurnRequest,
    ContactEvent,
    ContractModel,
    Month,
    NextBestAction,
    Offer,
    Paise,
    Probability,
    QueueItem,
    ReasonCode,
    Scorecard,
)

__all__ = [
    "AccountMonthSummary",
    "AccountSummary",
    "CallbackCreateRequest",
    "ChatSessionCreateRequest",
    "ChatSessionCreated",
    "ChatTranscript",
    "ChatTurn",
    "ChatTurnRequest",
    "ComplaintCreateRequest",
    "ComplaintUpdateRequest",
    "ContactCheckRequest",
    "CustomerProfile",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "KpiReport",
    "LoginRequest",
    "OfferCreateRequest",
    "OfferDecisionRequest",
    "PolicyDocument",
    "PolicyUpdateRequest",
    "QueuePage",
    "RedTeamRun",
    "SimulationMetrics",
    "StrategyMetrics",
    "TokenResponse",
    "WellnessRequest",
    "WellnessResult",
    "WellnessScenario",
]


# --- errors -----------------------------------------------------------------------------------
class ErrorBody(ContractModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    """Standard error envelope: ``{"error": {"code", "message", "details"}}``."""

    error: ErrorBody


# --- auth / health ----------------------------------------------------------------------------
class LoginRequest(ContractModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(ContractModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until expiry.")
    role: Role
    customer_id: str | None = Field(description="Set only for the customer role.")


class HealthResponse(ContractModel):
    status: Literal["ok", "degraded"]
    api_version: str
    contract_version: str
    packages: dict[str, str] = Field(description="Installed npa_* package versions.")
    providers: dict[str, Literal["real", "fixture"]]


# --- customers / accounts ---------------------------------------------------------------------
class CustomerProfile(ContractModel):
    """Profile minimised per role (RBI RBC Directions para 454O, DPDP Act 2023).

    Never contains protected attributes. Fields a role may not see are ``null``.
    """

    customer_id: str
    account_id: str
    full_name: str
    language_pref: Lang
    age: int | None
    city: str | None
    occupation_type: str | None
    card_limit_paise: Paise | None
    has_card_insurance: bool | None
    insurance_cover_type: str | None
    phone_masked: str | None
    email_masked: str | None
    preferred_contact_window: str | None


class AccountMonthSummary(ContractModel):
    month: Month
    total_due_paise: Paise
    min_due_paise: Paise
    payments_paise: Paise
    dpd: int = Field(ge=0)
    bucket: Bucket


class AccountSummary(ContractModel):
    account_id: str
    customer_id: str
    customer_name: str
    bucket: Bucket
    dpd: int = Field(ge=0)
    total_due_paise: Paise
    min_due_paise: Paise
    history: list[AccountMonthSummary]
    contacts: list[ContactEvent]
    offers: list[Offer]
    reasons: list[ReasonCode]
    nba: NextBestAction | None


class QueuePage(ContractModel):
    items: list[QueueItem]
    next_cursor: str | None = Field(description="Opaque cursor; null on the last page.")


# --- contacts / offers ------------------------------------------------------------------------
class ContactCheckRequest(ContractModel):
    customer_id: str
    channel: Channel
    at: AwareDatetime
    actor: Actor


class OfferCreateRequest(ContractModel):
    customer_id: str
    option_id: str


class OfferDecisionRequest(ContractModel):
    note: str | None = Field(default=None, max_length=1000)


# --- chat -------------------------------------------------------------------------------------
class ChatSessionCreateRequest(ContractModel):
    lang: Lang | None = None


class ChatSessionCreated(ContractModel):
    session_id: str = Field(examples=["SESS-1b4e28ba-2fa1-11d2-883f-0016d3cca427"])
    customer_id: str
    lang: Lang
    created_at: AwareDatetime


class ChatTurn(ContractModel):
    actor: Actor
    text: str
    lang: Lang
    ts: AwareDatetime
    flags: list[str]


class ChatTranscript(ContractModel):
    session_id: str
    customer_id: str
    created_at: AwareDatetime
    turns: list[ChatTurn]


# --- complaints / callbacks -------------------------------------------------------------------
class ComplaintCreateRequest(ContractModel):
    customer_id: str | None = Field(
        default=None, description="Staff only; customers file for self."
    )
    category: str
    text: str = Field(min_length=1, max_length=4000)
    lang: Lang


class ComplaintUpdateRequest(ContractModel):
    status: ComplaintStatus | None = None
    escalation_level: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)


class CallbackCreateRequest(ContractModel):
    customer_id: str | None = Field(
        default=None, description="Staff only; customers book for self."
    )
    slot_start: AwareDatetime
    role: Role
    summary: str = Field(max_length=2000)


# --- admin / red team -------------------------------------------------------------------------
class PolicyDocument(ContractModel):
    """The bank policy (``bank_policy.yaml``, owned by WS3) as JSON, with version metadata."""

    version: str
    effective_from: date
    updated_at: AwareDatetime
    updated_by: str
    policy: dict[str, Any]


class PolicyUpdateRequest(ContractModel):
    policy: dict[str, Any]
    change_note: str = Field(min_length=1, max_length=1000)


class RedTeamRun(ContractModel):
    run_id: str = Field(pattern=r"^RT-\d{8}-\d{4}$")
    status: Literal["queued", "running", "completed", "failed"]
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    scorecard: Scorecard | None


# --- metrics / wellness -----------------------------------------------------------------------
class StrategyMetrics(ContractModel):
    strategy: str = Field(examples=["call_everyone", "pre_npa_rescue"])
    npa_rate: Probability
    cure_rate: Probability
    collection_cost_paise: Paise
    contacts_made: int = Field(ge=0)


class SimulationMetrics(ContractModel):
    as_of_month: Month
    n_accounts: int = Field(ge=0)
    horizon_days: int = Field(ge=1)
    baseline: StrategyMetrics
    ours: StrategyMetrics
    npa_reduction_pct: float = Field(description="Relative NPA-rate reduction vs baseline, %.")
    illustrative: bool
    source: str = Field(description="Where the numbers come from, e.g. a report path.")


class KpiReport(ContractModel):
    """Contact-centre KPIs (IS/ISO 18295-1/-2:2017)."""

    as_of: AwareDatetime
    contacts_per_account: float
    in_window_share: Probability = Field(description="Should be 1.0 (RBI para 454Y(4)).")
    complaints_open: int = Field(ge=0)
    complaints_breaching_sla: int = Field(ge=0)
    handoff_rate: Probability
    avg_turns_to_resolution: float
    standard_refs: list[str]


class WellnessRequest(ContractModel):
    customer_id: str
    option_id: str | None = None


class WellnessScenario(ContractModel):
    name: Literal["pay_plan", "reach_npa"]
    score_band: str = Field(description="Illustrative band label, not a real bureau score.")
    months_to_recover: int = Field(ge=0)
    notes_key: str = Field(description="i18n key of the explanation text.")


class WellnessResult(ContractModel):
    customer_id: str
    illustrative: Literal[True] = True
    scenarios: list[WellnessScenario]
    disclaimer_key: str
