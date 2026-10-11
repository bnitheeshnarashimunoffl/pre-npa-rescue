# syntax=docker/dockerfile:1
# API image (owned by WS5). Build context: repo root (the API imports every workspace package).
# Bootstrap version - untested locally (no Docker yet); hardened in task 5.5.

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY . .
RUN uv sync --frozen --no-dev --no-editable --package npa-api

FROM python:3.11-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app contracts /app/contracts
COPY --chown=app:app packages/rules/policies /app/packages/rules/policies
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 CONTRACTS_DIR=/app/contracts
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
