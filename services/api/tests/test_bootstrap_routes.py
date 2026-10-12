"""Bootstrap smoke tests: stub routes serve fixtures or a 501 envelope. Task 5.1 replaces these.

Calls carry a token for an allowed role (task 5.3); auth itself is tested in test_auth.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from npa_contracts import CONTRACT_VERSION
from npa_contracts.api import ErrorResponse, QueuePage
from npa_contracts.models import BotReply
from tests.conftest import bearer_for

COLLECTOR = bearer_for("collector")
OFFICER = bearer_for("hardship_officer")
ADMIN = bearer_for("admin")
PRIYA = bearer_for("customer", "CUST-DEMO-PRIYA")
RAVI = bearer_for("customer", "CUST-DEMO-RAVI")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["packages"]["npa-contracts"] == CONTRACT_VERSION


def test_queue_filters_and_limit(client: TestClient) -> None:
    page = QueuePage.model_validate(client.get("/api/v1/collector/queue", headers=COLLECTOR).json())
    assert len(page.items) == 10
    assert page.items[0].account_id == "ACC-DEMO-PRIYA"
    sma1 = client.get(
        "/api/v1/collector/queue", params={"bucket": "sma1", "limit": 1}, headers=COLLECTOR
    ).json()
    assert [i["bucket"] for i in sma1["items"]] == ["sma1"]


def test_account_routes_echo_id(client: TestClient) -> None:
    for kind in ("risk", "segment", "uplift", "nba"):
        res = client.get(f"/api/v1/accounts/ACC-000001/{kind}", headers=OFFICER)
        assert res.status_code == 200
        assert res.json()["account_id"] == "ACC-000001"


def test_relief_options(client: TestClient) -> None:
    ravi = client.get("/api/v1/customers/CUST-DEMO-RAVI/relief-options", headers=RAVI).json()
    assert {o["type"] for o in ravi} == {"insurance_referral", "review_date"}
    missing = client.get("/api/v1/customers/CUST-NOPE/relief-options", headers=OFFICER)
    assert missing.status_code == 404
    assert ErrorResponse.model_validate(missing.json()).error.code == "NOT_FOUND"


def test_offer_lifecycle_stub(client: TestClient) -> None:
    created = client.post(
        "/api/v1/offers", json={"customer_id": "c", "option_id": "o"}, headers=OFFICER
    )
    assert created.status_code == 201 and created.json()["status"] == "proposed"
    approved = client.post("/api/v1/offers/OFFER-x/approve", headers=OFFICER)
    assert approved.json()["status"] == "approved" and approved.json()["offer_id"] == "OFFER-x"


def test_chat_message_stub(client: TestClient) -> None:
    res = client.post(
        "/api/v1/chat/sessions/SESS-1/messages", json={"text": "hello"}, headers=PRIYA
    )
    reply = BotReply.model_validate(res.json())
    assert reply.session_id == "SESS-1"


def test_fixture_backed_misc_routes(client: TestClient) -> None:
    for path, headers in (
        ("/api/v1/complaints/CMP-20261011-0002", OFFICER),
        ("/api/v1/callbacks", OFFICER),
        ("/api/v1/admin/policy", ADMIN),
        ("/api/v1/redteam/scorecard/latest", ADMIN),
        ("/api/v1/metrics/simulation", COLLECTOR),
    ):
        assert client.get(path, headers=headers).status_code == 200, path
    other_role = client.get("/api/v1/callbacks", params={"role": "collector"}, headers=OFFICER)
    assert other_role.json() == []


def test_not_implemented_envelope(client: TestClient) -> None:
    res = client.get("/api/v1/metrics/kpis", headers=ADMIN)
    assert res.status_code == 501
    assert ErrorResponse.model_validate(res.json()).error.code == "NOT_IMPLEMENTED"


def test_validation_and_unknown_route_envelopes(client: TestClient) -> None:
    bad = client.post("/api/v1/chat/sessions/S/messages", json={"text": ""}, headers=PRIYA)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    unknown = client.get("/api/v1/nope")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"
