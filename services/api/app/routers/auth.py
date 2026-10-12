from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit_login
from app.config import Settings, get_settings
from app.db import get_session
from app.errors import ApiError
from app.orm import User
from app.ratelimit import RateLimits, client_key, enforce
from app.routers._common import ERRORS, access
from app.security import Principal, create_access_token, verify_password
from npa_contracts.api import LoginRequest, TokenResponse
from npa_contracts.enums import Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, responses=ERRORS, **access("public"))
def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Demo login -> JWT (task 5.3)."""
    # One generic error for unknown user, wrong password or inactive user (no user
    # enumeration); rate-limited per client and username.
    enforce(RateLimits.login(), f"{client_key(request)}|{body.username.lower()}")
    user = session.scalars(select(User).where(User.username == body.username)).one_or_none()
    ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not ok or not user.is_active:
        audit_login(session, body.username, success=False)  # IS/ISO/IEC 27001 A.8.15
        session.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "Username or password is incorrect.")
    principal = Principal(user.username, Role(user.role), user.customer_id)
    token, expires_in = create_access_token(principal, settings)
    audit_login(session, user.username, success=True)
    session.commit()
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        role=principal.role,
        customer_id=principal.customer_id,
    )
