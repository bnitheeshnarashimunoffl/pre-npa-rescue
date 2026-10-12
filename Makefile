# Pre-NPA Rescue developer commands (owned by WS5).
# No make (e.g. Windows)? Every target's plain `uv run ...` command is listed in docs/setup.md.
# Targets tolerate missing upstream pieces: they print what is missing and exit 0.

SHELL := /bin/sh
.DEFAULT_GOAL := help
API_PORT ?= 8000

.PHONY: help setup data train migrate seed dev-db api web test lint format typecheck contracts check-contracts redteam demo

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install Python workspace (+ web deps once WS6 adds them)
	uv sync
	@if [ -f apps/web/pnpm-lock.yaml ]; then pnpm -C apps/web install; \
	else echo "[setup] apps/web has no pnpm-lock.yaml yet (WS6 task 6.1) - skipping web install"; fi

data: ## Generate synthetic data (WS1)
	@if uv run python -c "import datagen.cli" 2>/dev/null; then uv run datagen all; \
	else echo "[data] datagen CLI not available yet (WS1 task 1.1)"; fi

train: ## Train and score models (WS2)
	@if uv run python -c "import npa_models.cli" 2>/dev/null; then \
		uv run npa-models train --all && uv run npa-models score; \
	else echo "[train] npa-models CLI not available yet (WS2 task 2.1)"; fi

migrate: ## Apply database migrations (DATABASE_URL)
	uv run python -m alembic -c services/api/alembic.ini upgrade head

seed: migrate ## Migrate, then load Parquet (or fixtures) + demo users; SEED_ARGS=--reset to replace
	uv run python -m seed $(SEED_ARGS)

dev-db: ## Local Postgres 16 without Docker (prints DATABASE_URL)
	uv run --with pgserver python scripts/dev_postgres.py

api: ## Run the API with reload on :8000
	uv run uvicorn app.main:app --reload --port $(API_PORT) --app-dir services/api

web: ## Run the web app on :3000 (WS6)
	@if [ -f apps/web/pnpm-lock.yaml ]; then pnpm -C apps/web dev; \
	else echo "[web] web app not available yet (WS6 task 6.1)"; fi

test: ## Run all tests
	uv run pytest
	uv run pytest packages/contracts/tests --cov=npa_contracts --cov-fail-under=100 -q
	@if [ -f apps/web/pnpm-lock.yaml ]; then pnpm -C apps/web test; fi

lint: ## Lint and format-check
	uv run ruff check .
	uv run ruff format --check .
	@if [ -f apps/web/pnpm-lock.yaml ]; then pnpm -C apps/web lint; fi

format: ## Auto-fix lint and format
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## mypy (strict for npa_contracts and npa_rules)
	uv run python -m mypy
	@if [ -f apps/web/pnpm-lock.yaml ]; then pnpm -C apps/web typecheck; fi

contracts: ## Regenerate JSON Schemas and openapi.yaml
	uv run python scripts/export_schemas.py
	uv run python scripts/export_openapi.py

check-contracts: ## Verify generated contracts are current and fixtures validate
	uv run python scripts/export_schemas.py --check
	uv run python scripts/export_openapi.py --check
	uv run python scripts/check_contracts.py

redteam: ## Run the red-team harness against the local API (WS7)
	@if uv run python -c "import npa_redteam.cli" 2>/dev/null; then uv run npa-redteam run; \
	else echo "[redteam] red-team harness not available yet (WS7 task 7.1)"; fi

demo: ## docker compose up + seed + print URLs
	@if ! command -v docker >/dev/null 2>&1; then echo "[demo] docker not installed"; exit 0; fi
	docker compose up -d --build
	@if [ -f services/api/seed/__main__.py ]; then docker compose exec api python -m seed; \
	else echo "[demo] seed loader not available yet (WS5 task 5.2)"; fi
	@echo "API:  http://localhost:$(API_PORT)/docs"
	@echo "Web:  http://localhost:3000 (once WS6 adds apps/web/Dockerfile)"
