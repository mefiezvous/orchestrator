# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Pydantic response/request schemas for the orchestrator API.

WP-3 will add request schemas below the WP-3 section header.
WP-4 schemas live in the clearly-delimited section below.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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


# ---------------------------------------------------------------------------
# Robot specs (P1) — declare/branch robots from robot_specs/*.yaml
# ---------------------------------------------------------------------------

# Identifier pattern shared with lerobot-playground-portfolio's add_robot.py
# (LRB-004): technical keys (`id`, obs/feature names) used as registry keys,
# dataset namespaces, and dict keys must be snake_case identifiers.
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# MuJoCo Playground env class names (e.g. "CubeReachV1") — PascalCase identifiers.
_ENV_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# Hugging Face Hub repo id: "<owner>/<name>".
_HF_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _validate_id(value: str, label: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"{label} {value!r} must match {_ID_RE.pattern}")
    return value


def _validate_dataset_root(value: str) -> str:
    """Reject traversal/absolute paths; require a ``data/`` prefix (ORC-008-style)."""
    if ".." in value:
        raise ValueError("dataset.root must not contain '..'")
    p = Path(value)
    if p.is_absolute():
        raise ValueError("dataset.root must be a relative path")
    if p.parts[:1] != ("data",):
        raise ValueError("dataset.root must start with 'data/'")
    return value


class RobotSpecFields(BaseModel):
    """Mirrors ``mlcore.robots.base.RobotSpec`` (the ``spec:`` YAML section)."""

    n_joints: int = Field(gt=0)
    obs_keys: list[str] = Field(min_length=1)
    action_dim: int = Field(gt=0)
    target_pos_key: str
    success_threshold: float = Field(gt=0.0, lt=1.0, default=0.05)
    max_episode_steps: int = Field(gt=0, default=200)
    ee_pos_key: str = "ee_pos"
    extra_obs_keys: list[str] = Field(default_factory=list)
    relational_features: list[tuple[str, str]] = Field(default_factory=list)

    @field_validator("obs_keys", "extra_obs_keys")
    @classmethod
    def validate_key_lists(cls, v: list[str]) -> list[str]:
        return [_validate_id(k, "spec.obs_keys item") for k in v]

    @field_validator("target_pos_key", "ee_pos_key")
    @classmethod
    def validate_keys(cls, v: str) -> str:
        return _validate_id(v, "spec key")

    @field_validator("relational_features")
    @classmethod
    def validate_relational_features(cls, v: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [
            (
                _validate_id(a, "spec.relational_features item"),
                _validate_id(b, "spec.relational_features item"),
            )
            for a, b in v
        ]

    @model_validator(mode="after")
    def validate_target_pos_key_in_obs_keys(self) -> RobotSpecFields:
        if self.target_pos_key not in self.obs_keys:
            raise ValueError(
                f"spec.target_pos_key {self.target_pos_key!r} must be in "
                f"spec.obs_keys {self.obs_keys!r}"
            )
        return self


class RobotTaskFields(BaseModel):
    """The ``task:`` YAML section — "objectifs" not already covered by RobotSpecFields."""

    task_description: str = Field(default="", max_length=500)
    fps: int = Field(gt=0, default=20)
    episode_length: int = Field(gt=0, default=200)
    seed: int = 42


class RobotAdapterFields(BaseModel):
    """The ``adapter:`` YAML section. Absent/null = no auto-registration (lineage stub)."""

    type: Literal["mujoco_playground"]
    env_name: str

    @field_validator("env_name")
    @classmethod
    def validate_env_name(cls, v: str) -> str:
        if not _ENV_NAME_RE.fullmatch(v):
            raise ValueError(f"adapter.env_name {v!r} must match {_ENV_NAME_RE.pattern}")
        return v


class RobotDatasetFields(BaseModel):
    """The ``dataset:`` YAML section."""

    repo_id: str
    task_id: str
    root: str

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        if not _HF_REPO_ID_RE.fullmatch(v):
            raise ValueError(f"dataset.repo_id {v!r} must match '<owner>/<name>'")
        return v

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        return _validate_id(v, "dataset.task_id")

    @field_validator("root")
    @classmethod
    def validate_root(cls, v: str) -> str:
        return _validate_dataset_root(v)


class RobotSpecCreateRequest(BaseModel):
    """Body for ``POST /api/v1/robots`` — declares a new root robot spec."""

    id: str
    name: str
    description: str = Field(default="", max_length=500)
    spec: RobotSpecFields
    task: RobotTaskFields = Field(default_factory=RobotTaskFields)
    adapter: RobotAdapterFields | None = None
    dataset: RobotDatasetFields

    @field_validator("id", "name")
    @classmethod
    def validate_identifiers(cls, v: str) -> str:
        return _validate_id(v, "field")


class RobotSpecBranchRequest(RobotSpecCreateRequest):
    """Body for ``POST /api/v1/robots/{parent_id}/branch``.

    Same shape as :class:`RobotSpecCreateRequest` — ``parent_id`` is taken
    from the path, not the body, since it must reference an existing spec.
    """


class RobotSpecResponse(BaseModel):
    id: str
    name: str
    parent_id: str | None
    version: int
    created_at: str
    description: str
    spec: RobotSpecFields
    task: RobotTaskFields
    adapter: RobotAdapterFields | None
    dataset: RobotDatasetFields

    @classmethod
    def from_entry(cls, entry: Any) -> RobotSpecResponse:
        return cls(
            id=entry.id,
            name=entry.name,
            parent_id=entry.parent_id,
            version=entry.version,
            created_at=entry.created_at,
            description=entry.description,
            spec=RobotSpecFields.model_validate(entry.spec),
            task=RobotTaskFields.model_validate(entry.task),
            adapter=RobotAdapterFields.model_validate(entry.adapter) if entry.adapter else None,
            dataset=RobotDatasetFields.model_validate(entry.dataset),
        )


class LineageNodeResponse(BaseModel):
    id: str
    name: str
    parent_id: str | None
    description: str
    version: int
    created_at: str
    children: list[LineageNodeResponse] = Field(default_factory=list)

    @classmethod
    def from_node(cls, node: Any) -> LineageNodeResponse:
        return cls(
            id=node.id,
            name=node.name,
            parent_id=node.parent_id,
            description=node.description,
            version=node.version,
            created_at=node.created_at,
            children=[cls.from_node(child) for child in node.children],
        )
