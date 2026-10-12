from fastapi import APIRouter, status

from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import CallbackCreateRequest
from npa_contracts.enums import Role
from npa_contracts.models import Callback

router = APIRouter(prefix="/callbacks", tags=["callbacks"], **PROTECTED)


@router.post(
    "",
    response_model=Callback,
    status_code=status.HTTP_201_CREATED,
    **access("customer", "hardship_officer"),
)
def book_callback(body: CallbackCreateRequest) -> Callback:
    """Book a handoff callback inside 08:00-19:00 IST (RBI RBC Directions para 454Y(4))."""
    return Callback.model_validate(load_fixture("callback.json"))


@router.get("", response_model=list[Callback], **access("customer", "hardship_officer"))
def list_callbacks(role: Role | None = None) -> list[Callback]:
    cb = Callback.model_validate(load_fixture("callback.json"))
    return [cb] if role is None or cb.role == role else []
