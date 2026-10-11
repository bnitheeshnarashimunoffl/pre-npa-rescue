from fastapi import APIRouter

from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, roles
from npa_contracts.api import PolicyDocument, PolicyUpdateRequest

router = APIRouter(prefix="/admin", tags=["admin"], **PROTECTED)


@router.get("/policy", response_model=PolicyDocument, openapi_extra=roles("admin"))
def get_policy() -> PolicyDocument:
    """Current bank policy (``bank_policy.yaml``) as JSON."""
    return PolicyDocument.model_validate(load_fixture("policy.json"))


@router.put("/policy", response_model=PolicyDocument, openapi_extra=roles("admin"))
def put_policy(body: PolicyUpdateRequest) -> PolicyDocument:
    """Validate via ``npa_rules``, store a new version, hot-reload, audit (task 5.1/5.4)."""
    not_implemented("5.1")
