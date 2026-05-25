# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for orchestrator.core.mlflow_bridge."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from orchestrator.core.mlflow_bridge import (
    MlflowWatcher,
    parse_metric_line,
    resolve_metrics_dir,
)

# ---------------------------------------------------------------------------
# parse_metric_line
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_metric_line_valid() -> None:
    result = parse_metric_line("1716636000000 0.234 100")
    assert result == (1716636000000, 0.234, 100)


@pytest.mark.unit
def test_parse_metric_line_valid_scientific() -> None:
    result = parse_metric_line("1716636000000 1.5e-3 0")
    assert result == (1716636000000, 1.5e-3, 0)


@pytest.mark.unit
def test_parse_metric_line_invalid_float() -> None:
    result = parse_metric_line("1716636000000 notanumber 100")
    assert result is None


@pytest.mark.unit
def test_parse_metric_line_empty() -> None:
    result = parse_metric_line("")
    assert result is None


@pytest.mark.unit
def test_parse_metric_line_too_few_fields() -> None:
    result = parse_metric_line("1716636000000 0.234")
    assert result is None


@pytest.mark.unit
def test_parse_metric_line_too_many_fields() -> None:
    result = parse_metric_line("1716636000000 0.234 100 extra")
    assert result is None


@pytest.mark.unit
def test_parse_metric_line_whitespace_only() -> None:
    result = parse_metric_line("   ")
    assert result is None


# ---------------------------------------------------------------------------
# resolve_metrics_dir
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_metrics_dir_found(tmp_path: Path) -> None:
    mlflow_run_id = "abcdef0123456789abcdef0123456789"
    metrics_dir = tmp_path / "0" / mlflow_run_id / "metrics"
    metrics_dir.mkdir(parents=True)

    result = resolve_metrics_dir(str(tmp_path), mlflow_run_id)
    assert result == metrics_dir


@pytest.mark.unit
def test_resolve_metrics_dir_found_with_file_prefix(tmp_path: Path) -> None:
    mlflow_run_id = "abcdef0123456789abcdef0123456789"
    metrics_dir = tmp_path / "0" / mlflow_run_id / "metrics"
    metrics_dir.mkdir(parents=True)

    result = resolve_metrics_dir(f"file://{tmp_path}", mlflow_run_id)
    assert result == metrics_dir


@pytest.mark.unit
def test_resolve_metrics_dir_not_found(tmp_path: Path) -> None:
    result = resolve_metrics_dir(str(tmp_path), "nonexistent_run_id")
    assert result is None


@pytest.mark.unit
def test_resolve_metrics_dir_tracking_root_missing() -> None:
    result = resolve_metrics_dir("/nonexistent/path", "somerunid")
    assert result is None


@pytest.mark.unit
def test_resolve_metrics_dir_multiple_experiments(tmp_path: Path) -> None:
    mlflow_run_id = "aaaa0000bbbb1111cccc2222dddd3333"
    # Experiment 0 has a different run
    (tmp_path / "0" / "other_run" / "metrics").mkdir(parents=True)
    # Experiment 1 has our run
    metrics_dir = tmp_path / "1" / mlflow_run_id / "metrics"
    metrics_dir.mkdir(parents=True)

    result = resolve_metrics_dir(str(tmp_path), mlflow_run_id)
    assert result == metrics_dir


# ---------------------------------------------------------------------------
# MlflowWatcher start/stop with fakeredis
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mlflow_watcher_start_stop_no_metrics_dir(tmp_path: Path) -> None:
    """Watcher with no metrics dir starts without error (waits in background)."""
    fake_redis = fakeredis.FakeRedis()

    with patch("orchestrator.core.mlflow_bridge.redis_mod") as mock_redis_mod:
        mock_redis_mod.Redis.from_url.return_value = fake_redis

        watcher = MlflowWatcher(
            run_id="run001",
            mlflow_run_id="aaaa0000bbbb1111cccc2222dddd3333",
            mlflow_tracking_uri=str(tmp_path),
            redis_url="redis://localhost:6379/0",
        )
        watcher.start()
        assert watcher._started is True
        # start is idempotent
        watcher.start()
        assert watcher._started is True
        watcher.stop()


@pytest.mark.unit
def test_mlflow_watcher_publishes_existing_metrics(tmp_path: Path) -> None:
    """Watcher reads existing metric file and publishes to Redis on start."""
    mlflow_run_id = "aaaa0000bbbb1111cccc2222dddd3333"
    run_id = "orchestrator_run_001"

    metrics_dir = tmp_path / "0" / mlflow_run_id / "metrics"
    metrics_dir.mkdir(parents=True)
    loss_file = metrics_dir / "loss"
    loss_file.write_text("1716636000000 0.5 0\n1716636001000 0.4 1\n", encoding="utf-8")

    mock_redis_client = MagicMock()

    with patch("orchestrator.core.mlflow_bridge.redis_mod") as mock_redis_mod:
        mock_redis_mod.Redis.from_url.return_value = mock_redis_client

        watcher = MlflowWatcher(
            run_id=run_id,
            mlflow_run_id=mlflow_run_id,
            mlflow_tracking_uri=str(tmp_path),
            redis_url="redis://localhost:6379/0",
        )
        watcher.start()
        # Give observer time to start and seed files
        time.sleep(0.1)
        watcher.stop()

    publish_calls = mock_redis_client.publish.call_args_list
    assert len(publish_calls) == 2
    channel = f"mlflow:{run_id}"
    assert all(call.args[0] == channel for call in publish_calls)


@pytest.mark.unit
def test_mlflow_watcher_stop_is_safe_when_not_started() -> None:
    """stop() before start() must not raise."""
    watcher = MlflowWatcher(
        run_id="r1",
        mlflow_run_id="x" * 32,
        mlflow_tracking_uri="file:///nonexistent",
        redis_url="redis://localhost:6379/0",
    )
    watcher.stop()  # should not raise
