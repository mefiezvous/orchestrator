# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the main FastAPI app factory."""

from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient


def _inject_fake_queue() -> None:
    """Inject a fake orchestrator.worker.queue module to avoid import errors."""
    if "orchestrator.worker.queue" not in sys.modules:
        from unittest.mock import MagicMock

        fake_queue = types.ModuleType("orchestrator.worker.queue")
        fake_queue.enqueue_collect = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
        fake_queue.enqueue_train = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
        fake_queue.enqueue_eval = MagicMock(return_value="job_id")  # type: ignore[attr-defined]
        fake_queue.cancel_job = MagicMock(return_value=True)  # type: ignore[attr-defined]

        if "orchestrator.worker" not in sys.modules:
            fake_worker = types.ModuleType("orchestrator.worker")
            sys.modules["orchestrator.worker"] = fake_worker
        sys.modules["orchestrator.worker.queue"] = fake_queue


@pytest.mark.integration
def test_create_app_imports_cleanly() -> None:
    """create_app() can be imported and called without errors."""
    _inject_fake_queue()
    from orchestrator.api.main import create_app

    app = create_app()
    assert app is not None
    assert app.title == "orchestrator"


@pytest.mark.integration
def test_openapi_json_includes_expected_routes(settings_override: object) -> None:
    """GET /api/openapi.json includes paths from runs, system, configs, artifacts."""
    _inject_fake_queue()
    from orchestrator.api.main import create_app
    from orchestrator.core.config import get_settings

    app = create_app()
    # Override settings to avoid real filesystem/db issues

    app.dependency_overrides[get_settings] = lambda: settings_override

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/openapi.json")
    assert response.status_code == 200

    paths = response.json().get("paths", {})
    path_keys = list(paths.keys())

    # Verify runs routes
    assert any("/api/v1/runs" in p for p in path_keys), f"runs paths missing from {path_keys}"
    # Verify system routes
    assert any("/api/v1/health" in p for p in path_keys), f"health path missing from {path_keys}"
    assert any("/api/v1/version" in p for p in path_keys), f"version path missing from {path_keys}"
    # Verify configs routes
    assert any("/api/v1/configs" in p for p in path_keys), f"configs paths missing from {path_keys}"
    # Verify artifacts routes
    assert any("/api/v1/artifacts" in p for p in path_keys), (
        f"artifacts paths missing from {path_keys}"
    )


@pytest.mark.integration
def test_swagger_ui_returns_200(settings_override: object) -> None:
    """GET /api/docs returns 200 with text/html."""
    _inject_fake_queue()
    from orchestrator.api.main import create_app
    from orchestrator.core.config import get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_override

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
