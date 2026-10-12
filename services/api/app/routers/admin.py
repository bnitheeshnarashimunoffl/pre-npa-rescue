import importlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import orm
from app.audit import audit_policy_change, verify_chain
from app.db import get_session
from app.errors import ApiError, conflict
from app.fixtures import load_fixture
from app.providers import Deps, Providers
from app.routers._common import PROTECTED, access
from app.security import CurrentPrincipal
from app.services import convert
from npa_contracts.api import AuditChainStatus, PolicyDocument, PolicyUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]


def _active(session: Session) -> orm.PolicyVersion | None:
    return session.scalars(
        select(orm.PolicyVersion).where(orm.PolicyVersion.is_active.is_(True))
    ).first()


@router.get("/policy", response_model=PolicyDocument, **access("admin"))
def get_policy(session: DbSession, response: Response) -> PolicyDocument:
    """Current bank policy (``bank_policy.yaml``) as JSON."""
    row = _active(session)
    if row is None:  # database not seeded yet
        response.headers["X-Data-Source"] = "fixture"
        return PolicyDocument.model_validate(load_fixture("policy.json"))
    return convert.policy_document(row)


def validate_policy(policy: dict[str, Any]) -> tuple[str, Any]:
    """Validate with WS3's loader when installed; returns (version, parsed policy or None)."""
    try:
        loader = importlib.import_module("npa_rules.policy_loader")  # WS3, optional until merged
        policy_error: type[Exception] = loader.PolicyError
        parse_policy = loader.parse_policy
    except (ImportError, AttributeError):
        version = policy.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ApiError(
                422,
                "POLICY_INVALID",
                "Policy is invalid.",
                {"errors": ["version: a non-empty string is required"]},
            ) from None
        return version, None
    try:
        parsed = parse_policy(policy)
    except policy_error as exc:
        raise ApiError(
            422,
            "POLICY_INVALID",
            "Policy is invalid.",
            {"errors": list(getattr(exc, "errors", [str(exc)]))},
        ) from exc
    return str(parsed.version), parsed


def _hot_reload(providers: Providers, parsed: Any) -> None:
    if parsed is None:
        return
    for provider in (providers.policy, providers.compliance, providers.nba):
        reload = getattr(provider, "reload", None)
        if callable(reload):
            reload(parsed)


@router.put("/policy", response_model=PolicyDocument, **access("admin"))
def put_policy(
    body: PolicyUpdateRequest, principal: CurrentPrincipal, session: DbSession, providers: Deps
) -> PolicyDocument:
    """Validate the policy, store it as the new active version, reload the providers and
    record the change (old and new version) in the audit log."""
    version, parsed = validate_policy(body.policy)
    if session.scalar(select(orm.PolicyVersion).where(orm.PolicyVersion.version == version)):
        conflict(f"Policy version {version} already exists; bump `version`.", {"version": version})
    old = _active(session)
    session.execute(update(orm.PolicyVersion).values(is_active=False))
    row = orm.PolicyVersion(
        version=version,
        policy=body.policy,
        change_note=body.change_note,
        created_by=principal.username,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    audit_policy_change(
        session, principal.username, old.version if old else None, version, body.change_note
    )
    session.commit()
    _hot_reload(providers, parsed)
    return convert.policy_document(row)


@router.get("/audit/verify", response_model=AuditChainStatus, **access("admin", "auditor"))
def verify_audit_log(session: DbSession) -> AuditChainStatus:
    """Recompute the audit log's hash chain; ``ok: false`` names the first tampered row."""
    check = verify_chain(session)
    return AuditChainStatus(
        ok=check.ok,
        rows_checked=check.rows_checked,
        first_bad_id=check.first_bad_id,
        reason=check.reason,
        checked_at=datetime.now(UTC),
    )
