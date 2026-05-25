# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Health and version endpoints for the orchestrator API."""

from __future__ import annotations

import sys
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from orchestrator.api.schemas import HealthResponse, VersionResponse
from orchestrator.core.config import Settings, get_settings
from orchestrator.db.engine import get_session

router = APIRouter(
    prefix="/api/v1",
    tags=["system"],
)


@router.get("/health", response_model=HealthResponse)
def health(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Return service health status. No auth required."""
    # workspace
    workspace: Literal["ok", "missing"] = "ok" if settings.lerobot_repo.exists() else "missing"

    # database
    database: Literal["ok", "down"]
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        logger.warning("Database health check failed: {}", exc)
        database = "down"

    # redis
    redis_status: Literal["ok", "down", "unknown"]
    try:
        import redis as _redis

        _redis.from_url(settings.redis_url).ping()
        redis_status = "ok"
    except ImportError:
        redis_status = "unknown"
    except Exception as exc:
        logger.warning("Redis health check failed: {}", exc)
        redis_status = "down"

    # mlflow
    mlflow_status: Literal["ok", "down", "unknown"]
    if settings.mlruns_dir.exists():
        mlflow_status = "ok"
    else:
        mlflow_status = "unknown"

    return HealthResponse(
        api="ok",
        redis=redis_status,
        mlflow=mlflow_status,
        workspace=workspace,
        database=database,
    )


@router.get("/version", response_model=VersionResponse)
def version(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VersionResponse:
    """Return orchestrator and runtime version info."""
    from orchestrator import __version__

    return VersionResponse(
        orchestrator=__version__,
        python=sys.version.split()[0],
        lerobot_repo_exists=settings.lerobot_repo.exists(),
    )
