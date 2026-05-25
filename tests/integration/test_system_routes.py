# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the system routes (health, version)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from orchestrator.core.config import Settings, get_settings
from orchestrator.db.engine import get_session


def _make_system_app(db_session: Session, settings: Settings) -> object:
    from fastapi import FastAPI

    from orchestrator.api.routes.system import router

    app = FastAPI()
    app.include_router(router)

    def _override_session():  # type: ignore[return]
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: settings
    return app


@pytest.mark.integration
def test_health_returns_200(
    db_session: Session,
    settings_override: Settings,
) -> None:
    """GET /api/v1/health returns 200 with api=ok."""
    app = _make_system_app(db_session, settings_override)
    client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["api"] == "ok"
    assert "redis" in data
    assert "mlflow" in data
    assert "workspace" in data
    assert "database" in data
    assert data["database"] == "ok"


@pytest.mark.integration
def test_version_returns_200_with_expected_keys(
    db_session: Session,
    settings_override: Settings,
) -> None:
    """GET /api/v1/version returns 200 with orchestrator, python, lerobot_repo_exists keys."""
    app = _make_system_app(db_session, settings_override)
    client = TestClient(app, raise_server_exceptions=False)  # type: ignore[arg-type]
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    data = response.json()
    assert "orchestrator" in data
    assert "python" in data
    assert "lerobot_repo_exists" in data
    assert isinstance(data["lerobot_repo_exists"], bool)
    assert data["orchestrator"] == "0.1.0"
