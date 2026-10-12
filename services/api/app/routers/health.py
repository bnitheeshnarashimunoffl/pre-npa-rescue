from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_session
from app.providers import Deps
from app.routers._common import access
from npa_contracts import CONTRACT_VERSION
from npa_contracts.api import HealthResponse

router = APIRouter(tags=["health"])

_PACKAGES = ("npa-contracts", "datagen", "npa-models", "npa-rules", "npa-chat", "npa-redteam")


def _pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


@router.get("/health", response_model=HealthResponse, **access("public"))
def health(providers: Deps, session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    """Liveness plus package versions and which providers are real vs fixture."""
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except SQLAlchemyError:
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        api_version=__version__,
        contract_version=CONTRACT_VERSION,
        packages={p: _pkg_version(p) for p in _PACKAGES},
        providers=dict(providers.kinds),
    )
