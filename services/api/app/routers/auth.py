from fastapi import APIRouter

from app.errors import not_implemented
from app.routers._common import ERRORS, roles
from npa_contracts.api import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login", response_model=TokenResponse, responses=ERRORS, openapi_extra=roles("public")
)
def login(body: LoginRequest) -> TokenResponse:
    """Demo login -> JWT (task 5.3)."""
    not_implemented("5.3")
