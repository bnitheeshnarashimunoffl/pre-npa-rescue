from fastapi import APIRouter

from app.errors import not_found, not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal, ensure_customer_scope
from npa_contracts.api import CustomerProfile
from npa_contracts.models import ReliefOption

router = APIRouter(prefix="/customers", tags=["customers"], **PROTECTED)

_RELIEF_FIXTURES = {
    "CUST-DEMO-PRIYA": "relief_options_priya.json",
    "CUST-DEMO-RAVI": "relief_options_ravi.json",
}


@router.get(
    "/{customer_id}",
    response_model=CustomerProfile,
    **access("customer", "collector", "hardship_officer", "admin"),
)
def get_customer(customer_id: str, principal: CurrentPrincipal) -> CustomerProfile:
    """Customer profile, minimised per role (RBI para 454O, DPDP). Customers see only self."""
    ensure_customer_scope(principal, customer_id)
    not_implemented("5.1")


@router.get(
    "/{customer_id}/relief-options",
    response_model=list[ReliefOption],
    **access("customer", "hardship_officer"),
)
def relief_options(customer_id: str, principal: CurrentPrincipal) -> list[ReliefOption]:
    """Policy-permitted relief options given the customer affordability."""
    ensure_customer_scope(principal, customer_id)
    name = _RELIEF_FIXTURES.get(customer_id)
    if name is None:
        not_found("Customer", customer_id)
    return [ReliefOption.model_validate(o) for o in load_fixture(name)]
