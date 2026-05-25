# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""RQ job: train a policy via lerobot-playground-portfolio/train.py."""

from __future__ import annotations

from typing import Any

from loguru import logger

from orchestrator.worker.jobs.base import run_subprocess_job


def run(*, run_id: str, body: dict[str, Any], workspace_cwd: str) -> int:
    """Entry point invoked by the RQ worker for train jobs."""
    argv = _build_argv(body)
    logger.info("train job run_id={} argv={}", run_id, argv)
    return run_subprocess_job(
        run_id=run_id,
        job_type="train",
        argv=argv,
        workspace_cwd=workspace_cwd,
        body=body,
    )


def _build_argv(body: dict[str, Any]) -> list[str]:
    """Generate the Hydra CLI argv for train.py. Matches WP-3 contract."""
    argv: list[str] = ["uv", "run", "python", "train.py"]
    profile = body.get("profile")
    if profile:
        argv.extend(["--config-name", f"training/{profile}"])
    argv.append(f"policy={body['policy']}")
    argv.append(f"training.total_steps={body['total_steps']}")
    if body.get("env"):
        argv.append(f"env={body['env']}")
    if body.get("hf_repo_id"):
        argv.append(f"hf_repo_id={body['hf_repo_id']}")
    argv.extend(body.get("hydra_overrides", []))
    return argv
