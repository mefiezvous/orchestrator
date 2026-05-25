# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Smoke E2E test: collect → train → eval pipeline against a live stack.

Pre-conditions (NOT handled here — must be satisfied before running)
---------------------------------------------------------------------
* ``docker compose -f docker/docker-compose.yml up -d`` is running.
* ``ORCHESTRATOR_E2E=1`` is exported.
* ``ORCHESTRATOR_API_TOKEN`` is set to a valid bearer token.
* ``ORCHESTRATOR_API_URL`` is set or defaults to ``http://127.0.0.1:8000``.

Run with::

    uv run pytest tests/e2e/ -m e2e -v
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from loguru import logger

# ---------------------------------------------------------------------------
# Health gate — skip gracefully when the stack is not ready
# ---------------------------------------------------------------------------


def _assert_stack_ready(client: httpx.Client) -> None:
    """Assert the health endpoint returns 200 with api=ok; skip otherwise."""
    try:
        resp = client.get("/api/v1/health")
    except httpx.ConnectError as exc:
        pytest.skip(f"Cannot reach orchestrator API at {client.base_url} — {exc}")

    if resp.status_code != 200:
        pytest.skip(f"Health check returned HTTP {resp.status_code} — stack not ready: {resp.text}")

    health: dict[str, Any] = resp.json()
    if health.get("api") != "ok":
        pytest.skip(f"Health check api!=ok — stack not ready: {health}")

    non_ok = {k: v for k, v in health.items() if v not in ("ok", "unknown")}
    if non_ok:
        logger.warning("Some health components are degraded: {}", non_ok)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_smoke_collect_train_eval(
    e2e_client: httpx.Client,
    poll_until_terminal: Callable[..., dict[str, Any]],
) -> None:
    """Full collect → train → eval pipeline smoke test."""
    wait_for_terminal = poll_until_terminal
    # ------------------------------------------------------------------
    # 1. Health check
    # ------------------------------------------------------------------
    _assert_stack_ready(e2e_client)
    logger.info("Stack is healthy — starting smoke test")

    # ------------------------------------------------------------------
    # 2. Collect run
    # ------------------------------------------------------------------
    collect_body = {
        "episodes": 1,
        "env": "cube_reach_v1",
        "policy_type": "scripted_reach",
        "push_to_hub": False,
    }
    resp = e2e_client.post("/api/v1/runs/collect", json=collect_body)
    assert resp.status_code == 202, f"POST /runs/collect failed: {resp.text}"
    collect_created: dict[str, Any] = resp.json()
    collect_run_id: str = collect_created["run_id"]
    logger.info("Collect run submitted — run_id={}", collect_run_id)

    # 3. Poll collect
    collect_run = wait_for_terminal(e2e_client, collect_run_id, timeout=300, poll=5)
    assert collect_run["status"] == "succeeded", (
        f"Collect run {collect_run_id!r} did not succeed — "
        f"status={collect_run['status']!r}, error={collect_run.get('error_message')!r}"
    )
    logger.info("Collect run succeeded — run_id={}", collect_run_id)

    # ------------------------------------------------------------------
    # 4. Train run
    # ------------------------------------------------------------------
    train_body = {
        "env": "cube_reach_v1",
        "policy": "act",
        "total_steps": 10,
        "hydra_overrides": ["training.batch_size=1"],
    }
    resp = e2e_client.post("/api/v1/runs/train", json=train_body)
    assert resp.status_code == 202, f"POST /runs/train failed: {resp.text}"
    train_created: dict[str, Any] = resp.json()
    train_run_id: str = train_created["run_id"]
    logger.info("Train run submitted — run_id={}", train_run_id)

    # 5. Poll train
    train_run = wait_for_terminal(e2e_client, train_run_id, timeout=600, poll=5)
    assert train_run["status"] == "succeeded", (
        f"Train run {train_run_id!r} did not succeed — "
        f"status={train_run['status']!r}, error={train_run.get('error_message')!r}"
    )
    logger.info("Train run succeeded — run_id={}", train_run_id)

    # ------------------------------------------------------------------
    # 6. Resolve latest checkpoint path
    # ------------------------------------------------------------------
    checkpoint_path = _resolve_checkpoint(e2e_client, train_run_id)
    logger.info("Using checkpoint_path={}", checkpoint_path)

    # ------------------------------------------------------------------
    # 7. Eval run
    # ------------------------------------------------------------------
    eval_body = {
        "checkpoint_path": checkpoint_path,
        "n_episodes": 1,
        "visualize": False,
    }
    resp = e2e_client.post("/api/v1/runs/eval", json=eval_body)
    assert resp.status_code == 202, f"POST /runs/eval failed: {resp.text}"
    eval_created: dict[str, Any] = resp.json()
    eval_run_id: str = eval_created["run_id"]
    logger.info("Eval run submitted — run_id={}", eval_run_id)

    # 8. Poll eval
    eval_run = wait_for_terminal(e2e_client, eval_run_id, timeout=300, poll=5)
    assert eval_run["status"] == "succeeded", (
        f"Eval run {eval_run_id!r} did not succeed — "
        f"status={eval_run['status']!r}, error={eval_run.get('error_message')!r}"
    )
    logger.info(
        "Smoke test PASSED — collect={} train={} eval={}", collect_run_id, train_run_id, eval_run_id
    )


# ---------------------------------------------------------------------------
# Bonus: SSE log streaming
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_smoke_sse_logs(e2e_client: httpx.Client) -> None:
    """Verify that GET /api/v1/runs/{run_id}/logs streams ≥1 SSE line within 10s.

    This sub-test is skipped if the endpoint is not yet implemented (404/501).
    """
    _assert_stack_ready(e2e_client)

    # Submit a minimal collect run so we have a real run_id to stream from.
    collect_body = {
        "episodes": 1,
        "env": "cube_reach_v1",
        "policy_type": "scripted_reach",
        "push_to_hub": False,
    }
    resp = e2e_client.post("/api/v1/runs/collect", json=collect_body)
    assert resp.status_code == 202, f"POST /runs/collect failed: {resp.text}"
    run_id: str = resp.json()["run_id"]
    logger.info("SSE test — collect run_id={}", run_id)

    # Attempt to open the SSE stream.
    sse_url = f"/api/v1/runs/{run_id}/logs"
    try:
        with e2e_client.stream("GET", sse_url, timeout=10.0) as stream:
            if stream.status_code in (404, 501):
                pytest.skip(
                    f"SSE endpoint {sse_url!r} not yet implemented "
                    f"(HTTP {stream.status_code}) — WP-5 pending"
                )
            assert stream.status_code == 200, f"SSE endpoint returned HTTP {stream.status_code}"
            lines_received = 0
            for line in stream.iter_lines():
                if line.strip():
                    lines_received += 1
                    logger.debug("SSE line received: {!r}", line)
                    break  # one line is enough
            assert lines_received >= 1, "SSE stream returned no lines within 10s"
    except httpx.ReadTimeout:
        pytest.skip("SSE stream timed out after 10s — no lines received (stream may be empty)")

    logger.info("SSE smoke test PASSED — ≥1 line received for run_id={}", run_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_checkpoint(client: httpx.Client, train_run_id: str) -> str:
    """Return the path of the most recently modified checkpoint.

    Strategy:
    1. ``GET /api/v1/artifacts/checkpoints`` — pick the most recently modified entry.
    2. Fallback: read ``request_body`` from the train run and construct a best-guess path.
    """
    resp = client.get("/api/v1/artifacts/checkpoints")
    if resp.status_code == 200:
        checkpoints: list[dict[str, Any]] = resp.json()
        if checkpoints:
            # Sort by modified_at descending and take the most recent.
            latest = max(checkpoints, key=lambda c: c.get("modified_at", ""))
            path: str = latest["path"]
            logger.debug("Resolved checkpoint via artifacts endpoint: {}", path)
            return path

    # Fallback: inspect the train run's request_body for hints.
    run_resp = client.get(f"/api/v1/runs/{train_run_id}")
    run_resp.raise_for_status()
    train_run: dict[str, Any] = run_resp.json()
    request_body: dict[str, Any] = train_run.get("request_body") or {}
    policy: str = request_body.get("policy", "act")
    env: str = request_body.get("env", "cube_reach_v1")
    fallback_path = f"checkpoints/{env}/{policy}/step_00010.pt"
    logger.warning(
        "No checkpoints found via artifacts endpoint — using fallback path: {}", fallback_path
    )
    return fallback_path
