# API Reference — orchestrator

> Complete endpoint reference for the local HTTP orchestrator.
> All endpoints require `Authorization: Bearer $TOKEN` header (from `.env API_TOKEN`).

---

## System Endpoints

### Health Check

```
GET /api/v1/health
```

Check if the API is running and all services (Redis, SQLite, MLflow) are healthy.

**Response (200 OK):**
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

**Status Codes:**
- `200` — All services healthy
- `503` — One or more services down

**Example:**
```bash
TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/health
```

---

### Version

```
GET /api/v1/version
```

Get orchestrator version and build info.

**Response (200 OK):**
```json
{
  "version": "0.1.0",
  "build_date": "2026-05-25",
  "python_version": "3.11.0"
}
```

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/version
```

---

## Job Submission Endpoints

### Submit Collect Job

```
POST /api/v1/runs/collect
```

Enqueue a data collection job.

**Request Body:**
```json
{
  "episodes": 5,
  "env": "cube_reach_v1",
  "policy_type": "scripted",
  "push_to_hub": false,
  "hydra_overrides": ["dataset.repo_id=myuser/my-dataset"]
}
```

**Fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `episodes` | int | ✓ | — | Number of episodes to collect |
| `env` | str | | "cube_reach_v1" | Environment ID (from `/api/v1/configs/envs`) |
| `policy_type` | str | | "scripted" | Policy type: "scripted", "teleop" (from `/api/v1/configs/policies`) |
| `push_to_hub` | bool | | false | Push dataset to Hugging Face Hub after collection |
| `hydra_overrides` | list[str] | | [] | Additional Hydra config overrides (e.g., `["dataset.repo_id=..."]`) |

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "collect",
  "status": "queued",
  "created_at": "2026-05-25T12:34:56Z",
  "params": {
    "episodes": 5,
    "env": "cube_reach_v1",
    "policy_type": "scripted"
  }
}
```

**Status Codes:**
- `202` — Job enqueued successfully
- `400` — Invalid parameters
- `401` — Missing or invalid authorization
- `503` — Queue service unavailable

**Example:**
```bash
TOKEN=$(grep ^API_TOKEN= .env | cut -d= -f2)
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"episodes": 5, "env": "cube_reach_v1", "policy_type": "scripted"}' \
  http://127.0.0.1:8000/api/v1/runs/collect
```

---

### Submit Train Job

```
POST /api/v1/runs/train
```

Enqueue a model training job.

**Request Body:**
```json
{
  "env": "cube_reach_v1",
  "policy": "act",
  "total_steps": 100000,
  "profile": "default",
  "hf_repo_id": "myuser/my-checkpoint",
  "hydra_overrides": ["dataset.filter=success_only"]
}
```

**Fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `env` | str | | "cube_reach_v1" | Environment ID |
| `policy` | str | ✓ | — | Policy type: "act" or "diffusion" |
| `total_steps` | int | ✓ | — | Training steps |
| `profile` | str | | "default" | Training profile (from `/api/v1/configs/profiles`) |
| `hf_repo_id` | str | | | Hugging Face Hub repo for pushing checkpoints (optional) |
| `hydra_overrides` | list[str] | | [] | Additional Hydra overrides |

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "type": "train",
  "status": "queued",
  "created_at": "2026-05-25T12:34:56Z",
  "params": {
    "env": "cube_reach_v1",
    "policy": "act",
    "total_steps": 100000
  }
}
```

**Status Codes:**
- `202` — Job enqueued
- `400` — Invalid parameters (e.g., policy not in ["act", "diffusion"])
- `401` — Missing or invalid authorization

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"policy": "act", "total_steps": 10000}' \
  http://127.0.0.1:8000/api/v1/runs/train
```

---

### Submit Eval Job

```
POST /api/v1/runs/eval
```

Enqueue a model evaluation job.

**Request Body:**
```json
{
  "checkpoint_path": "checkpoints/checkpoint_00100000.ckpt",
  "n_episodes": 10,
  "visualize": false,
  "hydra_overrides": []
}
```

**Fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `checkpoint_path` | str | ✓ | — | Relative or absolute path to the checkpoint |
| `n_episodes` | int | ✓ | — | Number of episodes to evaluate |
| `visualize` | bool | | false | Record video (requires FFmpeg) |
| `hydra_overrides` | list[str] | | [] | Additional Hydra overrides |

**Response (202 Accepted):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "type": "eval",
  "status": "queued",
  "created_at": "2026-05-25T12:34:56Z",
  "params": {
    "checkpoint_path": "checkpoints/checkpoint_00100000.ckpt",
    "n_episodes": 10,
    "visualize": false
  }
}
```

**Status Codes:**
- `202` — Job enqueued
- `400` — Invalid parameters or checkpoint not found
- `401` — Missing or invalid authorization

**Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"checkpoint_path": "checkpoints/checkpoint_00100000.ckpt", "n_episodes": 10}' \
  http://127.0.0.1:8000/api/v1/runs/eval
```

---

## Job Status Endpoints

### List Jobs

```
GET /api/v1/runs?status=&job_type=&limit=20&offset=0
```

List all jobs, optionally filtered by status and type.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | str | | Filter by status: "queued", "running", "completed", "failed", "cancelled" |
| `job_type` | str | | Filter by type: "collect", "train", "eval" |
| `limit` | int | 20 | Number of results per page |
| `offset` | int | 0 | Offset for pagination |

**Response (200 OK):**
```json
{
  "jobs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "collect",
      "status": "completed",
      "created_at": "2026-05-25T12:34:56Z",
      "started_at": "2026-05-25T12:35:00Z",
      "completed_at": "2026-05-25T12:45:30Z",
      "exit_code": 0,
      "params": {
        "episodes": 5,
        "env": "cube_reach_v1"
      }
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

**Status Codes:**
- `200` — Success
- `401` — Unauthorized

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     'http://127.0.0.1:8000/api/v1/runs?status=completed&limit=10'
```

---

### Get Job Details

```
GET /api/v1/runs/{id}
```

Fetch detailed status and metadata for a specific job.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | str | Job ID (UUID) |

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "type": "collect",
  "status": "running",
  "created_at": "2026-05-25T12:34:56Z",
  "started_at": "2026-05-25T12:35:00Z",
  "completed_at": null,
  "exit_code": null,
  "params": {
    "episodes": 5,
    "env": "cube_reach_v1",
    "policy_type": "scripted"
  },
  "output": {
    "dataset_path": "data/datasets/cube_reach_v1_2026_05_25.hf",
    "log_urls": {
      "stdout": "data/logs/550e8400-e29b-41d4-a716-446655440000.stdout",
      "stderr": "data/logs/550e8400-e29b-41d4-a716-446655440000.stderr"
    }
  }
}
```

**Status Codes:**
- `200` — Success
- `401` — Unauthorized
- `404` — Job not found

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000
```

---

### Cancel Job

```
DELETE /api/v1/runs/{id}
```

Cancel a running or queued job. (Cannot cancel completed/failed jobs.)

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | str | Job ID |

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled"
}
```

**Status Codes:**
- `200` — Job cancelled
- `400` — Job already completed/failed
- `401` — Unauthorized
- `404` — Job not found

**Example:**
```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000
```

---

## Real-Time Streaming Endpoints (SSE)

### Stream Job Logs

```
GET /api/v1/runs/{id}/logs
```

Server-Sent Events stream for real-time stdout/stderr logs.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | str | Job ID |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `follow` | bool | true | Keep connection open until job completes |
| `tail` | int | 0 | Number of historical lines to send before new ones (0 = no history) |

**Event Format:**
```
data: {"ts": "2026-05-25T12:34:56Z", "stream": "stdout", "line": "..."}
```

**Fields:**
- `ts` — ISO8601 timestamp
- `stream` — "stdout" or "stderr"
- `line` — Log line (without newline)

**Status Codes:**
- `200` — Stream active
- `401` — Unauthorized
- `404` — Job not found

**Example:**
```bash
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/logs
```

**JavaScript/Fetch Example:**
```javascript
const eventSource = new EventSource(
  'http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/logs',
  {
    headers: { 'Authorization': `Bearer ${TOKEN}` }
  }
);

eventSource.onmessage = (event) => {
  const log = JSON.parse(event.data);
  console.log(`[${log.stream}] ${log.line}`);
};

eventSource.onerror = () => {
  console.log('Stream closed');
  eventSource.close();
};
```

---

### Stream Job Metrics

```
GET /api/v1/runs/{id}/metrics
```

Server-Sent Events stream for real-time training metrics (from MLflow).

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | str | Job ID (must be a train job) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `follow` | bool | true | Keep connection open until job completes |
| `tail` | int | 0 | Historical metric points to send |

**Event Format:**
```
data: {"ts": "2026-05-25T12:34:56Z", "step": 1000, "metric": "loss", "value": 0.123}
```

**Fields:**
- `ts` — Timestamp when metric was recorded
- `step` — Training step number
- `metric` — Metric name (e.g., "loss", "accuracy")
- `value` — Metric value (float)

**Status Codes:**
- `200` — Stream active
- `401` — Unauthorized
- `404` — Job not found

**Example:**
```bash
curl -N \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440001/metrics
```

**JavaScript Example:**
```javascript
const eventSource = new EventSource(
  'http://127.0.0.1:8000/api/v1/runs/550e8400-e29b-41d4-a716-446655440001/metrics',
  {
    headers: { 'Authorization': `Bearer ${TOKEN}` }
  }
);

eventSource.onmessage = (event) => {
  const metric = JSON.parse(event.data);
  console.log(`Step ${metric.step} — ${metric.metric}: ${metric.value}`);
};
```

---

## Configuration Introspection Endpoints

### Get Available Environments

```
GET /api/v1/configs/envs
```

List available environment configurations (read from Hydra YAML configs).

**Response (200 OK):**
```json
{
  "envs": [
    {
      "name": "cube_reach_v1",
      "description": "3D cube reach task with Mujoco"
    },
    {
      "name": "pusht_image",
      "description": "PushT environment from LeRobot"
    }
  ]
}
```

**Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://127.0.0.1:8000/api/v1/configs/envs
```

---

### Get Available Policies

```
GET /api/v1/configs/policies
```

List available policy types.

**Response (200 OK):**
```json
{
  "policies": [
    {
      "name": "act",
      "description": "Action Chunking with Transformers"
    },
    {
      "name": "diffusion",
      "description": "Diffusion Policy"
    }
  ]
}
```

---

### Get Available Training Profiles

```
GET /api/v1/configs/profiles
```

List available training profiles (hyperparameter presets).

**Response (200 OK):**
```json
{
  "profiles": [
    {
      "name": "default",
      "batch_size": 32,
      "learning_rate": 0.001
    },
    {
      "name": "kaggle",
      "batch_size": 64,
      "learning_rate": 0.0001
    }
  ]
}
```

---

### Get Available Datasets

```
GET /api/v1/configs/datasets
```

List available datasets (from `configs/dataset/*.yaml`).

**Response (200 OK):**
```json
{
  "datasets": [
    {
      "name": "multitask",
      "description": "Multi-task balanced dataset"
    },
    {
      "name": "cube_reach_v1",
      "description": "Single-task cube reach"
    }
  ]
}
```

---

### Get Collection Config

```
GET /api/v1/configs/collect
```

Get the full collect.py configuration schema (for UI form generation).

**Response (200 OK):**
```json
{
  "schema": {
    "env": { "type": "enum", "options": ["cube_reach_v1", "pusht_image"] },
    "episodes": { "type": "int", "default": 10, "min": 1 },
    "policy_type": { "type": "enum", "options": ["scripted", "teleop"] }
  }
}
```

---

### Get Eval Config

```
GET /api/v1/configs/eval
```

Get the eval.py configuration schema.

**Response (200 OK):**
```json
{
  "schema": {
    "checkpoint_path": { "type": "str" },
    "n_episodes": { "type": "int", "default": 10, "min": 1 },
    "visualize": { "type": "bool", "default": false }
  }
}
```

---

## Artifact Listing Endpoints

### List Checkpoints

```
GET /api/v1/artifacts/checkpoints
```

List trained model checkpoints.

**Response (200 OK):**
```json
{
  "checkpoints": [
    {
      "path": "checkpoints/checkpoint_00010000.ckpt",
      "size_mb": 145.2,
      "created_at": "2026-05-25T12:34:56Z",
      "policy": "act",
      "env": "cube_reach_v1",
      "steps": 10000
    }
  ]
}
```

---

### List Eval Reports

```
GET /api/v1/artifacts/eval-reports
```

List evaluation reports (with metrics and optional videos).

**Response (200 OK):**
```json
{
  "eval_reports": [
    {
      "path": "eval_reports/eval_2026_05_25_123456.json",
      "created_at": "2026-05-25T12:34:56Z",
      "checkpoint": "checkpoint_00010000.ckpt",
      "n_episodes": 10,
      "mean_success_rate": 0.8,
      "has_video": false
    }
  ]
}
```

---

### List Datasets

```
GET /api/v1/artifacts/datasets
```

List collected datasets.

**Response (200 OK):**
```json
{
  "datasets": [
    {
      "path": "data/datasets/cube_reach_v1_2026_05_25.hf",
      "size_mb": 512,
      "created_at": "2026-05-25T12:45:30Z",
      "n_episodes": 5,
      "env": "cube_reach_v1",
      "hf_repo_id": null
    }
  ]
}
```

---

## OpenAPI Documentation

### Swagger UI

```
GET /api/docs
```

Interactive Swagger UI for exploring and testing endpoints.

---

### OpenAPI Schema

```
GET /api/openapi.json
```

Machine-readable OpenAPI 3.0.0 schema (for code generation, IDE integration, etc.).

---

## Frontend Integration Notes

### CORS Posture

**Default (localhost):**
- CORS is disabled
- Frontend must run on `http://127.0.0.1` (same origin)
- Or use a reverse proxy (nginx/caddy) on the same domain

**LAN Access (if `ALLOW_LAN=true`):**
- CORS headers allow origins matching a whitelist (set in `.env`)
- Recommend: reverse proxy with TLS termination and CORS headers

### EventSource (SSE) Requirements

**Fetch API does NOT support custom headers with EventSource:**
```javascript
// ❌ This won't work — EventSource ignores fetch headers
const es = new EventSource('/api/v1/runs/123/logs', {
  headers: { 'Authorization': `Bearer ${TOKEN}` }
});
```

**Workaround 1: Use a Proxy**
Set up a lightweight nginx/caddy proxy on localhost that injects the token:
```nginx
location /api/v1/runs {
  proxy_pass http://orchestrator:8000;
  proxy_set_header Authorization "Bearer $token_from_env";
  proxy_buffering off;  # important for SSE
}
```

**Workaround 2: Query Parameter Token** (less secure)
Pass token in URL:
```javascript
const es = new EventSource(
  `/api/v1/runs/123/logs?token=${TOKEN}`
);
```

Then parse `?token=` on the server side (only safe for localhost).

**Workaround 3: Custom Fetch Wrapper** (best for SPA)
Use `fetch` to simulate SSE with manual line buffering:
```javascript
async function* fetchSSE(url, token) {
  const response = await fetch(url, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
}

// Usage
for await (const event of fetchSSE('/api/v1/runs/123/logs', TOKEN)) {
  console.log(event);
}
```

### Error Handling

**401 Unauthorized:**
- Token missing or invalid
- Redirect user to login / token refresh

**404 Not Found:**
- Job ID does not exist
- Show error message

**503 Service Unavailable:**
- Redis/SQLite/API down
- Retry with exponential backoff

---

## Rate Limiting

No rate limiting in v0.1. Single user, local-only.

---

## Pagination

Endpoints that return lists (e.g., `/api/v1/runs`) support `limit` and `offset` query parameters for pagination. Default: `limit=20`, `offset=0`.

---

## Next Steps

See [RUNBOOK.md](RUNBOOK.md) for operational instructions and troubleshooting.
