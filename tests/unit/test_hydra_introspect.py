# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for orchestrator.core.hydra_introspect."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.core.config import get_settings
from orchestrator.core.hydra_introspect import list_configs, list_env_configs


def _make_lerobot_repo(tmp_path: Path) -> Path:
    """Create a minimal fake lerobot repo structure."""
    repo = tmp_path / "lerobot-playground-portfolio"
    repo.mkdir()
    return repo


def _make_env_dir(repo: Path, files: dict[str, str]) -> Path:
    env_dir = repo / "configs" / "env"
    env_dir.mkdir(parents=True)
    for name, content in files.items():
        (env_dir / name).write_text(content, encoding="utf-8")
    return env_dir


# ---------------------------------------------------------------------------
# list_configs / list_env_configs
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_env_configs_finds_two_sorted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """list_env_configs returns 2 entries, sorted by name, underscore file skipped."""
    repo = _make_lerobot_repo(tmp_path)
    _make_env_dir(
        repo,
        {
            "zebra_env.yaml": "robot: zebra\nmax_steps: 100\n",
            "alpha_env.yaml": "robot: alpha\nmax_steps: 50\n",
            "_private.yaml": "robot: hidden\n",  # must be skipped
        },
    )

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        entries = list_env_configs()
    finally:
        get_settings.cache_clear()

    assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}: {entries}"
    assert entries[0].name == "alpha_env"
    assert entries[1].name == "zebra_env"
    # Verify group and relative path
    assert entries[0].group == "env"
    assert entries[0].path == "configs/env/alpha_env.yaml"
    assert entries[0].fields["robot"] == "alpha"
    assert entries[0].fields["max_steps"] == 50


@pytest.mark.unit
def test_list_configs_missing_dir_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_configs returns [] when the group directory does not exist."""
    repo = _make_lerobot_repo(tmp_path)
    # Do NOT create configs/env

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        result = list_configs("env")
    finally:
        get_settings.cache_clear()

    assert result == []


@pytest.mark.unit
def test_list_configs_missing_repo_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_configs returns [] when lerobot_repo itself does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    monkeypatch.setenv("LEROBOT_REPO", str(nonexistent))
    get_settings.cache_clear()

    try:
        result = list_env_configs()
    finally:
        get_settings.cache_clear()

    assert result == []


@pytest.mark.unit
def test_list_configs_malformed_yaml_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed YAML files are skipped; valid files are still returned."""
    repo = _make_lerobot_repo(tmp_path)
    _make_env_dir(
        repo,
        {
            "good.yaml": "robot: good\n",
            "bad.yaml": "robot: {unclosed_brace\n",  # invalid YAML
        },
    )

    monkeypatch.setenv("LEROBOT_REPO", str(repo))
    get_settings.cache_clear()

    try:
        entries = list_env_configs()
    finally:
        get_settings.cache_clear()

    names = [e.name for e in entries]
    assert "good" in names
    assert "bad" not in names


@pytest.mark.unit
def test_list_configs_lerobot_repo_kwarg(tmp_path: Path) -> None:
    """list_configs respects an explicit lerobot_repo kwarg without touching env."""
    repo = _make_lerobot_repo(tmp_path)
    _make_env_dir(repo, {"cube_reach_v1.yaml": "robot: so100\nmax_steps: 200\n"})

    entries = list_env_configs(lerobot_repo=repo)

    assert len(entries) == 1
    assert entries[0].name == "cube_reach_v1"
    assert entries[0].fields["robot"] == "so100"
