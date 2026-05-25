# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""MLflow metrics watcher — tails mlruns metric files and publishes to Redis pub/sub."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import redis as redis_mod
from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_metric_line(line: str) -> tuple[int, float, int] | None:
    """Parse '<ts_ms> <value> <step>' → (ts_ms, value, step). None on invalid input."""
    parts = line.strip().split()
    if len(parts) != 3:
        return None
    try:
        ts_ms = int(parts[0])
        value = float(parts[1])
        step = int(parts[2])
        return ts_ms, value, step
    except (ValueError, TypeError):
        return None


def resolve_metrics_dir(mlflow_tracking_uri: str, mlflow_run_id: str) -> Path | None:
    """Locate ``mlruns/{exp}/{run_id}/metrics/`` from tracking URI + run id.

    Strips the ``file://`` prefix and searches all experiments under the tracking root.
    Returns None if not found.
    """
    root = mlflow_tracking_uri
    if root.startswith("file://"):
        root = root[len("file://") :]
    tracking_root = Path(root)
    if not tracking_root.is_dir():
        return None
    # Search all experiment directories
    for exp_dir in tracking_root.iterdir():
        if not exp_dir.is_dir():
            continue
        metrics_dir = exp_dir / mlflow_run_id / "metrics"
        if metrics_dir.is_dir():
            return metrics_dir
    return None


# ---------------------------------------------------------------------------
# Watchdog handler
# ---------------------------------------------------------------------------


class _MetricFileHandler(FileSystemEventHandler):
    """Watch a metrics/ directory and publish new metric lines to Redis."""

    def __init__(self, run_id: str, redis_client: Any) -> None:
        super().__init__()
        self._run_id = run_id
        self._redis = redis_client
        # Maps file path → last read byte offset
        self._offsets: dict[Path, int] = {}
        self._channel = f"mlflow:{run_id}"

    def _process_file(self, path: Path) -> None:
        """Read new bytes from *path* since last offset, parse and publish."""
        if not path.is_file():
            return
        metric_name = path.stem  # filename without extension
        offset = self._offsets.get(path, 0)
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                raw = fh.read()
        except OSError as exc:
            logger.warning("MlflowWatcher: could not read {}: {}", path, exc)
            return

        if not raw:
            return

        # Only process up to the last newline to avoid partial lines
        last_nl = raw.rfind(b"\n")
        if last_nl == -1:
            # No complete line yet — wait for next event
            return

        complete = raw[: last_nl + 1]
        self._offsets[path] = offset + last_nl + 1

        text = complete.decode("utf-8", errors="replace")
        for line in text.splitlines():
            parsed = parse_metric_line(line)
            if parsed is None:
                continue
            ts_ms, value, step = parsed
            event_data = json.dumps(
                {
                    "ts": ts_ms / 1000.0,
                    "step": step,
                    "metric": metric_name,
                    "value": value,
                }
            )
            try:
                self._redis.publish(self._channel, event_data)
            except Exception as exc:
                logger.warning("MlflowWatcher: Redis publish error: {}", exc)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._process_file(Path(str(event.src_path)))

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._process_file(Path(str(event.src_path)))


# ---------------------------------------------------------------------------
# MlflowWatcher
# ---------------------------------------------------------------------------


class MlflowWatcher:
    """Watches ``mlruns/{exp}/{run_id}/metrics/`` for new lines and publishes them.

    File format per metric file (one per metric name):
        <timestamp_ms> <value> <step>\\n
    Each line is append-only. We track the byte offset per file and read only new bytes.
    """

    _POLL_INTERVAL = 2.0  # seconds between retries while waiting for metrics dir
    _POLL_TIMEOUT = 300.0  # 5 minutes

    def __init__(
        self,
        run_id: str,
        mlflow_run_id: str,
        mlflow_tracking_uri: str,
        redis_url: str,
    ) -> None:
        self._run_id = run_id
        self._mlflow_run_id = mlflow_run_id
        self._mlflow_tracking_uri = mlflow_tracking_uri
        self._redis_url = redis_url

        self._started = False
        self._lock = threading.Lock()
        self._observer: Any = None
        self._handler: _MetricFileHandler | None = None
        self._wait_thread: threading.Thread | None = None

        # Lazily created Redis connection
        self._redis: Any = None

    def _get_redis(self) -> Any:
        if self._redis is None:
            self._redis = redis_mod.Redis.from_url(self._redis_url)
        return self._redis

    def start(self) -> None:
        """Start watching for metrics. Idempotent."""
        with self._lock:
            if self._started:
                return
            self._started = True

        metrics_dir = resolve_metrics_dir(self._mlflow_tracking_uri, self._mlflow_run_id)
        if metrics_dir is not None:
            self._launch_observer(metrics_dir)
        else:
            # Wait in background thread until metrics dir appears
            self._wait_thread = threading.Thread(
                target=self._wait_for_metrics_dir,
                daemon=True,
                name=f"mlflow-wait-{self._run_id}",
            )
            self._wait_thread.start()

    def _wait_for_metrics_dir(self) -> None:
        """Poll until the metrics dir exists or timeout, then start the observer."""
        deadline = time.monotonic() + self._POLL_TIMEOUT
        while time.monotonic() < deadline:
            metrics_dir = resolve_metrics_dir(self._mlflow_tracking_uri, self._mlflow_run_id)
            if metrics_dir is not None:
                self._launch_observer(metrics_dir)
                return
            time.sleep(self._POLL_INTERVAL)
        logger.warning(
            "MlflowWatcher: metrics dir not found after {}s for run_id={} mlflow_run_id={}",
            self._POLL_TIMEOUT,
            self._run_id,
            self._mlflow_run_id,
        )

    def _launch_observer(self, metrics_dir: Path) -> None:
        """Create and start a watchdog Observer on *metrics_dir*."""
        redis_client = self._get_redis()
        handler = _MetricFileHandler(run_id=self._run_id, redis_client=redis_client)
        self._handler = handler

        # Seed offsets for already-existing files (re-read them from the start
        # so clients connecting after the run started get the full history)
        for f in metrics_dir.iterdir():
            if f.is_file():
                handler._process_file(f)

        observer: Any = Observer()
        observer.schedule(handler, str(metrics_dir), recursive=False)
        observer.start()
        self._observer = observer
        logger.info(
            "MlflowWatcher started for run_id={} watching {}",
            self._run_id,
            metrics_dir,
        )

    def stop(self) -> None:
        """Gracefully stop the observer."""
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5.0)
            except Exception as exc:
                logger.warning("MlflowWatcher: error stopping observer: {}", exc)
            self._observer = None
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None
        logger.debug("MlflowWatcher stopped for run_id={}", self._run_id)
