# orchestrator

[![CI](https://github.com/mefiezvous/orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/mefiezvous/orchestrator/actions/workflows/ci.yml)

> Local HTTP orchestrator for the robotics workspace.
> FastAPI + RQ + SQLite + Redis + SSE. Apache-2.0. Linux + Docker.

This repo is a thin orchestration layer over four sibling repos (`lerobot-playground-portfolio`, `ml-core`, `robotics-platform-template`, `_private/my-robot-stack`). It exposes a REST + SSE API so a frontend (built later) can drive collect / train / eval jobs without touching CLIs.

The four sibling repos are **never** tracked from here. They sit alongside this repo on disk and are bind-mounted into the api/worker containers at runtime.

## Quickstart (Linux + Docker)

```bash
cp .env.example .env
make install               # install Python deps (uv sync)
make token                 # generate API_TOKEN
make start                 # start stack, wait for healthy, open browser
```

`make start` wraps `docker compose up -d`, polls `GET /api/v1/health` until
the API is ready, prints a summary with the API / MLflow URLs, then opens the
browser automatically.  To stop the stack, run `make stop`.

> **Advanced / CI:** `make up` is still available and calls `docker compose up -d`
> directly, without the health-poll or browser step.  Use it for scripts and CI
> pipelines where you control readiness checks yourself.

To verify the API manually after startup:

```bash
curl -H "Authorization: Bearer $(grep ^API_TOKEN= .env | cut -d= -f2)" \
     http://127.0.0.1:8000/api/v1/health
```

Launch a collect job:

```bash
TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"episodes": 5}' \
     http://127.0.0.1:8000/api/v1/runs/collect
```

Stream its logs (SSE):

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/runs/$RUN_ID/logs
```

Full API surface at `http://127.0.0.1:8000/api/docs` (Swagger UI).

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). TL;DR:

- **api** (FastAPI): REST endpoints + SSE streams, persists job metadata in SQLite
- **worker** (RQ): invokes `lerobot-playground-portfolio/{collect,train,eval}.py` as subprocesses, captures stdout/stderr, updates SQLite
- **redis**: RQ queue + pub/sub channel for MLflow metric events
- **mlflow**: file backend in `./data/mlruns`, UI at `:5000`
- **SQLite**: jobs only; MLflow remains source of truth for metrics

## Scope (v0.1)

- ML batch jobs only: collect, train, eval
- Listing endpoints for datasets, checkpoints, eval reports
- SSE streams for job logs and live metrics
- Read-only Hydra config introspection (envs, policies, profiles)

Out of scope (deferred — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):

- Live inference HTTP endpoint
- Robot teleoperation / live state WebSocket
- Multi-user JWT auth
- HTTPS reverse proxy

## License

Apache-2.0. See [LICENSE](LICENSE).
