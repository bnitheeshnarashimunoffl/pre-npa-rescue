"""Shared router helpers."""

from typing import Any

from fastapi import Depends

from app.deps import bearer
from app.security import require_roles
from npa_contracts.api import ErrorResponse

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid token"},
    404: {"model": ErrorResponse, "description": "Not found (also used instead of 403)"},
    501: {"model": ErrorResponse, "description": "Not implemented yet"},
}
PROTECTED: dict[str, Any] = {"dependencies": [Depends(bearer)], "responses": ERRORS}


def access(*roles: str) -> dict[str, Any]:
    """Route kwargs: documents the allowed roles (``x-roles``) and enforces them (task 5.3).

    ``"public"`` means no token is needed. Keeping both in one place stops the OpenAPI contract
    and the enforced rule from drifting apart.
    """
    kwargs: dict[str, Any] = {"openapi_extra": {"x-roles": list(roles)}}
    if "public" not in roles:
        kwargs["dependencies"] = [Depends(require_roles(*roles))]
    return kwargs
