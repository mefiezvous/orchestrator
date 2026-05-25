# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for run_subprocess_job (base.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import fakeredis
import pytest

from orchestrator.core.config import Settings
from orchestrator.db.models import get_run
from orchestrator.worker.jobs.base import run_subprocess_job

# ---------------------------------------------------------------------------
# Helper: patch Redis inside base module so cancel-poll doesn't need a server
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_redis_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch Redis.from_url in base module to return a FakeRedis instance."""
    fake = fakeredis.FakeRedis()

    import redis as redis_mod

    monkeypatch.setattr(
        redis_mod, "Redis", type("Redis", (), {"from_url": staticmethod(lambda *a, **kw: fake)})
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _python_argv(*code_parts: str) -> list[str]:
    """Build a portable argv that runs Python inline code."""
    return [sys.executable, "-c", " ".join(code_parts)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_success_path(
    settings_override: Settings,
    db_session: Any,
    run_factory: Any,
    tmp_data_dir: Path,
) -> None:
    """argv exits 0 → status=succeeded, stdout contains the printed line."""
    run = run_factory(
        job_type="collect",
        argv=["python", "-c", "pass"],
        workspace_cwd=str(tmp_data_dir),
    )
    run_id = run.id
    db_session.commit()

    argv = _python_argv("import sys; print('hello'); sys.stdout.flush()")
    exit_code = run_subprocess_job(
        run_id=run_id,
        job_type="collect",
        argv=argv,
        workspace_cwd=str(tmp_data_dir),
        body={},
    )

    assert exit_code == 0

    # Reload run from a fresh session to see committed state
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(settings_override.database_url, connect_args={"check_same_thread": False})
    fresh_session = sessionmaker(bind=eng)()
    try:
        updated = get_run(fresh_session, run_id)
        assert updated is not None
        assert updated.status == "succeeded"
        assert updated.started_at is not None
        assert updated.finished_at is not None
        assert updated.exit_code == 0
        assert updated.stdout_path is not None
        stdout_content = Path(updated.stdout_path).read_text(encoding="utf-8")
        assert "hello" in stdout_content
    finally:
        fresh_session.close()
        eng.dispose()


@pytest.mark.integration
def test_failure_path(
    settings_override: Settings,
    db_session: Any,
    run_factory: Any,
    tmp_data_dir: Path,
) -> None:
    """argv exits non-zero → status=failed, exit_code matches, error_message set."""
    run = run_factory(
        job_type="train",
        argv=["python", "-c", "pass"],
        workspace_cwd=str(tmp_data_dir),
    )
    run_id = run.id
    db_session.commit()

    argv = _python_argv("import sys; sys.stderr.write('oops\\n'); sys.exit(7)")
    exit_code = run_subprocess_job(
        run_id=run_id,
        job_type="train",
        argv=argv,
        workspace_cwd=str(tmp_data_dir),
        body={},
    )

    assert exit_code == 7

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(settings_override.database_url, connect_args={"check_same_thread": False})
    fresh_session = sessionmaker(bind=eng)()
    try:
        updated = get_run(fresh_session, run_id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.exit_code == 7
        assert updated.error_message  # non-empty
    finally:
        fresh_session.close()
        eng.dispose()


@pytest.mark.integration
def test_mlflow_run_id_detected(
    settings_override: Settings,
    db_session: Any,
    run_factory: Any,
    tmp_data_dir: Path,
) -> None:
    """Script printing MLflow run_id causes mlflow_run_id column to be populated."""
    run = run_factory(
        job_type="train",
        argv=["python", "-c", "pass"],
        workspace_cwd=str(tmp_data_dir),
    )
    run_id = run.id
    db_session.commit()

    mlflow_id = "abcdef0123456789abcdef0123456789"
    argv = _python_argv(f"import sys; print('MLflow run_id: {mlflow_id}'); sys.stdout.flush()")
    exit_code = run_subprocess_job(
        run_id=run_id,
        job_type="train",
        argv=argv,
        workspace_cwd=str(tmp_data_dir),
        body={},
    )

    assert exit_code == 0

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine(settings_override.database_url, connect_args={"check_same_thread": False})
    fresh_session = sessionmaker(bind=eng)()
    try:
        updated = get_run(fresh_session, run_id)
        assert updated is not None
        assert updated.mlflow_run_id == mlflow_id
    finally:
        fresh_session.close()
        eng.dispose()
