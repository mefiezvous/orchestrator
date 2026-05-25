# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Read-only endpoints for browsing Hydra configs in the lerobot repo."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from orchestrator.api.schemas import HydraConfigResponse
from orchestrator.core.hydra_introspect import (
    HydraConfigEntry,
    list_collect_configs,
    list_dataset_configs,
    list_env_configs,
    list_eval_configs,
    list_policy_configs,
    list_profile_configs,
)

# Auth coordination: WP-3 will create orchestrator.api.auth.require_token.
# Import lazily to avoid breaking this module before WP-3 is integrated.
try:
    from orchestrator.api.auth import require_token
except ImportError:  # WP-3 not yet integrated

    def require_token() -> None:  # type: ignore[misc]
        return None


router = APIRouter(
    prefix="/api/v1/configs",
    tags=["configs"],
    dependencies=[Depends(require_token)],
)


def _to_response(entry: HydraConfigEntry) -> HydraConfigResponse:
    return HydraConfigResponse(
        name=entry.name,
        group=entry.group,
        path=entry.path,
        fields=entry.fields,
    )


@router.get("/envs", response_model=list[HydraConfigResponse])
def get_env_configs() -> list[HydraConfigResponse]:
    """List all environment configs (``configs/env/*.yaml``)."""
    return [_to_response(e) for e in list_env_configs()]


@router.get("/policies", response_model=list[HydraConfigResponse])
def get_policy_configs() -> list[HydraConfigResponse]:
    """List all policy configs (``configs/policy/*.yaml``)."""
    return [_to_response(e) for e in list_policy_configs()]


@router.get("/profiles", response_model=list[HydraConfigResponse])
def get_profile_configs() -> list[HydraConfigResponse]:
    """List all training profiles (``configs/training/*.yaml``)."""
    return [_to_response(e) for e in list_profile_configs()]


@router.get("/datasets", response_model=list[HydraConfigResponse])
def get_dataset_configs() -> list[HydraConfigResponse]:
    """List all dataset configs (``configs/dataset/*.yaml``)."""
    return [_to_response(e) for e in list_dataset_configs()]


@router.get("/collect", response_model=list[HydraConfigResponse])
def get_collect_configs() -> list[HydraConfigResponse]:
    """List all collect configs (``configs/collect/*.yaml``)."""
    return [_to_response(e) for e in list_collect_configs()]


@router.get("/eval", response_model=list[HydraConfigResponse])
def get_eval_configs() -> list[HydraConfigResponse]:
    """List all eval configs (``configs/eval/*.yaml``)."""
    return [_to_response(e) for e in list_eval_configs()]
