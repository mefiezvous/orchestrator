# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for require_token auth dependency."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.config import Settings, get_settings


def _make_app_with_protected_route(settings: Settings) -> FastAPI:
    """Build a minimal FastAPI app with one protected route."""
    from orchestrator.api.auth import require_token

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_token)])
    def protected() -> dict[str, str]:
        return {"status": "ok"}

    app.dependency_overrides[get_settings] = lambda: settings
    return app


@pytest.mark.integration
def test_no_auth_header_returns_401(settings_override: Settings) -> None:
    """Missing Authorization header yields 401."""
    app = _make_app_with_protected_route(settings_override)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/protected")
    assert response.status_code == 401
    assert "missing bearer token" in response.json()["detail"]


@pytest.mark.integration
def test_wrong_token_returns_401(settings_override: Settings) -> None:
    """Wrong token yields 401."""
    app = _make_app_with_protected_route(settings_override)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/protected", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert "invalid token" in response.json()["detail"]


@pytest.mark.integration
def test_wrong_scheme_returns_401(settings_override: Settings) -> None:
    """Non-Bearer scheme yields 401."""
    app = _make_app_with_protected_route(settings_override)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401
    assert "missing bearer token" in response.json()["detail"]


@pytest.mark.integration
def test_empty_api_token_allows_all_requests(tmp_data_dir: object) -> None:
    """When API_TOKEN is empty, auth is disabled and all requests pass through (dev mode)."""
    # Build settings with empty token
    settings_no_token = Settings(api_token="")  # type: ignore[call-arg]
    app = _make_app_with_protected_route(settings_no_token)
    client = TestClient(app, raise_server_exceptions=False)
    # No auth header — still succeeds because auth is disabled
    response = client.get("/protected")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
def test_correct_token_returns_200(settings_override: Settings) -> None:
    """Correct token yields 200."""
    app = _make_app_with_protected_route(settings_override)
    client = TestClient(app, raise_server_exceptions=False)
    # settings_override uses "test-token" per conftest
    response = client.get("/protected", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
