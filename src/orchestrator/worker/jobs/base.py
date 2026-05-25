# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Core subprocess runner shared by collect, train, and eval job types."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from redis import Redis

from orchestrator.core.config import get_settings
from orchestrator.db.models import update_run

# ---------------------------------------------------------------------------
# MLflow run id detection patterns (permissive)
# ---------------------------------------------------------------------------

_MLFLOW_RUN_PATTERNS = [
    re.compile(r"MLflow run[_ ]id[:=]\s*([0-9a-f]{32})", re.IGNORECASE),
    re.compile(r"View run.*runs/([0-9a-f]{32})"),
    re.compile(r"mlflow run id ([0-9a-f]{32})", re.IGNORECASE),
]


def _scan_for_mlflow_run_id(line: str) -> str | None:
    """Return the first MLflow run id found in *line*, or None."""
    for pattern in _MLFLOW_RUN_PATTERNS:
        m = pattern.search(line)
        if m:
            return m.group(1)
    return None


def _make_env(settings: Any) -> dict[str, str]:
    """Build the subprocess environment: inherit os.environ + inject secrets."""
    env = dict(os.environ)
    env["MLFLOW_TRACKING_URI"] = settings.mlflow_tracking_uri
    if settings.hf_token:
        env["HF_TOKEN"] = settings.hf_token
    if settings.wandb_api_key:
        env["WANDB_API_KEY"] = settings.wandb_api_key
    return env


def _reader_thread(
    stream: Any,
    log_file: Any,
    label: str,
    mlflow_id_holder: list[str | None],
    lock: threading.Lock,
    captured_lines: list[str],
) -> None:
    """Read *stream* line-by-line, write to *log_file*, and scan for MLflow run id."""
    for raw in stream:
        line: str = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        log_file.write(line)
        log_file.flush()
        logger.debug("[{}] {}", label, line.rstrip())
        captured_lines.append(line)
        with lock:
            if mlflow_id_holder[0] is None:
                found = _scan_for_mlflow_run_id(line)
                if found:
                    mlflow_id_holder[0] = found


def run_subprocess_job(
    *,
    run_id: str,
    job_type: str,
    argv: list[str],
    workspace_cwd: str,
    body: dict[str, Any],
) -> int:
    """Run *argv* as a subprocess in *workspace_cwd*. Returns exit code.

    Updates the Run row in SQLite at every state transition.
    Pipes stdout/stderr to data/logs/{run_id}.{stdout|stderr}.
    Polls Redis for ``cancel:{run_id}`` flag; on set, SIGTERMs the subprocess.
    Detects mlflow_run_id from stdout/stderr and updates the row.
    """
    settings = get_settings()
    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = str(logs_dir / f"{run_id}.stdout")
    stderr_path = str(logs_dir / f"{run_id}.stderr")

    # Redis connection for cancel polling
    redis_conn: Redis | None = None
    try:
        redis_conn = Redis.from_url(settings.redis_url)
    except Exception as exc:
        logger.warning("Could not connect to Redis for cancel polling: {}", exc)

    # Create a fresh engine and session from current settings (not cached engine).
    # This ensures tests can redirect the DB URL via settings_override.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    settings_local = get_settings()
    _local_engine = create_engine(
        settings_local.database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    _local_session_factory = sessionmaker(bind=_local_engine, autoflush=False, autocommit=False)
    session = _local_session_factory()

    cancellation_requested = False
    exit_code = -1

    try:
        # ------------------------------------------------------------------ #
        # Update Run: status=running, paths, started_at
        # ------------------------------------------------------------------ #
        update_run(
            session,
            run_id,
            status="running",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            started_at=datetime.now(UTC),
        )
        session.commit()

        env = _make_env(settings)

        # ------------------------------------------------------------------ #
        # Launch subprocess
        # ------------------------------------------------------------------ #
        proc = subprocess.Popen(
            argv,
            cwd=workspace_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Update pid
        update_run(session, run_id, pid=proc.pid)
        session.commit()
        logger.info("started subprocess run_id={} pid={} argv={}", run_id, proc.pid, argv)

        # ------------------------------------------------------------------ #
        # Reader threads
        # ------------------------------------------------------------------ #
        mlflow_id_holder: list[str | None] = [None]
        mlflow_lock = threading.Lock()
        stderr_lines: list[str] = []
        stdout_lines: list[str] = []

        with (
            open(stdout_path, "w", buffering=1, encoding="utf-8", errors="replace") as stdout_f,
            open(stderr_path, "w", buffering=1, encoding="utf-8", errors="replace") as stderr_f,
        ):
            stdout_thread = threading.Thread(
                target=_reader_thread,
                args=(proc.stdout, stdout_f, "stdout", mlflow_id_holder, mlflow_lock, stdout_lines),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_reader_thread,
                args=(proc.stderr, stderr_f, "stderr", mlflow_id_holder, mlflow_lock, stderr_lines),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # ---------------------------------------------------------------- #
            # Poll for cancellation + MLflow run id
            # ---------------------------------------------------------------- #
            mlflow_id_committed = False
            kill_after: float | None = None

            while proc.poll() is None:
                time.sleep(1.0)

                # Check Redis cancel flag
                if redis_conn is not None and not cancellation_requested:
                    try:
                        flag = redis_conn.get(f"cancel:{run_id}")
                        if flag is not None:
                            cancellation_requested = True
                            logger.info(
                                "cancel flag detected for run_id={}, sending SIGTERM", run_id
                            )
                            proc.terminate()
                            kill_after = time.monotonic() + 10.0
                    except Exception as exc:
                        logger.warning("Redis poll error for run_id={}: {}", run_id, exc)

                # Grace period: kill if still running after 10s
                if (
                    cancellation_requested
                    and kill_after is not None
                    and time.monotonic() >= kill_after
                    and proc.poll() is None
                ):
                    logger.warning("SIGKILL for run_id={} (grace period expired)", run_id)
                    proc.kill()

                # Flush MLflow run id to DB once detected
                if not mlflow_id_committed:
                    with mlflow_lock:
                        mid = mlflow_id_holder[0]
                    if mid is not None:
                        update_run(session, run_id, mlflow_run_id=mid)
                        session.commit()
                        logger.info("MLflow run_id={} detected for run_id={}", mid, run_id)
                        mlflow_id_committed = True

            # Wait for reader threads to drain
            stdout_thread.join(timeout=5.0)
            stderr_thread.join(timeout=5.0)

        # Final MLflow flush after process done
        if not mlflow_id_committed:
            with mlflow_lock:
                mid = mlflow_id_holder[0]
            if mid is not None:
                update_run(session, run_id, mlflow_run_id=mid)
                session.commit()
                mlflow_id_committed = True

        # ------------------------------------------------------------------ #
        # Determine final status
        # ------------------------------------------------------------------ #
        exit_code = proc.returncode if proc.returncode is not None else -1

        if exit_code == 0:
            status = "succeeded"
            error_message = None
        elif cancellation_requested:
            status = "cancelled"
            error_message = None
        else:
            status = "failed"
            last_lines = stderr_lines[-5:] if stderr_lines else []
            error_message = "".join(last_lines).strip() or f"exit code {exit_code}"

        update_run(
            session,
            run_id,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
            finished_at=datetime.now(UTC),
        )
        session.commit()
        logger.info("run_id={} finished status={} exit_code={}", run_id, status, exit_code)
        return exit_code

    except Exception as exc:
        logger.exception("Unexpected error in run_subprocess_job for run_id={}: {}", run_id, exc)
        try:
            update_run(
                session,
                run_id,
                status="failed",
                error_message=str(exc),
                finished_at=datetime.now(UTC),
            )
            session.commit()
        except Exception as inner:
            logger.error("Could not update run row on exception for run_id={}: {}", run_id, inner)
        raise
    finally:
        session.close()
        try:
            _local_engine.dispose()
        except Exception:
            pass
        if redis_conn is not None:
            try:
                redis_conn.close()
            except Exception:
                pass
