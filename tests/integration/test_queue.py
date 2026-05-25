# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for orchestrator.worker.queue using fakeredis."""

from __future__ import annotations

import fakeredis
import pytest

import orchestrator.worker.queue as queue_mod
from orchestrator.worker.queue import (
    _get_connection,
    _get_queue,
    cancel_job,
    enqueue_collect,
)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    """Replace the real Redis connection with a FakeRedis instance."""
    fake = fakeredis.FakeRedis()

    # Clear LRU caches so patched version is used
    _get_connection.cache_clear()
    _get_queue.cache_clear()

    monkeypatch.setattr(queue_mod, "_get_connection", lambda: fake)

    # Also patch _get_queue to use the fake connection
    from rq import Queue as RQQueue

    fake_queue = RQQueue("orchestrator", connection=fake, is_async=True)
    monkeypatch.setattr(queue_mod, "_get_queue", lambda: fake_queue)

    yield fake

    _get_connection.cache_clear()
    _get_queue.cache_clear()


@pytest.mark.integration
def test_enqueue_collect_returns_run_id_and_queues_job() -> None:
    """enqueue_collect returns run_id and puts exactly one job on the queue."""
    run_id = "test-run-001"
    body = {
        "episodes": 5,
        "policy_type": "scripted",
        "push_to_hub": False,
        "hydra_overrides": [],
    }

    returned_id = enqueue_collect(run_id, body, "/tmp")

    assert returned_id == run_id

    from orchestrator.worker.queue import _get_queue as get_q

    q = get_q()
    assert q.count == 1
    job = q.fetch_job(run_id)
    assert job is not None
    assert job.id == run_id


@pytest.mark.integration
def test_cancel_queued_job_returns_true_and_empties_queue() -> None:
    """cancel_job on a queued job returns True and removes it from the queue."""
    run_id = "test-run-cancel-001"
    body = {"episodes": 1, "hydra_overrides": []}

    enqueue_collect(run_id, body, "/tmp")

    from orchestrator.worker.queue import _get_queue as get_q

    assert get_q().count == 1

    result = cancel_job(run_id)

    assert result is True
    assert get_q().count == 0


@pytest.mark.integration
def test_cancel_nonexistent_job_returns_false() -> None:
    """cancel_job on a non-existent run_id returns False without raising."""
    result = cancel_job("does-not-exist-xyz")
    assert result is False
