from fastapi import APIRouter

from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import KpiReport, SimulationMetrics

router = APIRouter(prefix="/metrics", tags=["metrics"], **PROTECTED)


@router.get(
    "/simulation",
    response_model=SimulationMetrics,
    **access("collector", "hardship_officer", "admin", "auditor"),
)
def simulation() -> SimulationMetrics:
    """NPA reduction vs the call-everyone baseline (from WS2's policy_simulation.json)."""
    return SimulationMetrics.model_validate(load_fixture("simulation_metrics.json"))


@router.get("/kpis", response_model=KpiReport, **access("collector", "admin"))
def kpis() -> KpiReport:
    """Contact-centre KPIs (IS/ISO 18295-1/-2:2017)."""
    not_implemented("5.1")
