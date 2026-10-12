from fastapi import APIRouter

from app.config import get_settings
from app.errors import not_found
from app.providers import Deps
from app.routers._common import PROTECTED, access
from npa_contracts.models import NextBestAction, RiskScore, SegmentResult, UpliftResult

router = APIRouter(prefix="/accounts", tags=["accounts"], **PROTECTED)
_ACCESS = access("collector", "hardship_officer", "admin")


def _month() -> str:
    return get_settings().as_of_month


@router.get("/{account_id}/risk", response_model=RiskScore, **_ACCESS)
def risk(account_id: str, providers: Deps) -> RiskScore:
    try:
        return providers.risk.risk(account_id, _month())
    except KeyError:
        not_found("Account", account_id)


@router.get("/{account_id}/segment", response_model=SegmentResult, **_ACCESS)
def segment(account_id: str, providers: Deps) -> SegmentResult:
    try:
        return providers.risk.segment(account_id, _month())
    except KeyError:
        not_found("Account", account_id)


@router.get("/{account_id}/uplift", response_model=UpliftResult, **_ACCESS)
def uplift(account_id: str, providers: Deps) -> UpliftResult:
    try:
        return providers.risk.uplift(account_id, _month())
    except KeyError:
        not_found("Account", account_id)


@router.get("/{account_id}/nba", response_model=NextBestAction, **_ACCESS)
def nba(account_id: str, providers: Deps) -> NextBestAction:
    try:
        return providers.nba.next_best_action(account_id, _month())
    except KeyError:
        not_found("Account", account_id)
