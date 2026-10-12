"""FastAPI entry point: ``uvicorn app.main:app``.

Bootstrap state: every A7.4 route exists so ``contracts/openapi.yaml`` can be generated from
it. Routes either serve ``contracts/fixtures/`` or return a 501 error envelope until their
task (5.1-5.4) lands.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app import __version__
from app.config import get_settings
from app.db import get_engine
from app.errors import install_error_handlers
from app.providers import build_providers
from app.routers import (
    accounts,
    admin,
    auth,
    callbacks,
    chat,
    collector,
    complaints,
    contacts,
    customers,
    health,
    metrics,
    offers,
    redteam,
    wellness,
)
from app.security import check_secret
from npa_contracts import CONTRACT_VERSION

API_PREFIX = "/api/v1"

_ROUTERS = (
    auth,
    health,
    customers,
    accounts,
    collector,
    contacts,
    offers,
    chat,
    complaints,
    callbacks,
    admin,
    redteam,
    metrics,
    wellness,
)


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the app. ``engine`` defaults to ``DATABASE_URL`` (connected lazily, so the API
    starts and serves fixture-backed routes even when Postgres is down)."""
    settings = get_settings()
    check_secret(settings)
    app = FastAPI(
        title="Pre-NPA Rescue API",
        version=CONTRACT_VERSION,
        summary=f"REST contract v{CONTRACT_VERSION} (api {__version__}). Synthetic data only.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    sessions = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    app.state.sessionmaker = sessions
    app.state.providers = build_providers(settings, sessions)
    api = APIRouter(prefix=API_PREFIX)
    for module in _ROUTERS:
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
