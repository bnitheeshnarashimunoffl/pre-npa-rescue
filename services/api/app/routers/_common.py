"""Shared router helpers."""

from typing import Any

from fastapi import Depends

from app.deps import bearer
from npa_contracts.api import ErrorResponse

ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid token"},
    404: {"model": ErrorResponse, "description": "Not found (also used instead of 403)"},
    501: {"model": ErrorResponse, "description": "Not implemented yet"},
}
PROTECTED: dict[str, Any] = {"dependencies": [Depends(bearer)], "responses": ERRORS}


def roles(*names: str) -> dict[str, Any]:
    """OpenAPI extension listing the roles allowed on a route (enforced in task 5.3)."""
    return {"x-roles": list(names)}
