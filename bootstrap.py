# SPDX-FileCopyrightText: 2026 Arthur Mouraud
# SPDX-License-Identifier: Apache-2.0
"""One-shot setup: from a fresh ``git clone`` to a running orchestrator.

Usage
-----
    uv run bootstrap.py

What it does
------------
1. Creates ``.env`` from ``.env.example`` and fills in a fresh ``API_TOKEN``
   if one isn't already set (equivalent to ``cp .env.example .env`` + ``make token``).
2. Starts the Docker Compose stack, waits for the API to become healthy, and
   opens the browser (``orchestrator.launcher`` — ADR-002).

Python dependencies are installed automatically by ``uv run`` before this
script executes; the frontend is built inside the Docker image (ADR-003). No
other manual step is required — Docker Desktop just needs to be installed and
running.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _REPO_ROOT / ".env"
_EXAMPLE_PATH = _REPO_ROOT / ".env.example"

_TOKEN_LINE_RE = re.compile(r"^API_TOKEN=.*$", re.MULTILINE)
_TOKEN_SET_RE = re.compile(r"^API_TOKEN=.+$", re.MULTILINE)


def ensure_env_token() -> None:
    """Ensure ``.env`` exists and has a non-empty ``API_TOKEN``.

    Seeds ``.env`` from ``.env.example`` on first run, then generates and
    writes a fresh token in place of an empty ``API_TOKEN=`` line. Leaves an
    already-populated token untouched so re-running this script is safe.
    """
    src = (
        _ENV_PATH.read_text(encoding="utf-8")
        if _ENV_PATH.exists()
        else _EXAMPLE_PATH.read_text(encoding="utf-8")
    )

    if _TOKEN_SET_RE.search(src):
        print(f"{_ENV_PATH.name}: API_TOKEN already set — leaving it untouched.")
        return

    token = secrets.token_urlsafe(32)
    new_line = f"API_TOKEN={token}"
    text, count = _TOKEN_LINE_RE.subn(new_line, src, count=1)
    if count == 0:
        text = text.rstrip("\n") + f"\n{new_line}\n"

    _ENV_PATH.write_text(text, encoding="utf-8")
    try:
        os.chmod(_ENV_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    print(f"Generated a fresh API_TOKEN and wrote it to {_ENV_PATH.name}.")


def main() -> None:
    print("== Orchestrator bootstrap ==")
    ensure_env_token()

    # Imported lazily: this module lives in the project package, which `uv run`
    # has just synced into the venv that's executing this very script.
    from orchestrator.launcher import open_browser, up, wait_healthy

    print(
        "-- Starting the stack (first run also builds the frontend in Docker — can take a few minutes) --"
    )
    up()
    wait_healthy()
    open_browser()


if __name__ == "__main__":
    main()
