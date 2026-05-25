# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""SSE streaming endpoints — logs and MLflow metrics."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sse_starlette.sse import EventSourceResponse, ServerSentEvent  # type: ignore[attr-defined]

from orchestrator.api.auth import require_token
from orchestrator.core.config import Settings, get_settings
from orchestrator.core.mlflow_bridge import MlflowWatcher
from orchestrator.db.engine import get_session
from orchestrator.db.models import Run, get_run

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/runs", tags=["streams"])

# ---------------------------------------------------------------------------
# Watcher registry (run_id → (watcher, refcount))
# ---------------------------------------------------------------------------

_WATCHERS: dict[str, tuple[MlflowWatcher, int]] = {}
_WATCHERS_LOCK = asyncio.Lock()

# ---------------------------------------------------------------------------
# Secret sanitization
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(HF_TOKEN=)\S+", re.IGNORECASE),
    re.compile(r"(API_TOKEN=)\S+", re.IGNORECASE),
    re.compile(r"(WANDB_API_KEY=)\S+", re.IGNORECASE),
]


def _sanitize_secret(line: str) -> str:
    """Replace secret values in *line* with ``***``."""
    for pattern in _SECRET_PATTERNS:
        line = pattern.sub(r"\g<1>***", line)
    return line


# ---------------------------------------------------------------------------
# Terminal statuses
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch_file(path: str) -> None:
    """Create the file if it does not exist yet."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.touch()


def _get_run_or_404(session: object, run_id: str) -> Run:
    """Return the Run or raise 404."""
    run = get_run(session, run_id)  # type: ignore[arg-type]
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return run


# ---------------------------------------------------------------------------
# Logs SSE endpoint
# ---------------------------------------------------------------------------


@router.get("/{run_id}/logs", dependencies=[Depends(require_token)])
async def stream_logs(
    run_id: str,
    request: Request,
    session: Annotated[object, Depends(get_session)],
) -> EventSourceResponse:
    """SSE stream of stdout+stderr lines for a run."""
    run = _get_run_or_404(session, run_id)

    # Ensure log files exist (worker may not have started yet)
    settings = get_settings()
    stdout_path = run.stdout_path or str(settings.logs_dir / f"{run_id}.stdout")
    stderr_path = run.stderr_path or str(settings.logs_dir / f"{run_id}.stderr")
    _touch_file(stdout_path)
    _touch_file(stderr_path)

    async def _generator() -> AsyncGenerator[ServerSentEvent, None]:
        stdout_offset = 0
        stderr_offset = 0
        drained_after_terminal = False

        while True:
            if await request.is_disconnected():
                logger.debug("stream_logs: client disconnected for run_id={}", run_id)
                return

            # Reload run to check status (use a new session read)
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            current_settings = get_settings()
            _eng = create_engine(
                current_settings.database_url,
                connect_args={"check_same_thread": False},
            )
            _sf = sessionmaker(bind=_eng, autoflush=False, autocommit=False)
            _s = _sf()
            try:
                current_run = get_run(_s, run_id)
                current_status = current_run.status if current_run else "failed"
                current_exit_code = current_run.exit_code if current_run else -1
            finally:
                _s.close()
                _eng.dispose()

            # Read new stdout lines
            new_events: list[ServerSentEvent] = []
            for stream_label, path, offset_ref in [
                ("stdout", stdout_path, stdout_offset),
                ("stderr", stderr_path, stderr_offset),
            ]:
                try:
                    with open(path, "rb") as fh:
                        fh.seek(offset_ref)
                        raw = fh.read()
                except OSError:
                    raw = b""

                if raw:
                    last_nl = raw.rfind(b"\n")
                    if last_nl != -1:
                        complete = raw[: last_nl + 1]
                        new_offset = offset_ref + last_nl + 1
                        if stream_label == "stdout":
                            stdout_offset = new_offset
                        else:
                            stderr_offset = new_offset
                        text = complete.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            clean_line = _sanitize_secret(line)
                            payload = json.dumps(
                                {
                                    "ts": time.time(),
                                    "stream": stream_label,
                                    "line": clean_line,
                                }
                            )
                            new_events.append(ServerSentEvent(data=payload))

            for evt in new_events:
                yield evt

            is_terminal = current_status in _TERMINAL_STATUSES

            if is_terminal and not new_events:
                if drained_after_terminal:
                    # Send end event and stop
                    end_payload = json.dumps(
                        {"status": current_status, "exit_code": current_exit_code}
                    )
                    yield ServerSentEvent(data=end_payload, event="end")
                    return
                else:
                    drained_after_terminal = True

            if not is_terminal:
                drained_after_terminal = False

            await asyncio.sleep(0.25)

    return EventSourceResponse(_generator())


# ---------------------------------------------------------------------------
# Metrics SSE endpoint
# ---------------------------------------------------------------------------


@router.get("/{run_id}/metrics", dependencies=[Depends(require_token)])
async def stream_metrics(
    run_id: str,
    request: Request,
    session: Annotated[object, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EventSourceResponse:
    """SSE stream of MLflow metrics for a run."""
    run = _get_run_or_404(session, run_id)

    async def _generator() -> AsyncGenerator[ServerSentEvent, None]:
        import redis.asyncio as aioredis

        # ------------------------------------------------------------------
        # 1. Wait for mlflow_run_id to be available (max 60s)
        # ------------------------------------------------------------------
        mlflow_run_id: str | None = run.mlflow_run_id
        if mlflow_run_id is None:
            deadline = time.monotonic() + 60.0
            while mlflow_run_id is None and time.monotonic() < deadline:
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.5)

                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                _eng = create_engine(
                    settings.database_url,
                    connect_args={"check_same_thread": False},
                )
                _sf = sessionmaker(bind=_eng, autoflush=False, autocommit=False)
                _s = _sf()
                try:
                    _run = get_run(_s, run_id)
                    mlflow_run_id = _run.mlflow_run_id if _run else None
                finally:
                    _s.close()
                    _eng.dispose()

            if mlflow_run_id is None:
                yield ServerSentEvent(
                    data=json.dumps({"error": "mlflow_run_id not available after 60s"}),
                    event="error",
                )
                return

        mlflow_tracking_uri: str = run.mlflow_tracking_uri or settings.mlflow_tracking_uri

        # ------------------------------------------------------------------
        # 2. Register / increment refcount for the watcher
        # ------------------------------------------------------------------
        async with _WATCHERS_LOCK:
            if run_id in _WATCHERS:
                watcher, refcount = _WATCHERS[run_id]
                _WATCHERS[run_id] = (watcher, refcount + 1)
            else:
                watcher = MlflowWatcher(
                    run_id=run_id,
                    mlflow_run_id=mlflow_run_id,
                    mlflow_tracking_uri=mlflow_tracking_uri,
                    redis_url=settings.redis_url,
                )
                watcher.start()
                _WATCHERS[run_id] = (watcher, 1)

        # ------------------------------------------------------------------
        # 3. Subscribe to Redis and yield events
        # ------------------------------------------------------------------
        channel = f"mlflow:{run_id}"
        redis_client: aioredis.Redis = aioredis.Redis.from_url(
            settings.redis_url, decode_responses=True
        )
        pubsub = redis_client.pubsub()

        try:
            await pubsub.subscribe(channel)
            logger.debug("stream_metrics: subscribed to channel={} run_id={}", channel, run_id)

            last_message_time = time.monotonic()

            while True:
                if await request.is_disconnected():
                    logger.debug("stream_metrics: client disconnected for run_id={}", run_id)
                    return

                # Check if run is terminal
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                _eng = create_engine(
                    settings.database_url,
                    connect_args={"check_same_thread": False},
                )
                _sf = sessionmaker(bind=_eng, autoflush=False, autocommit=False)
                _s = _sf()
                try:
                    _run = get_run(_s, run_id)
                    current_status = _run.status if _run else "failed"
                finally:
                    _s.close()
                    _eng.dispose()

                is_terminal = current_status in _TERMINAL_STATUSES

                # Drain any pending messages (non-blocking)
                got_message = False
                try:
                    msg = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True), timeout=0.1
                    )
                except TimeoutError:
                    msg = None

                if msg is not None and msg.get("type") == "message":
                    data = msg.get("data", "")
                    yield ServerSentEvent(data=str(data))
                    last_message_time = time.monotonic()
                    got_message = True

                # Stop if terminal and no events for 5s grace period
                if is_terminal and not got_message:
                    idle_time = time.monotonic() - last_message_time
                    if idle_time >= 5.0:
                        logger.debug("stream_metrics: terminal+idle for run_id={}, closing", run_id)
                        return

                if not got_message:
                    await asyncio.sleep(0.1)

        finally:
            # ------------------------------------------------------------------
            # Cleanup: unsubscribe, decrement refcount, stop if last subscriber
            # ------------------------------------------------------------------
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()  # type: ignore[no-untyped-call]
                await redis_client.aclose()
            except Exception as exc:
                logger.warning("stream_metrics: cleanup error for run_id={}: {}", run_id, exc)

            async with _WATCHERS_LOCK:
                if run_id in _WATCHERS:
                    w, refcount = _WATCHERS[run_id]
                    if refcount <= 1:
                        w.stop()
                        del _WATCHERS[run_id]
                        logger.debug("stream_metrics: watcher stopped for run_id={}", run_id)
                    else:
                        _WATCHERS[run_id] = (w, refcount - 1)

    return EventSourceResponse(_generator())
