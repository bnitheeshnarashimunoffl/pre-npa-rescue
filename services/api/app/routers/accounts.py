from fastapi import APIRouter

from app.fixtures import load_fixture
from app.routers._common import PROTECTED, roles
from npa_contracts.models import NextBestAction, RiskScore, SegmentResult, UpliftResult

router = APIRouter(prefix="/accounts", tags=["accounts"], **PROTECTED)
_ROLES = roles("collector", "hardship_officer", "admin")


@router.get("/{account_id}/risk", response_model=RiskScore, openapi_extra=_ROLES)
def risk(account_id: str) -> RiskScore:
    score = RiskScore.model_validate(load_fixture("risk_score.json"))
    return score.model_copy(update={"account_id": account_id})


@router.get("/{account_id}/segment", response_model=SegmentResult, openapi_extra=_ROLES)
def segment(account_id: str) -> SegmentResult:
    result = SegmentResult.model_validate(load_fixture("segment.json"))
    return result.model_copy(update={"account_id": account_id})


@router.get("/{account_id}/uplift", response_model=UpliftResult, openapi_extra=_ROLES)
def uplift(account_id: str) -> UpliftResult:
    result = UpliftResult.model_validate(load_fixture("uplift.json"))
    return result.model_copy(update={"account_id": account_id})


@router.get("/{account_id}/nba", response_model=NextBestAction, openapi_extra=_ROLES)
def nba(account_id: str) -> NextBestAction:
    action = NextBestAction.model_validate(load_fixture("nba.json"))
    return action.model_copy(update={"account_id": account_id})
