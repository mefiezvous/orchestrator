# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Pure read-only helpers to browse training artifacts on disk."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from orchestrator.core.config import get_settings

_FILE_CAP = 1000  # max files to walk when computing dataset size


@dataclass(frozen=True)
class CheckpointEntry:
    robot: str  # robot_name from path
    policy: str  # policy_type from path
    step: int  # parsed from filename step_XXXXXX.pt
    path: str  # absolute path
    size_bytes: int
    modified_at: str  # ISO 8601


@dataclass(frozen=True)
class EvalReportEntry:
    robot: str
    policy: str
    path: str
    size_bytes: int
    modified_at: str
    has_video: bool  # True if viz/episode_*.mp4 exists in same dir
    summary: dict[str, Any]  # parsed JSON top-level keys


@dataclass(frozen=True)
class DatasetEntry:
    name: str  # last component of root dir
    path: str
    size_bytes: int  # sum of file sizes (capped at _FILE_CAP files)
    modified_at: str


def _resolve_lerobot_repo(lerobot_repo: Path | None) -> Path:
    if lerobot_repo is not None:
        return lerobot_repo
    return get_settings().lerobot_repo


def _iso(p: Path) -> str:
    mtime = p.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=UTC).isoformat()


def _dir_size(root: Path) -> int:
    """Sum sizes of files under *root*, capped at _FILE_CAP entries."""
    total = 0
    count = 0
    for f in root.rglob("*"):
        if count >= _FILE_CAP:
            break
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
            count += 1
    return total


def list_checkpoints(*, lerobot_repo: Path | None = None) -> list[CheckpointEntry]:
    """Walk ``{lerobot_repo}/checkpoints/{robot}/{policy}/step_*.pt``.

    Returns an empty list if the directory is missing.
    Entries are sorted by (robot, policy, step).
    """
    repo = _resolve_lerobot_repo(lerobot_repo)
    checkpoints_dir = repo / "checkpoints"

    if not repo.exists():
        logger.warning("lerobot_repo does not exist: {}", repo)
        return []

    if not checkpoints_dir.exists():
        logger.warning("Checkpoints directory does not exist: {}", checkpoints_dir)
        return []

    entries: list[CheckpointEntry] = []
    for pt_file in checkpoints_dir.glob("*/*/*"):
        if not pt_file.name.startswith("step_") or not pt_file.suffix == ".pt":
            continue
        parts = pt_file.relative_to(checkpoints_dir).parts
        if len(parts) != 3:  # robot / policy / filename
            continue
        robot, policy, filename = parts
        stem = Path(filename).stem  # "step_XXXXXX"
        try:
            step = int(stem.split("_", 1)[1])
        except (IndexError, ValueError):
            logger.warning("Cannot parse step from filename: {}", filename)
            continue
        try:
            stat = pt_file.stat()
        except OSError as exc:
            logger.warning("Cannot stat checkpoint {}: {}", pt_file, exc)
            continue
        entries.append(
            CheckpointEntry(
                robot=robot,
                policy=policy,
                step=step,
                path=str(pt_file),
                size_bytes=stat.st_size,
                modified_at=_iso(pt_file),
            )
        )

    entries.sort(key=lambda e: (e.robot, e.policy, e.step))
    return entries


def list_eval_reports(*, lerobot_repo: Path | None = None) -> list[EvalReportEntry]:
    """Walk ``{lerobot_repo}/eval_reports/{robot}/{policy}/eval_report.json``.

    Returns an empty list if the directory is missing.
    """
    repo = _resolve_lerobot_repo(lerobot_repo)
    eval_dir = repo / "eval_reports"

    if not repo.exists():
        logger.warning("lerobot_repo does not exist: {}", repo)
        return []

    if not eval_dir.exists():
        logger.warning("eval_reports directory does not exist: {}", eval_dir)
        return []

    entries: list[EvalReportEntry] = []
    for report_file in eval_dir.glob("*/*/eval_report.json"):
        parts = report_file.relative_to(eval_dir).parts
        if len(parts) != 3:  # robot / policy / eval_report.json
            continue
        robot, policy = parts[0], parts[1]
        try:
            stat = report_file.stat()
        except OSError as exc:
            logger.warning("Cannot stat eval report {}: {}", report_file, exc)
            continue
        try:
            raw = report_file.read_text(encoding="utf-8")
            parsed: Any = json.loads(raw)
            summary: dict[str, Any] = parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            logger.warning("Failed to parse eval report {}: {}", report_file, exc)
            summary = {}

        # Check for video files in viz/ sibling directory
        viz_dir = report_file.parent / "viz"
        has_video = viz_dir.is_dir() and any(viz_dir.glob("*.mp4"))

        entries.append(
            EvalReportEntry(
                robot=robot,
                policy=policy,
                path=str(report_file),
                size_bytes=stat.st_size,
                modified_at=_iso(report_file),
                has_video=has_video,
                summary=summary,
            )
        )

    entries.sort(key=lambda e: (e.robot, e.policy))
    return entries


def list_datasets(*, lerobot_repo: Path | None = None) -> list[DatasetEntry]:
    """Read ``configs/dataset/*.yaml``, extract ``root:`` paths, and return entries for each existing root.

    Dataset size is the sum of file sizes under the root directory (capped at _FILE_CAP files).
    """
    repo = _resolve_lerobot_repo(lerobot_repo)
    dataset_configs_dir = repo / "configs" / "dataset"

    if not repo.exists():
        logger.warning("lerobot_repo does not exist: {}", repo)
        return []

    if not dataset_configs_dir.exists():
        logger.warning("Dataset configs directory does not exist: {}", dataset_configs_dir)
        return []

    seen_roots: set[Path] = set()
    entries: list[DatasetEntry] = []

    for yaml_path in dataset_configs_dir.glob("*.yaml"):
        if yaml_path.name.startswith("_"):
            continue
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            data: Any = yaml.safe_load(raw)
        except Exception as exc:
            logger.warning("Failed to parse dataset config {}: {}", yaml_path, exc)
            continue

        if not isinstance(data, dict):
            continue

        root_val = data.get("root")
        if root_val is None:
            continue

        root_path = Path(str(root_val))
        if root_path in seen_roots:
            continue
        seen_roots.add(root_path)

        if not root_path.exists() or not root_path.is_dir():
            logger.warning("Dataset root does not exist or is not a dir: {}", root_path)
            continue

        try:
            # Use most-recently-modified file in root for modified_at; fallback to dir itself
            all_files = list(root_path.rglob("*"))[:_FILE_CAP]
            size = sum(f.stat().st_size for f in all_files if f.is_file())
            # Pick the most recent mtime among all entries
            mtimes = [f.stat().st_mtime for f in all_files if f.exists()]
            if mtimes:
                best_mtime = max(mtimes)
                modified_at = datetime.fromtimestamp(best_mtime, tz=UTC).isoformat()
            else:
                modified_at = _iso(root_path)
        except OSError as exc:
            logger.warning("Cannot stat dataset at {}: {}", root_path, exc)
            continue

        entries.append(
            DatasetEntry(
                name=root_path.name,
                path=str(root_path),
                size_bytes=size,
                modified_at=modified_at,
            )
        )

    entries.sort(key=lambda e: e.name)
    return entries
