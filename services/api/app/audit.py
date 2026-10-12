"""Audit logging (task 5.4). IS/ISO/IEC 27001:2022 A.8.15 (logging); RBI RBC Directions
para 454P (log time and number of calls, record call content).

``audit_log`` is append-only and hash-chained:

    row_hash = sha256(prev_hash + "\\n" + canonical(ts, actor, action, resource, details))

where the first row's ``prev_hash`` is 64 zeros. Changing, deleting or reordering any row
breaks the chain, which ``verify_chain`` (and ``GET /admin/audit/verify``) detects. Database
triggers (migration 0002) also reject UPDATE, DELETE and TRUNCATE on the table.

Details never carry raw personal data: contact *content* lives in ``contact_events`` (itself
retained 180 days); the audit row records that the contact happened and its decision.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.orm import AuditLog
from app.orm import ContactEvent as ContactEventRow
from npa_contracts.models import ContactEvent

GENESIS_HASH = "0" * 64
_PG_AUDIT_LOCK = 545_400_454  # advisory lock id serialising appends (any constant works)


def _ts_text(ts: datetime) -> str:
    # SQLite returns naive datetimes; everything is stored as UTC.
    aware = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat(timespec="microseconds")


def compute_hash(
    prev_hash: str, ts: datetime, actor: str, action: str, resource: str, details: dict[str, Any]
) -> str:
    payload = json.dumps(
        [_ts_text(ts), actor, action, resource, details],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(f"{prev_hash}\n{payload}".encode()).hexdigest()


def audit(
    session: Session,
    action: str,
    actor: str,
    resource: str,
    details: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> AuditLog:
    """Append one hash-chained row in the caller's transaction (the caller commits)."""
    if session.get_bind().dialect.name == "postgresql":
        # Serialise appenders so two transactions never chain onto the same predecessor.
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PG_AUDIT_LOCK})
    prev = session.scalar(select(AuditLog.row_hash).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = prev or GENESIS_HASH
    ts = (now or datetime.now(UTC)).astimezone(UTC)
    body = dict(details or {})
    row = AuditLog(
        ts=ts,
        actor=actor,
        action=action,
        resource=resource,
        details=body,
        prev_hash=prev_hash,
        row_hash=compute_hash(prev_hash, ts, actor, action, resource, body),
    )
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    rows_checked: int
    first_bad_id: int | None = None
    reason: str | None = None


def verify_chain(session: Session) -> ChainCheck:
    """Recompute every row hash in id order and check each link to its predecessor."""
    prev_hash = GENESIS_HASH
    count = 0
    for row in session.scalars(select(AuditLog).order_by(AuditLog.id)):
        count += 1
        if row.prev_hash != prev_hash:
            return ChainCheck(False, count, row.id, "prev_hash does not match previous row")
        expected = compute_hash(
            row.prev_hash, row.ts, row.actor, row.action, row.resource, row.details
        )
        if row.row_hash != expected:
            return ChainCheck(False, count, row.id, "row content does not match row_hash")
        prev_hash = row.row_hash
    return ChainCheck(True, count)


# --- domain events ------------------------------------------------------------------------------
class DbContactLogger:
    """``ContactLogger`` (npa_contracts.providers): every inbound/outbound contact is stored with
    its time, channel, actor, content and compliance decision, and audited (RBI para 454P)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def log(self, event: ContactEvent) -> None:
        self._session.add(
            ContactEventRow(
                event_id=event.event_id,
                customer_id=event.customer_id,
                account_id=event.account_id,
                channel=event.channel,
                direction=event.direction,
                actor=event.actor,
                ts=event.ts,
                content=event.content,
                lang=event.lang,
                recorded_notice_given=event.recorded_notice_given,
                allowed=event.compliance.allowed,
                compliance=event.compliance.model_dump(mode="json"),
                outcome=event.outcome,
            )
        )
        audit(
            self._session,
            "contact.logged",
            event.actor.value,
            f"customer:{event.customer_id}",
            {
                "event_id": event.event_id,
                "channel": event.channel.value,
                "direction": event.direction,
                "allowed": event.compliance.allowed,
                "rule_ids": list(event.compliance.rule_ids),
                "recorded_notice_given": event.recorded_notice_given,
            },
        )


def audit_offer_transition(
    session: Session,
    offer_id: str,
    from_status: str | None,
    to_status: str,
    actor: str,
    approved_by: str | None = None,
) -> AuditLog:
    """Offer state change with its approver (IS/ISO/IEC 38507:2022 human oversight)."""
    return audit(
        session,
        "offer.status_changed",
        actor,
        f"offer:{offer_id}",
        {"from": from_status, "to": to_status, "approved_by": approved_by},
    )


def audit_policy_change(
    session: Session, actor: str, old_version: str | None, new_version: str, change_note: str
) -> AuditLog:
    return audit(
        session,
        "policy.changed",
        actor,
        "policy",
        {"old_version": old_version, "new_version": new_version, "change_note": change_note},
    )


def audit_login(session: Session, username: str, success: bool) -> AuditLog:
    return audit(
        session,
        "auth.login" if success else "auth.login_failed",
        username[:64],
        f"user:{username[:64]}",
        {"success": success},
    )
