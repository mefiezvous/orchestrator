#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# entrypoint-worker.sh — installs sibling repos in editable mode once,
# then execs the actual worker command.
# Idempotent: guarded by a marker file so reinstall is skipped on container restart.
set -euo pipefail

MARKER=/var/lock/sibling-installed

if [ ! -f "$MARKER" ]; then
  echo "[entrypoint] Installing sibling repos in editable mode..."

  # Use the venv Python; fall back to pip inside the venv if uv not available
  PYTHON=/opt/venv/bin/python

  # ml-core (no GPU extras required at this stage)
  uv pip install --python "$PYTHON" -e /workspace/ml-core \
    || "$PYTHON" -m pip install -e /workspace/ml-core

  # lerobot-playground-portfolio
  uv pip install --python "$PYTHON" -e /workspace/lerobot-playground-portfolio \
    || "$PYTHON" -m pip install -e /workspace/lerobot-playground-portfolio

  touch "$MARKER"
  echo "[entrypoint] Sibling repos installed."
fi

exec "$@"
