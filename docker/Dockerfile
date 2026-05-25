# SPDX-License-Identifier: Apache-2.0
# syntax=docker/dockerfile:1.7

###############################################################################
# Stage: builder
###############################################################################
FROM python:3.12-slim-bookworm AS builder

# Install uv + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_SYSTEM_PYTHON=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN uv venv /opt/venv

# Copy dependency spec first for layer caching
WORKDIR /build
COPY pyproject.toml .
# Provide a minimal src stub so hatchling can introspect the project
RUN mkdir -p src/orchestrator && touch src/orchestrator/__init__.py

# Install all runtime (+ dev) deps into the venv, but not the project itself yet
RUN uv pip install --python /opt/venv/bin/python \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "sse-starlette>=2.1" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6" \
        "sqlalchemy>=2.0" \
        "alembic>=1.14" \
        "rq>=2.0" \
        "redis>=5.2" \
        "loguru>=0.7" \
        "watchdog>=6.0" \
        "httpx>=0.27" \
        "python-multipart>=0.0.12" \
        "pyyaml>=6.0" \
        "mlflow-skinny>=2.18"

# Now copy the real source and install the project in editable mode
COPY src/ src/
RUN uv pip install --python /opt/venv/bin/python -e .

# Copy the worker entrypoint so it lands in the final image via COPY --from=builder
COPY docker/entrypoint-worker.sh /tmp/entrypoint-worker.sh
RUN chmod +x /tmp/entrypoint-worker.sh

###############################################################################
# Stage: runtime
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy uv binary (needed for the worker entrypoint's `uv pip install`)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy the populated venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy the worker entrypoint
COPY --from=builder /tmp/entrypoint-worker.sh /usr/local/bin/entrypoint-worker.sh

# Data directory (bind-mounted in compose, but ensure it exists)
RUN mkdir -p /data /workspace

WORKDIR /app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "orchestrator.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
