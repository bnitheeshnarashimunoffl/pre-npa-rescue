# syntax=docker/dockerfile:1.7
# API image (owned by WS5, task 5.5). Build context: repo root (the API imports workspace packages).
#   docker build -f services/api/Dockerfile -t npa-api .
# Runs as a non-root user, with no build tools or package caches in the final image, and starts
# through `python -m app.entrypoint` (wait for DB -> alembic upgrade -> optional seed -> uvicorn).

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

# ---- build: resolve the locked environment for the npa-api package only -------------------------
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package npa-api

# ---- runtime ------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="pre-npa-rescue-api" \
      org.opencontainers.image.source="https://github.com/bnitheeshnarashimunoffl/pre-npa-rescue" \
      org.opencontainers.image.licenses="MIT"
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder --chown=root:root /src/.venv /app/.venv
# Read-only runtime assets (owned by root, readable by the app user).
COPY --chown=root:root contracts /app/contracts
COPY --chown=root:root packages/rules/policies /app/packages/rules/policies
COPY --chown=root:root packages/models/reports /app/packages/models/reports
COPY --chown=root:root services/api/alembic.ini /app/services/api/alembic.ini
COPY --chown=root:root services/api/alembic /app/services/api/alembic
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONTRACTS_DIR=/app/contracts \
    POLICY_PATH=/app/packages/rules/policies/bank_policy.yaml \
    REPORTS_DIR=/app/packages/models/reports \
    ALEMBIC_CONFIG=/app/services/api/alembic.ini \
    DATA_DIR=/data/generated \
    MODEL_DIR=/models \
    PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/v1/health\", timeout=4)"]
ENTRYPOINT ["python", "-m", "app.entrypoint"]
