# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for orchestrator.core.artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.core.artifacts import list_checkpoints, list_datasets, list_eval_reports


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "lerobot-playground-portfolio"
    repo.mkdir()
    return repo


# ---------------------------------------------------------------------------
# list_checkpoints
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_checkpoints_walks_robot_policy_tree(tmp_path: Path) -> None:
    """list_checkpoints discovers step_*.pt files under checkpoints/{robot}/{policy}/."""
    repo = _make_repo(tmp_path)
    ckpt_dir = repo / "checkpoints"

    # Create two robots, one policy each, multiple steps
    (ckpt_dir / "so100" / "act").mkdir(parents=True)
    (ckpt_dir / "so100" / "act" / "step_001000.pt").write_bytes(b"x" * 512)
    (ckpt_dir / "so100" / "act" / "step_002000.pt").write_bytes(b"x" * 1024)

    (ckpt_dir / "so101" / "diffusion").mkdir(parents=True)
    (ckpt_dir / "so101" / "diffusion" / "step_000500.pt").write_bytes(b"x" * 256)

    entries = list_checkpoints(lerobot_repo=repo)

    assert len(entries) == 3
    # sorted by (robot, policy, step)
    assert entries[0].robot == "so100" and entries[0].step == 1000
    assert entries[1].robot == "so100" and entries[1].step == 2000
    assert entries[2].robot == "so101" and entries[2].step == 500

    # size_bytes matches what we wrote
    assert entries[0].size_bytes == 512
    assert entries[1].size_bytes == 1024

    # path is absolute
    assert Path(entries[0].path).is_absolute()


@pytest.mark.unit
def test_list_checkpoints_missing_dir_returns_empty(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # No checkpoints/ dir
    assert list_checkpoints(lerobot_repo=repo) == []


@pytest.mark.unit
def test_list_checkpoints_missing_repo_returns_empty(tmp_path: Path) -> None:
    assert list_checkpoints(lerobot_repo=tmp_path / "nonexistent") == []


# ---------------------------------------------------------------------------
# list_eval_reports
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_eval_reports_parses_summary(tmp_path: Path) -> None:
    """list_eval_reports parses JSON summary and detects video files."""
    repo = _make_repo(tmp_path)
    eval_dir = repo / "eval_reports"

    # Robot A — with video
    report_a_dir = eval_dir / "so100" / "act"
    report_a_dir.mkdir(parents=True)
    summary_a = {
        "success_rate": 0.85,
        "mean_reward": 42.3,
        "n_episodes": 20,
    }
    (report_a_dir / "eval_report.json").write_text(json.dumps(summary_a), encoding="utf-8")
    viz_dir = report_a_dir / "viz"
    viz_dir.mkdir()
    (viz_dir / "episode_001.mp4").write_bytes(b"fakevideo")

    # Robot B — no video
    report_b_dir = eval_dir / "so101" / "diffusion"
    report_b_dir.mkdir(parents=True)
    (report_b_dir / "eval_report.json").write_text(
        json.dumps({"success_rate": 0.60, "n_episodes": 10}), encoding="utf-8"
    )

    entries = list_eval_reports(lerobot_repo=repo)

    assert len(entries) == 2
    by_robot = {e.robot: e for e in entries}

    a = by_robot["so100"]
    assert a.policy == "act"
    assert a.has_video is True
    assert a.summary["success_rate"] == pytest.approx(0.85)
    assert a.summary["n_episodes"] == 20

    b = by_robot["so101"]
    assert b.has_video is False
    assert b.summary["success_rate"] == pytest.approx(0.60)


@pytest.mark.unit
def test_list_eval_reports_missing_dir_returns_empty(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert list_eval_reports(lerobot_repo=repo) == []


# ---------------------------------------------------------------------------
# list_datasets
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_datasets_from_yaml_root(tmp_path: Path) -> None:
    """list_datasets reads root: from dataset YAML configs and sums file sizes.

    ORC-009: dataset root must be under lerobot_repo/data/ — the test now
    places the dataset root there to match the enforced confinement.
    """
    repo = _make_repo(tmp_path)
    dataset_dir = repo / "configs" / "dataset"
    dataset_dir.mkdir(parents=True)

    # Create a real dataset root inside lerobot_repo/data/ (ORC-009 confinement)
    ds_root = repo / "data" / "lerobot_cube"
    ds_root.mkdir(parents=True)
    (ds_root / "data.hdf5").write_bytes(b"0" * 2048)
    (ds_root / "meta.json").write_bytes(b"1" * 512)

    (dataset_dir / "cube_reach.yaml").write_text(
        f"root: {ds_root.as_posix()}\nname: cube_reach\n", encoding="utf-8"
    )

    entries = list_datasets(lerobot_repo=repo)

    assert len(entries) == 1
    e = entries[0]
    assert e.name == "lerobot_cube"
    assert e.size_bytes == 2048 + 512
    assert Path(e.path) == ds_root


@pytest.mark.unit
def test_list_datasets_nonexistent_root_skipped(tmp_path: Path) -> None:
    """Datasets whose root path does not exist on disk are skipped."""
    repo = _make_repo(tmp_path)
    dataset_dir = repo / "configs" / "dataset"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "ghost.yaml").write_text("root: /does/not/exist/at/all\n", encoding="utf-8")

    entries = list_datasets(lerobot_repo=repo)
    assert entries == []


@pytest.mark.unit
def test_list_datasets_missing_dir_returns_empty(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert list_datasets(lerobot_repo=repo) == []
