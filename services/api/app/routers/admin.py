from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import verify_chain
from app.db import get_session
from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import AuditChainStatus, PolicyDocument, PolicyUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"], **PROTECTED)


@router.get("/policy", response_model=PolicyDocument, **access("admin"))
def get_policy() -> PolicyDocument:
    """Current bank policy (``bank_policy.yaml``) as JSON."""
    return PolicyDocument.model_validate(load_fixture("policy.json"))


@router.put("/policy", response_model=PolicyDocument, **access("admin"))
def put_policy(body: PolicyUpdateRequest) -> PolicyDocument:
    """Validate via ``npa_rules``, store a new version, hot-reload, audit (task 5.1/5.4)."""
    not_implemented("5.1")


@router.get("/audit/verify", response_model=AuditChainStatus, **access("admin", "auditor"))
def verify_audit_log(session: Annotated[Session, Depends(get_session)]) -> AuditChainStatus:
    """Recompute the audit log's hash chain; ``ok: false`` names the first tampered row."""
    check = verify_chain(session)
    return AuditChainStatus(
        ok=check.ok,
        rows_checked=check.rows_checked,
        first_bad_id=check.first_bad_id,
        reason=check.reason,
        checked_at=datetime.now(UTC),
    )
