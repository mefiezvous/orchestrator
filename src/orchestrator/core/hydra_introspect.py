# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Pure read-only helpers to introspect Hydra YAML configs in the lerobot repo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from orchestrator.core.config import get_settings


@dataclass(frozen=True)
class HydraConfigEntry:
    name: str  # e.g. "cube_reach_v1"
    group: str  # e.g. "env"
    path: str  # relative path from lerobot_repo (e.g. "configs/env/cube_reach_v1.yaml")
    fields: dict[str, Any]  # parsed YAML content (top-level only)


def _resolve_lerobot_repo(lerobot_repo: Path | None) -> Path:
    if lerobot_repo is not None:
        return lerobot_repo
    return get_settings().lerobot_repo


def list_configs(group: str, *, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """Scan ``{lerobot_repo}/configs/{group}/*.yaml`` and return parsed entries.

    Files starting with ``_`` are skipped. Parse failures are logged and skipped.
    Returns an empty list if the directory does not exist.
    """
    repo = _resolve_lerobot_repo(lerobot_repo)
    configs_dir = repo / "configs" / group

    if not repo.exists():
        logger.warning("lerobot_repo does not exist: {}", repo)
        return []

    if not configs_dir.exists():
        logger.warning("Hydra config group directory does not exist: {}", configs_dir)
        return []

    entries: list[HydraConfigEntry] = []
    for yaml_path in configs_dir.glob("*.yaml"):
        if yaml_path.name.startswith("_"):
            continue
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            data: Any = yaml.safe_load(raw)
            fields: dict[str, Any] = data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to parse YAML config {}: {}", yaml_path, exc)
            continue

        rel_path = yaml_path.relative_to(repo)
        entries.append(
            HydraConfigEntry(
                name=yaml_path.stem,
                group=group,
                path=rel_path.as_posix(),
                fields=fields,
            )
        )

    entries.sort(key=lambda e: e.name)
    return entries


def list_env_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/env/*.yaml`` entries."""
    return list_configs("env", lerobot_repo=lerobot_repo)


def list_policy_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/policy/*.yaml`` entries."""
    return list_configs("policy", lerobot_repo=lerobot_repo)


def list_profile_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/training/*.yaml`` entries (training profiles)."""
    return list_configs("training", lerobot_repo=lerobot_repo)


def list_eval_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/eval/*.yaml`` entries."""
    return list_configs("eval", lerobot_repo=lerobot_repo)


def list_dataset_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/dataset/*.yaml`` entries."""
    return list_configs("dataset", lerobot_repo=lerobot_repo)


def list_collect_configs(*, lerobot_repo: Path | None = None) -> list[HydraConfigEntry]:
    """List ``configs/collect/*.yaml`` entries."""
    return list_configs("collect", lerobot_repo=lerobot_repo)
