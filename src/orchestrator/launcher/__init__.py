# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Launcher module — wraps docker compose up, polls the health endpoint, opens a browser.

Public API
----------
up()            Start the Docker Compose stack (api + worker + redis + mlflow).
wait_healthy()  Poll GET /api/v1/health until the API responds 200 or timeout.
open_browser()  Open the frontend SPA (or /api/docs) in the default browser.
down()          Stop and remove the Docker Compose stack.
"""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPOSE_FILE = Path(__file__).resolve().parents[4] / "docker" / "docker-compose.yml"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_HEALTH_URL = "http://127.0.0.1:8000/api/v1/health"
_FRONTEND_MARKER = _REPO_ROOT / "frontend" / "dist" / "index.html"

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def up() -> None:
    """Run ``docker compose up -d`` for the orchestrator stack.

    Raises
    ------
    SystemExit
        If Docker is not installed (``FileNotFoundError``) or Compose returns
        a non-zero exit code.
    """
    cmd = [
        "docker",
        "compose",
        "-f",
        str(_COMPOSE_FILE),
        "up",
        "-d",
    ]
    logger.info("Starting Docker Compose stack: {}", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.error(
            "Docker not found. Make sure Docker Desktop (or the Docker CLI) is installed"
            " and running, then try again."
        )
        sys.exit(1)

    if result.returncode != 0:
        logger.error(
            "docker compose up failed (exit code {}).\n"
            "--- stderr ---\n{}\n"
            "Tip: run `docker compose -f {} logs api` for more details.",
            result.returncode,
            result.stderr.strip(),
            _COMPOSE_FILE,
        )
        sys.exit(1)

    logger.info("Docker Compose stack started.")


def wait_healthy(timeout: int = 60) -> None:
    """Poll the health endpoint until a 200 is received or *timeout* seconds elapse.

    Uses exponential back-off: 0.5 s → 1 s → 2 s → 4 s → … (capped at 16 s).

    Parameters
    ----------
    timeout:
        Maximum number of seconds to wait before giving up.

    Raises
    ------
    SystemExit
        If the API does not become healthy within *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    delay = 0.5
    attempt = 0

    logger.info("Waiting for API to become healthy at {} (timeout={}s)…", _HEALTH_URL, timeout)

    while time.monotonic() < deadline:
        attempt += 1
        try:
            response = httpx.get(_HEALTH_URL, timeout=5.0)
            if response.status_code == 200:
                logger.info("API is healthy (attempt {}).", attempt)
                return
            logger.debug(
                "Health check attempt {} returned HTTP {}; retrying in {}s…",
                attempt,
                response.status_code,
                delay,
            )
        except httpx.TransportError as exc:
            logger.debug(
                "Health check attempt {} failed ({}); retrying in {}s…",
                attempt,
                exc,
                delay,
            )

        remaining = deadline - time.monotonic()
        actual_delay = min(delay, max(remaining, 0))
        if actual_delay > 0:
            time.sleep(actual_delay)
        delay = min(delay * 2, 16.0)

    # Timeout exceeded — dump compose logs for diagnosis then exit.
    logger.error(
        "API did not become healthy within {}s. Dumping `docker compose logs api`…",
        timeout,
    )
    _dump_api_logs()
    sys.exit(1)


def open_browser(url: str | None = None) -> None:
    """Open the given *url* (or an auto-detected one) in the default browser.

    If *url* is ``None`` the function checks whether the built frontend bundle
    is present (``frontend/dist/index.html`` relative to the repo root).  If
    it is, it opens ``http://127.0.0.1:8000/``; otherwise it falls back to
    ``/api/docs``.

    Parameters
    ----------
    url:
        Explicit URL to open.  When ``None`` the URL is inferred from the
        presence of the frontend bundle.
    """
    if url is None:
        if _FRONTEND_MARKER.is_file():
            url = "http://127.0.0.1:8000/"
            logger.debug("Frontend bundle detected — opening SPA at {}", url)
        else:
            url = "http://127.0.0.1:8000/api/docs"
            logger.debug("No frontend bundle — opening API docs at {}", url)

    logger.info("Opening browser at {}", url)
    webbrowser.open(url)


def down() -> None:
    """Run ``docker compose down`` to stop and remove the stack containers.

    Raises
    ------
    SystemExit
        If Docker is not installed or Compose returns a non-zero exit code.
    """
    cmd = [
        "docker",
        "compose",
        "-f",
        str(_COMPOSE_FILE),
        "down",
    ]
    logger.info("Stopping Docker Compose stack: {}", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.error("Docker not found. Is Docker Desktop running?")
        sys.exit(1)

    if result.returncode != 0:
        logger.error(
            "docker compose down failed (exit code {}).\n--- stderr ---\n{}",
            result.returncode,
            result.stderr.strip(),
        )
        sys.exit(1)

    logger.info("Docker Compose stack stopped.")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _dump_api_logs() -> None:
    """Run ``docker compose logs api`` and print the output to stderr."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(_COMPOSE_FILE),
        "logs",
        "api",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).strip()
        if output:
            logger.error("--- docker compose logs api ---\n{}", output)
    except FileNotFoundError:
        pass  # Docker not found — nothing we can dump.


__all__ = ["down", "open_browser", "up", "wait_healthy"]
