# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the schema validators added after the 2026-06-12 audit.

Covers:
- WS-02: ``env``/``profile``/``hf_repo_id`` reach the Hydra argv outside the
  ``hydra_overrides`` list and must reject the ``${oc.env:...}`` resolver and
  malformed repo ids.
- WS-01b: free-text robot fields (``name``, ``description``, ``task_description``)
  must reject private-layer / proprietary references before a YAML file is
  written into the PUBLIC ``robot_specs/`` directory.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas import (
    CollectRequest,
    RobotSpecCreateRequest,
    RobotTaskFields,
    TrainRequest,
)


def _robot_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "good_robot_v1",
        "name": "good_robot",
        "description": "a fine robot",
        "spec": {
            "n_joints": 7,
            "obs_keys": ["ee_pos", "cube_pos"],
            "action_dim": 8,
            "target_pos_key": "cube_pos",
        },
        "task": {"task_description": "Reach the cube"},
        "adapter": {"type": "mujoco_playground", "env_name": "CubeReachV1"},
        "dataset": {
            "repo_id": "mefiezvous/cube",
            "task_id": "good_robot_v1",
            "root": "data/good_robot_v1",
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# WS-02 — env / profile / hf_repo_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_collect_rejects_oc_env_resolver() -> None:
    with pytest.raises(ValidationError):
        CollectRequest(env="${oc.env:HF_TOKEN}")


@pytest.mark.unit
def test_collect_accepts_plain_env() -> None:
    assert CollectRequest(env="cube_reach_v1").env == "cube_reach_v1"


@pytest.mark.unit
@pytest.mark.parametrize("field", ["env", "profile"])
def test_train_rejects_oc_env_resolver(field: str) -> None:
    with pytest.raises(ValidationError):
        TrainRequest(policy="act", **{field: "${oc.env:HF_TOKEN}"})


@pytest.mark.unit
def test_train_rejects_malformed_hf_repo_id() -> None:
    with pytest.raises(ValidationError):
        TrainRequest(policy="act", hf_repo_id="not a repo id")


@pytest.mark.unit
def test_train_accepts_valid_fields() -> None:
    req = TrainRequest(
        policy="act",
        env="cube_reach_v1",
        profile="act_fast",
        hf_repo_id="mefiezvous/cube-reach",
    )
    assert req.hf_repo_id == "mefiezvous/cube-reach"


# ---------------------------------------------------------------------------
# WS-01b — IP-leak terms in free-text robot fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_robot_rejects_private_path_in_description() -> None:
    with pytest.raises(ValidationError):
        RobotSpecCreateRequest.model_validate(
            _robot_payload(description="derived from _private/my-robot-stack")
        )


@pytest.mark.unit
def test_robot_rejects_proprietary_in_name() -> None:
    with pytest.raises(ValidationError):
        RobotSpecCreateRequest.model_validate(
            _robot_payload(id="proprietary_bot", name="proprietary_bot")
        )


@pytest.mark.unit
def test_robot_rejects_leak_in_task_description() -> None:
    with pytest.raises(ValidationError):
        RobotSpecCreateRequest.model_validate(
            _robot_payload(task={"task_description": "see my-robot-stack/ for details"})
        )


@pytest.mark.unit
def test_task_fields_reject_all_rights_reserved() -> None:
    with pytest.raises(ValidationError):
        RobotTaskFields(task_description="All Rights Reserved")


@pytest.mark.unit
def test_robot_accepts_clean_payload() -> None:
    req = RobotSpecCreateRequest.model_validate(_robot_payload())
    assert req.id == "good_robot_v1"
