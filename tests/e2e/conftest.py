# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Fixtures and helpers shared by all E2E tests.

Pre-conditions
--------------
* ``docker compose -f docker/docker-compose.yml up -d`` must be running.
* ``ORCHESTRATOR_E2E=1`` must be set (otherwise every e2e test is skipped).
* ``ORCHESTRATOR_API_TOKEN`` must be set (skip if absent).
* ``ORCHESTRATOR_API_URL`` is optional (defaults to ``http://127.0.0.1:8000``).
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest
from loguru import logger

# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

_E2E_ENABLED = os.environ.get("ORCHESTRATOR_E2E", "").strip() not in ("", "0", "false", "False")
_API_URL = os.environ.get("ORCHESTRATOR_API_URL", "http://127.0.0.1:8000")
_API_TOKEN = os.environ.get("ORCHESTRATOR_API_TOKEN", "")


def _require_e2e() -> None:
    """Skip the calling test if the e2e environment is not set up."""
    if not _E2E_ENABLED:
        pytest.skip(
            "E2E requires docker compose stack — set ORCHESTRATOR_E2E=1 and run after `make up`"
        )
    if not _API_TOKEN:
        pytest.skip("E2E requires ORCHESTRATOR_API_TOKEN to be set (see `make token`)")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_client() -> httpx.Client:
    """Session-scoped httpx.Client pointed at the running stack.

    Skips the entire session if the e2e pre-conditions are not met.
    """
    _require_e2e()
    client = httpx.Client(
        base_url=_API_URL,
        headers={"Authorization": f"Bearer {_API_TOKEN}"},
        timeout=10.0,
    )
    logger.info("E2E client created — base_url={}", _API_URL)
    return client


@pytest.fixture(scope="session")
def poll_until_terminal():  # type: ignore[return]
    """Session-scoped fixture that exposes ``wait_for_terminal`` as an injectable helper."""
    return wait_for_terminal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def wait_for_terminal(
    client: httpx.Client,
    run_id: str,
    timeout: float = 300.0,
    poll: float = 5.0,
) -> dict[str, Any]:
    """Poll ``GET /api/v1/runs/{run_id}`` until the run reaches a terminal state.

    Parameters
    ----------
    client:
        An authenticated httpx.Client.
    run_id:
        The run UUID to poll.
    timeout:
        Maximum seconds to wait before raising ``TimeoutError``.
    poll:
        Seconds between each poll.

    Returns
    -------
    dict
        The final run JSON dict.

    Raises
    ------
    TimeoutError
        If the run has not terminated within *timeout* seconds.
    """
    terminal_statuses = {"succeeded", "failed", "cancelled"}
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/v1/runs/{run_id}")
        response.raise_for_status()
        run: dict[str, Any] = response.json()
        status: str = run.get("status", "unknown")
        logger.debug("run {} — status={}", run_id, status)
        if status in terminal_statuses:
            return run
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Run {run_id!r} did not reach a terminal state within {timeout}s "
                f"(last status: {status!r})"
            )
        time.sleep(min(poll, remaining))
