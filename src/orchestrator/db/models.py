# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""ORM models and CRUD helpers for the orchestrator database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Run model
# ---------------------------------------------------------------------------


class Run(Base):
    """Persisted metadata for a single orchestrated job."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    argv: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    workspace_cwd: Mapped[str] = mapped_column(String, nullable=False)
    stdout_path: Mapped[str | None] = mapped_column(String, nullable=True)
    stderr_path: Mapped[str | None] = mapped_column(String, nullable=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mlflow_tracking_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    hf_repo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Run id={self.id!r} job_type={self.job_type!r} status={self.status!r}>"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RunNotFound(Exception):  # noqa: N818
    """Raised when a Run with the given id does not exist."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id!r} not found")
        self.run_id = run_id


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def new_run_id() -> str:
    """Return a fresh UUID4 hex string."""
    return uuid.uuid4().hex


def create_run(
    session: Session,
    *,
    job_type: str,
    argv: list[str],
    request_body: dict[str, Any],
    workspace_cwd: str,
) -> Run:
    """Persist a new Run in *queued* status and return it."""
    run = Run(
        id=new_run_id(),
        job_type=job_type,
        status="queued",
        argv=argv,
        request_body=request_body,
        workspace_cwd=workspace_cwd,
        created_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    logger.debug("Created run {} (job_type={})", run.id, job_type)
    return run


def get_run(session: Session, run_id: str) -> Run | None:
    """Return the Run for *run_id*, or ``None`` if it does not exist."""
    return session.get(Run, run_id)


def list_runs(
    session: Session,
    *,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Run]:
    """Return runs ordered by *created_at* desc, with optional filters."""
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit).offset(offset)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    if job_type is not None:
        stmt = stmt.where(Run.job_type == job_type)
    return list(session.scalars(stmt).all())


_ALLOWED_UPDATE_FIELDS = frozenset(
    {
        "status",
        "stdout_path",
        "stderr_path",
        "mlflow_run_id",
        "mlflow_tracking_uri",
        "hf_repo_id",
        "pid",
        "exit_code",
        "error_message",
        "started_at",
        "finished_at",
        "argv",
        "request_body",
        "workspace_cwd",
    }
)


def update_run(session: Session, run_id: str, **fields: Any) -> Run:
    """Update *fields* on the Run identified by *run_id*.

    Raises :class:`RunNotFound` if the run does not exist.
    Flushes the session after applying changes so callers see updated state.
    """
    run = get_run(session, run_id)
    if run is None:
        raise RunNotFound(run_id)
    for key, value in fields.items():
        if key not in _ALLOWED_UPDATE_FIELDS:
            raise ValueError(f"Field {key!r} is not an updatable Run field")
        setattr(run, key, value)
    session.flush()
    logger.debug("Updated run {} fields={}", run_id, list(fields.keys()))
    return run


def to_dict(run: Run) -> dict[str, Any]:
    """Return a JSON-serialisable dict representation of *run*.

    Timestamps are ISO-8601 strings; JSON columns (argv, request_body) are
    returned as their native Python types (list / dict).
    """

    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt is not None else None

    return {
        "id": run.id,
        "job_type": run.job_type,
        "status": run.status,
        "argv": run.argv,
        "request_body": run.request_body,
        "workspace_cwd": run.workspace_cwd,
        "stdout_path": run.stdout_path,
        "stderr_path": run.stderr_path,
        "mlflow_run_id": run.mlflow_run_id,
        "mlflow_tracking_uri": run.mlflow_tracking_uri,
        "hf_repo_id": run.hf_repo_id,
        "pid": run.pid,
        "exit_code": run.exit_code,
        "error_message": run.error_message,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }
