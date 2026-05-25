# Contributing to orchestrator

> Guidelines for developing, testing, and submitting changes to the orchestrator.

---

## Branching & Commits

### Branch Naming

Use feature branches even for solo work. Naming convention:

```
feat/<short-description>    # New feature
fix/<short-description>     # Bug fix
docs/<short-description>    # Documentation
chore/<short-description>   # Maintenance, dependencies
refactor/<short-description> # Code restructuring
```

**Examples:**
- `feat/sse-metrics-streaming`
- `fix/redis-connection-timeout`
- `docs/runbook-wsl2-notes`

### Commit Messages

Use Conventional Commits format:

```
feat: add SSE metrics streaming for training jobs

- Implement watchdog observer on MLflow metrics directory
- Publish to Redis pubsub channel mlflow:{run_id}
- Add GET /api/v1/runs/{id}/metrics SSE endpoint

Closes #42
```

**Format:**
```
<type>: <subject>

<body (optional)>

<footer (optional)>
```

**Types:**
- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation
- `chore:` — Dependencies, tooling
- `refactor:` — Code restructuring (no behavior change)
- `test:` — Test additions / fixes
- `perf:` — Performance improvement

**Rules:**
- Subject line ≤ 50 characters
- Capitalize subject
- No period at end of subject
- Use imperative mood: "add" not "added"
- Body explains "why", not "what"

### PR Workflow

Even for solo work:

1. Create feature branch: `git checkout -b feat/my-feature`
2. Make changes, commit locally
3. Push to origin: `git push -u origin feat/my-feature`
4. Open a Pull Request (GitHub)
5. Run CI checks (see below)
6. Merge when green (squash, delete branch)

---

## Required Checks

### 1. Lint

All Python code must pass `ruff` check:

```bash
make lint
```

This runs:
- `ruff check .` — syntax, import order, unused variables
- `ruff format .` — auto-format code style

**Auto-fix:**
```bash
make format
```

### 2. Type Checking

All Python code must pass `mypy` (strict mode):

```bash
make typecheck
```

**Strict rules:**
- Every function parameter must have a type annotation
- Every function must have a return type
- No `Any` unless absolutely necessary (and justified in a comment)
- No untyped library imports (use type stubs or `# type: ignore`)

**Example:**
```python
# ✓ Good
def submit_job(job_type: str, params: dict[str, Any]) -> Job:
    ...

# ✗ Bad (missing types)
def submit_job(job_type, params):
    ...
```

### 3. Tests

All new code must have tests:

```bash
make test
```

This runs `pytest -m "not gpu"` (CPU tests only).

**Test Markers:**
- `@pytest.mark.unit` — Fast, no I/O (~1ms each)
- `@pytest.mark.integration` — Database, external services (~100ms each)
- `@pytest.mark.gpu` — GPU-only tests (run with `pytest -m gpu` on GPU machine)

**Example:**
```python
import pytest
from orchestrator.api.routes import submit_collect_job

@pytest.mark.unit
def test_submit_collect_job_valid():
    job = submit_collect_job(episodes=5, env="cube_reach_v1")
    assert job.status == "queued"

@pytest.mark.integration
def test_submit_collect_job_enqueues_to_redis(redis_client):
    job = submit_collect_job(episodes=5)
    queue_size = redis_client.llen("rq:queue:default")
    assert queue_size == 1
```

### 4. Coverage

Minimum coverage thresholds:
- **Global:** 70%
- **`src/orchestrator/api/`:** 90%
- **`src/orchestrator/db/`:** 90%
- **`src/orchestrator/core/`:** 85%

Check coverage:
```bash
make test --cov=src/orchestrator --cov-report=html
open htmlcov/index.html
```

### 5. SPDX Headers

Every `.py` file must start with an SPDX header:

```python
# SPDX-License-Identifier: Apache-2.0

"""Module docstring."""
```

**Why:**
- Apache-2.0 license compliance
- Automated license scanning
- Prevents accidental proprietary code

**Placement:**
- Line 1–2: SPDX header + blank line
- Line 3+: Module docstring and code

### 6. Logging

Replace all `print()` with `loguru`:

```python
from loguru import logger

# ✓ Good
logger.info(f"Job {job_id} started")
logger.error(f"Failed to queue job: {error}", exc_info=True)

# ✗ Bad
print(f"Job {job_id} started")
print(f"Error: {error}")
```

**Log Levels:**
- `logger.debug()` — Detailed debugging info (disabled by default)
- `logger.info()` — General informational messages (default)
- `logger.warning()` — Warning messages
- `logger.error()` — Error messages
- `logger.critical()` — Critical failures

### 7. Environment Access

Never access `os.environ` directly. Use `Settings`:

```python
from orchestrator.core.config import Settings

# ✓ Good
settings = Settings()
api_token = settings.API_TOKEN

# ✗ Bad
import os
api_token = os.environ.get("API_TOKEN")
```

**Why:**
- Centralized validation
- Type safety
- Easy testing (mock Settings)

### 8. Sibling Repo Boundaries

**Critical Rules:**

1. **Never import from sibling repos in production code**
   ```python
   # ✗ Bad
   from lerobot.scripts.add_robot import create_robot
   from mlcore.training import Trainer
   
   # ✓ Good (subprocess invocation only)
   subprocess.run(["python", "-m", "lerobot.train", ...])
   ```

2. **Never reference `_private/my-robot-stack` anywhere**
   ```python
   # ✗ Bad — never mention private repo
   # TODO: integrate with my-robot-stack adapter
   
   # ✓ Good
   # TODO: add support for custom robot adapters (future)
   ```

3. **Never modify sibling repos**
   - No patching, no monkey-patching
   - If a sibling needs a feature, ask the user to file an issue there

4. **Documentation points elsewhere**
   - "See `lerobot-playground-portfolio/README.md` for collection config"
   - Never duplicate sibling docs in this repo

---

## Code Style

### Naming Conventions

- **Classes:** `PascalCase` (e.g., `JobHandler`, `MLflowBridge`)
- **Functions:** `snake_case` (e.g., `submit_job`, `stream_logs`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`, `QUEUE_NAME`)
- **Private:** prefix with `_` (e.g., `_internal_helper`)

### Type Hints

Always use type hints:

```python
# ✓ Good
def enqueue_job(job_id: str, params: dict[str, Any]) -> Job:
    ...

def get_all_jobs(status: str | None = None) -> list[Job]:
    ...

# ✗ Bad
def enqueue_job(job_id, params):
    ...
```

### Docstrings

Every public class and function needs a docstring:

```python
def submit_train_job(
    policy: str,
    total_steps: int,
    env: str = "cube_reach_v1"
) -> Job:
    """Submit a training job to the queue.
    
    Args:
        policy: Policy type ("act" or "diffusion")
        total_steps: Number of training steps
        env: Environment name (default: cube_reach_v1)
    
    Returns:
        Job object with id, status, created_at
    
    Raises:
        ValueError: If policy not in ["act", "diffusion"]
        QueueError: If Redis is unreachable
    """
    ...
```

**Format:** Google-style docstrings (Args, Returns, Raises, Examples)

### Import Organization

```python
# Standard library
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Third-party
import redis
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseSettings

# Local
from orchestrator.db.models import Job
from orchestrator.core.config import Settings
from orchestrator.core.logging import setup_logger
```

**Rules:**
- Group by category (stdlib, third-party, local)
- Alphabetical within group
- One import per line (except `from ... import a, b`)

---

## Testing Guidelines

### Test Location

Tests live in `tests/` mirroring `src/` structure:

```
src/orchestrator/api/routes/jobs.py
tests/orchestrator/api/routes/test_jobs.py
```

### Test Structure

```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.mark.unit
def test_submit_job_creates_record():
    """Submitting a job creates a SQLite record."""
    # Arrange
    api_client = create_test_client()
    
    # Act
    response = api_client.post(
        "/api/v1/runs/collect",
        json={"episodes": 5}
    )
    
    # Assert
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    
@pytest.mark.integration
def test_submit_job_enqueues_to_redis(db_session, redis_client):
    """Submitting a job enqueues it to Redis."""
    # Arrange / Act / Assert same pattern
    ...
```

**Pattern:** Arrange → Act → Assert

### Fixtures

Reusable fixtures in `conftest.py`:

```python
# tests/conftest.py
@pytest.fixture
def app():
    """FastAPI test app."""
    from orchestrator.api.main import app
    return app

@pytest.fixture
def client(app):
    """Test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)

@pytest.fixture
def redis_client():
    """Redis test client (connect to test DB)."""
    import redis
    return redis.Redis(host="localhost", port=6379, db=1)
```

### Mocking

Use `unittest.mock` for external dependencies:

```python
@patch("orchestrator.worker.subprocess.run")
def test_worker_spawns_collect_subprocess(mock_run):
    """Worker spawns collect.py subprocess."""
    # Arrange
    mock_run.return_value = MagicMock(returncode=0)
    
    # Act
    handler = JobHandler(job_id="123")
    handler.execute()
    
    # Assert
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert "collect.py" in args[0]
```

---

## API Changes

### Adding a New Endpoint

1. **Define the route in `src/orchestrator/api/routes/`:**
   ```python
   from fastapi import APIRouter
   
   router = APIRouter(prefix="/api/v1", tags=["runs"])
   
   @router.get("/runs/{id}/summary")
   async def get_job_summary(id: str) -> dict[str, Any]:
       """Get a job summary (status + artifact paths)."""
       ...
   ```

2. **Add tests in `tests/orchestrator/api/routes/`:**
   ```python
   @pytest.mark.unit
   def test_get_job_summary_valid(client):
       response = client.get("/api/v1/runs/123/summary")
       assert response.status_code == 200
   ```

3. **Update `docs/API.md`:**
   - Add new section with endpoint, request/response, example curl
   - Include status codes, field descriptions

4. **Update OpenAPI schema** (auto-generated by FastAPI, no manual action needed)

---

## Documentation Changes

### docs/ARCHITECTURE.md

Update if:
- Component responsibilities change
- New modules added
- Data flow changes
- Stack choices change

### docs/API.md

Update if:
- New endpoint added
- Endpoint parameters change
- Response schema changes
- Error handling changes

### docs/RUNBOOK.md

Update if:
- Deployment process changes
- Troubleshooting section needs new entries
- New `make` targets added

### docs/CONTRIBUTING.md

Update if:
- Branching/commit conventions change
- Test requirements change
- Linting/typing rules change

---

## Checklist Before Submitting PR

- [ ] Feature branch created (`feat/*`, `fix/*`, etc.)
- [ ] Commits follow Conventional Commits
- [ ] `make lint` passes (no ruff errors)
- [ ] `make typecheck` passes (no mypy errors)
- [ ] `make test` passes (all tests, ≥70% coverage)
- [ ] New SPDX header on all `.py` files
- [ ] No `print()` — all `logger.*` calls
- [ ] No `os.environ` — all `Settings` access
- [ ] No imports from sibling repos (except subprocess)
- [ ] No mention of `_private/my-robot-stack`
- [ ] New/changed endpoints documented in `docs/API.md`
- [ ] PR title follows `<type>: <subject>` (50 chars max)
- [ ] PR description explains "why" this change

---

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG make up
```

Or in `.env`:
```
LOG_LEVEL=DEBUG
```

### Inspect Database

```bash
sqlite3 data/runs.db
> SELECT id, type, status FROM jobs LIMIT 5;
```

### Inspect Redis

```bash
docker exec orchestrator-redis-1 redis-cli
> LRANGE rq:queue:default 0 -1
> KEYS *
```

### Inspect Container Filesystem

```bash
docker exec -it orchestrator-api-1 bash
root@abc123:/app# ls -la data/logs/
root@abc123:/app# cat data/logs/<job_id>.stdout
```

---

## Performance Considerations

### Job Queuing

- 1 worker process = 1 job at a time (no parallelism for GPU contention)
- Queue depth checked via `redis-cli LLEN rq:queue:default`
- Add monitoring if queue grows > 10 jobs

### Log Streaming

- Watchdog observer scans file system every 1 second
- If log file > 1GB, consider log rotation in worker

### Metrics Streaming

- MLflow writes ~10 files per training run (one per metric per step)
- Watchdog publishes to Redis pubsub (buffer 5 seconds, send batch)
- For 1M+ metric points, consider archiving old runs

### Database Queries

- Index on `jobs.id` (primary key, auto-indexed)
- Index on `jobs.status` (add if filtering by status is slow)
- Query `jobs` table, not metrics (metrics are in MLflow)

---

## Security Considerations

### API Token

- Never log the token
- Rotate monthly via `make token`
- Store in `.env` (gitignored)

### Subprocess Invocation

- Never pass untrusted Hydra overrides directly to shell
- Validate Hydra overrides before passing to subprocess
- Use `subprocess.run(..., shell=False, ...)` (no shell injection)

### CORS

- Disabled by default (localhost only)
- LAN mode requires reverse proxy with HTTPS (use nginx/caddy)
- Never enable CORS to `*` (world-accessible)

---

## Continuous Integration (GitHub Actions)

Workflows in `.github/workflows/`:

1. **Lint + Type Check + Test** — on every push
   - `make lint`
   - `make typecheck`
   - `make test`

2. **Coverage Report** — required ≥70% global, ≥90% on api/ and db/

3. **Security Scan** — check for hardcoded secrets, dependency vulnerabilities

All must pass before merge.

---

## Getting Help

- Architecture questions? → See [ARCHITECTURE.md](ARCHITECTURE.md)
- API questions? → See [API.md](API.md)
- Operations questions? → See [RUNBOOK.md](RUNBOOK.md)
- Type errors? → `mypy` error message usually explains it
- Test failures? → Check logs, try `make test -v` for verbose output
- Still stuck? → Open an issue with error message and reproduction steps

---

## Code Review Checklist (for reviewers)

- [ ] Commits follow Conventional Commits
- [ ] Code passes all CI checks
- [ ] No forbidden imports (sibling repos, `_private`)
- [ ] No `print()`, all logging via `logger`
- [ ] SPDX headers present
- [ ] Type hints complete (no `Any` without justification)
- [ ] Tests cover new code (≥70% overall, ≥90% api/db)
- [ ] Documentation updated (API.md, ARCHITECTURE.md, etc.)
- [ ] No secrets or credentials in code
- [ ] Branch naming follows convention

---

## Thank You!

Contributing to the orchestrator helps the entire robotics workspace. Your effort is appreciated!
