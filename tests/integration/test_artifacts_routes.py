# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the artifacts API router (WP-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.config import get_settings


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with only the artifacts router."""
    from orchestrator.api.routes.artifacts import router

    app = FastAPI()
    app.include_router(router)
    return app


def _seed_artifacts(repo: Path) -> None:
    # Checkpoints
    ckpt_dir = repo / "checkpoints" / "so100" / "act"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / "step_001000.pt").write_bytes(b"x" * 512)

    # Eval reports
    report_dir = repo / "eval_reports" / "so100" / "act"
    report_dir.mkdir(parents=True)
    (report_dir / "eval_report.json").write_text(
        json.dumps({"success_rate": 0.9, "n_episodes": 10}), encoding="utf-8"
    )
    viz = report_dir / "viz"
    viz.mkdir()
    (viz / "episode_001.mp4").write_bytes(b"fakevideo")

    # Dataset config pointing to a real root
    ds_root = repo / "data" / "my_dataset"
    ds_root.mkdir(parents=True)
    (ds_root / "file.bin").write_bytes(b"0" * 1024)
    ds_cfg_dir = repo / "configs" / "dataset"
    ds_cfg_dir.mkdir(parents=True)
    (ds_cfg_dir / "default.yaml").write_text(f"root: {ds_root.as_posix()}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_checkpoints_returns_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/artifacts/checkpoints returns the seeded checkpoint."""
    repo = tmp_path / "lerobot"
    repo.mkdir()
    _seed_artifacts(repo)

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/artifacts/checkpoints")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["robot"] == "so100"
    assert entry["policy"] == "act"
    assert entry["step"] == 1000
    assert entry["size_bytes"] == 512
    assert "modified_at" in entry


@pytest.mark.integration
def test_get_eval_reports_returns_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/artifacts/eval-reports returns the seeded report with video flag."""
    repo = tmp_path / "lerobot"
    repo.mkdir()
    _seed_artifacts(repo)

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/artifacts/eval-reports")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["robot"] == "so100"
    assert entry["has_video"] is True
    assert entry["summary"]["success_rate"] == pytest.approx(0.9)


@pytest.mark.integration
def test_get_datasets_returns_expected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/artifacts/datasets returns the dataset discovered from YAML."""
    repo = tmp_path / "lerobot"
    repo.mkdir()
    _seed_artifacts(repo)

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        client = TestClient(_make_app())
        response = client.get("/api/v1/artifacts/datasets")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["name"] == "my_dataset"
    assert entry["size_bytes"] == 1024


@pytest.mark.integration
def test_all_artifact_routes_return_empty_when_repo_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All 3 artifact endpoints return [] when lerobot_repo does not exist."""
    monkeypatch.setenv("LEROBOT_REPO", str(tmp_path / "nonexistent"))
    get_settings.cache_clear()

    endpoints = ["/checkpoints", "/eval-reports", "/datasets"]

    try:
        client = TestClient(_make_app())
        for ep in endpoints:
            response = client.get(f"/api/v1/artifacts{ep}")
            assert response.status_code == 200, f"{ep} => {response.status_code}"
            assert response.json() == [], f"{ep} => {response.json()}"
    finally:
        get_settings.cache_clear()
