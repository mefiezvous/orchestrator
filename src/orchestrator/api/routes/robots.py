# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Endpoints to declare, branch, and browse robot specs (``robot_specs/*.yaml``)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from orchestrator.api.auth import require_token
from orchestrator.api.schemas import (
    LineageNodeResponse,
    RobotSpecBranchRequest,
    RobotSpecCreateRequest,
    RobotSpecResponse,
)
from orchestrator.core.robot_specs import (
    RobotSpecEntry,
    build_lineage_tree,
    get_robot_spec,
    list_robot_specs,
    write_robot_spec,
)

router = APIRouter(
    prefix="/api/v1/robots",
    tags=["robots"],
    dependencies=[Depends(require_token)],
)


def _to_entry(request: RobotSpecCreateRequest, *, parent_id: str | None) -> RobotSpecEntry:
    # mode="json" turns tuple fields (e.g. RobotSpecFields.relational_features)
    # into plain lists, so yaml.safe_dump/safe_load round-trip correctly.
    return RobotSpecEntry(
        id=request.id,
        name=request.name,
        parent_id=parent_id,
        version=1,
        created_at=datetime.now(UTC).isoformat(),
        description=request.description,
        spec=request.spec.model_dump(mode="json"),
        task=request.task.model_dump(mode="json"),
        adapter=request.adapter.model_dump(mode="json") if request.adapter else None,
        dataset=request.dataset.model_dump(mode="json"),
    )


def _write_or_409(entry: RobotSpecEntry) -> None:
    try:
        write_robot_spec(entry)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/", response_model=list[RobotSpecResponse])
def get_robots() -> list[RobotSpecResponse]:
    """List all robot specs."""
    return [RobotSpecResponse.from_entry(e) for e in list_robot_specs()]


@router.get("/lineage", response_model=list[LineageNodeResponse])
def get_robots_lineage() -> list[LineageNodeResponse]:
    """Return the parent/child lineage tree(s), grouped by root spec."""
    entries = list_robot_specs()
    return [LineageNodeResponse.from_node(n) for n in build_lineage_tree(entries)]


@router.get("/{spec_id}", response_model=RobotSpecResponse)
def get_robot(spec_id: str) -> RobotSpecResponse:
    """Return a single robot spec by id."""
    entry = get_robot_spec(spec_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Robot spec '{spec_id}' not found")
    return RobotSpecResponse.from_entry(entry)


@router.post("/", response_model=RobotSpecResponse, status_code=201)
def create_robot(request: RobotSpecCreateRequest) -> RobotSpecResponse:
    """Declare a new root robot spec (``parent_id=None``)."""
    if get_robot_spec(request.id) is not None:
        raise HTTPException(status_code=409, detail=f"Robot spec '{request.id}' already exists")
    entry = _to_entry(request, parent_id=None)
    _write_or_409(entry)
    return RobotSpecResponse.from_entry(entry)


@router.post("/{parent_id}/branch", response_model=RobotSpecResponse, status_code=201)
def branch_robot(parent_id: str, request: RobotSpecBranchRequest) -> RobotSpecResponse:
    """Create a new robot spec derived from ``parent_id``."""
    if get_robot_spec(parent_id) is None:
        raise HTTPException(status_code=404, detail=f"Robot spec '{parent_id}' not found")
    if get_robot_spec(request.id) is not None:
        raise HTTPException(status_code=409, detail=f"Robot spec '{request.id}' already exists")
    entry = _to_entry(request, parent_id=parent_id)
    _write_or_409(entry)
    return RobotSpecResponse.from_entry(entry)
