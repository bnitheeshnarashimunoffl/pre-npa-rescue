import json
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app import orm
from app.config import get_settings
from app.db import get_session
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from app.services.convert import utc
from npa_contracts.api import KpiReport, SimulationMetrics
from npa_contracts.constants import CONTACT_WINDOW
from npa_contracts.enums import ComplaintStatus

router = APIRouter(prefix="/metrics", tags=["metrics"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]
_OPEN = (ComplaintStatus.OPEN, ComplaintStatus.ACKNOWLEDGED, ComplaintStatus.ESCALATED)


@router.get(
    "/simulation",
    response_model=SimulationMetrics,
    **access("collector", "hardship_officer", "admin", "auditor"),
)
def simulation(response: Response) -> SimulationMetrics:
    """NPA reduction vs the call-everyone baseline (from WS2's policy_simulation.json)."""
    report = get_settings().reports_dir / "policy_simulation.json"
    if report.exists():
        try:
            return SimulationMetrics.model_validate(json.loads(report.read_text(encoding="utf-8")))
        except (ValueError, ValidationError):
            pass  # fall through to the fixture, flagged below
    response.headers["X-Data-Source"] = "fixture"
    return SimulationMetrics.model_validate(load_fixture("simulation_metrics.json"))


@router.get("/kpis", response_model=KpiReport, **access("collector", "admin"))
def kpis(session: DbSession) -> KpiReport:
    """Contact-centre KPIs (IS/ISO 18295-1/-2:2017)."""
    now = datetime.now(UTC)
    tz = ZoneInfo(get_settings().tz_business)
    contacts = session.scalar(select(func.count()).select_from(orm.ContactEvent)) or 0
    accounts = session.scalar(select(func.count(distinct(orm.ContactEvent.account_id)))) or 0
    outbound = list(
        session.scalars(select(orm.ContactEvent.ts).where(orm.ContactEvent.direction == "outbound"))
    )
    start, end = CONTACT_WINDOW
    in_window = sum(1 for ts in outbound if start <= utc(ts).astimezone(tz).time() < end)
    open_complaints = list(
        session.scalars(select(orm.Complaint.sla_due_at).where(orm.Complaint.status.in_(_OPEN)))
    )
    sessions_total = session.scalar(select(func.count()).select_from(orm.ChatSession)) or 0
    chatted = set(session.scalars(select(distinct(orm.ChatSession.customer_id))))
    handed_off = set(session.scalars(select(distinct(orm.Callback.customer_id)))) & chatted
    turns = session.scalar(select(func.count()).select_from(orm.ChatTurn)) or 0
    return KpiReport(
        as_of=now,
        contacts_per_account=round(contacts / accounts, 2) if accounts else 0.0,
        in_window_share=round(in_window / len(outbound), 4) if outbound else 1.0,
        complaints_open=len(open_complaints),
        complaints_breaching_sla=sum(1 for due in open_complaints if utc(due) < now),
        handoff_rate=round(len(handed_off) / len(chatted), 4) if chatted else 0.0,
        avg_turns_to_resolution=round(turns / sessions_total, 2) if sessions_total else 0.0,
        standard_refs=["IS/ISO 18295-1:2017", "IS/ISO 18295-2:2017", "RBI RBC para 454Y(4)"],
    )
