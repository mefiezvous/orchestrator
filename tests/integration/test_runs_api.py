# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the runs API router (WP-3)."""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from orchestrator.core.config import Settings, get_settings
from orchestrator.db.engine import get_session
from orchestrator.db.models import Run

# ---------------------------------------------------------------------------
# Fixture: fake worker queue module + app client
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client(
    db_session: Session,
    settings_override: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, dict[str, MagicMock]]:
    """
    Build a TestClient for the runs router with:
    - Fake orchestrator.worker.queue module (in case WP-2 is not merged)
    - get_session dependency overridden to use test db_session
    - get_settings dependency overridden to use settings_override
    """
    # Create a fake orchestrator.worker.queue module
    fake_queue = types.ModuleType("orchestrator.worker.queue")
    mock_enqueue_collect = MagicMock(return_value="job_id_123")
    mock_enqueue_train = MagicMock(return_value="job_id_123")
    mock_enqueue_eval = MagicMock(return_value="job_id_123")
    mock_cancel_job = MagicMock(return_value=True)

    fake_queue.enqueue_collect = mock_enqueue_collect  # type: ignore[attr-defined]
    fake_queue.enqueue_train = mock_enqueue_train  # type: ignore[attr-defined]
    fake_queue.enqueue_eval = mock_enqueue_eval  # type: ignore[attr-defined]
    fake_queue.cancel_job = mock_cancel_job  # type: ignore[attr-defined]

    # Also ensure parent package exists
    if "orchestrator.worker" not in sys.modules:
        fake_worker = types.ModuleType("orchestrator.worker")
        sys.modules["orchestrator.worker"] = fake_worker
    sys.modules["orchestrator.worker.queue"] = fake_queue

    # Build the app
    from orchestrator.api.main import create_app

    app = create_app()

    # Override dependencies
    def _override_session():  # type: ignore[return]
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: settings_override

    mocks = {
        "enqueue_collect": mock_enqueue_collect,
        "enqueue_train": mock_enqueue_train,
        "enqueue_eval": mock_enqueue_eval,
        "cancel_job": mock_cancel_job,
    }

    client = TestClient(app, raise_server_exceptions=False)
    return client, mocks


def _auth_headers(token: str = "test-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /collect
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_post_collect_returns_202(
    app_client: tuple[TestClient, dict[str, MagicMock]],
    db_session: Session,
) -> None:
    """POST /collect with valid token returns 202 and a run_id."""
    client, mocks = app_client
    response = client.post(
        "/api/v1/runs/collect",
        json={"episodes": 5},
        headers=_auth_headers(),
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "queued"
    # enqueue was called
    mocks["enqueue_collect"].assert_called_once()


@pytest.mark.integration
def test_post_collect_without_token_returns_401(
    app_client: tuple[TestClient, dict[str, MagicMock]],
) -> None:
    """POST /collect without token returns 401."""
    client, _ = app_client
    response = client.post("/api/v1/runs/collect", json={"episodes": 5})
    assert response.status_code == 401


@pytest.mark.integration
def test_post_collect_invalid_body_returns_422(
    app_client: tuple[TestClient, dict[str, MagicMock]],
) -> None:
    """POST /collect with episodes=0 (invalid) returns 422."""
    client, _ = app_client
    response = client.post(
        "/api/v1/runs/collect",
        json={"episodes": 0},
        headers=_auth_headers(),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET by id
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_run_by_id_returns_run(
    app_client: tuple[TestClient, dict[str, MagicMock]],
) -> None:
    """GET /runs/{id} returns the created run."""
    client, _ = app_client

    # Create a run first
    create_resp = client.post(
        "/api/v1/runs/collect",
        json={"episodes": 3},
        headers=_auth_headers(),
    )
    assert create_resp.status_code == 202
    run_id = create_resp.json()["run_id"]

    # Fetch by ID
    get_resp = client.get(f"/api/v1/runs/{run_id}", headers=_auth_headers())
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == run_id
    assert data["job_type"] == "collect"


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_runs_list_includes_created_run(
    app_client: tuple[TestClient, dict[str, MagicMock]],
) -> None:
    """GET /runs/ lists created runs."""
    client, _ = app_client

    create_resp = client.post(
        "/api/v1/runs/collect",
        json={"episodes": 2},
        headers=_auth_headers(),
    )
    assert create_resp.status_code == 202
    run_id = create_resp.json()["run_id"]

    list_resp = client.get("/api/v1/runs/", headers=_auth_headers())
    assert list_resp.status_code == 200
    ids = [r["id"] for r in list_resp.json()]
    assert run_id in ids


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_delete_run_returns_204_and_cancels(
    app_client: tuple[TestClient, dict[str, MagicMock]],
    db_session: Session,
) -> None:
    """DELETE /runs/{id} returns 204 and sets status to cancelled."""
    client, mocks = app_client

    create_resp = client.post(
        "/api/v1/runs/collect",
        json={"episodes": 1},
        headers=_auth_headers(),
    )
    assert create_resp.status_code == 202
    run_id = create_resp.json()["run_id"]

    del_resp = client.delete(f"/api/v1/runs/{run_id}", headers=_auth_headers())
    assert del_resp.status_code == 204

    # Verify status in DB
    db_session.expire_all()
    from orchestrator.db.models import get_run as _get_run

    run = _get_run(db_session, run_id)
    assert run is not None
    assert run.status == "cancelled"
    mocks["cancel_job"].assert_called()


@pytest.mark.integration
def test_delete_succeeded_run_returns_409(
    app_client: tuple[TestClient, dict[str, MagicMock]],
    db_session: Session,
    run_factory: Any,
) -> None:
    """DELETE on a succeeded run returns 409."""
    client, _ = app_client

    run: Run = run_factory(job_type="train", status="succeeded")
    db_session.commit()

    del_resp = client.delete(f"/api/v1/runs/{run.id}", headers=_auth_headers())
    assert del_resp.status_code == 409
