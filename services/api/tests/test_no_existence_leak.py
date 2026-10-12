"""Item 5 (404, not 403): a resource that exists but belongs to someone else must be
indistinguishable from one that does not exist - same status and byte-identical body - and so
must a route the caller's role may not use, and a route that does not exist at all.
RBI RBC Directions para 454O; DPDP Act 2023. The all-routes role sweep is in test_auth.py."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import bearer_for

API = "/api/v1"
PRIYA = bearer_for("customer", "CUST-DEMO-PRIYA", "priya")
RAVI = bearer_for("customer", "CUST-DEMO-RAVI", "ravi")
OFFICER = bearer_for("hardship_officer")
UNIFORM_404 = {"error": {"code": "NOT_FOUND", "message": "Not found.", "details": {}}}


@pytest.fixture
def owned(app_db: tuple[FastAPI, TestClient]) -> dict[str, Any]:
    """Resources owned by Ravi, created through the API."""
    _, client = app_db
    sid = client.post(f"{API}/chat/sessions", headers=RAVI, json={}).json()["session_id"]
    client.post(f"{API}/chat/sessions/{sid}/messages", headers=RAVI, json={"text": "hello"})
    docket = client.post(
        f"{API}/complaints", headers=RAVI, json={"category": "x", "text": "y", "lang": "en"}
    ).json()["docket_no"]
    options = client.get(f"{API}/customers/CUST-DEMO-PRIYA/relief-options", headers=OFFICER).json()
    # an offer that belongs to Priya, to probe as Ravi
    offer = client.post(
        f"{API}/offers",
        headers=OFFICER,
        json={"customer_id": "CUST-DEMO-PRIYA", "option_id": options[0]["option_id"]},
    ).json()
    return {"client": client, "sid": sid, "docket": docket, "offer": offer["offer_id"]}


def _probe(
    client: TestClient, method: str, path: str, headers: dict[str, str], body: Any = None
) -> tuple[int, Any]:
    res = client.request(method, path, headers=headers, json=body)
    is_json = res.headers.get("content-type", "").startswith("application/json")
    return res.status_code, res.json() if is_json else res.text


@pytest.mark.parametrize(
    ("method", "theirs", "missing", "body"),
    [
        ("GET", "/customers/CUST-DEMO-RAVI", "/customers/CUST-NOPE", None),
        (
            "GET",
            "/customers/CUST-DEMO-RAVI/relief-options",
            "/customers/CUST-NOPE/relief-options",
            None,
        ),
        ("GET", "/chat/sessions/{sid}", "/chat/sessions/SESS-nope", None),
        ("GET", "/chat/sessions/{sid}/stream", "/chat/sessions/SESS-nope/stream", None),
        (
            "POST",
            "/chat/sessions/{sid}/messages",
            "/chat/sessions/SESS-nope/messages",
            {"text": "hi"},
        ),
        ("GET", "/complaints/{docket}", "/complaints/CMP-20200101-9999", None),
    ],
)
def test_ravis_resources_look_missing_to_priya(
    owned: dict[str, Any], method: str, theirs: str, missing: str, body: Any
) -> None:
    client = owned["client"]
    theirs = API + theirs.format(**owned)
    assert _probe(client, method, theirs, RAVI, body)[0] != 404  # it does exist for its owner
    got_theirs = _probe(client, method, theirs, PRIYA, body)
    got_missing = _probe(client, method, API + missing, PRIYA, body)
    assert got_theirs == got_missing == (404, UNIFORM_404)


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_priyas_offer_looks_missing_to_ravi(owned: dict[str, Any], action: str) -> None:
    client = owned["client"]
    theirs = _probe(client, "POST", f"{API}/offers/{owned['offer']}/{action}", RAVI)
    missing = _probe(client, "POST", f"{API}/offers/OFFER-nope/{action}", RAVI)
    assert theirs == missing == (404, UNIFORM_404)


def test_wellness_for_someone_else_looks_missing(owned: dict[str, Any]) -> None:
    client = owned["client"]
    theirs = _probe(
        client, "POST", f"{API}/wellness/simulate", PRIYA, {"customer_id": "CUST-DEMO-RAVI"}
    )
    missing = _probe(
        client, "POST", f"{API}/wellness/simulate", PRIYA, {"customer_id": "CUST-NOPE"}
    )
    assert theirs == missing == (404, UNIFORM_404)


def test_forbidden_route_looks_like_no_route(owned: dict[str, Any]) -> None:
    client = owned["client"]
    staff_only = _probe(client, "GET", f"{API}/collector/queue", PRIYA)
    no_route = _probe(client, "GET", f"{API}/collector/no-such-route", PRIYA)
    assert staff_only == no_route == (404, UNIFORM_404)


def test_other_customers_callbacks_are_simply_absent(owned: dict[str, Any]) -> None:
    client = owned["client"]
    status, body = _probe(client, "GET", f"{API}/callbacks", PRIYA)
    assert status == 200 and all(c["customer_id"] == "CUST-DEMO-PRIYA" for c in body)
