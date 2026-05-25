# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for MLflow metrics watcher + Redis pub/sub."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.core.mlflow_bridge import MlflowWatcher, parse_metric_line

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metrics_dir(base: Path, mlflow_run_id: str, exp: str = "0") -> Path:
    """Create the mlruns/{exp}/{run_id}/metrics/ directory structure."""
    metrics_dir = base / exp / mlflow_run_id / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_watcher_publishes_metric_lines(tmp_path: Path) -> None:
    """Writing metric lines to the metrics file triggers Redis publish."""
    mlflow_run_id = "cafebabe0000111122223333deadbeef"
    run_id = "orch_run_xyz"

    metrics_dir = _make_metrics_dir(tmp_path, mlflow_run_id)
    loss_file = metrics_dir / "loss"
    loss_file.write_text("1716636000000 0.5 0\n", encoding="utf-8")

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
        time.sleep(0.2)  # Let observer seed existing file

        # Now write a new metric line
        with open(loss_file, "a", encoding="utf-8") as f:
            f.write("1716636001000 0.4 1\n")

        time.sleep(0.5)  # Let watchdog event fire

        watcher.stop()

    publish_calls = mock_redis_client.publish.call_args_list
    assert len(publish_calls) >= 2, f"Expected ≥2 publishes, got {len(publish_calls)}"

    channels = {call.args[0] for call in publish_calls}
    assert channels == {f"mlflow:{run_id}"}

    data_msgs = [json.loads(call.args[1]) for call in publish_calls]
    steps = {m["step"] for m in data_msgs}
    assert 0 in steps
    assert 1 in steps

    for msg in data_msgs:
        assert "ts" in msg
        assert "step" in msg
        assert "metric" in msg
        assert msg["metric"] == "loss"
        assert "value" in msg


@pytest.mark.integration
def test_watcher_multiple_metrics(tmp_path: Path) -> None:
    """Multiple metric files each publish under their own metric name."""
    mlflow_run_id = "11112222333344445555666677778888"
    run_id = "orch_multi"

    metrics_dir = _make_metrics_dir(tmp_path, mlflow_run_id)
    (metrics_dir / "loss").write_text("1716636000000 0.5 0\n", encoding="utf-8")
    (metrics_dir / "accuracy").write_text("1716636000000 0.8 0\n", encoding="utf-8")

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
        time.sleep(0.2)
        watcher.stop()

    publish_calls = mock_redis_client.publish.call_args_list
    assert len(publish_calls) == 2
    metric_names = {json.loads(call.args[1])["metric"] for call in publish_calls}
    assert metric_names == {"loss", "accuracy"}


@pytest.mark.integration
def test_watcher_waits_for_metrics_dir(tmp_path: Path) -> None:
    """If metrics dir doesn't exist at start, watcher eventually finds it."""
    mlflow_run_id = "aaaa1111bbbb2222cccc3333dddd4444"
    run_id = "orch_wait"

    mock_redis_client = MagicMock()

    with patch("orchestrator.core.mlflow_bridge.redis_mod") as mock_redis_mod:
        mock_redis_mod.Redis.from_url.return_value = mock_redis_client

        watcher = MlflowWatcher(
            run_id=run_id,
            mlflow_run_id=mlflow_run_id,
            mlflow_tracking_uri=str(tmp_path),
            redis_url="redis://localhost:6379/0",
        )
        # Override poll interval to be very fast for test
        watcher._POLL_INTERVAL = 0.1  # type: ignore[assignment]

        watcher.start()
        assert watcher._started is True

        # Create the directory after start
        time.sleep(0.15)
        metrics_dir = _make_metrics_dir(tmp_path, mlflow_run_id)
        (metrics_dir / "train_loss").write_text("1716636000000 1.0 0\n", encoding="utf-8")

        time.sleep(0.5)  # Let watcher find and seed the directory
        watcher.stop()

    publish_calls = mock_redis_client.publish.call_args_list
    assert len(publish_calls) >= 1


@pytest.mark.integration
def test_parse_metric_line_roundtrip() -> None:
    """parse_metric_line correctly handles typical MLflow file-backend format."""
    line = "1716636000123 0.234567 42"
    result = parse_metric_line(line)
    assert result is not None
    ts_ms, value, step = result
    assert ts_ms == 1716636000123
    assert abs(value - 0.234567) < 1e-6
    assert step == 42
