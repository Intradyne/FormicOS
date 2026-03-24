# Contributing to FormicOS

Thank you for your interest in contributing to FormicOS. This guide covers
everything you need to get started, from environment setup through
submitting a pull request.

**Before contributing**, please read:

- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community expectations
- [GOVERNANCE.md](GOVERNANCE.md) — decision-making process and CLA requirements
- [SECURITY.md](SECURITY.md) — how to report vulnerabilities (do not open
  public issues for security bugs)

## Contribution Flow

1. Check existing issues or open a new one describing the change
2. Fork the repository and create a feature branch
3. Sign the CLA when prompted (see [GOVERNANCE.md](GOVERNANCE.md))
4. Make your changes following the architecture rules below
5. Run the full CI pipeline locally (lint, typecheck, layer-check, tests,
   frontend build)
6. Submit a pull request using the PR template
7. Address review feedback from maintainers

### Good First Issues

Look for issues labeled `good-first-issue` for tasks suitable for new
contributors. These are scoped to avoid touching architectural seams.

## Environment Setup

### Backend

```bash
# Python 3.12+ required
uv sync --dev
```

This installs all runtime and development dependencies including pytest,
pyright, and ruff.

### Frontend

```bash
# Node 22+ required
cd frontend
npm ci
```

### Running Locally Without Docker

```bash
# Terminal 1: backend
python -m formicos

# Terminal 2: frontend dev server (optional -- for HMR during UI work)
cd frontend && npm run dev
```

The backend serves the built frontend from `frontend/dist/` at port 8080. The
dev server proxies to the backend for WebSocket connections.

You'll need a configured LLM path: local llama.cpp / OpenAI-compatible
inference, or cloud credentials such as `ANTHROPIC_API_KEY` / `GEMINI_API_KEY`
in `.env`.

### Docker Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full Docker Compose
deployment guide, including GPU setup, persistence rules, and security posture.

## Running Tests

```bash
# Full CI pipeline (run all of these before submitting)
uv run ruff check src/
uv run pyright src/
python scripts/lint_imports.py
python -m pytest -q

# Or as one command
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && python -m pytest -q

# Frontend build check
cd frontend && npm run build
```

### Browser Smoke Tests

The browser smoke tests use Playwright and verify core operator-facing behavior.

```bash
# Prerequisites: the backend must be running (python -m formicos)
# Install Playwright browsers (first time only)
cd frontend && npx playwright install chromium

# Run smoke tests
cd frontend && npm run smoke
```

The smoke spec lives at `tests/browser/smoke.spec.ts` (repo root). The
`npm run smoke` script in `frontend/package.json` resolves the relative
path automatically.

The test suite includes:
- **Unit tests** for core types, events, adapters, engine, and surface modules
- **Feature tests** (pytest-bdd) for the executable specifications under `docs/specs/`
- **Contract parity tests** verifying Python and TypeScript type alignment
- **Layer boundary test** (AST-based import analysis)

## Working Style

The most successful contributions to FormicOS are:

- focused on one concern at a time
- grounded in the current code, tests, and documented contracts
- accompanied by the tests and docs needed to explain the change
- explicit about any architectural or protocol implications

When possible:

- keep refactors separate from feature changes
- avoid mixing unrelated fixes into the same PR
- update affected docs when user-visible behavior changes
- call out any follow-up work that remains

## Architecture Rules

Read these before making changes:

1. **4-layer dependency rule.** Core imports nothing. Engine imports only Core.
   Adapters import only Core. Surface imports all. `scripts/lint_imports.py`
   enforces this via AST analysis. Backward imports fail the build.

2. **Event sourcing.** Every state change is an event. No shadow databases,
   no second stores, no CRUD updates. State is derived by replaying events
   into projections. See [ADR-001](docs/decisions/001-event-sourcing.md).

3. **Pydantic v2 only.** All serialized types use `pydantic.BaseModel`. No
   msgspec, no dataclasses for events. See [ADR-002](docs/decisions/002-pydantic-only.md).

4. **Closed event union.** The event types in `core/events.py` form a closed
   union. Adding a new event type requires maintainer approval because it
   extends every consumer and adapter. See the process below.

5. **20K LOC soft ceiling** on `core/` + `engine/` + `adapters/` + `surface/`
   combined. Exceeding it requires justification; it is guidance, not a hard CI gate.

6. **No print() statements.** Use `structlog` for all logging.

7. **Frozen contracts.** Files in `docs/contracts/` are the integration seams.
   Do not modify them without maintainer approval. Code against them.

## How to Add a New Event Type

This is intentionally difficult because it affects every layer:

1. **Get maintainer approval.** Event types are a closed union and affect every
   consumer, projection, and contract mirror.
2. Add the event class to `src/formicos/core/events.py` extending `EventEnvelope`.
3. Add it to the `FormicOSEvent` union type and `__all__`.
4. Update `docs/contracts/events.py` (the frozen contract mirror).
5. Add TypeScript mirror to `docs/contracts/types.ts` and `frontend/src/types.ts`.
6. Add a handler to `surface/projections.py` `_HANDLERS` dict.
7. Add serialization to `surface/view_state.py` if it affects the browser or
   API snapshot shape.
8. Write a `.feature` scenario in `docs/specs/` that exercises the event.
9. Run the full CI pipeline. The contract parity test will catch mismatches.

## How to Add a New MCP Tool

1. Add the tool function in `src/formicos/surface/mcp_server.py` using the
   `@mcp.tool()` decorator.
2. If the tool mutates state, route it through `handle_command()` in
   `surface/commands.py` so it emits proper events.
3. Add the corresponding WebSocket command type to `docs/contracts/types.ts`
   if it should be callable from the browser UI.
4. Update the protocol status tool count in `surface/view_state.py`.
5. Write a feature scenario exercising the tool.

## How to Add a New Frontend Component

1. Create `frontend/src/components/your-component.ts`.
2. Use Lit Web Components (`LitElement`, `html`, `css`).
3. Import shared styles from `../styles/shared.js`.
4. Keep components under 200 LOC (soft limit; the app shell is an exception).
5. Import the component in the parent that uses it.
6. Types go in `frontend/src/types.ts`.
7. Run `cd frontend && npm run build` to verify.

## Code Style

- **Python:** ruff (rules: E, F, W, I, UP, B, SIM, TCH), line length 100
- **Python typing:** pyright strict mode, `from __future__ import annotations`
- **Logging:** structlog with descriptive event names (`module.action`)
- **Frontend:** TypeScript, Lit decorators (`@customElement`, `@state`, `@property`)
- **Serialization:** Pydantic v2 `BaseModel` with `ConfigDict(frozen=True)` for events

## Decision Records

Before making an architectural choice, check `docs/decisions/` for existing ADRs:

| ADR | Decision |
|-----|----------|
| [001](docs/decisions/001-event-sourcing.md) | Event sourcing as sole persistence |
| [002](docs/decisions/002-pydantic-only.md) | Pydantic v2 as sole serialization |
| [003](docs/decisions/003-lit-web-components.md) | Lit Web Components for frontend |
| [004](docs/decisions/004-typing-protocol.md) | typing.Protocol for port interfaces |
| [005](docs/decisions/005-mcp-sole-api.md) | MCP as sole programmatic API |
| [006](docs/decisions/006-trunk-based-development.md) | Trunk-based development with feature flags |

See [docs/decisions/INDEX.md](docs/decisions/INDEX.md) for the full list
(47 ADRs covering event sourcing, knowledge metabolism, federation,
parallel planning, and more).

If your change contradicts an ADR, stop and flag the conflict.

## Key Paths

These are the most important files and directories to understand:

| Path | Purpose |
|------|---------|
| `src/formicos/core/events.py` | Closed event union — source of truth for all state changes |
| `src/formicos/core/types.py` | Shared domain types (ColonyContext, etc.) |
| `src/formicos/core/ports.py` | Port interfaces (typing.Protocol) |
| `src/formicos/engine/runner.py` | Colony round execution loop |
| `src/formicos/surface/projections.py` | Event replay into in-memory read models |
| `src/formicos/surface/queen_runtime.py` | Queen orchestration and tool dispatch |
| `src/formicos/surface/knowledge_catalog.py` | Federated knowledge retrieval with 6-signal scoring |
| `docs/contracts/` | Frozen integration seams — do not modify without maintainer approval |
| `docs/decisions/` | Architecture Decision Records (ADR files present in the repo) |
| `docs/specs/` | Executable specifications (pytest-bdd scenarios) |
| `frontend/src/types.ts` | TypeScript type mirrors of Python contracts |

## PR Expectations

- Keep PRs focused: one concern per PR when possible
- Include a clear description of what changed and why
- Reference related issues
- Ensure all CI checks pass before requesting review
- If your change touches overlap files shared between teams, note it in the
  PR description

## Admin-Owned Setup

Some project infrastructure requires repository administrator action and
cannot be configured through code alone. See
[docs/GITHUB_ADMIN_SETUP.md](docs/GITHUB_ADMIN_SETUP.md) for the complete
checklist including branch protection, CLA enforcement, labels, and
security scanning configuration.
