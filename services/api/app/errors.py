"""Standard error envelope (A7.4): ``{"error": {"code", "message", "details"}}``."""

import logging
from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from npa_contracts.api import ErrorBody, ErrorResponse

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = dict(headers or {})
        if status_code == 401:
            self.headers.setdefault("WWW-Authenticate", "Bearer")


def not_implemented(task: str) -> NoReturn:
    """Raise a 501 for a route that is declared in the contract but not built yet."""
    raise ApiError(501, "NOT_IMPLEMENTED", f"Stub route; implemented in WS5 task {task}.")


def not_found(resource: str, resource_id: str) -> NoReturn:
    raise ApiError(404, "NOT_FOUND", f"{resource} not found.", {"id": resource_id})


def _envelope(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"), headers=headers
    )


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    429: "RATE_LIMITED",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return _envelope(exc.status_code, code, str(exc.detail), {})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _envelope(422, "VALIDATION_ERROR", "Request validation failed.", {"errors": errors})

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        # Never leak connection strings or SQL to the client.
        log.error("database unavailable: %s", exc.__class__.__name__)
        return _envelope(503, "DB_UNAVAILABLE", "The service is temporarily unavailable.", {})
