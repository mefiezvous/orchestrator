# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit-ish tests for _build_argv in collect/train/eval job modules."""

from __future__ import annotations

import pytest

from orchestrator.worker.jobs.collect import _build_argv as collect_argv
from orchestrator.worker.jobs.eval import _build_argv as eval_argv
from orchestrator.worker.jobs.train import _build_argv as train_argv

# ---------------------------------------------------------------------------
# collect _build_argv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectArgv:
    def test_minimal(self) -> None:
        body = {"episodes": 10, "hydra_overrides": []}
        argv = collect_argv(body)
        assert argv[0:4] == ["uv", "run", "python", "collect.py"]
        assert "episodes=10" in argv
        assert "policy_type=scripted" in argv
        assert "push_to_hub=false" in argv

    def test_with_env_and_seed(self) -> None:
        body = {
            "episodes": 5,
            "env": "cube_reach_v1",
            "seed": 42,
            "hydra_overrides": [],
        }
        argv = collect_argv(body)
        assert "env=cube_reach_v1" in argv
        assert "seed=42" in argv

    def test_env_none_not_in_argv(self) -> None:
        body = {"episodes": 3, "env": None, "hydra_overrides": []}
        argv = collect_argv(body)
        assert not any(a.startswith("env=") for a in argv)

    def test_seed_none_not_in_argv(self) -> None:
        body = {"episodes": 3, "seed": None, "hydra_overrides": []}
        argv = collect_argv(body)
        assert not any(a.startswith("seed=") for a in argv)

    def test_policy_type_teleop(self) -> None:
        body = {"episodes": 1, "policy_type": "teleop", "hydra_overrides": []}
        argv = collect_argv(body)
        assert "policy_type=teleop" in argv

    def test_push_to_hub_true(self) -> None:
        body = {"episodes": 1, "push_to_hub": True, "hydra_overrides": []}
        argv = collect_argv(body)
        assert "push_to_hub=true" in argv

    def test_hydra_overrides_appended(self) -> None:
        body = {
            "episodes": 1,
            "hydra_overrides": ["dataset.repo_id=myorg/repo", "logger=wandb"],
        }
        argv = collect_argv(body)
        assert "dataset.repo_id=myorg/repo" in argv
        assert "logger=wandb" in argv

    def test_hydra_overrides_at_end(self) -> None:
        overrides = ["foo=bar", "baz=qux"]
        body = {"episodes": 1, "hydra_overrides": overrides}
        argv = collect_argv(body)
        assert argv[-2:] == overrides


# ---------------------------------------------------------------------------
# train _build_argv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrainArgv:
    def test_minimal(self) -> None:
        body = {"policy": "act", "total_steps": 1000, "hydra_overrides": []}
        argv = train_argv(body)
        assert argv[0:4] == ["uv", "run", "python", "train.py"]
        assert "policy=act" in argv
        assert "training.total_steps=1000" in argv

    def test_profile_inserted_before_policy(self) -> None:
        body = {
            "policy": "diffusion",
            "total_steps": 500,
            "profile": "kaggle",
            "hydra_overrides": [],
        }
        argv = train_argv(body)
        assert "--config-name" in argv
        cfg_idx = argv.index("--config-name")
        assert argv[cfg_idx + 1] == "training/kaggle"
        # --config-name must come before policy
        assert cfg_idx < argv.index("policy=diffusion")

    def test_profile_default(self) -> None:
        body = {
            "policy": "act",
            "total_steps": 100,
            "profile": "default",
            "hydra_overrides": [],
        }
        argv = train_argv(body)
        assert "--config-name" in argv
        idx = argv.index("--config-name")
        assert argv[idx + 1] == "training/default"

    def test_no_profile_no_config_name(self) -> None:
        body = {"policy": "act", "total_steps": 100, "hydra_overrides": []}
        argv = train_argv(body)
        assert "--config-name" not in argv

    def test_env_included(self) -> None:
        body = {
            "policy": "act",
            "total_steps": 100,
            "env": "cube_reach_v1",
            "hydra_overrides": [],
        }
        argv = train_argv(body)
        assert "env=cube_reach_v1" in argv

    def test_env_none_excluded(self) -> None:
        body = {"policy": "act", "total_steps": 100, "env": None, "hydra_overrides": []}
        argv = train_argv(body)
        assert not any(a.startswith("env=") for a in argv)

    def test_hf_repo_id_included(self) -> None:
        body = {
            "policy": "act",
            "total_steps": 100,
            "hf_repo_id": "myorg/model",
            "hydra_overrides": [],
        }
        argv = train_argv(body)
        assert "hf_repo_id=myorg/model" in argv

    def test_hf_repo_id_none_excluded(self) -> None:
        body = {
            "policy": "act",
            "total_steps": 100,
            "hf_repo_id": None,
            "hydra_overrides": [],
        }
        argv = train_argv(body)
        assert not any(a.startswith("hf_repo_id=") for a in argv)

    def test_hydra_overrides_appended(self) -> None:
        body = {
            "policy": "act",
            "total_steps": 100,
            "hydra_overrides": ["training.batch_size=64"],
        }
        argv = train_argv(body)
        assert argv[-1] == "training.batch_size=64"


# ---------------------------------------------------------------------------
# eval _build_argv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEvalArgv:
    def test_minimal(self) -> None:
        body = {
            "checkpoint_path": "/data/ckpt/last.pt",
            "n_episodes": 10,
            "hydra_overrides": [],
        }
        argv = eval_argv(body)
        assert argv[0:4] == ["uv", "run", "python", "eval.py"]
        assert "+eval.checkpoint_path=/data/ckpt/last.pt" in argv
        assert "+eval.n_episodes=10" in argv
        assert "+eval.visualize=false" in argv

    def test_visualize_true(self) -> None:
        body = {
            "checkpoint_path": "/ckpt",
            "n_episodes": 5,
            "visualize": True,
            "hydra_overrides": [],
        }
        argv = eval_argv(body)
        assert "+eval.visualize=true" in argv

    def test_policy_included(self) -> None:
        body = {
            "checkpoint_path": "/ckpt",
            "n_episodes": 5,
            "policy": "act",
            "hydra_overrides": [],
        }
        argv = eval_argv(body)
        assert "policy=act" in argv

    def test_policy_none_excluded(self) -> None:
        body = {
            "checkpoint_path": "/ckpt",
            "n_episodes": 5,
            "policy": None,
            "hydra_overrides": [],
        }
        argv = eval_argv(body)
        assert not any(a.startswith("policy=") for a in argv)

    def test_hydra_overrides_appended(self) -> None:
        body = {
            "checkpoint_path": "/ckpt",
            "n_episodes": 2,
            "hydra_overrides": ["eval.render_mode=rgb_array"],
        }
        argv = eval_argv(body)
        assert argv[-1] == "eval.render_mode=rgb_array"
