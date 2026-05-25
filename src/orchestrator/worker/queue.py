# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""RQ queue helpers — enqueue collect/train/eval jobs, cancel running jobs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger
from redis import Redis
from rq import Queue

from orchestrator.core.config import get_settings


@lru_cache(maxsize=1)
def _get_connection() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url)


@lru_cache(maxsize=1)
def _get_queue() -> Queue:
    return Queue("orchestrator", connection=_get_connection())


def enqueue_collect(run_id: str, body: dict[str, Any], workspace_cwd: str) -> str:
    """Enqueue a collect job. Returns the RQ job id (== run_id)."""
    try:
        job = _get_queue().enqueue(
            "orchestrator.worker.jobs.collect.run",
            kwargs={"run_id": run_id, "body": body, "workspace_cwd": workspace_cwd},
            job_id=run_id,
            job_timeout=86400,
            result_ttl=86400,
            failure_ttl=86400,
        )
        logger.info("enqueued collect job run_id={} rq_id={}", run_id, job.id)
        return job.id
    except Exception as exc:
        logger.error("Failed to enqueue collect job run_id={}: {}", run_id, exc)
        raise


def enqueue_train(run_id: str, body: dict[str, Any], workspace_cwd: str) -> str:
    """Enqueue a train job. Returns the RQ job id (== run_id)."""
    try:
        job = _get_queue().enqueue(
            "orchestrator.worker.jobs.train.run",
            kwargs={"run_id": run_id, "body": body, "workspace_cwd": workspace_cwd},
            job_id=run_id,
            job_timeout=86400,
            result_ttl=86400,
            failure_ttl=86400,
        )
        logger.info("enqueued train job run_id={} rq_id={}", run_id, job.id)
        return job.id
    except Exception as exc:
        logger.error("Failed to enqueue train job run_id={}: {}", run_id, exc)
        raise


def enqueue_eval(run_id: str, body: dict[str, Any], workspace_cwd: str) -> str:
    """Enqueue an eval job. Returns the RQ job id (== run_id)."""
    try:
        job = _get_queue().enqueue(
            "orchestrator.worker.jobs.eval.run",
            kwargs={"run_id": run_id, "body": body, "workspace_cwd": workspace_cwd},
            job_id=run_id,
            job_timeout=86400,
            result_ttl=86400,
            failure_ttl=86400,
        )
        logger.info("enqueued eval job run_id={} rq_id={}", run_id, job.id)
        return job.id
    except Exception as exc:
        logger.error("Failed to enqueue eval job run_id={}: {}", run_id, exc)
        raise


def cancel_job(run_id: str) -> bool:
    """Cancel a queued job, or signal SIGTERM to a running one via Redis SET.

    Returns True if a job was found and acted upon, False otherwise.
    """
    from rq.command import send_stop_job_command
    from rq.job import Job

    try:
        job = Job.fetch(run_id, connection=_get_connection())
    except Exception:
        logger.debug("cancel_job: run_id={} not found in RQ", run_id)
        return False

    try:
        if job.is_queued:
            job.cancel()
            logger.info("cancelled queued job run_id={}", run_id)
            return True
        # running → set a cancellation flag the worker polls
        _get_connection().set(f"cancel:{run_id}", "1", ex=3600)
        send_stop_job_command(_get_connection(), run_id)  # RQ 2.0+
        logger.info("sent SIGTERM signal to running job run_id={}", run_id)
        return True
    except Exception as exc:
        logger.error("cancel_job: error for run_id={}: {}", run_id, exc)
        return False
