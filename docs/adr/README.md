<!--
SPDX-FileCopyrightText: 2026 Arthur Mouraud
SPDX-License-Identifier: Apache-2.0
-->

# Architecture Decision Records (ADR) — orchestrator

Cross-module architectural decisions that affect this repo. Each ADR is a short, immutable note: once accepted, it is amended only via a successor ADR.

## When to write an ADR
- A decision changes the public API contract (endpoints, request/response shape, auth model).
- A decision changes how jobs are queued, executed, or persisted (RQ ↔ subprocess invariants).
- A decision changes the boundary with sibling repos (we still must NOT import them).
- A trade-off has been made between two viable alternatives.

If the decision is local and reversible, a code comment is enough.

## Format

`ADR-NNN-short-kebab-title.md`:

```markdown
# ADR-NNN — Title

- **Status**: Proposed | Accepted YYYY-MM-DD | Superseded by ADR-MMM | Implemented YYYY-MM-DD
- **Deciders**: Arthur Mouraud
- **Scope**: <which repos / modules>

## Context
## Decision
## Alternatives considered
## Consequences
```

## Related ADRs in sibling repos

- [robotics-platform-template/docs/adr/ADR-001](../../../robotics-platform-template/docs/adr/ADR-001-unify-on-envadapter.md) — Unify on EnvAdapter. Orchestrator only invokes CLIs via subprocess; no direct impact, but introspection (`/api/v1/configs/*`) should reflect the canonical vocabulary.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-002](ADR-002-wrapping-strategy.md) | Orchestrator Wrapping Strategy (launcher) | Accepted 2026-06-03 |
| [ADR-003](ADR-003-frontend-strategy.md) | Orchestrator Frontend Strategy | Accepted 2026-06-04 |
| [ADR-004](ADR-004-robots-endpoint-rw-mount.md) | `/api/v1/robots`: scoped RW mount for `robot_specs/` | Implemented 2026-06-10 |
