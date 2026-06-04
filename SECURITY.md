# Security Policy

## Supported Versions

Only the latest commit on `main` is supported.
There are no versioned releases with independent security support windows.

## Reporting a Vulnerability

Do NOT open public issues for security reports.

Please report security vulnerabilities via **GitHub Security Advisories**:
1. Go to the repo → **Security** tab → **Advisories** → **Report a vulnerability**.
2. Include: affected component, reproduction steps, potential impact.
3. Expected first response within **7 days**.
4. We follow a **90-day disclosure window** before public disclosure.

## Threat Model (single-user, single-machine)

The orchestrator is designed exclusively for a **single authenticated user on a
single local machine** (or a trusted LAN with `ALLOW_LAN=true`).
It is **not** designed for multi-user, Internet-exposed, or production
deployment scenarios.

Key controls:

- **Network**: binds `127.0.0.1` by default; `ALLOW_LAN=true` is an explicit
  opt-in and should be paired with token rotation.
- **Auth**: all mutating endpoints and SSE streams require a `Bearer` token
  validated with `secrets.compare_digest`. `API_TOKEN` is mandatory at startup
  (an empty token causes the process to refuse to start).
- **Subprocess env isolation**: Hydra subprocesses receive only a whitelisted
  set of environment variables — never the full `os.environ`. This prevents
  exfiltration of `API_TOKEN`, `DATABASE_URL`, or other secrets via
  `${oc.env:...}` OmegaConf resolvers in `hydra_overrides`.
- **Override validation**: `hydra_overrides` entries are validated against a
  strict character allowlist and a dangerous-resolver blocklist on every request.
- **SSE log sanitization**: stdout/stderr lines pass through a multi-pattern
  secret sanitizer (Bearer tokens, HF/WANDB/MLflow creds, HuggingFace tokens,
  GitHub PATs, OpenAI keys, JWTs, AWS keys) before delivery to the client.
- **Checkpoint path confinement**: `EvalRequest.checkpoint_path` is confined
  to `lerobot_repo/checkpoints/` via `Path.resolve()` + `is_relative_to()`.
- **Dataset root confinement**: YAML-sourced `root:` paths in dataset configs
  are constrained to `lerobot_repo/data/` to prevent disk-traversal via
  malicious YAML files.
- **Docker hardening**: all services run as uid 1000 (non-root), with
  `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `read_only: true`
  (plus `tmpfs` for `/tmp`). Sibling repo mounts are read-only where possible.

## Explicitly Out of Scope

- Production multi-user or Internet-exposed deployments.
- Runtime security of the lerobot/ml-core CLIs invoked by the worker.
- MLflow tracking server hardening (upstream concern).
- Redis AUTH (container is on the private compose network, not host-exposed).
- Hardware safety of any robot driven via this orchestrator (covered by
  `robotics-platform-template` HAL audits).
- Tauri / launcher-based deployment (to be audited when implemented, ADR-002).
