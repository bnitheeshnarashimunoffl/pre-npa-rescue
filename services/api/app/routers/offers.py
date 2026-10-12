from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import orm
from app.audit import audit_offer_transition
from app.db import get_session
from app.errors import conflict, not_found
from app.providers import Deps
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal, Principal
from app.services import convert
from npa_contracts.api import OfferCreateRequest, OfferDecisionRequest
from npa_contracts.enums import Actor, OfferStatus, Role
from npa_contracts.models import Offer

router = APIRouter(prefix="/offers", tags=["offers"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]

# Offer lifecycle. Approval needs a hardship officer or admin (IS/ISO/IEC 38507:2022).
_FROM: dict[OfferStatus, set[OfferStatus]] = {
    OfferStatus.APPROVED: {OfferStatus.PROPOSED},
    OfferStatus.ACCEPTED: {OfferStatus.APPROVED, OfferStatus.PRESENTED},
    OfferStatus.REJECTED: {OfferStatus.PROPOSED, OfferStatus.APPROVED, OfferStatus.PRESENTED},
}
_TERMINAL = {OfferStatus.ACCEPTED, OfferStatus.REJECTED, OfferStatus.EXPIRED}


def _actor(principal: Principal) -> Actor:
    return {
        Role.CUSTOMER: Actor.CUSTOMER,
        Role.HARDSHIP_OFFICER: Actor.HARDSHIP_OFFICER,
        Role.COLLECTOR: Actor.AGENT,
    }.get(principal.role, Actor.SYSTEM)


@router.post(
    "",
    response_model=Offer,
    status_code=status.HTTP_201_CREATED,
    **access("hardship_officer", "admin", "system"),
)
def create_offer(
    body: OfferCreateRequest, principal: CurrentPrincipal, session: DbSession, providers: Deps
) -> Offer:
    """Propose an offer from a policy-permitted relief option."""
    if session.get(orm.Customer, body.customer_id) is None:
        not_found("Customer", body.customer_id)
    try:
        offer = providers.policy.propose_offer(body.customer_id, body.option_id, _actor(principal))
    except KeyError:
        not_found("Relief option", body.option_id)
    session.add(convert.offer_row(offer))
    audit_offer_transition(
        session, offer.offer_id, None, offer.status, principal.username, offer.approved_by
    )
    session.commit()
    return offer


def _transition(
    session: Session,
    offer_id: str,
    to: OfferStatus,
    principal: Principal,
    body: OfferDecisionRequest | None,
) -> Offer:
    row = session.get(orm.Offer, offer_id)
    if row is None or (
        principal.role is Role.CUSTOMER and row.customer_id != principal.customer_id
    ):
        not_found("Offer", offer_id)
    now = datetime.now(UTC)
    current = OfferStatus(row.status)
    if current not in _TERMINAL and convert.utc(row.expires_at) <= now:
        row.status, row.updated_at = OfferStatus.EXPIRED, now
        audit_offer_transition(session, offer_id, current, OfferStatus.EXPIRED, "system")
        session.commit()
        conflict("Offer has expired.", {"offer_id": offer_id})
    if current not in _FROM[to]:
        conflict(
            f"Offer cannot move from {current.value} to {to.value}.",
            {"offer_id": offer_id, "status": current.value},
        )
    row.status, row.updated_at = to, now
    if to is OfferStatus.APPROVED:
        row.approved_by = principal.username
    audit_offer_transition(
        session,
        offer_id,
        current,
        to,
        principal.username,
        row.approved_by,
        note=body.note if body else None,
    )
    session.commit()
    return convert.offer(row)


@router.post("/{offer_id}/approve", response_model=Offer, **access("hardship_officer", "admin"))
def approve_offer(
    offer_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
    body: OfferDecisionRequest | None = None,
) -> Offer:
    """Human approval (IS/ISO/IEC 38507:2022); records ``approved_by``."""
    return _transition(session, offer_id, OfferStatus.APPROVED, principal, body)


@router.post("/{offer_id}/accept", response_model=Offer, **access("customer"))
def accept_offer(
    offer_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
    body: OfferDecisionRequest | None = None,
) -> Offer:
    return _transition(session, offer_id, OfferStatus.ACCEPTED, principal, body)


@router.post(
    "/{offer_id}/reject",
    response_model=Offer,
    **access("customer", "hardship_officer", "admin"),
)
def reject_offer(
    offer_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
    body: OfferDecisionRequest | None = None,
) -> Offer:
    return _transition(session, offer_id, OfferStatus.REJECTED, principal, body)
