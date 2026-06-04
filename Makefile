.PHONY: install token up up-gpu down logs ps test lint typecheck migrate revision clean help frontend-install frontend-dev frontend-build frontend-codegen

PY := uv run python
COMPOSE := docker compose -f docker/docker-compose.yml
COMPOSE_GPU := docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml

help:
	@echo "Common targets:"
	@echo "  make install    uv sync (dev extras)"
	@echo "  make token      generate a fresh API_TOKEN and write it to .env"
	@echo "  make up         docker compose up (api + worker + redis + mlflow)"
	@echo "  make up-gpu     same with GPU runtime"
	@echo "  make down       stop and remove containers"
	@echo "  make logs       tail compose logs"
	@echo "  make migrate    alembic upgrade head"
	@echo "  make test       pytest (unit + integration, skip gpu/e2e)"
	@echo "  make lint       ruff check + format check"
	@echo "  make typecheck  mypy strict"

install:
	uv sync --extra dev
	pre-commit install

token:
	@$(PY) -c "import secrets, pathlib, os, stat; \
p = pathlib.Path('.env'); \
src = p.read_text() if p.exists() else pathlib.Path('.env.example').read_text(); \
tok = secrets.token_urlsafe(32); \
lines = []; \
done = False; \
import re; \
for line in src.splitlines():\
    line2 = re.sub(r'^API_TOKEN=.*', f'API_TOKEN={tok}', line); \
    lines.append(line2); \
    done = done or line2.startswith('API_TOKEN='); \
if not done: lines.append(f'API_TOKEN={tok}'); \
p.write_text('\n'.join(lines) + '\n'); \
try: os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)\
except OSError: pass; \
print(f'API_TOKEN written to .env ({len(tok)} chars, mode 0o600).')"

up:
	$(COMPOSE) up -d

up-gpu:
	$(COMPOSE_GPU) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

migrate:
	uv run alembic -c src/orchestrator/db/alembic.ini upgrade head

revision:
	@test -n "$(m)" || (echo "Usage: make revision m=\"message\""; exit 1)
	uv run alembic -c src/orchestrator/db/alembic.ini revision --autogenerate -m "$(m)"

test:
	uv run pytest -m "not gpu and not e2e"

test-e2e:
	uv run pytest -m e2e

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

frontend-install:
	cd frontend && npm ci

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-codegen:
	cd frontend && npm run codegen
