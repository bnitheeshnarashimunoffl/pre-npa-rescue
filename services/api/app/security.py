"""Authentication and role checks (tasks 5.2, 5.3).

- Passwords: bcrypt, used directly (passlib is unmaintained and warns with bcrypt >= 4.1).
- Tokens: JWT HS256 signed with ``JWT_SECRET``, expiring after ``JWT_EXPIRE_MINUTES``.
- Roles: ``require_roles(...)`` per route. A role that may not use a route gets **404, not
  403**, and so does a customer asking for another customer's data, so IDs cannot be
  enumerated (RBI RBC Directions para 454O; DPDP Act 2023 data minimisation).

IS/ISO/IEC 27001:2022 Annex A 5.15 (access control), 5.17 / 8.5 (authentication).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.config import Settings, get_settings
from app.deps import bearer
from app.errors import NOT_FOUND_MESSAGE, ApiError, not_found
from npa_contracts.enums import Role

log = logging.getLogger(__name__)

DEFAULT_BCRYPT_ROUNDS = 12
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "pre-npa-rescue"
MIN_SECRET_BYTES = 32  # RFC 7518 section 3.2 for HS256

# Verified when the username is unknown, so a miss costs as much as a wrong password
# (no user enumeration by timing).
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=DEFAULT_BCRYPT_ROUNDS))


# --- passwords --------------------------------------------------------------------------------
def hash_password(password: str, *, rounds: int = DEFAULT_BCRYPT_ROUNDS) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: always runs one bcrypt check, even when there is no user."""
    target = password_hash.encode("ascii") if password_hash else _DUMMY_HASH
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), target)
    except ValueError:  # malformed hash
        return False
    return ok and password_hash is not None


# --- tokens -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Principal:
    """The authenticated caller, taken from the token (no DB hit per request)."""

    username: str
    role: Role
    customer_id: str | None = None

    def is_staff(self) -> bool:
        return self.role is not Role.CUSTOMER


def check_secret(settings: Settings) -> None:
    if len(settings.jwt_secret.encode("utf-8")) < MIN_SECRET_BYTES:
        log.warning(
            "JWT_SECRET is shorter than %s bytes; use a long random secret outside local dev",
            MIN_SECRET_BYTES,
        )


def create_access_token(
    principal: Principal, settings: Settings, *, now: datetime | None = None
) -> tuple[str, int]:
    """Signed token and its lifetime in seconds."""
    issued = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.jwt_expire_minutes)
    claims: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "sub": principal.username,
        "role": principal.role.value,
        "iat": issued,
        "exp": issued + lifetime,
    }
    if principal.customer_id is not None:
        claims["cid"] = principal.customer_id
    token = jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "iss", "sub", "role"]},
        )
        role = Role(claims["role"])
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "Token has expired.") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise ApiError(401, "UNAUTHORIZED", "Invalid token.") from exc
    customer_id = claims.get("cid")
    if (role is Role.CUSTOMER) != isinstance(customer_id, str):
        raise ApiError(401, "UNAUTHORIZED", "Invalid token.")
    return Principal(username=str(claims["sub"]), role=role, customer_id=customer_id)


# --- dependencies -----------------------------------------------------------------------------
def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "UNAUTHORIZED", "Missing bearer token.")
    return decode_access_token(credentials.credentials, settings)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency allowing only ``roles``. Unknown names (e.g. ``"system"`` for in-process
    callers) are ignored. Denial is a 404 so a route's existence is not revealed."""
    allowed = {Role(r) for r in roles if r in Role._value2member_map_}

    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return principal

    return dependency


def ensure_customer_scope(principal: Principal, customer_id: str) -> None:
    """Customers may only see themselves; anything else is a 404 (no ID enumeration)."""
    if principal.role is Role.CUSTOMER and principal.customer_id != customer_id:
        not_found("Customer", customer_id)
