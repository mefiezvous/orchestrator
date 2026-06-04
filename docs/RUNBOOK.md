# Runbook — orchestrator

> Operational instructions for deploying, running, maintaining, and troubleshooting the orchestrator.

---

## Initial Deployment (Linux + Docker)

### Prerequisites
- Docker and Docker Compose installed
- 4 sibling repos cloned alongside this repo:
  - `../lerobot-playground-portfolio/`
  - `../ml-core/`
  - `../robotics-platform-template/`
  - `../_private/my-robot-stack/` (optional, proprietary)
- Linux environment (WSL2 on Windows also works)

### Step 1: Set Up Environment Variables

```bash
cd orchestrator
cp .env.example .env
```

Review `.env` and adjust if needed:
- `API_TOKEN` — will be generated below
- `API_PORT` — default 8000
- `ALLOW_LAN` — default false (localhost only)
- `LOG_LEVEL` — default INFO
- `WORKER_TIMEOUT` — default 86400 (24 hours)
- `REDIS_URL` — default redis://redis:6379 (internal, no change needed)
- `MLFLOW_TRACKING_URI` — default file:///app/data/mlruns (internal, no change needed)

### Step 2: Generate API Token

```bash
make token
```

This generates a random hex token and updates `.env`:
```
API_TOKEN=550e8400e29b41d4a716446655440000
```

The token is used for all API requests: `Authorization: Bearer $TOKEN`.

### Step 3: Start All Services

```bash
make up
```

This runs `docker compose up -d` and starts:
- **api** — FastAPI server on port 8000
- **worker** — RQ worker process
- **redis** — Redis server (internal)
- **mlflow** — MLflow UI on port 5000 (optional debugging)

### Step 4: Verify Health

```bash
TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/health
```

Expected response:
```json
{
  "status": "ok",
  "timestamp": "2026-05-25T12:34:56Z",
  "services": {
    "redis": "ok",
    "sqlite": "ok",
    "mlflow": "ok"
  }
}
```

### Step 5: Access OpenAPI Documentation

Open in browser:
```
http://127.0.0.1:8000/api/docs
```

This is an interactive Swagger UI. You can test endpoints directly (copy your token into the "Authorize" button).

---

## Running Jobs

### Submit a Collect Job

```bash
TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"episodes": 5, "env": "cube_reach_v1", "policy_type": "scripted"}' \
  http://127.0.0.1:8000/api/v1/runs/collect
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "collect",
  "status": "queued",
  "created_at": "2026-05-25T12:34:56Z"
}
```

Save the `id` for later queries.

### Submit a Train Job

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "policy": "act",
    "total_steps": 10000,
    "env": "cube_reach_v1"
  }' \
  http://127.0.0.1:8000/api/v1/runs/train
```

### Submit an Eval Job

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "checkpoint_path": "checkpoints/checkpoint_00010000.ckpt",
    "n_episodes": 10
  }' \
  http://127.0.0.1:8000/api/v1/runs/eval
```

---

## Monitoring Jobs

### Check Job Status

```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000
```

### List All Jobs

```bash
curl -H "Authorization: Bearer $TOKEN" \
     'http://127.0.0.1:8000/api/v1/runs?status=running'
```

### Stream Live Logs (SSE)

```bash
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/logs
```

This will print log lines in real-time:
```
data: {"ts": "2026-05-25T12:34:56Z", "stream": "stdout", "line": "[2026-05-25 12:34:56] Episode 1/5"}
data: {"ts": "2026-05-25T12:34:57Z", "stream": "stdout", "line": "[2026-05-25 12:34:57] Episode 2/5"}
```

Press `Ctrl+C` to stop.

> **ORC-004 — Browser EventSource limitation (deferred to ADR-003):**
> The SSE endpoints (`/logs`, `/metrics`) require a `Bearer` token via the
> `Authorization` header.  The browser-native `EventSource` API **cannot set
> custom headers**, so a JavaScript frontend cannot connect using the standard
> flow.  Until ADR-003 decides on the frontend auth transport (short-lived
> signed stream token vs. WebSockets vs. same-origin cookie), **browser SSE
> clients are unsupported**.  CLI and backend consumers using `curl -H
> "Authorization: Bearer $TOKEN"` work without restriction.
>
> **Do NOT work around this by passing `?token=...` as a query parameter** —
> query-string tokens appear in nginx/uvicorn access logs, browser history,
> and `document.referrer`, which negates the protection.  Wait for ADR-003.

### Stream Live Metrics (SSE)

For a training job:
```bash
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440001/metrics
```

### View MLflow UI

```
http://127.0.0.1:5000
```

This shows experiments, runs, and metrics in a web UI. Useful for comparing multiple training runs.

---

## Service Verification

### Check All Containers

```bash
docker compose ps
```

Expected output:
```
NAME             IMAGE                    COMMAND              SERVICE    STATUS
orchestrator-api-1      orchestrator:api         "python -m orchestr…"   api        Up
orchestrator-worker-1   orchestrator:worker      "rq worker -u redis:…"  worker     Up
orchestrator-redis-1    redis:7-alpine           "redis-server"          redis      Up
orchestrator-mlflow-1   mlflow:latest            "mlflow ui"              mlflow     Up
```

### View Container Logs

**API logs:**
```bash
docker compose logs -f api
```

**Worker logs:**
```bash
docker compose logs -f worker
```

**All logs:**
```bash
docker compose logs -f
```

Or use the shortcut:
```bash
make logs
```

### Check Redis Connection

```bash
docker exec orchestrator-redis-1 redis-cli ping
```

Expected: `PONG`

### Check SQLite Database

```bash
docker exec orchestrator-api-1 sqlite3 /app/data/runs.db ".tables"
```

Expected: list of tables (jobs, etc.)

---

## Data Management

### Data Directory Structure

```
data/
├── runs.db                  # SQLite job metadata database
├── mlruns/                  # MLflow experiments + metrics (file backend)
│   ├── 0/                   # MLflow experiment 0
│   │   ├── uuid-run-1/
│   │   │   ├── metrics/
│   │   │   ├── artifacts/
│   │   │   └── params.yaml
│   │   └── uuid-run-2/
│   ├── ...
├── logs/                    # Job stdout/stderr files
│   ├── 550e8400-e29b-41d4-a716-446655440000.stdout
│   ├── 550e8400-e29b-41d4-a716-446655440000.stderr
│   └── ...
├── checkpoints/             # Trained model checkpoints
│   ├── checkpoint_00010000.ckpt
│   └── ...
└── eval_reports/            # Evaluation metrics and videos
    ├── eval_2026_05_25_123456.json
    └── ...
```

### Backup Data

```bash
tar -czf orchestrator-backup-$(date +%Y%m%d_%H%M%S).tar.gz data/
```

This creates a compressed backup of all job data, runs, metrics, logs, and checkpoints.

### Clean Up Old Jobs (Manual)

```bash
# Remove old log files (keep last 10 days)
find data/logs -type f -mtime +10 -delete

# Remove old checkpoints (manual review recommended)
ls -lt data/checkpoints | head -20
```

**Warning:** Deleting checkpoints or MLflow runs is permanent. Verify before deleting.

### Export Job Metadata to CSV

```bash
docker exec orchestrator-api-1 sqlite3 /app/data/runs.db \
  ".headers on" \
  ".mode csv" \
  "SELECT id, type, status, created_at, started_at, completed_at FROM jobs;" \
  > jobs.csv
```

---

## API Token Management

### Generate New Token

```bash
make token
```

This generates a new token and updates `.env`. **Container restart required:**

```bash
make down && make up
```

**Important:** The old token becomes invalid immediately.

### Rotate Token Regularly

For production use (even local), rotate the token monthly:
```bash
make token && make down && make up
```

### Secure Token in `.env`

- `.env` is in `.gitignore` (never committed)
- Keep `.env` readable by your user only: `chmod 600 .env`
- Never share the token with untrusted users (even locally, different machine)

---

## GPU Support (Optional)

### Prerequisites
- NVIDIA GPU on host
- `nvidia-container-toolkit` installed on Docker host

### Use GPU Compose Overlay

Instead of the default `docker-compose.yml`, use the GPU variant:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Or update your `.env`:
```bash
DOCKER_COMPOSE_FILE=docker-compose.gpu.yml
make up
```

The GPU variant adds:
- `deploy.resources.reservations.devices` (GPU) to api and worker services
- Environment variables: `CUDA_VISIBLE_DEVICES=0` (adjust if multiple GPUs)

### Verify GPU Access

```bash
docker exec orchestrator-worker-1 nvidia-smi
```

Expected: NVIDIA GPU(s) listed.

### Troubleshooting GPU

If GPUs not detected:
- Check host: `nvidia-smi` on the host machine
- Check Docker daemon config: `cat /etc/docker/daemon.json` (should have `"runtimes": {"nvidia": {...}}`)
- Restart Docker: `sudo systemctl restart docker`
- Rebuild images: `docker compose down && docker compose build --no-cache && make up`

---

## Custom Workspace Layout

By default, `docker-compose.yml` expects the canonical workspace layout, with the four sibling repos checked out next to `orchestrator/`:

```
robotics-workspace/
├── orchestrator/                      ← this repo (compose is invoked from here)
├── lerobot-playground-portfolio/
├── ml-core/
├── robotics-platform-template/
└── _private/my-robot-stack/           (optional)
```

Volume sources in `docker/docker-compose.yml` use `${WORKSPACE_HOST_PATH:-../..}` to resolve to that layout (`../..` is relative to `orchestrator/docker/`, i.e. `robotics-workspace/`).

### Override for non-canonical layouts

If the sibling repos live elsewhere on the host (e.g. cloned to `/srv/robotics/`), set `WORKSPACE_HOST_PATH` to an absolute path:

```bash
# in .env (preferred — persisted)
WORKSPACE_HOST_PATH=/srv/robotics

# or one-shot
WORKSPACE_HOST_PATH=/srv/robotics docker compose -f docker/docker-compose.yml up -d
```

### Verify resolved volume mounts

Before starting containers, validate the rendered compose config:

```bash
docker compose -f docker/docker-compose.yml config | grep -A1 "source:"
```

Each `source:` line should resolve to an existing path on the host. Missing repos → Docker will fail at startup with `no such file or directory`.

### Distinguishing host vs container

| Variable | Side | Purpose |
|---|---|---|
| `WORKSPACE_HOST_PATH` | host (compose) | Volume mount source (where Docker reads sibling repos from) |
| `WORKSPACE_ROOT` | container | Where the api/worker code expects to find sibling repos (`/workspace`) — **do not change** unless rewriting `Dockerfile` |

---

## WSL2 Notes (Windows + Docker Desktop)

### Path Binding

Docker on WSL2 requires proper path translation:
```yaml
# ✓ Correct (forward slashes, relative or absolute WSL path)
volumes:
  - ./data:/app/data
  - /mnt/c/Users/username/robotics-workspace/lerobot:/app/lerobot

# ✗ Incorrect (Windows path)
volumes:
  - C:\Users\username\robotics-workspace\data:/app/data
```

### Ensure WSL2 Integration

Docker Desktop settings:
1. Settings > Resources > WSL Integration
2. Enable "Windows Subsystem for Linux (WSL) 2"
3. Check "Use the default WSL distro"
4. Apply & Restart

### Performance

WSL2 disk I/O is slower on cross-mounted paths. For best performance:
- Store `orchestrator/` inside WSL2 filesystem (not mounted from Windows)
- Or use `WSL_MOUNT_KIND=drvfs` (Windows 11 only, experimental)

---

## Common Troubleshooting

### 401 Unauthorized

**Symptom:**
```json
{
  "detail": "Invalid token"
}
```

**Solution:**
1. Verify token in `.env`:
   ```bash
   grep ^API_TOKEN= .env
   ```
2. Use exact token in curl:
   ```bash
   TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
   curl -H "Authorization: Bearer $TOKEN" ...
   ```
3. Ensure no extra whitespace in token
4. If token was just rotated, verify container restarted:
   ```bash
   docker compose ps | grep api
   ```

### Worker Not Picking Up Jobs

**Symptoms:**
- Job stays in "queued" status
- `docker compose logs worker` shows no activity

**Solutions:**
1. Check Redis is healthy:
   ```bash
   docker compose logs redis
   docker exec orchestrator-redis-1 redis-cli ping
   ```
2. Check worker logs for errors:
   ```bash
   docker compose logs -f worker
   ```
3. Verify RQ queue is not stuck:
   ```bash
   docker exec orchestrator-redis-1 redis-cli LLEN rq:queue:default
   ```
4. Restart worker:
   ```bash
   docker compose restart worker
   ```

### MLflow Metrics Not Streaming

**Symptom:**
- Logs stream fine, but metrics endpoint returns no events

**Solutions:**
1. Check MLflow tracking URI:
   ```bash
   grep MLFLOW_TRACKING_URI .env
   ```
2. Verify metrics files are being written:
   ```bash
   ls -la data/mlruns/*/*/metrics/
   ```
3. Check watchdog observer in API logs:
   ```bash
   docker compose logs api | grep -i "watchdog\|observer"
   ```
4. Manually check a metrics file:
   ```bash
   cat data/mlruns/0/*/metrics/loss/1.json
   ```

### Port Already in Use

**Symptom:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:8000: bind: address already in use
```

**Solution:**
1. Find process using port 8000:
   ```bash
   lsof -i :8000
   ```
2. Kill it (if safe):
   ```bash
   kill -9 <PID>
   ```
3. Or change port in `.env`:
   ```
   API_PORT=8001
   ```

### GPU Not Detected in Container

**Symptom:**
```bash
docker exec orchestrator-worker-1 nvidia-smi
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
```

**Solutions:**
1. Verify host GPU:
   ```bash
   nvidia-smi
   ```
2. Check Docker runtime:
   ```bash
   docker run --rm --gpus all nvidia/cuda:11.8.0-runtime-ubuntu22.04 nvidia-smi
   ```
3. Reinstall nvidia-container-toolkit:
   ```bash
   sudo apt-get remove nvidia-container-toolkit
   sudo apt-get install nvidia-container-toolkit
   sudo systemctl restart docker
   ```

### Container Crashes on Startup

**Symptom:**
```bash
docker compose logs api
ERROR: Cannot connect to SQLite / Redis
```

**Solutions:**
1. Check all containers are running:
   ```bash
   docker compose ps
   ```
2. Check logs for each service:
   ```bash
   docker compose logs
   ```
3. Rebuild images:
   ```bash
   docker compose build --no-cache
   ```
4. Remove old volumes:
   ```bash
   docker compose down -v
   make up
   ```

### Logs Not Persisting

**Symptom:**
- Jobs complete but `data/logs/{id}.stdout` is empty or missing

**Solutions:**
1. Verify stdout capture in worker:
   ```bash
   docker compose logs worker | grep -i "stdout\|pipe"
   ```
2. Check file permissions on `data/logs/`:
   ```bash
   ls -la data/logs/
   chmod 755 data/logs
   ```
3. Check subprocess is actually writing to stdout (not buffering):
   - Add `PYTHONUNBUFFERED=1` in Dockerfile (already done)
   - Add `--tb=short` to pytest/python for unbuffered output

---

## Operational Best Practices

### Monitor Queue Depth

```bash
docker exec orchestrator-redis-1 redis-cli LLEN rq:queue:default
```

This shows how many jobs are waiting. For long runs, occasionally check this to detect stuck workers.

### Periodic Health Checks

Add to cron or systemd timer:
```bash
0 */6 * * * cd /path/to/orchestrator && \
  TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2) && \
  curl -f -H "Authorization: Bearer $TOKEN" \
    http://127.0.0.1:8000/api/v1/health || \
  systemctl restart docker
```

### Log Rotation

Logs accumulate in `data/logs/`. Implement rotation (e.g., with `logrotate`):

```
# /etc/logrotate.d/orchestrator
/path/to/orchestrator/data/logs/*.stdout {
  daily
  rotate 7
  missingok
  compress
  delaycompress
  notifempty
  create 0644 $USER $USER
}
```

### Backup Schedule

Weekly backup:
```bash
0 0 * * 0 cd /path/to/orchestrator && \
  tar -czf ../backups/orchestrator-$(date +\%Y\%m\%d).tar.gz data/
```

---

## Shutdown and Cleanup

### Graceful Shutdown

```bash
docker compose down
```

This stops containers gracefully (10-second timeout). If a job is running, it will attempt to finish.

To force shutdown:
```bash
docker compose kill
```

### Clean Up Everything

```bash
docker compose down -v
rm -rf data/
make up
```

This removes containers, volumes, and data. **Use with caution — data loss is permanent.**

---

## Support & Escalation

If issues persist:
1. Check logs: `docker compose logs`
2. Search this document for your symptom
3. Open an issue in the `orchestrator` repo with:
   - Error message
   - Steps to reproduce
   - Output of `docker compose ps` and `docker compose logs`
   - `.env` (token redacted)

---

## Next Steps

- Frontend integration: see [API.md#frontend-integration-notes](API.md#frontend-integration-notes)
- Architecture deep-dive: see [ARCHITECTURE.md](ARCHITECTURE.md)
- Development: see [CONTRIBUTING.md](CONTRIBUTING.md)
