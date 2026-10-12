from fastapi import APIRouter, status

from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import RedTeamRun
from npa_contracts.models import Scorecard

router = APIRouter(prefix="/redteam", tags=["redteam"], **PROTECTED)
_ACCESS = access("admin", "auditor")


@router.post("/runs", response_model=RedTeamRun, status_code=status.HTTP_202_ACCEPTED, **_ACCESS)
def start_run() -> RedTeamRun:
    """Trigger WS7's harness in a background task."""
    not_implemented("5.1")


@router.get("/runs/{run_id}", response_model=RedTeamRun, **_ACCESS)
def get_run(run_id: str) -> RedTeamRun:
    not_implemented("5.1")


@router.get("/scorecard/latest", response_model=Scorecard, **_ACCESS)
def latest_scorecard() -> Scorecard:
    return Scorecard.model_validate(load_fixture("scorecard.json"))
