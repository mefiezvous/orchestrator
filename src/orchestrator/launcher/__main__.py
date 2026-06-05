# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""Entry point for ``python -m orchestrator.launcher``.

Usage
-----
    python -m orchestrator.launcher              # start stack, wait healthy, open browser
    python -m orchestrator.launcher --down       # stop the stack
    python -m orchestrator.launcher --no-browser # start without opening browser
    python -m orchestrator.launcher --timeout 90 # override healthcheck timeout (seconds)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from orchestrator.launcher import down, open_browser, up, wait_healthy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_URL = "http://127.0.0.1:8000"
_MLFLOW_URL = "http://127.0.0.1:5000"
_REPO_ROOT = Path(__file__).resolve().parents[4]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.launcher",
        description="Start (or stop) the orchestrator Docker Compose stack.",
    )
    parser.add_argument(
        "--down",
        action="store_true",
        help="Stop and remove the stack containers, then exit.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip opening the browser after the stack is healthy.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        metavar="INT",
        help="Healthcheck timeout in seconds (default: 60).",
    )
    return parser


def main() -> None:
    """Entry point for ``python -m orchestrator.launcher``."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.down:
        down()
        sys.exit(0)

    # ------------------------------------------------------------------
    # 1. Start the stack.
    # ------------------------------------------------------------------
    up()

    # ------------------------------------------------------------------
    # 2. Wait for the API to become healthy.
    # ------------------------------------------------------------------
    wait_healthy(timeout=args.timeout)

    # ------------------------------------------------------------------
    # 3. Print a friendly summary.
    # ------------------------------------------------------------------
    _print_summary()

    # ------------------------------------------------------------------
    # 4. Open the browser (unless suppressed).
    # ------------------------------------------------------------------
    if not args.no_browser:
        open_browser()


def _print_summary() -> None:
    """Log a post-startup summary with URLs and usage hints."""
    env_file = _REPO_ROOT / ".env"
    token_hint = (
        f"Token is in {env_file} (grep ^API_TOKEN= .env | cut -d= -f2)"
        if env_file.is_file()
        else "Token is in .env (file not found — run `make token` first)"
    )
    logger.info(
        "\n"
        "  Orchestrator is up!\n"
        "\n"
        "  API:     {api}\n"
        "  Docs:    {api}/api/docs\n"
        "  MLflow:  {mlflow}\n"
        "\n"
        "  {token}\n"
        "\n"
        "  To stop:  make stop   OR   python -m orchestrator.launcher --down\n",
        api=_API_URL,
        mlflow=_MLFLOW_URL,
        token=token_hint,
    )


if __name__ == "__main__":
    main()
