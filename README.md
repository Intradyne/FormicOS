# FormicOS

**Your AI agents plan in parallel, extract knowledge, and maintain themselves — while you watch.**

FormicOS is a stigmergic multi-agent colony framework where an operator directs a Queen LLM that decomposes goals, spawns specialized worker colonies, and coordinates them through shared environmental signals (pheromones) — not direct messaging. Every action is an event. Every decision is explained. The system is local-first, event-sourced, and self-maintaining.

> **Try the demo:** Launch FormicOS, click **Try the Demo** on the Queen landing page, and watch the system detect a knowledge contradiction, plan a task in parallel, execute colonies, extract knowledge, and resolve the contradiction — all autonomously.

## What makes it different

- **Plans work in parallel and shows you why** — The Queen decomposes tasks into a DAG of parallel groups. You see colonies execute side-by-side with live status, cost accumulation, and dependency arrows. The Queen's reasoning is always accessible.

- **Extracts and maintains institutional knowledge** — Colonies produce knowledge entries with Bayesian confidence posteriors, decay classes, and 6-signal composite retrieval scoring. Knowledge improves with use, decays when stale, and gets distilled into higher-order entries.

- **Detects problems and fixes them autonomously** — Proactive intelligence surfaces contradictions, confidence decline, coverage gaps, and stale clusters. Self-maintenance dispatches colonies to investigate and resolve issues without operator intervention.

- **Explains every decision** — Retrieval scoring shows per-signal breakdowns. Colony outcomes track cost, quality, and knowledge extraction. The Queen references outcomes as recommendations, not opaque overrides.

## Quick Start

```bash
git clone https://github.com/Intradyne/FormicOS.git
cd FormicOS
cp .env.example .env          # optional: add ANTHROPIC_API_KEY or GEMINI_API_KEY
```

For the default local stack:

```bash
mkdir -p .models

# download the GGUFs into .models before first boot
# see docs/LOCAL_FIRST_QUICKSTART.md for the exact huggingface-cli commands

# build the local llama.cpp image once if you are using the default local model
bash scripts/build_llm_image.sh

docker compose up -d
```

If you want cloud-only operation instead, add `ANTHROPIC_API_KEY` and/or `GEMINI_API_KEY` to `.env` and skip the local-model build.

When the app is ready:
1. Open **http://localhost:8080**
2. Wait for the startup panel to clear and the Queen welcome message to appear
3. Click **Try the Demo** to create a pre-seeded workspace and see FormicOS in action
4. Or describe a task to the Queen, spawn colonies, and explore the Knowledge view

Startup verification:

```bash
docker compose ps
curl http://localhost:8080/health
curl http://localhost:8008/health
curl http://localhost:8200/health
curl http://localhost:6333/collections
```

## Architecture

Current repo state: the core event contract is a closed 69-event union.
Wave 64 added addon system events (66 -> 69).

Four layers with strict inward dependency, enforced by CI:

```
  Surface   wiring + HTTP/WS/CLI       imports all layers
     |
  Adapters  LLM, SQLite, Qdrant, KG   imports only Core
     |
  Engine    colony execution           imports only Core
     |
  Core      types, events, ports       imports nothing
```

- **Core** — closed 69-event Pydantic union, shared types, CRDTs, ports, and knowledge/federation contracts
- **Engine** — colony execution, context assembly, tool loop, stigmergic + sequential strategies, optimistic file locking
- **Adapters** — SQLite event store, Qdrant-backed knowledge search, knowledge graph adapter, federation transport, sandbox, multi-provider LLM bindings (OpenAI-compatible, Anthropic, Gemini) with per-endpoint concurrency
- **Surface** — Starlette app, MCP/HTTP/WS/AG-UI/A2A surfaces, Queen runtime/tools (36 built-in), projections, maintenance services, addon loader, trigger dispatch, and operator wiring

The frontend is a Lit component shell driven by WebSocket state snapshots, promoted events, and replay-safe projections.

Persistence is event-sourced: a single SQLite file is the source of truth. On startup, events replay into in-memory projections. Crash-recoverable by design.

## Key Concepts

**Workspaces, Threads, Colonies, Rounds** — the data model is a tree. A workspace contains threads. A thread contains colonies. A colony runs rounds. Each round executes the 5-phase loop across all agents.

**The Queen** — the operator-facing LLM agent. The operator chats with the Queen, who decomposes goals and spawns colonies. Each thread has its own Queen conversation.

**Stigmergic Routing** — in stigmergic mode, agents are connected by a weighted topology graph. Pheromone weights evolve each round based on output quality (cosine similarity). High-performing paths get reinforced; low-performing paths decay. The `sequential` strategy is a simpler fallback.

**Merge / Prune / Broadcast** — operator controls for inter-colony information flow. Merge creates a directed edge between colonies. Prune removes it. Broadcast copies a colony's compressed output to all colonies in a thread.

**Model Cascade** — model assignment follows a nullable cascade: thread override > workspace override > system default. Change the model for one workspace without affecting others.

**Protocol surfaces** — MCP remains the primary external tool surface, while HTTP, WebSocket, AG-UI, and A2A expose the same event-sourced system from different integration angles.

## Project Status

FormicOS currently ships with:

- [x] Event-sourced persistence with replay-safe projections and a closed 69-event contract
- [x] Unified knowledge system with Bayesian confidence, gamma decay, co-occurrence, thread scoping, transcript harvest, outcome-weighted reinforcement, admission scoring, and bi-temporal surfacing
- [x] Proactive intelligence, maintenance policies, deterministic self-maintenance services, and configuration recommendations grounded in outcome history
- [x] Queen parallel planning via `spawn_parallel`, workflow threads/steps, operator directives, and colony audit surfaces
- [x] Queen autonomous agency: 36 built-in tools including batch_command, summarize_thread, draft_document, retry_colony, and MCP-aware chaining guidance
- [x] Addon system: YAML manifest discovery, tool/handler/trigger registration, 4 built-in addons (codebase-index, git-control, proactive-intelligence, hello-world)
- [x] Multi-provider parallel execution: per-endpoint adapter factory, per-model concurrency control, heuristic cloud routing, optimistic file locking for concurrent agents
- [x] Reasoning and cache token accounting through the full pipeline (adapters to dashboard)
- [x] Federated knowledge exchange via Computational CRDTs, Bayesian peer trust hardening, and truthful A2A / Agent Card protocol surfaces
- [x] Local-first inference plus cloud fallback, sandboxed code execution, NemoClaw-compatible external specialists, and operator steering
- [x] Unified operator surfaces for colonies, knowledge, workflow, explainable retrieval, and local-first knowledge overlays
- [x] Colony outcome metrics, escalation reporting, validator-aware completion states, and replay-derived history views
- [x] Guided demo path with pre-seeded workspace and contradiction-driven maintenance walkthrough
- [x] DAG visualization with live status, cost accumulation, and knowledge annotations
- [x] Sequential task runner with locked experiment conditions for compounding measurement
- [x] Static workspace analysis and structural topology prior for knowledge-informed routing
- [x] Adaptive evaporation with bounded stagnation-responsive pheromone control
- [x] Contradiction resolution with classification-aware conflict handling
- [x] Web foraging with reactive and proactive gap detection, egress-controlled fetch, source-credibility-aware admission, content quality scoring, and domain strategy memory

## Development

```bash
# Install dependencies
uv sync --dev

# Run all checks (same as CI)
uv run ruff check src/
uv run pyright src/
python scripts/lint_imports.py
python -m pytest -q

# Or run the full CI pipeline in one command
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && python -m pytest -q

# Run locally without Docker
python -m formicos                    # backend on :8080
cd frontend && npm run dev            # frontend dev server with HMR

# Build frontend
cd frontend && npm run build
```

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | Project context and rules (loaded by AI agents automatically) |
| [AGENTS.md](AGENTS.md) | File ownership and coordination rules for parallel agents |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide: clone to running stack |
| [CHANGELOG.md](CHANGELOG.md) | Narrative development history |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture overview, event flow, data model |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Hardware requirements, operations, troubleshooting |
| [docs/LOCAL_FIRST_QUICKSTART.md](docs/LOCAL_FIRST_QUICKSTART.md) | Detailed local setup and first interaction walkthrough |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer guide: setup, testing, adding features |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records |
| [docs/contracts/](docs/contracts/) | Frozen interface definitions (events, ports, types) |
| [docs/specs/](docs/specs/) | Executable specifications and regression scenarios |
| [docs/waves/PROGRESS.md](docs/waves/PROGRESS.md) | Development progress log |
| [addons/README.md](addons/README.md) | Addon development guide |
| [FINDINGS.md](FINDINGS.md) | What 59 waves of measurement proved |
| [frontend/CHANGELOG.md](frontend/CHANGELOG.md) | Frontend component inventory and bundle stats |

## License

AGPLv3 with a small-business and educational exception. See [LICENSE](LICENSE) for details.
