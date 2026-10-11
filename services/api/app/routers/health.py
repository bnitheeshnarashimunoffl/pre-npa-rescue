from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

from app import __version__
from app.routers._common import roles
from npa_contracts import CONTRACT_VERSION
from npa_contracts.api import HealthResponse

router = APIRouter(tags=["health"])

_PACKAGES = ("npa-contracts", "datagen", "npa-models", "npa-rules", "npa-chat", "npa-redteam")


def _pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "missing"


@router.get("/health", response_model=HealthResponse, openapi_extra=roles("public"))
def health() -> HealthResponse:
    """Liveness plus package versions and which providers are real vs fixture."""
    return HealthResponse(
        status="ok",
        api_version=__version__,
        contract_version=CONTRACT_VERSION,
        packages={p: _pkg_version(p) for p in _PACKAGES},
        providers={
            "risk": "fixture",
            "policy": "fixture",
            "compliance": "fixture",
            "nba": "fixture",
            "chat": "fixture",
        },
    )
