# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Read-only endpoints for browsing training artifacts in the lerobot repo."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from orchestrator.api.schemas import CheckpointResponse, DatasetResponse, EvalReportResponse
from orchestrator.core.artifacts import (
    CheckpointEntry,
    DatasetEntry,
    EvalReportEntry,
    list_checkpoints,
    list_datasets,
    list_eval_reports,
)

# Auth coordination: WP-3 will create orchestrator.api.auth.require_token.
try:
    from orchestrator.api.auth import require_token
except ImportError:  # WP-3 not yet integrated

    def require_token() -> None:  # type: ignore[misc]
        return None


router = APIRouter(
    prefix="/api/v1/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(require_token)],
)


def _ckpt_to_response(entry: CheckpointEntry) -> CheckpointResponse:
    return CheckpointResponse(
        robot=entry.robot,
        policy=entry.policy,
        step=entry.step,
        path=entry.path,
        size_bytes=entry.size_bytes,
        modified_at=entry.modified_at,
    )


def _eval_to_response(entry: EvalReportEntry) -> EvalReportResponse:
    return EvalReportResponse(
        robot=entry.robot,
        policy=entry.policy,
        path=entry.path,
        size_bytes=entry.size_bytes,
        modified_at=entry.modified_at,
        has_video=entry.has_video,
        summary=entry.summary,
    )


def _ds_to_response(entry: DatasetEntry) -> DatasetResponse:
    return DatasetResponse(
        name=entry.name,
        path=entry.path,
        size_bytes=entry.size_bytes,
        modified_at=entry.modified_at,
    )


@router.get("/checkpoints", response_model=list[CheckpointResponse])
def get_checkpoints() -> list[CheckpointResponse]:
    """List all checkpoint files (``checkpoints/{robot}/{policy}/step_*.pt``)."""
    return [_ckpt_to_response(e) for e in list_checkpoints()]


@router.get("/eval-reports", response_model=list[EvalReportResponse])
def get_eval_reports() -> list[EvalReportResponse]:
    """List all eval reports (``eval_reports/{robot}/{policy}/eval_report.json``)."""
    return [_eval_to_response(e) for e in list_eval_reports()]


@router.get("/datasets", response_model=list[DatasetResponse])
def get_datasets() -> list[DatasetResponse]:
    """List all datasets discovered via ``configs/dataset/*.yaml`` root fields."""
    return [_ds_to_response(e) for e in list_datasets()]
