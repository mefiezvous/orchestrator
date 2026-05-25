# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for orchestrator.db.models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from orchestrator.db.models import (
    Run,
    RunNotFound,
    create_run,
    list_runs,
    new_run_id,
    to_dict,
    update_run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    session: Session,
    *,
    job_type: str = "train",
    argv: list[str] | None = None,
    request_body: dict[str, Any] | None = None,
    workspace_cwd: str = "/workspace",
) -> Run:
    return create_run(
        session,
        job_type=job_type,
        argv=argv if argv is not None else ["python", "train.py"],
        request_body=request_body if request_body is not None else {"dataset": "default"},
        workspace_cwd=workspace_cwd,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_create_run_defaults_to_queued(db_session: Session) -> None:
    """A freshly created run must have status='queued'."""
    run = _make_run(db_session)
    assert run.status == "queued"
    assert run.id is not None
    assert run.job_type == "train"
    assert run.created_at is not None


@pytest.mark.unit
def test_run_to_dict_roundtrip(db_session: Session) -> None:
    """to_dict should return ISO timestamp strings and native JSON types."""
    run = _make_run(db_session, argv=["train.py", "--lr", "0.001"])
    d = to_dict(run)

    # Timestamps are ISO strings
    assert isinstance(d["created_at"], str)
    # Verify it's parseable as ISO datetime
    parsed = datetime.fromisoformat(d["created_at"])
    assert parsed.tzinfo is not None  # timezone-aware

    # JSON columns come back as native types
    assert isinstance(d["argv"], list)
    assert d["argv"] == ["train.py", "--lr", "0.001"]
    assert isinstance(d["request_body"], dict)

    # Optional fields default to None
    assert d["started_at"] is None
    assert d["finished_at"] is None
    assert d["pid"] is None
    assert d["exit_code"] is None


@pytest.mark.unit
def test_list_runs_filters_by_status(db_session: Session) -> None:
    """list_runs(status=...) returns only runs with that status."""
    r1 = _make_run(db_session, job_type="train")
    r2 = _make_run(db_session, job_type="eval")
    _make_run(db_session, job_type="collect")

    # Promote r1 to running
    update_run(db_session, r1.id, status="running")
    # Promote r2 to succeeded
    update_run(db_session, r2.id, status="succeeded")

    running = list_runs(db_session, status="running")
    assert len(running) == 1
    assert running[0].id == r1.id

    queued = list_runs(db_session, status="queued")
    assert len(queued) == 1  # only collect is still queued


@pytest.mark.unit
def test_list_runs_filters_by_job_type(db_session: Session) -> None:
    """list_runs(job_type=...) returns only runs of that type."""
    _make_run(db_session, job_type="train")
    _make_run(db_session, job_type="train")
    _make_run(db_session, job_type="eval")

    trains = list_runs(db_session, job_type="train")
    assert len(trains) == 2
    assert all(r.job_type == "train" for r in trains)

    evals = list_runs(db_session, job_type="eval")
    assert len(evals) == 1


@pytest.mark.unit
def test_update_run_partial(db_session: Session) -> None:
    """update_run changes only the supplied fields; other fields unchanged."""
    run = _make_run(db_session)
    original_job_type = run.job_type
    original_created_at = run.created_at

    now = datetime.now(UTC)
    updated = update_run(
        db_session,
        run.id,
        status="running",
        pid=12345,
        started_at=now,
    )

    assert updated.status == "running"
    assert updated.pid == 12345
    assert updated.started_at == now
    # Unchanged fields must be intact
    assert updated.job_type == original_job_type
    assert updated.created_at == original_created_at
    assert updated.exit_code is None


@pytest.mark.unit
def test_update_run_not_found_raises(db_session: Session) -> None:
    """update_run raises RunNotFound for a non-existent run_id."""
    with pytest.raises(RunNotFound) as exc_info:
        update_run(db_session, "nonexistent-run-id", status="failed")

    assert "nonexistent-run-id" in str(exc_info.value)


@pytest.mark.unit
def test_new_run_id_unique() -> None:
    """new_run_id() should produce unique hex strings (no collision in 1 000)."""
    ids = [new_run_id() for _ in range(1000)]
    assert len(set(ids)) == 1000
    # Each should be a 32-char hex string (uuid4.hex)
    for run_id in ids:
        assert len(run_id) == 32
        assert run_id.isalnum()
