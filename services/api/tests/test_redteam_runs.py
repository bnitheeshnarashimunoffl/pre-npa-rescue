"""Red-team runs: POST /redteam/runs runs WS7's harness in a background task; GET returns the
status and scorecard. The harness is faked with WS7's published signature; a contract check
against the real `npa_redteam.harness.run` runs whenever WS7's package is installed."""

import importlib
import inspect
import json
import sys
import types
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import orm
from app.config import get_settings
from app.routers.redteam import run_id_for
from npa_contracts.models import Scorecard
from tests.conftest import CONTRACTS_DIR, bearer_for

API = "/api/v1/redteam"
ADMIN = bearer_for("admin")
AUDITOR = bearer_for("auditor")


def _fake_harness(calls: list[dict[str, Any]], *, fail: Exception | None = None) -> Any:
    sample = json.loads((CONTRACTS_DIR / "fixtures" / "scorecard.json").read_text("utf-8"))

    def run(  # WS7's published signature (redteam/src/npa_redteam/harness.py)
        api_base_url: str | None = None,
        token: str | None = None,
        suites: Any = None,
        langs: Any = ("en", "ta", "hi"),
        seed: int = 42,
        *,
        target: Any = None,
        cases_dir: Any = None,
        now: datetime | None = None,
        lexicon: Any = None,
    ) -> Scorecard:
        calls.append({"api_base_url": api_base_url, "token": token, "now": now})
        if fail is not None:
            raise fail
        assert now is not None
        run_id = run_id_for(now)  # what WS7's new_run_id() computes
        card = Scorecard.model_validate(sample)
        return card.model_copy(
            update={
                "run_id": run_id,
                "created_at": now,
                "results": [r.model_copy(update={"run_id": run_id}) for r in card.results],
            }
        )

    module = types.ModuleType("npa_redteam.harness")
    module.run = run  # type: ignore[attr-defined]
    return module


@pytest.fixture
def client(app_db: tuple[FastAPI, TestClient]) -> TestClient:
    return app_db[1]


def test_run_completes_and_is_stored(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setitem(sys.modules, "npa_redteam.harness", _fake_harness(calls))
    started = client.post(f"{API}/runs", headers=ADMIN)
    assert started.status_code == 202
    run = started.json()
    assert run["status"] == "queued" and run["run_id"].startswith("RT-")
    # TestClient runs background tasks before returning, so the run is finished now
    done = client.get(f"{API}/runs/{run['run_id']}", headers=AUDITOR).json()
    assert done["status"] == "completed" and done["finished_at"] is not None
    assert done["scorecard"]["run_id"] == run["run_id"]
    assert len(calls) == 1
    # library mode by default: no URL or token handed to the harness
    assert calls[0]["api_base_url"] is None and calls[0]["token"] is None
    assert run_id_for(calls[0]["now"]) == run["run_id"]
    latest = client.get(f"{API}/scorecard/latest", headers=AUDITOR)
    assert "X-Data-Source" not in latest.headers
    assert latest.json()["run_id"] == run["run_id"]
    with Session(engine) as s:
        n = s.scalar(select(func.count()).select_from(orm.RedTeamResult))
        assert n == len(done["scorecard"]["results"]) > 0
        finished = s.scalars(
            select(orm.AuditLog).where(orm.AuditLog.action == "redteam.run_finished")
        ).one()
        assert finished.details["status"] == "completed" and finished.details["mode"] == "library"


def test_api_mode_passes_base_url_and_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setitem(sys.modules, "npa_redteam.harness", _fake_harness(calls))
    monkeypatch.setattr(get_settings(), "redteam_mode", "api")
    client.post(f"{API}/runs", headers=ADMIN)
    assert calls[0]["api_base_url"] == get_settings().api_base_url
    assert calls[0]["token"] == ADMIN["Authorization"].removeprefix("Bearer ")


def test_harness_failure_marks_run_failed(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    boom = NotImplementedError("API mode is not implemented yet; use library mode")
    monkeypatch.setitem(sys.modules, "npa_redteam.harness", _fake_harness(calls, fail=boom))
    run = client.post(f"{API}/runs", headers=ADMIN).json()
    done = client.get(f"{API}/runs/{run['run_id']}", headers=ADMIN).json()
    assert done["status"] == "failed" and done["scorecard"] is None
    with Session(engine) as s:
        row = s.scalars(
            select(orm.AuditLog).where(orm.AuditLog.action == "redteam.run_finished")
        ).one()
        assert row.details["status"] == "failed" and "NotImplementedError" in row.details["error"]
    assert (
        client.get(f"{API}/scorecard/latest", headers=ADMIN).headers["X-Data-Source"] == "fixture"
    )


def test_one_run_per_minute(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "npa_redteam.harness", _fake_harness([]))
    first = client.post(f"{API}/runs", headers=ADMIN).json()
    second = client.post(f"{API}/runs", headers=ADMIN)
    if second.status_code == 202:  # the clock crossed a minute boundary between the calls
        assert second.json()["run_id"] != first["run_id"]
    else:
        assert second.status_code == 409 and second.json()["error"]["code"] == "CONFLICT"


def test_missing_harness_is_501(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "npa_redteam.harness", None)  # import raises ImportError
    res = client.post(f"{API}/runs", headers=ADMIN)
    assert res.status_code == 501 and res.json()["error"]["code"] == "REDTEAM_UNAVAILABLE"


def test_real_harness_signature_matches() -> None:
    """Contract check against WS7's real harness once it is installed (it is on main)."""
    try:
        harness = importlib.import_module("npa_redteam.harness")
    except ImportError:
        pytest.skip("WS7's npa_redteam.harness is not installed on this branch")
    params = inspect.signature(harness.run).parameters
    assert list(params)[:2] == ["api_base_url", "token"]
    assert params["now"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["api_base_url"].default is None and params["token"].default is None
    if hasattr(harness, "new_run_id"):
        now = datetime.fromisoformat("2026-10-12T05:30:00+00:00")
        assert harness.new_run_id(now) == run_id_for(now) == "RT-20261012-1100"
