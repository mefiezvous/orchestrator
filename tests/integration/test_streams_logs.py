# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the /logs SSE endpoint."""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from orchestrator.core.config import Settings, get_settings
from orchestrator.db.engine import get_session
from orchestrator.db.models import create_run, update_run

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client_streams(
    db_session: Session,
    settings_override: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """TestClient with DB overridden to test session."""
    # Stub out the worker.queue module so create_app() doesn't fail
    fake_queue = types.ModuleType("orchestrator.worker.queue")
    fake_queue.enqueue_collect = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
    fake_queue.enqueue_train = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
    fake_queue.enqueue_eval = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
    fake_queue.cancel_job = MagicMock(return_value=True)  # type: ignore[attr-defined]
    if "orchestrator.worker" not in sys.modules:
        fake_worker = types.ModuleType("orchestrator.worker")
        sys.modules["orchestrator.worker"] = fake_worker
    sys.modules["orchestrator.worker.queue"] = fake_queue

    from orchestrator.api.main import create_app

    app = create_app()

    def _override_session():  # type: ignore[return]
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: settings_override

    return TestClient(app, raise_server_exceptions=False)


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_stream_logs_404_unknown_run(app_client_streams: TestClient) -> None:
    """GET /logs for unknown run_id returns 404."""
    resp = app_client_streams.get("/api/v1/runs/nonexistent/logs", headers=_auth())
    assert resp.status_code == 404


@pytest.mark.integration
def test_stream_logs_delivers_lines(
    app_client_streams: TestClient,
    db_session: Session,
    settings_override: Settings,
    tmp_data_dir: Path,
) -> None:
    """Lines written to stdout_path are received as SSE events."""
    # Create a run row
    run = create_run(
        db_session,
        job_type="train",
        argv=["python", "train.py"],
        request_body={},
        workspace_cwd="/workspace",
    )
    run_id = run.id

    # Set up log file paths
    logs_dir = settings_override.logs_dir
    stdout_path = str(logs_dir / f"{run_id}.stdout")
    stderr_path = str(logs_dir / f"{run_id}.stderr")
    update_run(db_session, run_id, stdout_path=stdout_path, stderr_path=stderr_path)
    db_session.commit()

    # Write some lines to stdout after a short delay (simulating worker output)
    def _write_and_finish() -> None:
        time.sleep(0.3)
        with open(stdout_path, "a", encoding="utf-8") as f:
            f.write("hello world\n")
            f.write("epoch 1\n")
        time.sleep(0.3)
        # Mark the run as succeeded so the stream closes
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        _eng = create_engine(
            settings_override.database_url,
            connect_args={"check_same_thread": False},
        )
        _sf = sessionmaker(bind=_eng, autoflush=False, autocommit=False)
        _s = _sf()
        try:
            update_run(_s, run_id, status="succeeded", exit_code=0)
            _s.commit()
        finally:
            _s.close()
            _eng.dispose()

    writer = threading.Thread(target=_write_and_finish, daemon=True)
    writer.start()

    # Stream with a timeout
    collected_events: list[dict[str, Any]] = []
    end_event: dict[str, Any] | None = None

    with app_client_streams.stream("GET", f"/api/v1/runs/{run_id}/logs", headers=_auth()) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
                if event_type == "end":
                    # Next line should be the data for end event
                    continue
            if line.startswith("data:"):
                data_str = line[len("data:") :].strip()
                try:
                    payload = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if "status" in payload and "exit_code" in payload:
                    # This is the end event payload
                    end_event = payload
                    break
                elif "line" in payload:
                    collected_events.append(payload)

    writer.join(timeout=5.0)

    lines = [e["line"] for e in collected_events]
    assert "hello world" in lines
    assert "epoch 1" in lines
    assert end_event is not None
    assert end_event["status"] == "succeeded"
    assert end_event["exit_code"] == 0


@pytest.mark.integration
def test_stream_logs_sanitizes_secrets(
    app_client_streams: TestClient,
    db_session: Session,
    settings_override: Settings,
    tmp_data_dir: Path,
) -> None:
    """Bearer tokens in log output are sanitized before streaming."""
    run = create_run(
        db_session,
        job_type="train",
        argv=["python", "train.py"],
        request_body={},
        workspace_cwd="/workspace",
    )
    run_id = run.id

    logs_dir = settings_override.logs_dir
    stdout_path = str(logs_dir / f"{run_id}.stdout")
    stderr_path = str(logs_dir / f"{run_id}.stderr")
    update_run(db_session, run_id, stdout_path=stdout_path, stderr_path=stderr_path)
    db_session.commit()

    def _write_and_finish() -> None:
        time.sleep(0.2)
        with open(stdout_path, "a", encoding="utf-8") as f:
            f.write("Authorization: Bearer supersecret123\n")
        time.sleep(0.3)
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        _eng = create_engine(
            settings_override.database_url,
            connect_args={"check_same_thread": False},
        )
        _sf = sessionmaker(bind=_eng, autoflush=False, autocommit=False)
        _s = _sf()
        try:
            update_run(_s, run_id, status="succeeded", exit_code=0)
            _s.commit()
        finally:
            _s.close()
            _eng.dispose()

    writer = threading.Thread(target=_write_and_finish, daemon=True)
    writer.start()

    collected_lines: list[str] = []

    with app_client_streams.stream("GET", f"/api/v1/runs/{run_id}/logs", headers=_auth()) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            try:
                payload = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            if "status" in payload:
                break
            if "line" in payload:
                collected_lines.append(payload["line"])

    writer.join(timeout=5.0)

    # Secret must not appear in streamed output
    assert not any("supersecret123" in ln for ln in collected_lines)
    assert any("Bearer ***" in ln for ln in collected_lines)
