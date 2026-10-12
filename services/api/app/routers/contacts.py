from fastapi import APIRouter

from app.errors import not_implemented
from app.routers._common import PROTECTED, access
from npa_contracts.api import ContactCheckRequest
from npa_contracts.models import ComplianceDecision, ContactEvent

router = APIRouter(prefix="/contacts", tags=["contacts"], **PROTECTED)


@router.post("/check", response_model=ComplianceDecision, **access("system", "collector"))
def check_contact(body: ContactCheckRequest) -> ComplianceDecision:
    """Compliance-guard pre-check (RBI RBC Directions para 454Y, 454Z)."""
    not_implemented("5.1")


@router.get("", response_model=list[ContactEvent], **access("collector", "auditor"))
def list_contacts(customer_id: str) -> list[ContactEvent]:
    """Contact log for a customer (RBI RBC Directions para 454P)."""
    not_implemented("5.4")
