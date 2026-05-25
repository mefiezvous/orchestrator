# Docker — orchestrator

## Prerequisites

- Docker Engine >= 24 with Compose v2
- The 4 sibling repos must exist alongside `orchestrator/` in the workspace root
- A `.env` file at `orchestrator/.env` (copy `.env.example` and fill in `API_TOKEN`)

## Start (CPU, default)

From the **repo root** (`orchestrator/`):

```bash
docker compose -f docker/docker-compose.yml up -d
```

## Start with GPU (NVIDIA runtime required)

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
```

## Stop

```bash
docker compose -f docker/docker-compose.yml down
```

## Logs

```bash
docker compose -f docker/docker-compose.yml logs -f api
docker compose -f docker/docker-compose.yml logs -f worker
```

## Volume layout

| Mount | Purpose |
|---|---|
| `../data` → `/data` | SQLite DB, MLflow runs, checkpoints |
| `../../ml-core` → `/workspace/ml-core` | Editable install (worker: RW) |
| `../../lerobot-playground-portfolio` → `/workspace/lerobot-playground-portfolio` | Editable install (worker: RW for dataset writes) |
| `../../robotics-platform-template` → `/workspace/robotics-platform-template:ro` | HAL base (read-only) |

> **Warning**: bind paths assume the sibling repos exist at `../` relative to `orchestrator/`.
> Missing repos will cause the worker's editable-install step to fail at startup.
