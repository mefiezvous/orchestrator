# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Pydantic response/request schemas for the orchestrator API.

WP-3 will add request schemas below the WP-3 section header.
WP-4 schemas live in the clearly-delimited section below.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# hydra_overrides validation (ORC-002)
# ---------------------------------------------------------------------------

# Dangerous OmegaConf resolvers that could exfiltrate env-vars or execute code.
# Reject any ${<resolver>:...} interpolation that isn't a known-safe Hydra
# config reference.  The whitelist below allows structural references like
# ${dataset.name} while blocking ${oc.env:SECRET}.
_DANGEROUS_RESOLVER_RE = re.compile(
    r"\$\{(?!dataset\.|policy\.|env_config\.|training\.|eval\.|robot\.)[A-Za-z_][^}]*:[^}]*\}"
)

# Allow only safe characters in each override entry.  Covers the common
# Hydra syntax: key=value, +key=value, ~key, //key, group/subgroup=value.
# Structural references like ${dataset.name} (no colon) are still allowed.
_SAFE_OVERRIDE_RE = re.compile(
    r"^[A-Za-z0-9_.+@/=,\-~]+(\$\{[A-Za-z0-9_.]+\}[A-Za-z0-9_.+@/=,\-~]*)*$"
)

_MAX_OVERRIDES = 32
_MAX_OVERRIDE_LEN = 256

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


def _validate_hydra_overrides(overrides: list[str]) -> list[str]:
    """Shared validator for hydra_overrides across all request types (ORC-002).

    Rejects:
    - More than _MAX_OVERRIDES entries
    - Any single entry longer than _MAX_OVERRIDE_LEN characters
    - Any entry containing a dangerous OmegaConf resolver (e.g. ${oc.env:VAR})
    - Any entry with characters outside the safe allowlist
    """
    if len(overrides) > _MAX_OVERRIDES:
        raise ValueError(
            f"hydra_overrides must contain at most {_MAX_OVERRIDES} entries, got {len(overrides)}"
        )
    for entry in overrides:
        if len(entry) > _MAX_OVERRIDE_LEN:
            raise ValueError(
                f"hydra_override entry too long (max {_MAX_OVERRIDE_LEN} chars): {entry[:64]!r}..."
            )
        if _DANGEROUS_RESOLVER_RE.search(entry):
            raise ValueError(
                f"hydra_override entry contains a forbidden OmegaConf resolver "
                f"(e.g. ${{oc.env:...}}): {entry!r}"
            )
        if not _SAFE_OVERRIDE_RE.match(entry):
            raise ValueError(f"hydra_override entry contains forbidden characters: {entry!r}")
    return overrides


class CollectRequest(BaseModel):
    episodes: int = Field(gt=0, le=10000, default=10)
    env: str | None = None
    policy_type: Literal["scripted", "teleop"] = "scripted"
    push_to_hub: bool = False
    seed: int | None = None
    hydra_overrides: list[str] = Field(default_factory=list)

    @field_validator("hydra_overrides")
    @classmethod
    def validate_overrides(cls, v: list[str]) -> list[str]:
        return _validate_hydra_overrides(v)


class TrainRequest(BaseModel):
    policy: Literal["act", "diffusion"]
    total_steps: int = Field(gt=0, le=10_000_000, default=10000)
    env: str | None = None
    profile: str | None = None
    hf_repo_id: str | None = None
    hydra_overrides: list[str] = Field(default_factory=list)

    @field_validator("hydra_overrides")
    @classmethod
    def validate_overrides(cls, v: list[str]) -> list[str]:
        return _validate_hydra_overrides(v)


class EvalRequest(BaseModel):
    checkpoint_path: str
    n_episodes: int = Field(gt=0, le=1000, default=50)
    visualize: bool = False
    policy: Literal["act", "diffusion"] | None = None
    hydra_overrides: list[str] = Field(default_factory=list)

    @field_validator("hydra_overrides")
    @classmethod
    def validate_overrides(cls, v: list[str]) -> list[str]:
        return _validate_hydra_overrides(v)

    @field_validator("checkpoint_path")
    @classmethod
    def validate_checkpoint_path(cls, v: str) -> str:
        """Reject path traversal and absolute paths outside allowed roots (ORC-008).

        Full confinement to lerobot_repo/checkpoints/ is enforced at the route
        level (where settings are available).  Here we reject obvious traversal
        attempts and non-.pt/.safetensors extensions.
        """
        if ".." in v:
            raise ValueError("checkpoint_path must not contain '..'")
        from pathlib import Path

        p = Path(v)
        if p.is_absolute():
            raise ValueError(
                "checkpoint_path must be a relative path under the checkpoints/ directory"
            )
        if p.suffix not in {".pt", ".safetensors"}:
            raise ValueError("checkpoint_path must end with .pt or .safetensors")
        return v


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
