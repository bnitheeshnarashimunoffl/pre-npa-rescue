"""ORM rows -> ``npa_contracts`` models. Timestamps read back from SQLite are naive; they are
stored as UTC, so they are re-labelled UTC here (Postgres returns aware values already)."""

from datetime import UTC, datetime
from typing import Any

from app import orm
from npa_contracts.api import AccountMonthSummary, ChatTurn, CustomerProfile, PolicyDocument
from npa_contracts.models import (
    Callback,
    Complaint,
    ComplianceDecision,
    ContactEvent,
    GrievanceOfficer,
    Offer,
    ReliefOption,
)


def utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def utc_or_none(ts: datetime | None) -> datetime | None:
    return None if ts is None else utc(ts)


def customer_profile(row: orm.Customer) -> CustomerProfile:
    return CustomerProfile(
        customer_id=row.customer_id,
        account_id=row.account_id,
        full_name=row.full_name,
        language_pref=row.language_pref,
        age=row.age,
        city=row.city,
        occupation_type=row.occupation_type,
        card_limit_paise=row.card_limit_paise,
        has_card_insurance=row.has_card_insurance,
        insurance_cover_type=row.insurance_cover_type,
        phone_masked=row.phone_masked,
        email_masked=row.email_masked,
        preferred_contact_window=row.preferred_contact_window,
    )


def offer(row: orm.Offer) -> Offer:
    return Offer(
        offer_id=row.offer_id,
        customer_id=row.customer_id,
        account_id=row.account_id,
        option=ReliefOption.model_validate(row.option),
        status=row.status,
        proposed_by=row.proposed_by,
        approved_by=row.approved_by,
        created_at=utc(row.created_at),
        expires_at=utc(row.expires_at),
    )


def offer_row(o: Offer) -> orm.Offer:
    return orm.Offer(
        offer_id=o.offer_id,
        customer_id=o.customer_id,
        account_id=o.account_id,
        option_type=o.option.type,
        option=o.option.model_dump(mode="json"),
        status=o.status,
        proposed_by=o.proposed_by,
        approved_by=o.approved_by,
        created_at=o.created_at,
        expires_at=o.expires_at,
    )


def contact_event(row: orm.ContactEvent) -> ContactEvent:
    return ContactEvent(
        event_id=row.event_id,
        customer_id=row.customer_id,
        account_id=row.account_id,
        channel=row.channel,
        direction=row.direction,  # type: ignore[arg-type]
        actor=row.actor,
        ts=utc(row.ts),
        content=row.content,
        lang=row.lang,
        recorded_notice_given=row.recorded_notice_given,
        compliance=ComplianceDecision.model_validate(row.compliance),
        outcome=row.outcome,
    )


def complaint(row: orm.Complaint) -> Complaint:
    return Complaint(
        docket_no=row.docket_no,
        customer_id=row.customer_id,
        category=row.category,
        text=row.text,
        lang=row.lang,
        status=row.status,
        escalation_level=row.escalation_level,
        created_at=utc(row.created_at),
        sla_due_at=utc(row.sla_due_at),
        grievance_officer=GrievanceOfficer.model_validate(row.grievance_officer),
    )


def callback(row: orm.Callback) -> Callback:
    return Callback(
        callback_id=row.callback_id,
        customer_id=row.customer_id,
        role=row.role,
        slot_start=utc(row.slot_start),
        slot_end=utc(row.slot_end),
        summary=row.summary,
        created_at=utc(row.created_at),
    )


def chat_turn(row: orm.ChatTurn) -> ChatTurn:
    return ChatTurn(actor=row.actor, text=row.text, lang=row.lang, ts=utc(row.ts), flags=row.flags)


def account_month(row: orm.AccountMonth) -> AccountMonthSummary:
    return AccountMonthSummary(
        month=row.month,
        total_due_paise=row.total_due_paise,
        min_due_paise=row.min_due_paise,
        payments_paise=row.payments_paise,
        dpd=row.dpd,
        bucket=row.bucket,
    )


def policy_document(row: orm.PolicyVersion) -> PolicyDocument:
    created = utc(row.created_at)
    effective: Any = row.policy.get("effective_from") or created.date()
    return PolicyDocument(
        version=row.version,
        effective_from=effective,
        updated_at=created,
        updated_by=row.created_by,
        policy=row.policy,
    )
