# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Pydantic response/request schemas for the orchestrator API.

WP-3 will add request schemas below the WP-3 section header.
WP-4 schemas live in the clearly-delimited section below.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---- Hydra introspection responses (WP-4) ----


class HydraConfigResponse(BaseModel):
    name: str
    group: str
    path: str
    fields: dict[str, Any]


class CheckpointResponse(BaseModel):
    robot: str
    policy: str
    step: int
    path: str
    size_bytes: int
    modified_at: str


class EvalReportResponse(BaseModel):
    robot: str
    policy: str
    path: str
    size_bytes: int
    modified_at: str
    has_video: bool
    summary: dict[str, Any]


class DatasetResponse(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified_at: str


# ---- Run job requests/responses (WP-3) ----


class CollectRequest(BaseModel):
    episodes: int = Field(gt=0, le=10000, default=10)
    env: str | None = None
    policy_type: Literal["scripted", "teleop"] = "scripted"
    push_to_hub: bool = False
    seed: int | None = None
    hydra_overrides: list[str] = Field(default_factory=list)


class TrainRequest(BaseModel):
    policy: Literal["act", "diffusion"]
    total_steps: int = Field(gt=0, le=10_000_000, default=10000)
    env: str | None = None
    profile: str | None = None
    hf_repo_id: str | None = None
    hydra_overrides: list[str] = Field(default_factory=list)


class EvalRequest(BaseModel):
    checkpoint_path: str
    n_episodes: int = Field(gt=0, le=1000, default=50)
    visualize: bool = False
    policy: Literal["act", "diffusion"] | None = None
    hydra_overrides: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    id: str
    job_type: str
    status: str
    argv: list[str]
    request_body: dict[str, Any]
    workspace_cwd: str
    stdout_path: str | None
    stderr_path: str | None
    mlflow_run_id: str | None
    hf_repo_id: str | None
    pid: int | None
    exit_code: int | None
    error_message: str | None
    created_at: str  # ISO
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_run(cls, run: Any) -> RunResponse:
        from orchestrator.db.models import to_dict

        return cls.model_validate(to_dict(run))


class RunCreatedResponse(BaseModel):
    run_id: str
    status: str


class HealthResponse(BaseModel):
    api: Literal["ok"]
    redis: Literal["ok", "down", "unknown"]
    mlflow: Literal["ok", "down", "unknown"]
    workspace: Literal["ok", "missing"]
    database: Literal["ok", "down"]


class VersionResponse(BaseModel):
    orchestrator: str
    python: str
    lerobot_repo_exists: bool
