import importlib
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import orm
from app.audit import audit
from app.config import get_settings
from app.db import get_session
from app.errors import ApiError, conflict, not_found
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal
from app.services import convert
from npa_contracts.api import RedTeamRun
from npa_contracts.constants import BUSINESS_TZ
from npa_contracts.models import Scorecard

router = APIRouter(prefix="/redteam", tags=["redteam"], **PROTECTED)
_ACCESS = access("admin", "auditor")
log = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_session)]


def _harness() -> Any:
    """WS7's ``npa_redteam.harness`` module, or None when it is not installed."""
    try:
        harness = importlib.import_module("npa_redteam.harness")
    except ImportError:
        return None
    return harness if callable(getattr(harness, "run", None)) else None


def run_id_for(now: datetime) -> str:
    """``RT-YYYYMMDD-HHMM`` in IST - the id WS7's harness gives a run started at ``now``."""
    return now.astimezone(ZoneInfo(BUSINESS_TZ)).strftime("RT-%Y%m%d-%H%M")


def _run_harness(
    sessions: sessionmaker[Session], run_id: str, started: datetime, token: str
) -> None:
    """Background task: run WS7's harness and store its scorecard and results.

    Uses WS7's published signature ``run(api_base_url=None, token=None, suites=None,
    langs=("en", "ta", "hi"), seed=42, *, target=None, cases_dir=None, now=None, lexicon=None)
    -> Scorecard``. ``REDTEAM_MODE=library`` (default) attacks the providers in-process;
    ``REDTEAM_MODE=api`` attacks this API over HTTP with the caller's token (WS7 phase 2).
    """
    settings = get_settings()
    with sessions() as s, s.begin():
        row = s.get(orm.RedTeamRun, run_id)
        assert row is not None
        row.status = "running"
    api = settings.redteam_mode == "api"
    error: str | None = None
    scorecard: Scorecard | None = None
    try:
        raw = _harness().run(
            settings.api_base_url if api else None,
            token if api else None,
            now=started,
        )
        scorecard = Scorecard.model_validate(raw)
        if scorecard.run_id != run_id:  # keep the stored run and its results consistent
            log.warning(
                "harness run_id %s != %s; storing under %s", scorecard.run_id, run_id, run_id
            )
            scorecard = scorecard.model_copy(
                update={
                    "run_id": run_id,
                    "results": [r.model_copy(update={"run_id": run_id}) for r in scorecard.results],
                }
            )
    except Exception as exc:  # third-party code: record the failure, never crash the API
        log.exception("red-team run %s failed", run_id)
        error = f"{type(exc).__name__}: {exc}"[:500]
    with sessions() as s, s.begin():
        row = s.get(orm.RedTeamRun, run_id)
        assert row is not None
        row.status = "completed" if scorecard is not None else "failed"
        row.finished_at = datetime.now(UTC)
        if scorecard is not None:
            row.scorecard = scorecard.model_dump(mode="json")
            for r in scorecard.results:
                s.add(
                    orm.RedTeamResult(
                        run_id=run_id,
                        test_id=r.test_id,
                        category=r.category,
                        lang=r.lang,
                        input=r.input,
                        output=r.output,
                        passed=r.passed,
                        severity=r.severity,
                        rule_refs=r.rule_refs,
                        bis_refs=r.bis_refs,
                        notes=r.notes,
                    )
                )
        details: dict[str, Any] = {"status": row.status, "mode": settings.redteam_mode}
        if scorecard is not None:
            details["totals"] = dict(scorecard.totals)
        if error:
            details["error"] = error
        audit(s, "redteam.run_finished", "system", f"redteam:{run_id}", details)


def _run_model(row: orm.RedTeamRun) -> RedTeamRun:
    return RedTeamRun(
        run_id=row.run_id,
        status=row.status,  # type: ignore[arg-type]
        created_at=convert.utc(row.created_at),
        finished_at=convert.utc_or_none(row.finished_at),
        scorecard=Scorecard.model_validate(row.scorecard) if row.scorecard else None,
    )


@router.post("/runs", response_model=RedTeamRun, status_code=status.HTTP_202_ACCEPTED, **_ACCESS)
def start_run(
    request: Request,
    background: BackgroundTasks,
    principal: CurrentPrincipal,
    session: DbSession,
) -> RedTeamRun:
    """Trigger WS7's harness in a background task."""
    if _harness() is None:
        raise ApiError(
            501,
            "REDTEAM_UNAVAILABLE",
            "The red-team harness (WS7 npa_redteam) is not installed yet.",
        )
    now = datetime.now(UTC)
    row = orm.RedTeamRun(
        run_id=run_id_for(now),
        status="queued",
        created_by=principal.username,
        created_at=now,
    )
    if session.get(orm.RedTeamRun, row.run_id) is not None:
        conflict("A red-team run was already started this minute.", {"run_id": row.run_id})
    session.add(row)
    audit(
        session,
        "redteam.run_started",
        principal.username,
        f"redteam:{row.run_id}",
        {"mode": get_settings().redteam_mode},
    )
    session.commit()
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    background.add_task(_run_harness, request.app.state.sessionmaker, row.run_id, now, token)
    return _run_model(row)


@router.get("/runs/{run_id}", response_model=RedTeamRun, **_ACCESS)
def get_run(run_id: str, session: DbSession) -> RedTeamRun:
    row = session.get(orm.RedTeamRun, run_id)
    if row is None:
        not_found("Red-team run", run_id)
    return _run_model(row)


@router.get("/scorecard/latest", response_model=Scorecard, **_ACCESS)
def latest_scorecard(session: DbSession, response: Response) -> Scorecard:
    row = session.scalars(
        select(orm.RedTeamRun)
        .where(orm.RedTeamRun.status == "completed")
        .order_by(orm.RedTeamRun.finished_at.desc())
        .limit(1)
    ).first()
    if row is None or row.scorecard is None:
        # No run yet: the sample scorecard, clearly marked so it is never mistaken for a run.
        response.headers["X-Data-Source"] = "fixture"
        return Scorecard.model_validate(load_fixture("scorecard.json"))
    return Scorecard.model_validate(row.scorecard)
