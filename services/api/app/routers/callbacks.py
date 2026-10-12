from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import orm
from app.db import get_session
from app.errors import bad_request, conflict, not_found
from app.providers import Deps
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal
from app.services import convert
from app.services.records import SlotUnavailableError
from npa_contracts.api import CallbackCreateRequest
from npa_contracts.enums import Role
from npa_contracts.models import Callback

router = APIRouter(prefix="/callbacks", tags=["callbacks"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]


@router.post(
    "",
    response_model=Callback,
    status_code=status.HTTP_201_CREATED,
    **access("customer", "hardship_officer"),
)
def book_callback(
    body: CallbackCreateRequest, principal: CurrentPrincipal, session: DbSession, providers: Deps
) -> Callback:
    """Book a handoff callback inside 08:00-19:00 IST (RBI RBC Directions para 454Y(4))."""
    if principal.role is Role.CUSTOMER:
        customer_id = principal.customer_id
    elif body.customer_id:
        customer_id = body.customer_id
    else:
        bad_request("CUSTOMER_REQUIRED", "customer_id is required when staff book a callback.")
    assert customer_id is not None
    if session.get(orm.Customer, customer_id) is None:
        not_found("Customer", customer_id)
    try:
        return providers.callbacks.book(customer_id, body.slot_start, body.role, body.summary)
    except SlotUnavailableError:
        conflict(
            "That slot is not available. Callbacks are 08:00-19:00 IST, in the future, "
            "and not already booked.",
            {"slot_start": body.slot_start.isoformat()},
        )


@router.get("", response_model=list[Callback], **access("customer", "hardship_officer"))
def list_callbacks(
    principal: CurrentPrincipal, session: DbSession, role: Role | None = None
) -> list[Callback]:
    stmt = select(orm.Callback).order_by(orm.Callback.slot_start)
    if principal.role is Role.CUSTOMER:
        stmt = stmt.where(orm.Callback.customer_id == principal.customer_id)
    if role is not None:
        stmt = stmt.where(orm.Callback.role == role)
    return [convert.callback(r) for r in session.scalars(stmt)]
