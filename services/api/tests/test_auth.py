"""Task 5.3: login, JWT validation, role checks (404 not 403), customer scope, rate limits,
data minimisation."""

import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session, make_engine
from app.main import create_app
from app.minimise import VISIBLE_FIELDS, mask_email, mask_phone, minimise_profile
from app.orm import User
from app.ratelimit import TokenBucket
from app.security import (
    JWT_ALGORITHM,
    Principal,
    check_secret,
    create_access_token,
    decode_access_token,
)
from npa_contracts.api import CustomerProfile
from npa_contracts.enums import Role
from seed import seed_database
from tests.conftest import CONTRACTS_DIR, bearer_for

ROLES = [r.value for r in Role]


@pytest.fixture
def app_db(engine: Engine, tmp_path: Path) -> Iterator[tuple[FastAPI, TestClient]]:
    """App wired to a freshly migrated + seeded DB (fixtures source, demo users)."""
    seed_database(
        engine,
        data_dir=tmp_path,
        contracts_dir=CONTRACTS_DIR,
        policy_path=tmp_path / "none.yaml",
        as_of_month="2026-09",
        bcrypt_rounds=4,
    )
    app = create_app()

    def _session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    yield app, TestClient(app)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _login(client: TestClient, username: str, password: str = "demo") -> Any:
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


# --- login ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("username", "role", "customer_id"),
    [
        ("priya", "customer", "CUST-DEMO-PRIYA"),
        ("ravi", "customer", "CUST-DEMO-RAVI"),
        ("collector1", "collector", None),
        ("officer1", "hardship_officer", None),
        ("admin1", "admin", None),
        ("auditor1", "auditor", None),
    ],
)
def test_demo_users_can_log_in(
    app_db: tuple[FastAPI, TestClient], username: str, role: str, customer_id: str | None
) -> None:
    _, client = app_db
    res = _login(client, username)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["role"], body["customer_id"], body["token_type"]) == (role, customer_id, "bearer")
    assert body["expires_in"] == get_settings().jwt_expire_minutes * 60
    principal = decode_access_token(body["access_token"], get_settings())
    assert principal == Principal(username, Role(role), customer_id)


@pytest.mark.parametrize(("username", "password"), [("priya", "wrong"), ("nobody", "demo")])
def test_bad_credentials_get_one_generic_error(
    app_db: tuple[FastAPI, TestClient], username: str, password: str
) -> None:
    _, client = app_db
    res = _login(client, username, password)
    assert res.status_code == 401
    assert res.json()["error"] == {
        "code": "INVALID_CREDENTIALS",
        "message": "Username or password is incorrect.",
        "details": {},
    }
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_inactive_user_cannot_log_in(app_db: tuple[FastAPI, TestClient], engine: Engine) -> None:
    _, client = app_db
    with Session(engine) as s:
        s.execute(update(User).where(User.username == "admin1").values(is_active=False))
        s.commit()
    assert _login(client, "admin1").json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_is_rate_limited_per_client_and_username(app_db: tuple[FastAPI, TestClient]) -> None:
    _, client = app_db
    limit = get_settings().login_rate_per_minute
    codes = [_login(client, "priya", "wrong").status_code for _ in range(limit)]
    assert codes == [401] * limit
    blocked = _login(client, "priya", "demo")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert _login(client, "ravi").status_code == 200  # other username unaffected


def test_login_when_database_is_down_returns_503() -> None:
    app = create_app()
    dead = make_engine("postgresql+psycopg://npa:npa@127.0.0.1:1/npa?connect_timeout=1")

    def _session() -> Iterator[Session]:
        with Session(dead) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    res = TestClient(app).post("/api/v1/auth/login", json={"username": "x", "password": "y"})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "DB_UNAVAILABLE"
    assert "127.0.0.1" not in res.text  # no connection details leak


# --- tokens -----------------------------------------------------------------------------------
def _token(settings: Settings, **override: Any) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "pre-npa-rescue",
        "sub": "x",
        "role": "collector",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    } | override
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ({}, "UNAUTHORIZED"),
        ({"Authorization": "Bearer not-a-jwt"}, "UNAUTHORIZED"),
        ({"Authorization": "Basic dXNlcjpwYXNz"}, "UNAUTHORIZED"),
    ],
)
def test_missing_or_malformed_token(client: TestClient, headers: dict[str, str], code: str) -> None:
    res = client.get("/api/v1/collector/queue", headers=headers)
    assert res.status_code == 401 and res.json()["error"]["code"] == code
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_expired_wrong_key_and_bad_claims_rejected(client: TestClient) -> None:
    s = get_settings()
    past = datetime.now(UTC) - timedelta(hours=3)
    cases = {
        "TOKEN_EXPIRED": _token(s, iat=past, exp=past + timedelta(minutes=1)),
        "UNAUTHORIZED": jwt.encode({"sub": "x", "role": "admin"}, "x" * 40, algorithm="HS256"),
    }
    for code, token in cases.items():
        res = client.get("/api/v1/collector/queue", headers={"Authorization": f"Bearer {token}"})
        assert (res.status_code, res.json()["error"]["code"]) == (401, code)
    for bad in (
        _token(s, role="superuser"),  # unknown role
        _token(s, role="customer"),  # customer without cid
        _token(s, cid="CUST-1"),  # staff with cid
        _token(s, iss="someone-else"),
        _token(s, exp=None),  # no expiry
    ):
        res = client.get("/api/v1/collector/queue", headers={"Authorization": f"Bearer {bad}"})
        assert res.status_code == 401, bad


def test_none_algorithm_rejected(client: TestClient) -> None:
    unsigned = jwt.encode({"iss": "pre-npa-rescue", "sub": "x", "role": "admin"}, None, "none")
    res = client.get("/api/v1/admin/policy", headers={"Authorization": f"Bearer {unsigned}"})
    assert res.status_code == 401


# --- roles: every route enforces exactly its documented x-roles ---------------------------------
def _operations() -> list[tuple[str, str, list[str]]]:
    """(method, path, x-roles) for every operation in the published OpenAPI document."""
    spec = create_app().openapi()
    return [
        (method.upper(), path, op.get("x-roles", []))
        for path, item in sorted(spec["paths"].items())
        for method, op in sorted(item.items())
    ]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "CUST-DEMO-PRIYA", path)


@pytest.mark.parametrize(("method", "path", "allowed"), _operations(), ids=lambda v: str(v))
def test_route_enforces_documented_roles(
    client: TestClient, method: str, path: str, allowed: list[str]
) -> None:
    assert allowed, f"{method} {path} declares no x-roles"
    if "public" in allowed:
        return
    anon = client.request(method, _concrete(path), json={})
    assert anon.status_code == 401, path
    for role in ROLES:
        res = client.request(method, _concrete(path), json={}, headers=bearer_for(role))
        denied = res.status_code == 404 and res.json()["error"]["message"] == "Not found."
        assert denied == (role not in allowed), (method, path, role, res.status_code)


def test_every_operation_is_covered() -> None:
    assert len(_operations()) >= 30


# --- customer scope -----------------------------------------------------------------------------
def test_customer_sees_only_self(client: TestClient) -> None:
    priya = bearer_for("customer", "CUST-DEMO-PRIYA")
    own = client.get("/api/v1/customers/CUST-DEMO-PRIYA/relief-options", headers=priya)
    other = client.get("/api/v1/customers/CUST-DEMO-RAVI/relief-options", headers=priya)
    absent = client.get("/api/v1/customers/CUST-000999/relief-options", headers=priya)
    assert own.status_code == 200
    assert other.status_code == absent.status_code == 404  # no enumeration
    assert other.json()["error"]["code"] == absent.json()["error"]["code"] == "NOT_FOUND"
    profile = client.get("/api/v1/customers/CUST-DEMO-RAVI", headers=priya)
    assert profile.status_code == 404


def test_officer_can_see_any_customer(client: TestClient) -> None:
    res = client.get(
        "/api/v1/customers/CUST-DEMO-RAVI/relief-options", headers=bearer_for("hardship_officer")
    )
    assert res.status_code == 200


# --- chat rate limit ----------------------------------------------------------------------------
def test_chat_rate_limited_per_user(client: TestClient) -> None:
    priya, ravi = (
        bearer_for("customer", "CUST-DEMO-PRIYA"),
        bearer_for("customer", "CUST-DEMO-RAVI"),
    )
    limit = get_settings().chat_rate_per_minute
    url = "/api/v1/chat/sessions/S/messages"
    codes = [client.post(url, json={"text": "hi"}, headers=priya).status_code for _ in range(limit)]
    assert set(codes) == {200}
    assert client.post(url, json={"text": "hi"}, headers=priya).status_code == 429
    assert client.post(url, json={"text": "hi"}, headers=ravi).status_code == 200


def test_token_bucket_refills() -> None:
    now = [0.0]
    bucket = TokenBucket(capacity=2, refill_per_second=1, clock=lambda: now[0])
    assert bucket.take("k") == bucket.take("k") == 0
    assert bucket.take("k") == pytest.approx(1.0)
    now[0] = 0.5
    assert bucket.take("k") == pytest.approx(0.5)
    now[0] = 1.0
    assert bucket.take("k") == 0
    assert bucket.take("other") == 0


# --- secrets ------------------------------------------------------------------------------------
def test_short_secret_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        check_secret(Settings(jwt_secret="short"))
    assert "JWT_SECRET is shorter" in caplog.text
    caplog.clear()
    check_secret(Settings(jwt_secret="x" * 32))
    assert caplog.text == ""


def test_token_round_trip_and_lifetime() -> None:
    s = Settings(jwt_secret="y" * 32, jwt_expire_minutes=5)
    token, ttl = create_access_token(Principal("officer1", Role.HARDSHIP_OFFICER), s)
    assert ttl == 300
    assert decode_access_token(token, s).role is Role.HARDSHIP_OFFICER


# --- data minimisation (RBI para 454O, DPDP) ------------------------------------------------------
FULL = CustomerProfile(
    customer_id="CUST-DEMO-RAVI",
    account_id="ACC-DEMO-RAVI",
    full_name="Ravi Shankar",
    language_pref="en",
    age=44,
    city="Coimbatore",
    occupation_type="salaried",
    card_limit_paise=20_000_000,
    has_card_insurance=True,
    insurance_cover_type="job_loss",
    phone_masked="+91-9787654358",
    email_masked="ravi.shankar@example.com",
    preferred_contact_window="10:00-13:00",
)


def test_collector_sees_contact_fields_only() -> None:
    p = minimise_profile(FULL, Principal("collector1", Role.COLLECTOR))
    assert p.full_name == "Ravi Shankar" and p.preferred_contact_window == "10:00-13:00"
    assert (p.age, p.city, p.occupation_type, p.has_card_insurance, p.card_limit_paise) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert p.phone_masked == "+91-97XXXXXX58" and p.email_masked == "r****@example.com"


def test_officer_sees_hardship_fields_and_auditor_identity_only() -> None:
    officer = minimise_profile(FULL, Principal("officer1", Role.HARDSHIP_OFFICER))
    assert officer.has_card_insurance is True and officer.insurance_cover_type == "job_loss"
    auditor = minimise_profile(FULL, Principal("auditor1", Role.AUDITOR))
    assert auditor.phone_masked is None and auditor.city is None
    assert auditor.customer_id == "CUST-DEMO-RAVI"


def test_customer_and_admin_see_everything_masked() -> None:
    for principal in (
        Principal("ravi", Role.CUSTOMER, "CUST-DEMO-RAVI"),
        Principal("admin1", Role.ADMIN),
    ):
        p = minimise_profile(FULL, principal)
        assert p.age == 44 and p.card_limit_paise == 20_000_000
        assert "X" in (p.phone_masked or "") and "*" in (p.email_masked or "")


def test_every_role_has_a_field_policy_and_no_protected_fields() -> None:
    assert set(VISIBLE_FIELDS) == set(Role)
    protected = {"gender", "religion", "caste_category", "state", "region"}
    assert not protected & set(CustomerProfile.model_fields)


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("+91-9876543221", "+91-98XXXXXX21"),
        ("+91-98XXXXXX21", "+91-98XXXXXX21"),
        (None, None),
        ("", ""),
    ],
)
def test_mask_phone(raw: str | None, masked: str | None) -> None:
    assert mask_phone(raw) == masked


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("priya.raman@example.com", "p****@example.com"),
        ("p****@example.com", "p****@example.com"),
        ("not-an-email", "not-an-email"),
        (None, None),
    ],
)
def test_mask_email(raw: str | None, masked: str | None) -> None:
    assert mask_email(raw) == masked
