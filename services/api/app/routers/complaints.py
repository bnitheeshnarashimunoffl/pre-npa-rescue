from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import orm
from app.audit import audit
from app.db import get_session
from app.errors import bad_request, not_found
from app.providers import Deps
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal, Principal
from app.services import convert
from npa_contracts.api import ComplaintCreateRequest, ComplaintUpdateRequest
from npa_contracts.enums import Role
from npa_contracts.models import Complaint

router = APIRouter(prefix="/complaints", tags=["complaints"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]


def _subject(principal: Principal, requested: str | None) -> str:
    """Customers always file for themselves; staff must name the customer."""
    if principal.role is Role.CUSTOMER:
        assert principal.customer_id is not None
        return principal.customer_id
    if not requested:
        bad_request("CUSTOMER_REQUIRED", "customer_id is required when staff file a complaint.")
    return requested


@router.post(
    "",
    response_model=Complaint,
    status_code=status.HTTP_201_CREATED,
    **access("customer", "hardship_officer", "admin"),
)
def open_complaint(
    body: ComplaintCreateRequest, principal: CurrentPrincipal, providers: Deps
) -> Complaint:
    """Open a complaint with docket number and 30-day SLA (IS/ISO 10002:2018)."""
    customer_id = _subject(principal, body.customer_id)
    try:
        return providers.complaints.open(customer_id, body.category, body.text, body.lang)
    except KeyError:
        not_found("Customer", customer_id)


def _owned(session: Session, docket_no: str, principal: Principal) -> orm.Complaint:
    row = session.get(orm.Complaint, docket_no)
    if row is None or (
        principal.role is Role.CUSTOMER and row.customer_id != principal.customer_id
    ):
        not_found("Complaint", docket_no)
    return row


@router.get(
    "/{docket_no}",
    response_model=Complaint,
    **access("customer", "hardship_officer", "admin", "auditor"),
)
def get_complaint(docket_no: str, principal: CurrentPrincipal, session: DbSession) -> Complaint:
    return convert.complaint(_owned(session, docket_no, principal))


@router.patch("/{docket_no}", response_model=Complaint, **access("hardship_officer", "admin"))
def update_complaint(
    docket_no: str, body: ComplaintUpdateRequest, principal: CurrentPrincipal, session: DbSession
) -> Complaint:
    row = _owned(session, docket_no, principal)
    changes: dict[str, object] = {}
    if body.status is not None and body.status != row.status:
        changes["status"] = {"from": str(row.status), "to": str(body.status)}
        row.status = body.status
    if body.escalation_level is not None and body.escalation_level != row.escalation_level:
        changes["escalation_level"] = {"from": row.escalation_level, "to": body.escalation_level}
        row.escalation_level = body.escalation_level
    if body.note:
        changes["note"] = body.note
    row.updated_at = datetime.now(UTC)
    audit(session, "complaint.updated", principal.username, f"complaint:{docket_no}", changes)
    session.commit()
    return convert.complaint(row)
