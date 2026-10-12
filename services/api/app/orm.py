"""SQLAlchemy 2.0 ORM (task 5.2).

Conventions (A7.0, B7):
- money is ``BIGINT`` paise, never float;
- timestamps are ``TIMESTAMP WITH TIME ZONE`` (UTC), never naive;
- months are ``CHAR(7)`` ``YYYY-MM``;
- enum columns are ``VARCHAR`` + ``CHECK`` built from the ``npa_contracts`` enums, so adding
  an enum value is a small Alembic migration rather than an ``ALTER TYPE``;
- JSON is ``JSONB`` on Postgres (plain JSON elsewhere, e.g. SQLite in unit tests).

``protected_attributes`` is a separate table that **no API route exposes** (A3, RBI RBC
Directions para 454O, DPDP Act 2023); only the auditor-only bias-test seed endpoint used by
WS7 may read it.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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

# Deterministic constraint names so Alembic migrations are stable across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JsonDoc = JSON().with_variant(JSONB(), "postgresql")
Paise = BigInteger
Month = String(7)
Id = String(64)


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK constraint holding the enum's wire values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def _ts(**kw: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = _ts(server_default=func.now(), nullable=False)


# --- people and accounts ----------------------------------------------------------------------
class Customer(Base):
    """Minimised customer profile (customers.parquet, contracts/data/customers.md)."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(Id, primary_key=True)
    account_id: Mapped[str] = mapped_column(Id, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    age: Mapped[int | None] = mapped_column(SmallInteger)
    city: Mapped[str | None] = mapped_column(String(100))
    language_pref: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    occupation_type: Mapped[str | None] = mapped_column(String(32))
    employer_type: Mapped[str | None] = mapped_column(String(64))
    monthly_income_paise: Mapped[int | None] = mapped_column(Paise)
    dependants: Mapped[int | None] = mapped_column(SmallInteger)
    card_limit_paise: Mapped[int | None] = mapped_column(Paise)
    card_open_date: Mapped[date | None] = mapped_column(Date)
    has_card_insurance: Mapped[bool | None] = mapped_column(Boolean)
    insurance_cover_type: Mapped[str | None] = mapped_column(String(32))
    phone_masked: Mapped[str | None] = mapped_column(String(32))
    email_masked: Mapped[str | None] = mapped_column(String(128))
    preferred_contact_window: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint("monthly_income_paise >= 0", name="income_non_negative"),
        CheckConstraint("card_limit_paise >= 0", name="limit_non_negative"),
    )


class ProtectedAttributes(Base):
    """Bias-test only. Never a model feature, never exposed by an API route (A3)."""

    __tablename__ = "protected_attributes"

    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id", ondelete="CASCADE"), primary_key=True
    )
    gender: Mapped[str | None] = mapped_column(String(32))
    religion: Mapped[str | None] = mapped_column(String(32))
    caste_category: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[str | None] = mapped_column(String(64))
    region: Mapped[str | None] = mapped_column(String(32))


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(Id, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    limit_paise: Mapped[int | None] = mapped_column(Paise)
    opened_on: Mapped[date | None] = mapped_column(Date)

    customer: Mapped[Customer] = relationship()


class AccountMonth(Base):
    """Monthly statement (account_months.parquet). DPD from the statement due date."""

    __tablename__ = "account_months"

    account_id: Mapped[str] = mapped_column(
        Id, ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[str] = mapped_column(Month, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Id, nullable=False)
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    purchases_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    cash_advance_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    payments_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date)
    total_due_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    min_due_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    interest_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    late_fee_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    closing_balance_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    utilisation: Mapped[float] = mapped_column(Float, nullable=False)
    dpd: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket: Mapped[Bucket] = mapped_column(_enum(Bucket, "bucket"), nullable=False)

    __table_args__ = (CheckConstraint("dpd >= 0", name="dpd_non_negative"),)


class User(Base, TimestampMixin):
    """Demo/staff login. Passwords are bcrypt hashes only."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(
        Id, ForeignKey("customers.customer_id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        # Only customer users are tied to a customer record (and they must be).
        CheckConstraint(
            "(role = 'customer') = (customer_id IS NOT NULL)", name="customer_link_matches_role"
        ),
    )


# --- model and rules outputs ------------------------------------------------------------------
class Score(Base, TimestampMixin):
    """Risk, segment and uplift per account and as-of month (WS2 scores.parquet / RiskProvider)."""

    __tablename__ = "scores"

    account_id: Mapped[str] = mapped_column(
        Id, ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True
    )
    as_of_month: Mapped[str] = mapped_column(Month, primary_key=True)
    p_roll_forward: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[RiskBand] = mapped_column(_enum(RiskBand, "risk_band"), nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JsonDoc, nullable=False)
    risk_model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    segment: Mapped[Segment] = mapped_column(_enum(Segment, "segment"), nullable=False)
    segment_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    segment_model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    uplift_score: Mapped[float] = mapped_column(Float, nullable=False)
    uplift_group: Mapped[UpliftGroup] = mapped_column(
        _enum(UpliftGroup, "uplift_group"), nullable=False
    )
    recommended_treatment: Mapped[Treatment] = mapped_column(
        _enum(Treatment, "treatment"), nullable=False
    )
    uplift_model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint("p_roll_forward BETWEEN 0 AND 1", name="p_roll_forward_range"),
        CheckConstraint("segment_confidence BETWEEN 0 AND 1", name="confidence_range"),
    )


class NBA(Base, TimestampMixin):
    """Next-best-action cache per as-of month; also the collector queue (denormalised).

    Queue reads use keyset pagination on ``(as_of_month, priority DESC, account_id)``.
    """

    __tablename__ = "nba"

    account_id: Mapped[str] = mapped_column(
        Id, ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True
    )
    as_of_month: Mapped[str] = mapped_column(Month, primary_key=True)
    action: Mapped[NextAction] = mapped_column(_enum(NextAction, "next_action"), nullable=False)
    channel: Mapped[Channel | None] = mapped_column(_enum(Channel, "channel"))
    earliest_contact_at: Mapped[datetime | None] = _ts()
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bucket: Mapped[Bucket] = mapped_column(_enum(Bucket, "bucket"), nullable=False)
    dpd: Mapped[int] = mapped_column(Integer, nullable=False)
    total_due_paise: Mapped[int] = mapped_column(Paise, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JsonDoc, nullable=False, doc="Full NextBestAction JSON (npa_contracts.models)."
    )

    __table_args__ = (CheckConstraint("total_due_paise >= 0", name="total_due_non_negative"),)


# Collector queue: WHERE as_of_month = ? ORDER BY priority DESC, account_id (keyset cursor).
Index("ix_nba_queue", NBA.as_of_month, NBA.priority.desc(), NBA.account_id)


class Offer(Base, TimestampMixin):
    """Offer lifecycle. ``approved_by`` records the human approver (IS/ISO/IEC 38507:2022)."""

    __tablename__ = "offers"

    offer_id: Mapped[str] = mapped_column(Id, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(Id, ForeignKey("accounts.account_id"), nullable=False)
    option_type: Mapped[ReliefType] = mapped_column(
        _enum(ReliefType, "relief_type"), nullable=False
    )
    option: Mapped[dict[str, Any]] = mapped_column(JsonDoc, nullable=False)
    status: Mapped[OfferStatus] = mapped_column(_enum(OfferStatus, "offer_status"), nullable=False)
    proposed_by: Mapped[Actor] = mapped_column(_enum(Actor, "actor"), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = _ts(nullable=False)
    updated_at: Mapped[datetime] = _ts(server_default=func.now(), nullable=False)


# --- conversations and contacts ---------------------------------------------------------------
class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(Id, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="greeting")
    closed_at: Mapped[datetime | None] = _ts()

    turns: Mapped[list["ChatTurn"]] = relationship(
        back_populates="session", order_by="ChatTurn.seq", cascade="all, delete-orphan"
    )


class ChatTurn(Base):
    """One message. Retained 180 days (RBI RBC Directions para 454P)."""

    __tablename__ = "chat_turns"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(
        Id, ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[Actor] = mapped_column(_enum(Actor, "actor"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    flags: Mapped[list[str]] = mapped_column(JsonDoc, nullable=False, default=list)
    ts: Mapped[datetime] = _ts(server_default=func.now(), nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="turns")

    __table_args__ = (UniqueConstraint("session_id", "seq"),)


class ContactEvent(Base):
    """Every contact, inbound or outbound (RBI RBC Directions para 454P: time, number, content).

    Written by ``app.audit`` (task 5.4). Retained 180 days.
    """

    __tablename__ = "contact_events"

    event_id: Mapped[str] = mapped_column(Id, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(Id, nullable=False)
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "channel"), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    actor: Mapped[Actor] = mapped_column(_enum(Actor, "actor"), nullable=False)
    ts: Mapped[datetime] = _ts(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    recorded_notice_given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    compliance: Mapped[dict[str, Any]] = mapped_column(JsonDoc, nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("direction IN ('outbound', 'inbound')", name="direction_valid"),
        Index("ix_contact_events_customer_ts", "customer_id", "ts"),
    )


class ContactFlag(Base, TimestampMixin):
    """Do-not-contact and sensitive-occasion flags (RBI para 454Y(6): bereavement, medical
    emergency, borrower's request to avoid certain times)."""

    __tablename__ = "contact_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[Actor] = mapped_column(_enum(Actor, "actor"), nullable=False)
    valid_from: Mapped[datetime] = _ts(server_default=func.now(), nullable=False)
    valid_until: Mapped[datetime | None] = _ts()

    __table_args__ = (
        CheckConstraint(
            "flag IN ('do_not_contact', 'bereavement', 'medical_emergency', 'avoid_times', "
            "'distress')",
            name="flag_valid",
        ),
    )


class Complaint(Base, TimestampMixin):
    """Complaint with docket number and 30-day SLA (IS/ISO 10002:2018; RBI para 454AA)."""

    __tablename__ = "complaints"

    docket_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    status: Mapped[ComplaintStatus] = mapped_column(
        _enum(ComplaintStatus, "complaint_status"), nullable=False
    )
    escalation_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    sla_due_at: Mapped[datetime] = _ts(nullable=False)
    grievance_officer: Mapped[dict[str, Any]] = mapped_column(JsonDoc, nullable=False)
    updated_at: Mapped[datetime] = _ts(server_default=func.now(), nullable=False)


class Callback(Base, TimestampMixin):
    """Handoff booking inside 08:00-19:00 IST (RBI para 454Y(4); checked by the scheduler)."""

    __tablename__ = "callbacks"

    callback_id: Mapped[str] = mapped_column(Id, primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        Id, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), nullable=False)
    slot_start: Mapped[datetime] = _ts(nullable=False)
    slot_end: Mapped[datetime] = _ts(nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (CheckConstraint("slot_end > slot_start", name="slot_order"),)


# --- governance -------------------------------------------------------------------------------
class PolicyVersion(Base, TimestampMixin):
    """Every bank-policy version; exactly one active (IS/ISO/IEC 42001 change control)."""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JsonDoc, nullable=False)
    change_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuditLog(Base):
    """Append-only, hash-chained audit log (IS/ISO/IEC 27001:2022; RBI para 454P).

    Table only; the writer, hash chain and the UPDATE/DELETE lock-down arrive in task 5.4.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    ts: Mapped[datetime] = _ts(server_default=func.now(), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JsonDoc, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class RedTeamRun(Base, TimestampMixin):
    __tablename__ = "redteam_runs"

    run_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    finished_at: Mapped[datetime | None] = _ts()
    scorecard: Mapped[dict[str, Any] | None] = mapped_column(JsonDoc)

    results: Mapped[list["RedTeamResult"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')", name="status_valid"
        ),
    )


class RedTeamResult(Base):
    __tablename__ = "redteam_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("redteam_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    test_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[RedTeamCategory] = mapped_column(
        _enum(RedTeamCategory, "redteam_category"), nullable=False
    )
    lang: Mapped[Lang] = mapped_column(_enum(Lang, "lang"), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_refs: Mapped[list[str]] = mapped_column(JsonDoc, nullable=False)
    bis_refs: Mapped[list[str]] = mapped_column(JsonDoc, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("run_id", "test_id"),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="severity_valid"),
    )


def table_of(model: type[Base]) -> Table:
    """The ``Table`` behind a mapped class (``__table__`` is typed as ``FromClause``)."""
    return cast(Table, model.__table__)
