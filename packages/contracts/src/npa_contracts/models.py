"""Shared objects (contract A7.3), Pydantic v2.

JSON Schemas in ``contracts/schemas/`` are generated from these models by
``scripts/export_schemas.py``; never edit the schemas by hand.

Conventions (A7.0): money is ``int`` paise, timestamps are timezone-aware
(:class:`pydantic.AwareDatetime`; naive datetimes are rejected), months are ``YYYY-MM``.
"""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from npa_contracts.enums import (
    Actor,
    Bucket,
    Channel,
    ComplaintStatus,
    Lang,
    NextAction,
    OfferStatus,
    RedTeamCategory,
    ReliefType,
    RiskBand,
    Role,
    Segment,
    Treatment,
    UpliftGroup,
)

Month = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-09"])]
Paise = Annotated[int, Field(ge=0, description="Amount in paise (1 rupee = 100 paise).")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class ContractModel(BaseModel):
    """Base for every shared object: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


class ReasonCode(ContractModel):
    code: str = Field(examples=["SALARY_STOPPED"])
    weight: float
    text: dict[Lang, str]


class RiskScore(ContractModel):
    account_id: str
    as_of_month: Month
    p_roll_forward: Probability = Field(description="Probability of rolling forward in 30-60 days.")
    risk_band: RiskBand
    reasons: list[ReasonCode] = Field(max_length=3, description="Top 3 reasons.")
    model_version: str


class SegmentResult(ContractModel):
    account_id: str
    segment: Segment
    confidence: Probability
    model_version: str


class UpliftResult(ContractModel):
    account_id: str
    uplift_score: float = Field(description="Estimated cure-probability gain if treated.")
    uplift_group: UpliftGroup
    recommended_treatment: Treatment
    model_version: str


class Affordability(ContractModel):
    customer_id: str
    declared_income_paise: Paise | None
    declared_expenses_paise: Paise | None
    dependants: int | None = Field(ge=0)
    max_monthly_payment_paise: Paise = Field(description="0 means zero-capacity.")
    source: Literal["declared", "estimated"]


class ReliefOption(ContractModel):
    option_id: str
    type: ReliefType
    monthly_amount_paise: Paise | None
    tenure_months: int | None = Field(ge=1)
    waiver_paise: Paise | None
    settlement_amount_paise: Paise | None
    policy_ref: str = Field(examples=["bank_policy.yaml#fee_waiver.v1"])
    regulatory_refs: list[str] = Field(examples=[["RBI Prudential Framework 2019"]])
    disclosure_keys: list[str] = Field(description="i18n keys of mandatory trade-off texts.")
    requires_human_approval: bool
    eligibility_reason: str


class Offer(ContractModel):
    offer_id: str = Field(examples=["OFFER-1b4e28ba-2fa1-11d2-883f-0016d3cca427"])
    customer_id: str
    account_id: str
    option: ReliefOption
    status: OfferStatus
    proposed_by: Actor
    approved_by: str | None
    created_at: AwareDatetime
    expires_at: AwareDatetime


class ComplianceDecision(ContractModel):
    allowed: bool
    rule_ids: list[str] = Field(examples=[["RBI-454Y4-WINDOW"]])
    next_allowed_at: AwareDatetime | None
    explanation: str


class NextBestAction(ContractModel):
    account_id: str
    action: NextAction
    channel: Channel | None
    earliest_contact_at: AwareDatetime | None
    reason_codes: list[str]
    risk: RiskScore
    segment: SegmentResult
    uplift: UpliftResult


class ContactEvent(ContractModel):
    event_id: str = Field(examples=["EVT-1b4e28ba-2fa1-11d2-883f-0016d3cca427"])
    customer_id: str
    account_id: str
    channel: Channel
    direction: Literal["outbound", "inbound"]
    actor: Actor
    ts: AwareDatetime
    content: str
    lang: Lang
    recorded_notice_given: bool
    compliance: ComplianceDecision
    outcome: str | None


class GrievanceOfficer(ContractModel):
    """Grievance officer details from ``bank_policy.yaml`` (RBI RBC Directions para 454AA)."""

    name: str
    email: str
    phone: str
    address: str


class Complaint(ContractModel):
    docket_no: str = Field(pattern=r"^CMP-\d{8}-\d{4}$", examples=["CMP-20260920-0001"])
    customer_id: str
    category: str
    text: str
    lang: Lang
    status: ComplaintStatus
    escalation_level: int = Field(ge=0)
    created_at: AwareDatetime
    sla_due_at: AwareDatetime = Field(description="created_at + 30 days (IS/ISO 10002:2018).")
    grievance_officer: GrievanceOfficer


class Callback(ContractModel):
    callback_id: str
    customer_id: str
    role: Role
    slot_start: AwareDatetime
    slot_end: AwareDatetime
    summary: str
    created_at: AwareDatetime


class ChatTurnRequest(ContractModel):
    text: str = Field(min_length=1, max_length=4000)
    lang: Lang | None = Field(default=None, description="None means auto-detect.")


class QuickReply(ContractModel):
    id: str
    label: str


class BotReply(ContractModel):
    session_id: str
    text: str
    lang: Lang
    quick_replies: list[QuickReply]
    offers: list[Offer]
    handoff: Callback | None
    complaint: Complaint | None
    flags: list[str] = Field(examples=[["distress_detected", "zero_capacity", "injection_blocked"]])
    state: str = Field(description="Current conversation state name.")


class RedTeamResult(ContractModel):
    test_id: str
    run_id: str = Field(pattern=r"^RT-\d{8}-\d{4}$", examples=["RT-20261011-1030"])
    category: RedTeamCategory
    lang: Lang
    input: str
    output: str
    passed: bool
    severity: Literal["low", "medium", "high", "critical"]
    rule_refs: list[str]
    bis_refs: list[str]
    notes: str


class Scorecard(ContractModel):
    run_id: str = Field(pattern=r"^RT-\d{8}-\d{4}$")
    created_at: AwareDatetime
    totals: dict[str, int]
    by_category: dict[RedTeamCategory, dict[str, int]]
    results: list[RedTeamResult]
    rbi_coverage: dict[str, bool]
    bis_coverage: dict[str, bool]


class QueueItem(ContractModel):
    account_id: str
    customer_name: str
    bucket: Bucket
    dpd: int = Field(ge=0)
    total_due_paise: Paise
    nba: NextBestAction
    priority: float
