# CLAUDE.md — orchestrator

## Identity
Local HTTP orchestration layer over the robotics workspace.
FastAPI + RQ + SQLite + Redis + SSE. Apache-2.0. Linux + Docker target.
Single-user, single-machine. No frontend in this repo.

## Critical Rules
1. NEVER track the 4 sibling repos (`lerobot-playground-portfolio`, `ml-core`, `robotics-platform-template`, `_private/`) — they live alongside on disk.
2. NEVER modify those sibling repos. We invoke their CLIs via subprocess only.
3. SPDX header on every `.py`:
   `# SPDX-FileCopyrightText: 2026 Arthur Mouraud`
   `# SPDX-License-Identifier: Apache-2.0`
4. `from loguru import logger` — never `print()`.
5. All env access through `orchestrator.core.config.Settings` (pydantic-settings) — never `os.environ` directly.
6. Auth: bind `127.0.0.1` by default. Bearer token from `.env`. `ALLOW_LAN=true` opt-in.
7. SQLite stores job metadata; MLflow is the source of truth for metrics — do not duplicate.

## Code Standards
- mypy strict, type hints everywhere.
- ruff (E, F, I, B, UP, N, RUF). Line length 100.
- pytest markers: `unit`, `integration`, `e2e`, `gpu`.
- Coverage gate: 70% global, 90% on `api/` and `db/`.

## Documentation enfant
- [README.md](README.md) — quickstart
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data flow, decisions
- [docs/API.md](docs/API.md) — endpoint reference (or `/api/docs`)
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — deploy, rotate token, backup, troubleshooting
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — workflow

## Workspace context (non committé)
- Cross-repo rules: `../CLAUDE.md` racine workspace
- État volatile: `../.claude/projects/.../memory/project_state.md`
