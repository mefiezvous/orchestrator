# Architecture — orchestrator

> Local HTTP orchestration layer for the robotics workspace.
> Single-user, local-only, drives ML batch jobs (collect / train / eval) without modifying 4 sibling repos.

## Purpose & Non-Goals

**Purpose:**
- Expose a unified REST + SSE API for orchestrating ML batch workflows (collect → train → eval)
- Persist job metadata and status in local SQLite
- Stream live logs (stdout/stderr) and training metrics (MLflow) to clients via SSE
- Read-only introspection of Hydra configs so a frontend can populate dropdowns without hardcoding
- All data stored locally in `./data/` (runs.db + mlruns + logs + checkpoints + eval reports)

**Non-Goals (v0.1, deferred):**
- Live inference HTTP endpoint (`POST /api/v1/infer`)
- Robot teleoperation / live state WebSocket
- Dataset browser with MP4 preview
- Multi-user JWT authentication
- HTTPS reverse proxy (use external nginx/caddy if needed)
- DAG / workflow orchestration engine (Prefect / Dagster)

The 4 sibling repos (`lerobot-playground-portfolio`, `ml-core`, `robotics-platform-template`, `_private/my-robot-stack`) are **never** modified from this repo. They are bind-mounted into containers at runtime and invoked as subprocesses.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Frontend)                         │
│  (Future: web UI in separate repo)                              │
└────────────┬──────────────────────────────────────────┬──────────┘
             │                                          │
      REST + SSE (http://127.0.0.1:8000)       Bearer token in .env
             │                                          │
┌────────────▼──────────────────────────────────────────▼──────────┐
│                    API Container (FastAPI)                        │
│  Port 8000                                                        │
│  ├─ POST /api/v1/runs/{collect,train,eval}  (enqueue job)       │
│  ├─ GET  /api/v1/runs/{id}                  (fetch status)       │
│  ├─ GET  /api/v1/runs/{id}/logs              (SSE stream)       │
│  ├─ GET  /api/v1/runs/{id}/metrics           (SSE metrics)      │
│  ├─ GET  /api/v1/configs/*                   (Hydra introspect) │
│  └─ GET  /api/v1/artifacts/*                 (list artifacts)   │
│                                                                    │
│  Auth: bind 127.0.0.1, check Bearer token vs .env API_TOKEN      │
│  Persist jobs to:  ./data/runs.db  (SQLite)                      │
│  Read metrics from: ./data/mlruns/ (MLflow file backend)         │
└──────┬──────────────────────────────────────────────┬────────────┘
       │                                              │
       │  RQ queue (job enqueue)                      │
       │                                              │ Metrics pubsub
       │                                              │ ("mlflow:{run_id}")
   ┌───▼────────────────────┐      ┌────────────────▼──────────┐
   │   RQ Queue / Worker    │      │   Redis Pub/Sub           │
   │   Container            │      │   ├─ Log events           │
   │   Processes 1 job      │      │   ├─ Metrics events       │
   │   at a time            │      │   └─ Rate-limited SSE     │
   │                        │      │   (5 sec window)          │
   └──────┬─────────────────┘      └───────────────────────────┘
          │
          │  Subprocess spawn
          │  uv run python train.py ...
          │  (with Hydra overrides from API)
          │
   ┌──────▼───────────────────────────────────────────────────────┐
   │  Sibling Repo Containers (bind-mounts, read-only code)       │
   │                                                               │
   │  ├─ lerobot-playground-portfolio/                            │
   │  │  ├─ collect.py (Hydra CLI)                               │
   │  │  ├─ train.py   (Hydra CLI)                               │
   │  │  └─ eval.py    (Hydra CLI)                               │
   │  │                                                           │
   │  ├─ ml-core/                                                 │
   │  │  ├─ Trainer (calls MLflow tracking)                      │
   │  │  ├─ Evaluator                                            │
   │  │  └─ RobotSpec / policies                                 │
   │  │                                                           │
   │  ├─ robotics-platform-template/                              │
   │  │  └─ HAL Protocols / Adapters                             │
   │  │                                                           │
   │  └─ _private/my-robot-stack/                                 │
   │     └─ (proprietary stub — never on public remote)          │
   │                                                               │
   │  Stdout/Stderr piped to:  ./data/logs/{run_id}.{stdout,stderr}
   │  MLflow tracking URI:     file:///app/data/mlruns            │
   └─────────────────────────────────────────────────────────────┘
          │
          │  MLflow file write
          │  (metrics, artifacts, params)
          │
    ┌─────▼──────────────┐
    │  ./data/            │
    │  ├─ runs.db        │  Job metadata (status, timestamps, params)
    │  ├─ mlruns/        │  MLflow experiments + runs + metrics
    │  ├─ logs/          │  stdout/stderr per job
    │  ├─ checkpoints/   │  Model weights (from train runs)
    │  └─ eval_reports/  │  Eval metrics + video (if enabled)
    └────────────────────┘
```

---

## Component Responsibilities

### `api/` — FastAPI Application

**Files:** `src/orchestrator/api/main.py`, `src/orchestrator/api/routes/`

**Responsibilities:**
- Boot a FastAPI server on `127.0.0.1:8000` (or `0.0.0.0` if `ALLOW_LAN=true`)
- Parse and validate Bearer token from `.env API_TOKEN`
- Expose REST endpoints for job submission (POST), status retrieval (GET), listing (GET), cancellation (DELETE)
- Expose SSE endpoints for real-time log and metric streams
- Read-only introspection of Hydra YAML configs to populate frontend dropdowns
- List available datasets, checkpoints, eval reports from `./data/`
- Enqueue jobs into RQ queue
- Fetch job metadata from SQLite
- Serve OpenAPI schema at `/api/docs` and `/api/openapi.json`

**Auth Model:**
- Bind to `127.0.0.1` by default (localhost only, safe for single-user)
- Check `Authorization: Bearer $TOKEN` header against `.env API_TOKEN`
- Optional `ALLOW_LAN=true` to bind `0.0.0.0` for LAN access (less safe)
- Token rotation: `make token` updates `.env` and requires container restart (`make down && make up`)

**No Write to Metrics:**
- Does NOT write to MLflow directly — that is the worker's responsibility
- Reads MLflow metrics via watchdog observer + Redis pubsub

### `worker/` — RQ Worker

**Files:** `src/orchestrator/worker/job_handler.py`, `docker/worker.Dockerfile`

**Responsibilities:**
- Poll RQ queue for jobs
- Pop a job, read its parameters from SQLite
- Spawn a subprocess: `uv run python <repo>/{collect,train,eval}.py` with Hydra overrides
- Capture stdout and stderr, pipe to `./data/logs/{run_id}.stdout` and `./data/logs/{run_id}.stderr` in real-time
- Update SQLite job status: `queued` → `running` → `completed` or `failed`
- Write exit code to SQLite
- **Never** modify the 4 sibling repos (they are read-only bind-mounts)

**Concurrency Model:**
- Single RQ worker = 1 job at a time (GPU contention prevents parallelism)
- Queue serializes subsequent jobs
- If a job crashes, worker logs the exit code and moves to next job

**MLflow Integration:**
- Sets `MLFLOW_TRACKING_URI=file:///app/data/mlruns` before spawning subprocess
- The subprocess (Trainer, etc.) calls `mlflow.log_metric()` directly
- Worker does NOT read or write metrics — that is the job's responsibility

### `db/` — SQLite Database + Alembic

**Files:** `src/orchestrator/db/models.py`, `src/orchestrator/db/migrations/`

**Responsibilities:**
- Store job metadata in `./data/runs.db`:
  - Job ID (uuid), type (collect/train/eval), status, created_at, started_at, completed_at
  - Input parameters (episodes, policy type, checkpoint path, etc.) as JSON
  - Output summary (exit_code, error message, artifact URLs)
- **Never** duplicate metrics — metrics live in MLflow only
- Alembic for schema migrations (apply on container boot)
- Provide ORM models for the API to query and update

**Data Retention:**
- Jobs are immutable once created
- SQLite is a metadata-only store — source of truth for job state, not for metrics

### `core/` — Shared Utilities

**Files:** `src/orchestrator/core/*.py`

**Key modules:**

#### `config.py` — Settings Management
- Singleton `Settings` class (Pydantic BaseSettings)
- Read `.env` file on startup
- Expose `API_TOKEN`, `ALLOW_LAN`, `API_PORT`, `REDIS_URL`, `MLFLOW_TRACKING_URI`, `WORKER_TIMEOUT`
- Never access `os.environ` directly elsewhere — use `Settings` instance
- Validate required fields on boot

#### `logging.py` — Logging Setup
- Configure `loguru` logger on startup
- Set log level from `LOG_LEVEL` env var (default: INFO)
- Log to stdout (captured by Docker) + optionally to `./data/logs/orchestrator.log`
- Ensure all prints are replaced with `logger.info()`, etc.

#### `mlflow_bridge.py` — Watchdog over MLflow File Backend
- Monitor `./data/mlruns/` directory for new metric files
- When metrics appear, publish an event to Redis pubsub channel: `mlflow:{run_id}`
- Payload: `{"ts": iso8601, "step": int, "metric": str, "value": float}`
- Clients subscribed to SSE `/api/v1/runs/{id}/metrics` receive events in real-time
- Use `watchdog.observers.Observer` to avoid polling

#### `hydra_introspect.py` — Read-Only Hydra Config Scanner
- Scan `<sibling-repo>/configs/{env,policy,training,dataset,...}/*.yaml`
- Parse YAML to extract config options (enum-like lists)
- Expose via endpoints like `GET /api/v1/configs/envs` → `["cube_reach_v1", "pusht_image", ...]`
- Never modify configs — read-only only

### `launcher/` — Python Launcher (ADR-002)

**Files:** `src/orchestrator/launcher/__init__.py`, `src/orchestrator/launcher/__main__.py`

The launcher is a thin (~150 LOC) developer-experience wrapper that chains three steps in
sequence: `up()` calls `docker compose up -d`; `wait_healthy()` polls
`GET /api/v1/health` with exponential back-off until the API responds 200 (or the timeout is
exceeded and exits 1 after dumping `docker compose logs api`); `open_browser()` opens the
SPA at `/` when `frontend/dist/index.html` is present, or `/api/docs` otherwise.

Invoked via `make start` / `python -m orchestrator.launcher`.  The `--down` flag delegates
to `down()` which wraps `docker compose down`.  See **ADR-002** for the decision rationale.

### `docker/` — Docker Compose + Dockerfiles

**Files:** `docker/docker-compose.yml`, `docker/docker-compose.gpu.yml`, `docker/api.Dockerfile`, `docker/worker.Dockerfile`

**Services:**
1. **api** — FastAPI server, port 8000, uses `api.Dockerfile`
2. **worker** — RQ worker, uses `worker.Dockerfile`
3. **redis** — Redis server, port 6379 (internal only)
4. **mlflow** — MLflow UI, port 5000 (optional, for debugging)

**Bind Mounts:**
- `./data/` → `/app/data` (runs.db, mlruns, logs, checkpoints, eval_reports)
- Sibling repos (read-only) → `/app/lerobot`, `/app/ml-core`, etc. (if needed for subprocess PATH)
- `.env` → `/app/.env` (read by Settings on boot)

**Environment:**
- `MLFLOW_TRACKING_URI=file:///app/data/mlruns`
- `PYTHONUNBUFFERED=1` (so logs are unbuffered)
- Shared `REDIS_URL=redis://redis:6379`

---

## Data Flow — Collect Job Example

1. **Client submits collect job:**
   ```
   POST /api/v1/runs/collect
   Authorization: Bearer $TOKEN
   Content-Type: application/json
   
   {
     "episodes": 5,
     "env": "cube_reach_v1",
     "policy_type": "scripted",
     "hydra_overrides": ["dataset.repo_id=user/my-dataset"]
   }
   ```

2. **API validates and enqueues:**
   - Create a new job record in SQLite: `{id: uuid, type: "collect", status: "queued", params: {...}, created_at: now}`
   - Serialize parameters into an RQ job
   - Enqueue to Redis queue
   - Return `{id, status: "queued", created_at}`

3. **Worker picks up job:**
   - Fetch job record from SQLite
   - Spawn subprocess:
     ```
     cd /app/lerobot-playground-portfolio
     MLFLOW_TRACKING_URI=file:///app/data/mlruns \
     uv run python collect.py \
       env=cube_reach_v1 \
       policy_type=scripted \
       dataset.repo_id=user/my-dataset \
       episodes=5
     ```
   - Open pipes for stdout and stderr
   - Update SQLite: `status = "running"`, `started_at = now`

4. **Subprocess runs and logs:**
   - LeRobot collect.py spawns environments, records episodes
   - Each log line is written to stdout
   - Worker reads lines and appends to `./data/logs/{id}.stdout` (streamed to clients via SSE)
   - If errors occur, stderr goes to `./data/logs/{id}.stderr`

5. **Subprocess completes:**
   - Writes final artifacts (HF Hub push if configured)
   - Exits with code 0 (success) or non-zero (failure)
   - Worker captures exit code, updates SQLite: `status = "completed"` or `"failed"`, `completed_at = now`, `exit_code = ...`
   - Closes log file handles

6. **Client streams logs in real-time:**
   - Open SSE connection: `GET /api/v1/runs/{id}/logs`
   - Authorization: Bearer token
   - Receive events:
     ```
     data: {"ts": "2026-05-25T12:34:56Z", "stream": "stdout", "line": "[2026-05-25 12:34:56] Episode 1/5..."}
     data: {"ts": "2026-05-25T12:34:57Z", "stream": "stdout", "line": "[2026-05-25 12:34:57] Episode 2/5..."}
     ```

7. **Client polls status:**
   - `GET /api/v1/runs/{id}`
   - Response: `{id, type: "collect", status: "completed", created_at, started_at, completed_at, exit_code: 0}`

8. **Client lists collected datasets:**
   - `GET /api/v1/artifacts/datasets`
   - Response: `{datasets: [{name: "cube-reach-v1-dataset-2026-05-25", size_mb: 125, created_at}]}`

---

## Why Subprocess Invocation (Not Import)?

**Decision:** Invoke `lerobot-playground-portfolio/{collect,train,eval}.py` as subprocesses, not import them as Python modules.

**Rationale:**

1. **Zero modifications to 4 sibling repos**
   - If we import, we risk adding imports or code that couples the sibling repos to the orchestrator
   - Subprocess invocation keeps repo boundaries clean

2. **Crash isolation**
   - If a training job runs out of memory, it crashes and kills only the subprocess, not the API/worker
   - Imports can corrupt the worker's Python process state

3. **Native Hydra CLI compatibility**
   - `lerobot train.py` is designed as a Hydra CLI
   - Invoking it as a subprocess respects Hydra's argument parsing and config composition
   - Importing would require reimplementing Hydra argument parsing in the worker

4. **Simple stdout/stderr capture**
   - Subprocess stdout/stderr are file descriptors, easy to pipe to logs
   - If we import, we'd need to redirect sys.stdout/sys.stderr, which is fragile

**Trade-off:**
- Subprocess startup overhead (~1 sec) is acceptable for multi-minute jobs
- Error messages from the CLI go to stderr, not Python exceptions (must parse logs to extract errors)

---

## Why SQLite + MLflow Split (Not Duplicating)?

**Decision:** SQLite holds job metadata only (status, timestamps, parameters). MLflow remains the canonical metrics store.

**Rationale:**

1. **MLflow as single source of truth**
   - Trainer + Evaluator already write metrics to MLflow
   - Duplicating metrics in SQLite risks divergence (which value is correct?)
   - MLflow UI provides a built-in dashboard; no need to reimplement

2. **Job state is separate from metrics**
   - A job can be "running" (SQLite) but have no metrics yet (MLflow)
   - Job status and metrics are different concerns (status is binary, metrics are time-series)
   - Separating them simplifies the data model

3. **Scalability**
   - MLflow file backend scales better for large metric datasets (millions of events)
   - SQLite would bloat if we stored every metric row

**Query pattern:**
- Client wants job status? Query SQLite (fast, ~1ms)
- Client wants live metrics? Subscribe to SSE / watchdog over MLflow files (real-time, via Redis pubsub)

---

## Hydra Introspection

**Purpose:** Frontend doesn't hardcode available policies, envs, etc. Read from YAML configs at runtime.

**Implementation:**
- Endpoint `GET /api/v1/configs/envs` scans `lerobot-playground-portfolio/configs/env/*.yaml`
- Parse YAML and extract top-level keys or `_target_` fields
- Return list: `["cube_reach_v1", "pusht_image", ...]`
- Similar endpoints for `policies`, `profiles`, `datasets`, `collect`, `eval`

**Read-only:** Never modify configs. If a user wants a new environment, they edit the YAML and restart the API (or we add a /admin/reload-configs endpoint later).

---

## Auth Model

**Bind Address:**
- Default: `127.0.0.1:8000` (localhost only)
- Rationale: Single-user local orchestrator, no need for network auth
- Client must run on same machine or reverse-proxy through nginx/caddy

**Bearer Token:**
- Read from `.env API_TOKEN` on API startup
- Check every request: `Authorization: Bearer <token>`
- Return 401 if missing or wrong
- Token is a random hex string (generated by `make token`)

**Token Rotation:**
- `make token` generates a new token, updates `.env`
- Requires container restart (`make down && make up`)
- Old token immediately invalid (no grace period)

**Optional LAN Access:**
- Set `ALLOW_LAN=true` in `.env` to bind `0.0.0.0`
- Enables access from other machines on the LAN
- **Less safe:** Token is sent in plaintext unless reverse-proxied over HTTPS
- Use external reverse proxy (nginx/caddy) to add TLS if exposing to untrusted networks

---

## Concurrency Model

**Single Worker, Sequential Queue:**
- 1 RQ worker process services the queue FIFO
- GPU contention prevents running multiple train/eval jobs in parallel
- If 2 jobs enqueued in quick succession, the second waits in the queue
- Status is "queued" until the first job completes

**Job Timeout:**
- Worker enforces `WORKER_TIMEOUT` (default: 24h) per job
- If a job runs longer, it is killed with SIGTERM
- SQLite is updated: `status = "failed"`, `exit_code = -15`

**Graceful Shutdown:**
- `docker compose down` waits for the current job to finish (timeout: 10s)
- If a job is killed mid-run, its output file is left incomplete (next run can continue appending)

---

## SSE Strategy

**Two SSE Streams per Job:**

### 1. Logs: `/api/v1/runs/{id}/logs`
- Real-time stdout/stderr lines from the running subprocess
- **Source:** Watchdog observer on `./data/logs/{id}.stdout` and `./data/logs/{id}.stderr`
  - When a new line is written, watchdog triggers
  - API reads the line and publishes to Redis pubsub channel: `logs:{run_id}`
  - SSE clients subscribed to that channel receive the event
- **Event format:**
  ```json
  {"ts": "2026-05-25T12:34:56Z", "stream": "stdout", "line": "..."}
  ```
- **Latency:** ~100ms (watchdog observer callback + Redis roundtrip)

### 2. Metrics: `/api/v1/runs/{id}/metrics`
- Real-time training metrics (loss, accuracy, etc.) from MLflow
- **Source:** Watchdog observer on `./data/mlruns/{exp_id}/{run_id}/metrics/`
  - MLflow writes a new file per metric per step: `loss/1.json`, `loss/2.json`, etc.
  - When a file appears, watchdog triggers
  - API parses the file, publishes to Redis pubsub channel: `mlflow:{run_id}`
  - SSE clients subscribed receive the metric
- **Event format:**
  ```json
  {"ts": "2026-05-25T12:34:56Z", "step": 1000, "metric": "loss", "value": 0.123}
  ```
- **Buffering:** Metrics are buffered in memory for 5 seconds, then sent as a batch (reduces SSE overhead)

**Subscriber Topology:**
- Multiple clients can subscribe to the same job's SSE stream
- Redis pubsub broadcasts to all subscribers
- If no subscribers, events are lost (pubsub is not persistent)
- Clients can replay logs/metrics by polling `/api/v1/runs/{id}/logs/history` and `/api/v1/runs/{id}/metrics/history` (not in v0.1)

---

## Out-of-Scope (v0.1, Deferred)

| Feature | Why Deferred | Estimated Scope |
|---------|-------------|-----------------|
| Live inference HTTP (`POST /api/v1/infer`) | Requires real-time policy execution; GPU + CUDA graphs | 2–3 WPs, P1 |
| Teleop WebSocket (`WS /api/v1/teleop`) | Depends on `my-robot-stack` HW finalisation | 1–2 WPs, P1 |
| Dataset browser with MP4 preview | Requires FFmpeg + web streaming | 1–2 WPs, P2 |
| Multi-user JWT auth | Out of scope for single-user local tool | 1 WP, DEFER |
| HTTPS reverse proxy | Use external nginx/caddy (not in this repo) | — |
| DAG orchestration (Prefect/Dagster) | Scope creep; RQ queue is sufficient for v0.1 | 3–4 WPs, DEFER |

---

## Repository Boundary Rules

**Critical:**
1. **Never modify the 4 sibling repos from this repo's code or docs**
   - No `git clone`, `pip install <sibling>` from this repo
   - Sibling repos are bind-mounted read-only at runtime

2. **Never reference `_private/my-robot-stack` in any file**
   - Not in code, not in docs, not in comments
   - This repo is Apache-2.0; `my-robot-stack` is Proprietary

3. **Never hardcode sibling repo paths in code**
   - Use environment variables or config injection
   - Docker Compose binds paths; code should not assume locations

4. **Documentation stays in sibling repos**
   - If a user needs to understand `lerobot collect.py`, point them to `lerobot-playground-portfolio/docs/`
   - This repo documents the orchestrator layer, not the sibling repos

---

## Next Steps (Roadmap)

See [ROADMAP.md](ROADMAP.md) for feature additions, performance optimizations, and future iterations.
