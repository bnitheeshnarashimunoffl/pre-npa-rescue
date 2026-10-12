from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import orm
from app.db import get_session
from app.errors import not_found
from app.minimise import minimise_profile
from app.providers import Deps
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal, ensure_customer_scope
from app.services import convert
from npa_contracts.api import CustomerProfile
from npa_contracts.models import Affordability, ReliefOption

router = APIRouter(prefix="/customers", tags=["customers"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]


@router.get(
    "/{customer_id}",
    response_model=CustomerProfile,
    **access("customer", "collector", "hardship_officer", "admin"),
)
def get_customer(
    customer_id: str, principal: CurrentPrincipal, session: DbSession
) -> CustomerProfile:
    """Customer profile, minimised per role (RBI para 454O, DPDP). Customers see only self."""
    ensure_customer_scope(principal, customer_id)
    row = session.get(orm.Customer, customer_id)
    if row is None:
        not_found("Customer", customer_id)
    return minimise_profile(convert.customer_profile(row), principal)


def estimated_affordability(row: orm.Customer) -> Affordability:
    """Without a chat declaration the policy engine works from an estimate, which the chatbot
    must confirm with the customer before offering a plan (WS3 relief_calc)."""
    return Affordability(
        customer_id=row.customer_id,
        declared_income_paise=None,
        declared_expenses_paise=None,
        dependants=row.dependants,
        max_monthly_payment_paise=0,
        source="estimated",
    )


@router.get(
    "/{customer_id}/relief-options",
    response_model=list[ReliefOption],
    **access("customer", "hardship_officer"),
)
def relief_options(
    customer_id: str, principal: CurrentPrincipal, session: DbSession, providers: Deps
) -> list[ReliefOption]:
    """Policy-permitted relief options given the customer affordability."""
    ensure_customer_scope(principal, customer_id)
    row = session.get(orm.Customer, customer_id)
    if row is None:
        not_found("Customer", customer_id)
    return providers.policy.relief_options(customer_id, estimated_affordability(row))
