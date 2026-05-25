# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the configs API router (WP-4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.config import get_settings


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with only the configs router."""
    # Import here so monkeypatching of settings takes effect first
    from orchestrator.api.routes.configs import router

    app = FastAPI()
    app.include_router(router)
    return app


def _seed_env_configs(lerobot_repo: Path) -> None:
    env_dir = lerobot_repo / "configs" / "env"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "cube_reach_v1.yaml").write_text("robot: so100\nmax_steps: 100\n", encoding="utf-8")
    (env_dir / "push_t_v1.yaml").write_text("robot: so101\nmax_steps: 200\n", encoding="utf-8")
    (env_dir / "_hidden.yaml").write_text("robot: hidden\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_envs_returns_expected_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/configs/envs returns 2 configs (underscore file excluded)."""
    repo = tmp_path / "lerobot"
    repo.mkdir()
    _seed_env_configs(repo)

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/configs/envs")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    names = {item["name"] for item in data}
    assert names == {"cube_reach_v1", "push_t_v1"}
    for item in data:
        assert "group" in item
        assert item["group"] == "env"
        assert "path" in item
        assert "fields" in item


@pytest.mark.integration
def test_get_envs_missing_lerobot_repo_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/v1/configs/envs returns [] when lerobot_repo does not exist."""
    monkeypatch.setenv("LEROBOT_REPO", str(tmp_path / "nonexistent"))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/configs/envs")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_get_policies_empty_without_yamls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/configs/policies returns [] when no policy yamls exist."""
    repo = tmp_path / "lerobot"
    (repo / "configs" / "policy").mkdir(parents=True)

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/configs/policies")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_all_config_routes_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All 6 config endpoints return 200 (even when empty)."""
    repo = tmp_path / "lerobot"
    repo.mkdir()

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    endpoints = ["/envs", "/policies", "/profiles", "/datasets", "/collect", "/eval"]

    try:
        client = TestClient(_make_app())
        for ep in endpoints:
            response = client.get(f"/api/v1/configs{ep}")
            assert response.status_code == 200, f"Endpoint {ep} returned {response.status_code}"
            assert isinstance(response.json(), list), f"Endpoint {ep} did not return a list"
    finally:
        get_settings.cache_clear()
