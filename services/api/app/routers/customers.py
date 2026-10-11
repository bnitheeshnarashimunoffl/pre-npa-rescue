from fastapi import APIRouter

from app.errors import not_found, not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, roles
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
    openapi_extra=roles("customer", "collector", "hardship_officer", "admin"),
)
def get_customer(customer_id: str) -> CustomerProfile:
    """Customer profile, minimised per role (RBI para 454O, DPDP). Customers see only self."""
    not_implemented("5.1")


@router.get(
    "/{customer_id}/relief-options",
    response_model=list[ReliefOption],
    openapi_extra=roles("customer", "hardship_officer"),
)
def relief_options(customer_id: str) -> list[ReliefOption]:
    """Policy-permitted relief options given the customer affordability."""
    name = _RELIEF_FIXTURES.get(customer_id)
    if name is None:
        not_found("Customer", customer_id)
    return [ReliefOption.model_validate(o) for o in load_fixture(name)]
