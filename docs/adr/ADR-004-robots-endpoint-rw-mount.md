<!--
SPDX-FileCopyrightText: 2026 Arthur Mouraud
SPDX-License-Identifier: Apache-2.0
-->

# ADR-004 — `/api/v1/robots`: scoped RW mount for `robot_specs/`

- **Status**: Implemented 2026-06-10
- **Deciders**: Arthur Mouraud
- **Scope**: `orchestrator` (`api/routes/robots.py`, `core/robot_specs.py`, `core/config.py`, `docker/docker-compose.yml`). Consumes `lerobot-playground-portfolio/docs/adr/ADR-001-robot-specs-yaml-registry.md`, `ml-core/docs/adr/ADR-001-yaml-spec-loader.md`, `robotics-platform-template/docs/adr/ADR-002-env-adapter-factory-registration.md`.

## Context

The user wants to declare new robots, branch/edit existing ones (all fields, via a parent/child lineage model keyed by `id`), and edit their "objectifs" (task metadata) from the frontend. `CLAUDE.md` rule #2 ("never modify sibling repos, invoke their CLIs via subprocess only") and the `api` service's `read_only: true` + all-`:ro` sibling-repo mounts (`docker/docker-compose.yml`) make this impossible for any file under `lerobot-playground-portfolio/src/` or `configs/`.

The sibling-repo data-driven registry (`lerobot-playground-portfolio` ADR-001) introduces `robot_specs/*.yaml` — a directory of plain YAML files, each fully describing one robot spec version (`spec`, `task`, `adapter`, `dataset` sections), consumed at import time by `load_specs_from_dir()` (ml-core ADR-001) and `register_from_yaml()` (robotics-platform-template ADR-002). This directory is sibling to `src/` and `configs/`, contains no executable code, and is the only artifact the orchestrator needs to write to support robot declaration/branching.

## Decision

Add a single, narrowly-scoped **RW bind mount** for the `api` service:

```yaml
- ${WORKSPACE_HOST_PATH:-../..}/lerobot-playground-portfolio/robot_specs:/workspace/lerobot-playground-portfolio/robot_specs
```

placed *after* the existing `:ro` mount of the whole `lerobot-playground-portfolio` repo. Docker bind mounts let a more specific path override the parent mount's options for that subtree, so `robot_specs/` becomes writable while the rest of the repo (`src/`, `configs/`, etc.) stays `:ro`. The `api` service's `read_only: true` root filesystem is untouched — bind mounts are independent of the container's root FS mode.

New module `orchestrator/src/orchestrator/core/robot_specs.py` provides the only read/write surface for this directory:
- `list_robot_specs()` / `get_robot_spec(id)` — parse `*.yaml`, skip `_`-prefixed and malformed files with a warning (mirrors `core/hydra_introspect.py`'s read pattern).
- `write_robot_spec(entry)` — atomic write (`tmp` file + `Path.replace`), **refuses to overwrite an existing `id`** — every edit must produce a new `id` (the branch/lineage model), so a collision is always an error.
- `build_lineage_tree(entries)` — builds parent/child trees from `id`/`parent_id`.

`orchestrator/src/orchestrator/api/routes/robots.py` exposes:
- `GET /api/v1/robots` — list all specs
- `GET /api/v1/robots/lineage` — parent/child tree(s)
- `GET /api/v1/robots/{id}` — single spec, 404 if absent
- `POST /api/v1/robots` — create a root spec (`parent_id=null`), 409 if `id` exists
- `POST /api/v1/robots/{parent_id}/branch` — create a child spec, 404 if parent absent, 409 if new `id` exists

All write paths go through Pydantic schemas (`RobotSpecFields`, `RobotTaskFields`, `RobotAdapterFields`, `RobotDatasetFields` in `api/schemas.py`) that mirror `mlcore.robots.base.RobotSpec.__post_init__` invariants — including `target_pos_key in obs_keys` — plus an `_ID_RE = ^[a-z][a-z0-9_]{1,63}$` identifier check shared with `add_robot.py` (LRB-004). Validation failures return 422 before any file is written; no YAML reaches disk that `load_specs_from_dir()` would later reject.

`Settings.robot_specs_dir` (default `/workspace/lerobot-playground-portfolio/robot_specs`, override `ROBOT_SPECS_DIR`) is the single source of truth for the path, set explicitly in `docker-compose.yml` to match the new mount.

There is no PUT/PATCH/DELETE — consistent with `RobotSpec` being `frozen=True` and the lineage model: an "edit" is a new `id` with `parent_id` pointing at the spec it was derived from. No RQ job is involved (synchronous YAML write, no subprocess).

## Alternatives considered

1. **Mount the entire `lerobot-playground-portfolio` repo RW for `api`.** Rejected: directly violates `CLAUDE.md` rule #2 and the `read_only`/`:ro` security posture (ORC-005) for no benefit — every other path under the repo is source code or Hydra config the API must never touch.
2. **Orchestrator shells out to `add_robot.py` via subprocess (existing pattern for collect/train/eval).** Rejected: `add_robot.py` writes 6 files across 3 repos including Python source (`mlcore/robots/specs/*.py`, `registrations.py` append) — none of which the `api` service can write without the same blast-radius problem as option 1. This is exactly the gap the YAML registry (sibling-repo ADRs) was introduced to close.
3. **Stage writes through the `worker` service** (which already has a broader RW mount for datasets/checkpoints) **via an RQ job.** Rejected as unnecessary indirection: writing one small YAML file is synchronous, sub-millisecond, and has no subprocess/long-running component — routing it through the job queue would add latency, a `Run` row, and SSE plumbing for no benefit. Revisit only if `robot_specs/` writes ever need to trigger heavier side effects (e.g. regenerating Hydra configs).

## Consequences

**Positive**:
- Minimal, auditable blast radius: one new bind mount, one new directory, pure YAML, strict Pydantic validation before any write.
- `read_only: true` and the `:ro` mounts for `src/`/`configs/`/ml-core/robotics-platform-template are unchanged — this ADR adds exactly one writable path.
- The lineage/branch model (`parent_id`) means existing specs are never mutated in place — datasets/checkpoints keyed by an existing `id` remain valid forever.
- `core/robot_specs.py` is fully unit-testable without Docker (it's just `Path`/`yaml` operations parameterized by `robot_specs_dir`).

**Negative**:
- A second writable mount path on the `api` service (previously zero) — must be remembered if the security posture (ORC-005) is re-audited. Mitigated by the directory being scoped, code-free, and schema-validated.
- `write_robot_spec`'s existing-file check has a (benign, single-user-local) TOCTOU race between `get_robot_spec(id)` and `write_robot_spec`; the route layer also catches `FileExistsError` from the write itself and returns 409, so a race only ever produces a clean error, never a silent overwrite.

**Verification**: `pytest orchestrator/tests/integration/test_robots_routes.py` (list/lineage/get/create/branch, 404/409/422 cases) — 11 passed. Full suite: `pytest -m "unit or integration"` — 137 passed. `ruff check` and `mypy --strict` clean on all new/edited files.
