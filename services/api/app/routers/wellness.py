from typing import Annotated, Final

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import orm
from app.config import get_settings
from app.db import get_session
from app.errors import not_found
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal, ensure_customer_scope
from npa_contracts.api import WellnessRequest, WellnessResult, WellnessScenario
from npa_contracts.enums import Bucket

router = APIRouter(prefix="/wellness", tags=["wellness"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]

# ILLUSTRATIVE ONLY. Not a credit-score formula and not bureau data: coarse bands so a customer
# can compare "pay on a plan now" with "reach NPA". Months are rough recovery horizons.
PAY_PLAN_BANDS: Final[dict[Bucket, tuple[str, int]]] = {
    Bucket.CURRENT: ("good", 0),
    Bucket.SMA0: ("good", 3),
    Bucket.SMA1: ("fair", 6),
    Bucket.SMA2: ("fair", 9),
    Bucket.NPA: ("poor", 18),
}
REACH_NPA_BAND: Final = ("poor", 36)


@router.post("/simulate", response_model=WellnessResult, **access("customer"))
def simulate(
    body: WellnessRequest, principal: CurrentPrincipal, session: DbSession
) -> WellnessResult:
    """Illustrative pay-now vs NPA credit impact. Not a real credit-score formula."""
    ensure_customer_scope(principal, body.customer_id)
    customer = session.get(orm.Customer, body.customer_id)
    if customer is None:
        not_found("Customer", body.customer_id)
    latest = session.scalars(
        select(orm.AccountMonth)
        .where(orm.AccountMonth.account_id == customer.account_id)
        .order_by(orm.AccountMonth.month.desc())
        .limit(1)
    ).first()
    nba = session.get(orm.NBA, (customer.account_id, get_settings().as_of_month))
    bucket = Bucket(latest.bucket if latest else nba.bucket if nba else Bucket.CURRENT)
    plan_band, plan_months = PAY_PLAN_BANDS[bucket]
    npa_band, npa_months = REACH_NPA_BAND
    return WellnessResult(
        customer_id=body.customer_id,
        scenarios=[
            WellnessScenario(
                name="pay_plan",
                score_band=plan_band,
                months_to_recover=plan_months,
                notes_key="wellness.pay_plan.explanation",
            ),
            WellnessScenario(
                name="reach_npa",
                score_band=npa_band,
                months_to_recover=npa_months,
                notes_key="wellness.reach_npa.explanation",
            ),
        ],
        disclaimer_key="wellness.disclaimer.illustrative",
    )
