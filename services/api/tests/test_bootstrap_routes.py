"""Bootstrap smoke tests: stub routes serve fixtures or a 501 envelope. Task 5.1 replaces these."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from npa_contracts import CONTRACT_VERSION
from npa_contracts.api import ErrorResponse, QueuePage
from npa_contracts.models import BotReply


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
    page = QueuePage.model_validate(client.get("/api/v1/collector/queue").json())
    assert len(page.items) == 10
    assert {i.account_id for i in page.items[:2]} == {"ACC-DEMO-PRIYA", "ACC-DEMO-RAVI"}
    sma1 = client.get("/api/v1/collector/queue", params={"bucket": "sma1", "limit": 1}).json()
    assert [i["bucket"] for i in sma1["items"]] == ["sma1"]


def test_account_routes_echo_id(client: TestClient) -> None:
    for kind in ("risk", "segment", "uplift", "nba"):
        res = client.get(f"/api/v1/accounts/ACC-000001/{kind}")
        assert res.status_code == 200
        assert res.json()["account_id"] == "ACC-000001"


def test_relief_options(client: TestClient) -> None:
    ravi = client.get("/api/v1/customers/CUST-DEMO-RAVI/relief-options").json()
    assert {"insurance_referral", "review_date"} <= {o["type"] for o in ravi}
    missing = client.get("/api/v1/customers/CUST-NOPE/relief-options")
    assert missing.status_code == 404
    assert ErrorResponse.model_validate(missing.json()).error.code == "NOT_FOUND"


def test_offer_lifecycle_stub(client: TestClient) -> None:
    created = client.post("/api/v1/offers", json={"customer_id": "c", "option_id": "o"})
    assert created.status_code == 201 and created.json()["status"] == "proposed"
    approved = client.post("/api/v1/offers/OFFER-x/approve")
    assert approved.json()["status"] == "approved" and approved.json()["offer_id"] == "OFFER-x"


def test_chat_message_stub(client: TestClient) -> None:
    res = client.post("/api/v1/chat/sessions/SESS-1/messages", json={"text": "hello"})
    reply = BotReply.model_validate(res.json())
    assert reply.session_id == "SESS-1"


def test_fixture_backed_misc_routes(client: TestClient) -> None:
    for path in (
        "/api/v1/complaints/CMP-20261011-0002",
        "/api/v1/callbacks",
        "/api/v1/admin/policy",
        "/api/v1/redteam/scorecard/latest",
        "/api/v1/metrics/simulation",
    ):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/v1/callbacks", params={"role": "collector"}).json() == []


def test_not_implemented_envelope(client: TestClient) -> None:
    res = client.post("/api/v1/auth/login", json={"username": "priya", "password": "demo"})
    assert res.status_code == 501
    assert ErrorResponse.model_validate(res.json()).error.code == "NOT_IMPLEMENTED"


def test_validation_and_unknown_route_envelopes(client: TestClient) -> None:
    bad = client.post("/api/v1/chat/sessions/S/messages", json={"text": ""})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    unknown = client.get("/api/v1/nope")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"
