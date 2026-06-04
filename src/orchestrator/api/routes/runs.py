# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Run job endpoints: collect, train, eval, list, get, delete."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy.orm import Session

from orchestrator.api.auth import require_token
from orchestrator.api.limiter import limiter
from orchestrator.api.schemas import (
    CollectRequest,
    EvalRequest,
    RunCreatedResponse,
    RunResponse,
    TrainRequest,
)
from orchestrator.core.config import Settings, get_settings
from orchestrator.db.engine import get_session
from orchestrator.db.models import create_run, get_run, list_runs, update_run

router = APIRouter(
    prefix="/api/v1/runs",
    tags=["runs"],
    dependencies=[Depends(require_token)],
)

# ---------------------------------------------------------------------------
# Lazy enqueue imports — avoids hard dependency on WP-2 at import time
# ---------------------------------------------------------------------------


def _get_enqueue_collect() -> Callable[..., str]:
    from orchestrator.worker.queue import enqueue_collect

    return enqueue_collect


def _get_enqueue_train() -> Callable[..., str]:
    from orchestrator.worker.queue import enqueue_train

    return enqueue_train


def _get_enqueue_eval() -> Callable[..., str]:
    from orchestrator.worker.queue import enqueue_eval

    return enqueue_eval


def _get_cancel_job() -> Callable[..., bool]:
    from orchestrator.worker.queue import cancel_job

    return cancel_job


# ---------------------------------------------------------------------------
# argv builders
# ---------------------------------------------------------------------------


def _argv_collect(body: CollectRequest) -> list[str]:
    argv: list[str] = [
        "uv",
        "run",
        "python",
        "collect.py",
        f"episodes={body.episodes}",
        f"push_to_hub={body.push_to_hub}",
        f"policy_type={body.policy_type}",
    ]
    if body.env is not None:
        argv.append(f"env={body.env}")
    if body.seed is not None:
        argv.append(f"seed={body.seed}")
    argv.extend(body.hydra_overrides)
    return argv


def _argv_train(body: TrainRequest) -> list[str]:
    argv: list[str] = [
        "uv",
        "run",
        "python",
        "train.py",
        f"policy={body.policy}",
        f"training.total_steps={body.total_steps}",
    ]
    if body.env is not None:
        argv.append(f"env={body.env}")
    if body.profile is not None:
        argv.append(f"profile={body.profile}")
    if body.hf_repo_id is not None:
        argv.append(f"hf_repo_id={body.hf_repo_id}")
    argv.extend(body.hydra_overrides)
    return argv


def _argv_eval(body: EvalRequest) -> list[str]:
    argv: list[str] = [
        "uv",
        "run",
        "python",
        "eval.py",
        f"+eval.checkpoint_path={body.checkpoint_path}",
        f"+eval.n_episodes={body.n_episodes}",
        f"+eval.visualize={str(body.visualize).lower()}",
    ]
    if body.policy is not None:
        argv.append(f"policy={body.policy}")
    argv.extend(body.hydra_overrides)
    return argv


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/collect", status_code=202, response_model=RunCreatedResponse)
@limiter.limit("5/minute")  # ORC-010: max 5 job enqueues/min per IP
def post_collect(
    request: Request,
    body: CollectRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunCreatedResponse:
    """Submit a data-collection job."""
    argv = _argv_collect(body)
    run = create_run(
        session,
        job_type="collect",
        argv=argv,
        request_body=body.model_dump(),
        workspace_cwd=str(settings.lerobot_repo),
    )
    session.flush()
    try:
        enqueue_collect = _get_enqueue_collect()
        enqueue_collect(run.id, body.model_dump(), str(settings.lerobot_repo))
    except Exception as exc:
        logger.error("Failed to enqueue collect job {}: {}", run.id, exc)
        update_run(session, run.id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=502, detail=f"Failed to enqueue job: {exc}") from exc
    logger.info("Enqueued collect run {}", run.id)
    return RunCreatedResponse(run_id=run.id, status=run.status)


@router.post("/train", status_code=202, response_model=RunCreatedResponse)
@limiter.limit("5/minute")  # ORC-010: max 5 job enqueues/min per IP
def post_train(
    request: Request,
    body: TrainRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunCreatedResponse:
    """Submit a training job."""
    argv = _argv_train(body)
    run = create_run(
        session,
        job_type="train",
        argv=argv,
        request_body=body.model_dump(),
        workspace_cwd=str(settings.lerobot_repo),
    )
    session.flush()
    try:
        enqueue_train = _get_enqueue_train()
        enqueue_train(run.id, body.model_dump(), str(settings.lerobot_repo))
    except Exception as exc:
        logger.error("Failed to enqueue train job {}: {}", run.id, exc)
        update_run(session, run.id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=502, detail=f"Failed to enqueue job: {exc}") from exc
    logger.info("Enqueued train run {}", run.id)
    return RunCreatedResponse(run_id=run.id, status=run.status)


@router.post("/eval", status_code=202, response_model=RunCreatedResponse)
@limiter.limit("5/minute")  # ORC-010: max 5 job enqueues/min per IP
def post_eval(
    request: Request,
    body: EvalRequest,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunCreatedResponse:
    """Submit an evaluation job."""
    # ORC-008: confine checkpoint_path to lerobot_repo/checkpoints/ (resolve
    # symlinks so is_relative_to is not fooled by a traversal via symlink).

    checkpoints_root = (settings.lerobot_repo / "checkpoints").resolve()
    try:
        resolved = (settings.lerobot_repo / "checkpoints" / body.checkpoint_path).resolve(
            strict=False
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid checkpoint_path: {exc}") from exc
    if not resolved.is_relative_to(checkpoints_root):
        raise HTTPException(
            status_code=422,
            detail=(
                "checkpoint_path must resolve to a path under "
                f"{checkpoints_root} — path traversal is not allowed"
            ),
        )

    argv = _argv_eval(body)
    run = create_run(
        session,
        job_type="eval",
        argv=argv,
        request_body=body.model_dump(),
        workspace_cwd=str(settings.lerobot_repo),
    )
    session.flush()
    try:
        enqueue_eval = _get_enqueue_eval()
        enqueue_eval(run.id, body.model_dump(), str(settings.lerobot_repo))
    except Exception as exc:
        logger.error("Failed to enqueue eval job {}: {}", run.id, exc)
        update_run(session, run.id, status="failed", error_message=str(exc))
        raise HTTPException(status_code=502, detail=f"Failed to enqueue job: {exc}") from exc
    logger.info("Enqueued eval run {}", run.id)
    return RunCreatedResponse(run_id=run.id, status=run.status)


@router.get("/", response_model=list[RunResponse])
def get_runs(
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RunResponse]:
    """List runs with optional filters."""
    limit = min(limit, 200)
    runs = list_runs(session, status=status, job_type=job_type, limit=limit, offset=offset)
    return [RunResponse.from_run(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
def get_run_by_id(
    run_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> RunResponse:
    """Get a single run by ID."""
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return RunResponse.from_run(run)


@router.delete("/{run_id}", status_code=204)
def delete_run(
    run_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Cancel or delete a run."""
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    terminal_statuses = {"succeeded", "failed", "cancelled"}
    if run.status in terminal_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id!r} is already in terminal status {run.status!r}",
        )

    # Attempt to cancel via worker (best-effort)
    try:
        cancel_job = _get_cancel_job()
        cancel_job(run.id)
    except Exception as exc:
        logger.warning(
            "cancel_job({}) raised {}: {} — marking cancelled anyway",
            run.id,
            type(exc).__name__,
            exc,
        )

    update_run(session, run_id, status="cancelled")
    logger.info("Cancelled run {}", run_id)
