# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Read/write helpers for ``robot_specs/*.yaml`` (data-driven robot registry).

This is the only part of the orchestrator allowed to write into a sibling
repo's working tree — ``robot_specs/`` is a scoped, RW-mounted data directory
(see ``orchestrator/docs/adr/ADR-004-robots-endpoint-rw-mount.md``), not source
code. Writes are pure YAML, validated by the API schema layer before reaching
this module.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from orchestrator.core.config import get_settings


@dataclass(frozen=True)
class RobotSpecEntry:
    """One ``robot_specs/{id}.yaml`` entry."""

    id: str
    name: str
    parent_id: str | None
    version: int
    created_at: str
    description: str
    spec: dict[str, Any]
    task: dict[str, Any]
    adapter: dict[str, Any] | None
    dataset: dict[str, Any]


@dataclass(frozen=True)
class LineageNode:
    """A node in the parent/child lineage tree, keyed by ``id``."""

    id: str
    name: str
    parent_id: str | None
    description: str
    version: int
    created_at: str
    children: tuple[LineageNode, ...]


def _resolve_robot_specs_dir(robot_specs_dir: Path | None) -> Path:
    if robot_specs_dir is not None:
        return robot_specs_dir
    return get_settings().robot_specs_dir


def _entry_from_dict(data: dict[str, Any]) -> RobotSpecEntry:
    adapter = data.get("adapter")
    return RobotSpecEntry(
        id=data["id"],
        name=data["name"],
        parent_id=data.get("parent_id"),
        version=data.get("version", 1),
        created_at=data.get("created_at", ""),
        description=data.get("description", ""),
        spec=dict(data["spec"]),
        task=dict(data.get("task", {})),
        adapter=dict(adapter) if adapter else None,
        dataset=dict(data.get("dataset", {})),
    )


def _entry_to_dict(entry: RobotSpecEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        "parent_id": entry.parent_id,
        "version": entry.version,
        "created_at": entry.created_at,
        "description": entry.description,
        "spec": entry.spec,
        "task": entry.task,
        "adapter": entry.adapter,
        "dataset": entry.dataset,
    }


def list_robot_specs(*, robot_specs_dir: Path | None = None) -> list[RobotSpecEntry]:
    """Parse every ``*.yaml`` file in ``robot_specs_dir``.

    Returns an empty list if the directory does not exist. Files starting
    with ``_``, files that fail to parse, and entries missing required
    fields are skipped with a warning (consistent with
    ``core.hydra_introspect``'s read-only introspection).
    """
    specs_dir = _resolve_robot_specs_dir(robot_specs_dir)
    if not specs_dir.is_dir():
        return []

    entries: list[RobotSpecEntry] = []
    for path in sorted(specs_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data: Any = yaml.safe_load(raw)
        except Exception as exc:
            logger.warning("Failed to parse robot spec {}: {}", path, exc)
            continue
        if not isinstance(data, dict):
            logger.warning("Robot spec {} does not contain a YAML mapping — skipping", path)
            continue
        try:
            entries.append(_entry_from_dict(data))
        except (KeyError, TypeError) as exc:
            logger.warning("Robot spec {} is missing required field {} — skipping", path, exc)
            continue

    entries.sort(key=lambda e: e.id)
    return entries


def get_robot_spec(spec_id: str, *, robot_specs_dir: Path | None = None) -> RobotSpecEntry | None:
    """Return the spec with ``id == spec_id``, or ``None`` if not found."""
    for entry in list_robot_specs(robot_specs_dir=robot_specs_dir):
        if entry.id == spec_id:
            return entry
    return None


def write_robot_spec(entry: RobotSpecEntry, *, robot_specs_dir: Path | None = None) -> Path:
    """Atomically write *entry* to ``{robot_specs_dir}/{entry.id}.yaml``.

    Refuses to overwrite an existing spec — every edit must produce a new
    ``id`` (the branch/lineage model), so an existing file means a duplicate
    or colliding ``id``.

    Raises:
        FileExistsError: If a spec with this ``id`` already exists.
    """
    specs_dir = _resolve_robot_specs_dir(robot_specs_dir)
    specs_dir.mkdir(parents=True, exist_ok=True)

    target = specs_dir / f"{entry.id}.yaml"
    if target.exists():
        raise FileExistsError(f"Robot spec '{entry.id}' already exists at {target}")

    payload = _entry_to_dict(entry)
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(payload, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    tmp.replace(target)
    logger.info("Wrote robot spec '{}' to {}", entry.id, target)
    return target


def build_lineage_tree(entries: list[RobotSpecEntry]) -> list[LineageNode]:
    """Build parent/child trees keyed by ``id``/``parent_id``.

    Entries whose ``parent_id`` is ``None`` or does not match any other
    entry's ``id`` are treated as roots. Returns one tree per root, sorted
    by ``id``.
    """
    by_id = {e.id: e for e in entries}
    children_of: dict[str, list[RobotSpecEntry]] = defaultdict(list)
    roots: list[RobotSpecEntry] = []

    for entry in entries:
        if entry.parent_id is not None and entry.parent_id in by_id:
            children_of[entry.parent_id].append(entry)
        else:
            roots.append(entry)

    def _build(entry: RobotSpecEntry, visited: frozenset[str]) -> LineageNode:
        visited = visited | {entry.id}
        children = sorted(
            (
                _build(child, visited)
                for child in children_of.get(entry.id, [])
                if child.id not in visited
            ),
            key=lambda n: n.id,
        )
        return LineageNode(
            id=entry.id,
            name=entry.name,
            parent_id=entry.parent_id,
            description=entry.description,
            version=entry.version,
            created_at=entry.created_at,
            children=tuple(children),
        )

    return sorted((_build(root, frozenset()) for root in roots), key=lambda n: n.id)
