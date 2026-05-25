# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""RQ job: evaluate a checkpoint via lerobot-playground-portfolio/eval.py."""

from __future__ import annotations

from typing import Any

from loguru import logger

from orchestrator.worker.jobs.base import run_subprocess_job


def run(*, run_id: str, body: dict[str, Any], workspace_cwd: str) -> int:
    """Entry point invoked by the RQ worker for eval jobs."""
    argv = _build_argv(body)
    logger.info("eval job run_id={} argv={}", run_id, argv)
    return run_subprocess_job(
        run_id=run_id,
        job_type="eval",
        argv=argv,
        workspace_cwd=workspace_cwd,
        body=body,
    )


def _build_argv(body: dict[str, Any]) -> list[str]:
    """Generate the Hydra CLI argv for eval.py. Matches WP-3 contract."""
    argv: list[str] = [
        "uv",
        "run",
        "python",
        "eval.py",
        f"+eval.checkpoint_path={body['checkpoint_path']}",
        f"+eval.n_episodes={body['n_episodes']}",
        f"+eval.visualize={str(body.get('visualize', False)).lower()}",
    ]
    if body.get("policy"):
        argv.append(f"policy={body['policy']}")
    argv.extend(body.get("hydra_overrides", []))
    return argv
