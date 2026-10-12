from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import orm
from app.db import get_session
from app.errors import not_found
from app.providers import Deps
from app.routers._common import PROTECTED, access
from app.services import convert
from npa_contracts.api import ContactCheckRequest
from npa_contracts.models import ComplianceDecision, ContactEvent

router = APIRouter(prefix="/contacts", tags=["contacts"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]


@router.post("/check", response_model=ComplianceDecision, **access("system", "collector"))
def check_contact(body: ContactCheckRequest, providers: Deps) -> ComplianceDecision:
    """Compliance-guard pre-check (RBI RBC Directions para 454Y, 454Z)."""
    return providers.compliance.check_contact(body.customer_id, body.channel, body.at, body.actor)


@router.get("", response_model=list[ContactEvent], **access("collector", "auditor"))
def list_contacts(customer_id: str, session: DbSession) -> list[ContactEvent]:
    """Contact log for a customer (RBI RBC Directions para 454P)."""
    if session.get(orm.Customer, customer_id) is None:
        not_found("Customer", customer_id)
    rows = session.scalars(
        select(orm.ContactEvent)
        .where(orm.ContactEvent.customer_id == customer_id)
        .order_by(orm.ContactEvent.ts)
    )
    return [convert.contact_event(r) for r in rows]
