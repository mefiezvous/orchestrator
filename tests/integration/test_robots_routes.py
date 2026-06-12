# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the robots API router (P1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.config import Settings, get_settings
from orchestrator.core.robot_specs import RobotSpecEntry, write_robot_spec


def _make_app(settings: Settings) -> FastAPI:
    """Build a minimal FastAPI app with only the robots router.

    Injects *settings* as a ``get_settings`` override for the FastAPI DI layer,
    and monkeypatching of env vars + cache_clear handles the internal
    ``get_settings()`` calls inside ``core.robot_specs`` helpers.
    """
    from orchestrator.api.routes.robots import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def _create_payload(spec_id: str, name: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": spec_id,
        "name": name,
        "description": "test robot",
        "spec": {
            "n_joints": 7,
            "obs_keys": ["ee_pos", "cube_pos"],
            "action_dim": 8,
            "target_pos_key": "cube_pos",
        },
        "task": {
            "task_description": "Reach the cube",
            "fps": 20,
            "episode_length": 200,
            "seed": 42,
        },
        "adapter": {
            "type": "mujoco_playground",
            "env_name": "CubeReachV2",
        },
        "dataset": {
            "repo_id": "mefiezvous/cube-reach-dataset",
            "task_id": spec_id,
            "root": f"data/{spec_id}",
        },
    }
    payload.update(overrides)
    return payload


def _seed_specs(specs_dir: Path) -> None:
    write_robot_spec(
        RobotSpecEntry(
            id="cube_reach_v1",
            name="cube_reach",
            parent_id=None,
            version=1,
            created_at="2026-06-10T00:00:00Z",
            description="Cube reach v1",
            spec={
                "n_joints": 7,
                "obs_keys": ["ee_pos", "cube_pos"],
                "action_dim": 8,
                "target_pos_key": "cube_pos",
                "success_threshold": 0.05,
                "max_episode_steps": 200,
                "ee_pos_key": "ee_pos",
                "extra_obs_keys": [],
                "relational_features": [],
            },
            task={
                "task_description": "Reach the cube",
                "fps": 20,
                "episode_length": 200,
                "seed": 42,
            },
            adapter={"type": "mujoco_playground", "env_name": "CubeReachV1"},
            dataset={
                "repo_id": "mefiezvous/cube-reach-v1",
                "task_id": "cube_reach_v1",
                "root": "data/cube_reach_v1",
            },
        ),
        robot_specs_dir=specs_dir,
    )
    write_robot_spec(
        RobotSpecEntry(
            id="cube_reach_v2",
            name="cube_reach",
            parent_id="cube_reach_v1",
            version=1,
            created_at="2026-06-10T01:00:00Z",
            description="stub",
            spec={
                "n_joints": 7,
                "obs_keys": ["ee_pos", "cube_pos"],
                "action_dim": 8,
                "target_pos_key": "cube_pos",
                "success_threshold": 0.05,
                "max_episode_steps": 200,
                "ee_pos_key": "ee_pos",
                "extra_obs_keys": [],
                "relational_features": [],
            },
            task={
                "task_description": "Reach the cube",
                "fps": 20,
                "episode_length": 200,
                "seed": 42,
            },
            adapter=None,
            dataset={
                "repo_id": "mefiezvous/cube-reach-v2",
                "task_id": "cube_reach_v2",
                "root": "data/cube_reach_v2",
            },
        ),
        robot_specs_dir=specs_dir,
    )


def _settings_for(specs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("ROBOT_SPECS_DIR", str(specs_dir))
    monkeypatch.setenv("API_TOKEN", "test-token")
    get_settings.cache_clear()
    return Settings(_env_file=None)  # type: ignore[call-arg]


_AUTH = {"Authorization": "Bearer test-token"}


# ---------------------------------------------------------------------------
# GET /api/v1/robots
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_robots_empty_when_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"  # not created
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.get("/api/v1/robots/", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_get_robots_lists_seeded_specs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.get("/api/v1/robots/", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    ids = {e["id"] for e in data}
    assert ids == {"cube_reach_v1", "cube_reach_v2"}

    v2 = next(e for e in data if e["id"] == "cube_reach_v2")
    assert v2["parent_id"] == "cube_reach_v1"
    assert v2["adapter"] is None


# ---------------------------------------------------------------------------
# GET /api/v1/robots/lineage
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_robots_lineage_returns_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.get("/api/v1/robots/lineage", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    root = data[0]
    assert root["id"] == "cube_reach_v1"
    assert len(root["children"]) == 1
    assert root["children"][0]["id"] == "cube_reach_v2"


# ---------------------------------------------------------------------------
# GET /api/v1/robots/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_get_robot_by_id_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.get("/api/v1/robots/does_not_exist", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404


@pytest.mark.integration
def test_get_robot_by_id_returns_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.get("/api/v1/robots/cube_reach_v1", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "cube_reach_v1"
    assert data["spec"]["target_pos_key"] == "cube_pos"
    assert data["adapter"]["env_name"] == "CubeReachV1"


# ---------------------------------------------------------------------------
# POST /api/v1/robots
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_robot_writes_yaml_and_returns_201(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs_dir = tmp_path / "robot_specs"
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.post(
            "/api/v1/robots/", json=_create_payload("push_t_v1", "push_t"), headers=_AUTH
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "push_t_v1"
    assert data["parent_id"] is None
    assert (specs_dir / "push_t_v1.yaml").exists()


@pytest.mark.integration
def test_create_robot_with_relational_features_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tuple fields (relational_features) must survive a YAML round trip.

    ``RobotSpecFields.relational_features: list[tuple[str, str]]`` is dumped
    via ``model_dump()`` and written with ``yaml.safe_dump``; if tuples leak
    through as Python tuples, ``yaml.safe_load`` cannot parse them back and
    the spec becomes invisible to GET/list/lineage.
    """
    specs_dir = tmp_path / "robot_specs"
    s = _settings_for(specs_dir, monkeypatch)
    payload = _create_payload("rel_feat_v1", "rel_feat")
    payload["spec"]["relational_features"] = [["cube_pos", "ee_pos"]]
    try:
        client = TestClient(_make_app(s))
        create_response = client.post("/api/v1/robots/", json=payload, headers=_AUTH)
        get_response = client.get("/api/v1/robots/rel_feat_v1", headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json()["spec"]["relational_features"] == [["cube_pos", "ee_pos"]]


@pytest.mark.integration
def test_create_robot_duplicate_id_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.post(
            "/api/v1/robots/", json=_create_payload("cube_reach_v1", "cube_reach"), headers=_AUTH
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 409


@pytest.mark.integration
def test_create_robot_invalid_target_pos_key_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs_dir = tmp_path / "robot_specs"
    s = _settings_for(specs_dir, monkeypatch)
    payload = _create_payload("bad_robot_v1", "bad_robot")
    payload["spec"]["target_pos_key"] = "not_an_obs_key"
    try:
        client = TestClient(_make_app(s))
        response = client.post("/api/v1/robots/", json=payload, headers=_AUTH)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 422
    assert not (specs_dir / "bad_robot_v1.yaml").exists()


# ---------------------------------------------------------------------------
# POST /api/v1/robots/{parent_id}/branch
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_branch_robot_creates_child_with_parent_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.post(
            "/api/v1/robots/cube_reach_v1/branch",
            json=_create_payload("cube_reach_v3", "cube_reach"),
            headers=_AUTH,
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "cube_reach_v3"
    assert data["parent_id"] == "cube_reach_v1"


@pytest.mark.integration
def test_branch_robot_missing_parent_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.post(
            "/api/v1/robots/does_not_exist/branch",
            json=_create_payload("cube_reach_v3", "cube_reach"),
            headers=_AUTH,
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404


@pytest.mark.integration
def test_branch_robot_duplicate_id_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    specs_dir = tmp_path / "robot_specs"
    _seed_specs(specs_dir)
    s = _settings_for(specs_dir, monkeypatch)
    try:
        client = TestClient(_make_app(s))
        response = client.post(
            "/api/v1/robots/cube_reach_v1/branch",
            json=_create_payload("cube_reach_v2", "cube_reach"),
            headers=_AUTH,
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 409
