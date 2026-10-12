"""DB-backed implementations of the WS5 provider protocols (``npa_contracts.providers``):
``ComplaintSink``, ``CallbackScheduler`` and ``CustomerContextProvider``.

They are long-lived (the chat engine holds them), so each call opens its own short session from
the app's session factory and commits it.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app import orm
from app.audit import audit
from app.services import convert
from npa_contracts.constants import BUSINESS_TZ, COMPLAINT_SLA_DAYS, CONTACT_WINDOW
from npa_contracts.enums import Actor, Channel, ComplaintStatus, Lang, Role
from npa_contracts.models import Callback, Complaint
from npa_contracts.providers import ComplianceProvider, PolicyProvider

SLOT_MINUTES = 30
SLOT_CAPACITY = 4  # hardship-officer callbacks bookable in the same half hour


class SlotUnavailableError(ValueError):
    """The requested callback slot is outside the contact window, in the past or full."""


class DbComplaintSink:
    """IS/ISO 10002:2018: docket ``CMP-YYYYMMDD-NNNN``, 30-day SLA, grievance officer details
    (RBI RBC Directions para 454AA) on every complaint."""

    def __init__(self, sessions: sessionmaker[Session], policy: PolicyProvider) -> None:
        self._sessions = sessions
        self._policy = policy

    def open(self, customer_id: str, category: str, text: str, lang: Lang) -> Complaint:
        now = datetime.now(UTC)
        prefix = f"CMP-{now:%Y%m%d}-"
        with self._sessions() as s, s.begin():
            if s.get(orm.Customer, customer_id) is None:
                raise KeyError(customer_id)
            n = s.scalar(select(func.count()).where(orm.Complaint.docket_no.startswith(prefix)))
            row = orm.Complaint(
                docket_no=f"{prefix}{(n or 0) + 1:04d}",
                customer_id=customer_id,
                category=category,
                text=text,
                lang=lang,
                status=ComplaintStatus.OPEN,
                escalation_level=0,
                created_at=now,
                sla_due_at=now + timedelta(days=COMPLAINT_SLA_DAYS),
                grievance_officer=self._policy.grievance_officer().model_dump(),
            )
            s.add(row)
            s.flush()
            audit(
                s,
                "complaint.opened",
                customer_id,
                f"complaint:{row.docket_no}",
                {"category": category, "lang": str(lang)},
            )
            return convert.complaint(row)


class DbCallbackScheduler:
    """Half-hour hardship-officer callback slots inside the contact window (RBI RBC Directions
    para 454Y(4)), each confirmed by the ``ComplianceProvider`` (do-not-contact, quiet times)."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        compliance: ComplianceProvider,
        *,
        tz: str = BUSINESS_TZ,
        clock: Any = None,
    ) -> None:
        self._sessions = sessions
        self._compliance = compliance
        self._tz = ZoneInfo(tz)
        self._clock = clock or (lambda: datetime.now(UTC))

    def _candidates(self, day: date) -> list[datetime]:
        start, end = CONTACT_WINDOW
        slot = datetime.combine(day, start, self._tz)
        last = datetime.combine(day, end, self._tz) - timedelta(minutes=SLOT_MINUTES)
        out = []
        while slot <= last:
            out.append(slot.astimezone(UTC))
            slot += timedelta(minutes=SLOT_MINUTES)
        return out

    def available_slots(self, customer_id: str, day: date) -> list[tuple[datetime, datetime]]:
        now = self._clock()
        with self._sessions() as s:
            booked = s.execute(
                select(orm.Callback.slot_start, orm.Callback.customer_id).where(
                    orm.Callback.slot_start >= datetime.combine(day, time(0), self._tz),
                    orm.Callback.slot_start
                    < datetime.combine(day, time(0), self._tz) + timedelta(days=1),
                )
            ).all()
        load: dict[datetime, int] = {}
        mine: set[datetime] = set()
        for slot_start, cid in booked:
            key = convert.utc(slot_start)
            load[key] = load.get(key, 0) + 1
            if cid == customer_id:
                mine.add(key)
        free = []
        for start in self._candidates(day):
            if start <= now or start in mine or load.get(start, 0) >= SLOT_CAPACITY:
                continue
            decision = self._compliance.check_contact(
                customer_id, Channel.CALL, start, Actor.HARDSHIP_OFFICER
            )
            if decision.allowed:
                free.append((start, start + timedelta(minutes=SLOT_MINUTES)))
        return free

    def book(self, customer_id: str, slot_start: datetime, role: Role, summary: str) -> Callback:
        start = slot_start.astimezone(UTC)
        day = start.astimezone(self._tz).date()
        if start not in {s for s, _ in self.available_slots(customer_id, day)}:
            raise SlotUnavailableError(f"slot {start.isoformat()} is not available")
        with self._sessions() as s, s.begin():
            row = orm.Callback(
                callback_id=f"CB-{uuid.uuid4()}",
                customer_id=customer_id,
                role=role,
                slot_start=start,
                slot_end=start + timedelta(minutes=SLOT_MINUTES),
                summary=summary,
                created_at=self._clock(),
            )
            s.add(row)
            s.flush()
            audit(
                s,
                "callback.booked",
                customer_id,
                f"callback:{row.callback_id}",
                {"slot_start": start.isoformat(), "role": str(role)},
            )
            return convert.callback(row)


class DbCustomerContext:
    """Minimised context for the chatbot (no protected attributes, masked contact data)."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def context(self, customer_id: str) -> dict[str, Any]:
        with self._sessions() as s:
            c = s.get(orm.Customer, customer_id)
            if c is None:
                raise KeyError(customer_id)
            latest = s.scalars(
                select(orm.AccountMonth)
                .where(orm.AccountMonth.account_id == c.account_id)
                .order_by(orm.AccountMonth.month.desc())
                .limit(1)
            ).first()
            return {
                "customer_id": c.customer_id,
                "account_id": c.account_id,
                "first_name": c.full_name.split()[0],
                "language_pref": str(c.language_pref),
                "dependants": c.dependants,
                "has_card_insurance": c.has_card_insurance,
                "insurance_cover_type": c.insurance_cover_type,
                "preferred_contact_window": c.preferred_contact_window,
                "bucket": str(latest.bucket) if latest else None,
                "dpd": latest.dpd if latest else None,
                "total_due_paise": latest.total_due_paise if latest else None,
                "min_due_paise": latest.min_due_paise if latest else None,
            }
