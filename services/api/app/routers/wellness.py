from fastapi import APIRouter

from app.errors import not_implemented
from app.routers._common import PROTECTED, roles
from npa_contracts.api import WellnessRequest, WellnessResult

router = APIRouter(prefix="/wellness", tags=["wellness"], **PROTECTED)


@router.post("/simulate", response_model=WellnessResult, openapi_extra=roles("customer"))
def simulate(body: WellnessRequest) -> WellnessResult:
    """Illustrative pay-now vs NPA credit impact. Not a real credit-score formula."""
    not_implemented("5.1")
