# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""RQ job: collect episodes via lerobot-playground-portfolio/collect.py."""

from __future__ import annotations

from typing import Any

from loguru import logger

from orchestrator.worker.jobs.base import run_subprocess_job


def run(*, run_id: str, body: dict[str, Any], workspace_cwd: str) -> int:
    """Entry point invoked by the RQ worker for collect jobs."""
    argv = _build_argv(body)
    logger.info("collect job run_id={} argv={}", run_id, argv)
    return run_subprocess_job(
        run_id=run_id,
        job_type="collect",
        argv=argv,
        workspace_cwd=workspace_cwd,
        body=body,
    )


def _build_argv(body: dict[str, Any]) -> list[str]:
    """Generate the Hydra CLI argv for collect.py. Matches WP-3 contract."""
    argv: list[str] = [
        "uv",
        "run",
        "python",
        "collect.py",
        f"episodes={body['episodes']}",
    ]
    argv.append(f"policy_type={body.get('policy_type', 'scripted')}")
    argv.append(f"push_to_hub={str(body.get('push_to_hub', False)).lower()}")
    if body.get("env"):
        argv.append(f"env={body['env']}")
    if body.get("seed") is not None:
        argv.append(f"seed={body['seed']}")
    argv.extend(body.get("hydra_overrides", []))
    return argv
