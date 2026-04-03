# FormicOS

**Your AI agents plan in parallel, extract knowledge, and maintain themselves -- while you watch.**

FormicOS is a stigmergic multi-agent colony framework where an operator directs a Queen LLM that decomposes goals, spawns specialized worker colonies, and coordinates them through shared environmental signals (pheromones) -- not direct messaging. Every action is an event. Every decision is explained. The system is local-first, event-sourced, and self-maintaining.

FormicOS is also an MCP server. Connect Claude Code or any MCP client, and the Queen's institutional memory, strategic delegation, and autonomous background work become part of your development workflow.

> **Try the demo:** Launch FormicOS, click **Try the Demo** on the Queen landing page, and watch the system detect a knowledge contradiction, plan a task in parallel, execute colonies, extract knowledge, and resolve the contradiction -- all autonomously.

## What makes it different

- **Plans work in parallel and shows you why** -- The Queen decomposes tasks into a DAG of parallel groups with deferred-group dispatch. A planning workbench lets you reshape, compare, and validate plans before launch. You see colonies execute side-by-side with live status, cost accumulation, and dependency arrows. The Queen's reasoning is always accessible.

- **Extracts and maintains institutional knowledge** -- Colonies produce knowledge entries with Bayesian confidence posteriors, hierarchical domains, provenance chains, and 7-signal composite retrieval scoring including Personalized PageRank. Knowledge improves with use, decays when stale, and gets distilled into higher-order entries. The operator can review, confirm, edit, or invalidate entries through the Operations inbox.

- **Detects problems and fixes them autonomously** -- Proactive intelligence surfaces contradictions, confidence decline, coverage gaps, and stale clusters. Self-maintenance dispatches colonies to investigate and resolve issues. Blast radius estimation gates autonomous dispatch. The operator sets autonomy levels and daily budgets; the system earns trust through a track record.

- **Explains every decision** -- Retrieval scoring shows per-signal breakdowns. Colony outcomes track cost, quality, and knowledge extraction. The Queen references outcomes as recommendations, not opaque overrides.

- **Operates across sessions and idle time** -- The Queen maintains a journal, follows operating procedures, and continues work on pending milestones when the operator is away. An operational sweep runs every 30 minutes, queuing and executing work within guardrails. The action queue captures every proposal, execution, and rejection for full audit.

- **Bridges to your editor** -- FormicOS is an MCP server with 29 tools, 12 resources, and 8 prompts. Run `python -m formicos init-mcp` to connect Claude Code. Search institutional memory, delegate tasks, review autonomous work, and record discoveries -- all from your editor.

## Why FormicOS?

Every agent framework has knowledge, planning, and multi-agent. Here is what FormicOS has that others don't:

- **Event-sourced everything.** LangGraph has checkpointing. AutoGen has memory. FormicOS has a closed 69-event union where every state change is an immutable fact. Crash, replay, same state. No other framework does this at the event level. A planning workbench lets operators reshape, compare, and dispatch parallel plans through deterministic reviewed-plan validation.
- **Earned autonomy.** CrewAI lets agents run. FormicOS gates autonomy through blast radius estimation, daily budget caps, and graduated trust scores. The system earns the right to work unsupervised.
- **Bayesian knowledge that improves with use.** Not just RAG. Not just a vector store. Entries carry Beta posteriors, decay naturally, strengthen through successful use, and get distilled into higher-order knowledge. The system gets smarter without retraining.
- **MCP-native.** Not a library you import. A server you connect to. Claude Code and Claude Desktop become your interface. The agent framework disappears into your existing workflow.

## Quick Start

### Cloud (recommended -- 3 commands)

```bash
git clone https://github.com/Intradyne/FormicOS.git
cd FormicOS
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env   # your real key
docker compose build && docker compose up -d
```

Three containers start: FormicOS, Qdrant, and Docker proxy. No GPU needed.

### Local GPU (advanced)

For local inference with no cloud dependency:

```bash
bash scripts/setup-local-gpu.sh    # downloads models, builds image, patches .env
docker compose up -d               # 5 containers
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for manual setup and GPU configuration.

### When the app is ready

1. Open **http://localhost:8080**
2. Wait for the startup panel to clear and the Queen welcome message to appear
3. Click **Try the Demo** to create a pre-seeded workspace and see FormicOS in action
4. Or describe a task to the Queen, spawn colonies, and explore the Knowledge view

### Connect Claude Code (optional)

```bash
python -m formicos init-mcp
# Generates .mcp.json for Claude Code + .formicos/DEVELOPER_QUICKSTART.md
# Restart Claude Code to connect via http://localhost:8080/mcp
```

### Connect Claude Desktop (optional)

Prerequisites: [Node.js](https://nodejs.org/) (for `npx mcp-remote`).

Add FormicOS to Claude Desktop's config
(`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "formicOSa": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8080/mcp"]
    }
  }
}
```

Or run `python -m formicos init-mcp --desktop` to print the snippet.
Restart Claude Desktop. The FormicOS tools appear via the hammer icon.

Both Claude Code and Claude Desktop connect to the same FormicOS instance simultaneously.

Once connected, try these from either client:
- `morning-status` -- what happened, what's pending, project plan status
- `delegate-task` -- hand off work to a colony
- `knowledge-for-context` -- search institutional memory
- `log-finding` -- record a discovery

See [docs/DEVELOPER_BRIDGE.md](docs/DEVELOPER_BRIDGE.md) for daily workflows, available prompts, and knowledge population.

### Startup verification

```bash
docker compose ps                      # 3 containers (cloud) or 5 (local GPU)
curl http://localhost:8080/health      # FormicOS
curl http://localhost:6333/collections # Qdrant
# Local GPU only:
# curl http://localhost:8008/health    # LLM
# curl http://localhost:8200/health    # Embedding sidecar
```

## Architecture

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

- **Core** -- closed 69-event Pydantic union, shared types, CRDTs, ports, and knowledge/federation contracts
- **Engine** -- colony execution, context assembly, tool loop, stigmergic + sequential strategies, optimistic file locking, task-aware tool pruning
- **Adapters** -- SQLite event store, Qdrant-backed knowledge search, knowledge graph adapter, federation transport, sandbox, multi-provider LLM bindings (OpenAI-compatible, Anthropic, Gemini) with per-endpoint concurrency and provider-aware schema sanitization
- **Surface** -- Starlette app, MCP/HTTP/WS/AG-UI/A2A surfaces, Queen runtime with ~45 tools (dynamic toolset loading), projections, maintenance services, addon loader, trigger dispatch, operational state (journal, procedures, action queue), planning workbench (reviewed-plan validation, saved patterns, DAG editing), and operator wiring

The frontend is a Lit component shell with 8 tabs (Queen, Knowledge, Workspace, Operations, Addons, Playbook, Models, Settings) driven by WebSocket state snapshots and replay-safe projections. The Queen chat includes inline colony previews with a planning workbench overlay for DAG editing and validation before dispatch.

### MCP developer bridge

FormicOS is a FastMCP 3.0 server at `/mcp` with:

- **29 MCP tools** -- colony management, knowledge search, addon control, approvals, service queries, configuration, and developer workflows (log_finding, handoff_to_formicos)
- **12 MCP resources** -- knowledge catalog, thread/colony detail, project plan, operating procedures, journal, briefing
- **8 MCP prompts** -- morning-status, delegate-task, review-overnight-work, knowledge-for-context, knowledge-query, plan-task, economic-status, review-task-receipt
- **PromptsAsTools + ResourcesAsTools transforms** -- every prompt and resource is also callable as a tool

### Persistence

Event-sourced: a single SQLite file is the source of truth. On startup, events replay into in-memory projections. Crash-recoverable by design.

Operational state (journal, procedures, action queue) is file-backed under `.formicos/operations/`. Project plans live at `.formicos/project_plan.md`. These are workspace-scoped files the operator can read and edit directly.

## Key Concepts

**Workspaces, Threads, Colonies, Rounds** -- the data model is a tree. A workspace contains threads. A thread contains colonies. A colony runs rounds. Each round executes the 5-phase loop across all agents.

**The Queen** -- the operator-facing LLM agent with ~45 tools (dynamic toolset loading). The operator chats with the Queen, who decomposes goals and spawns colonies. Each thread has its own Queen conversation. The Queen maintains a journal, follows operating procedures, checks blast radius before autonomous dispatch, and earns trust through a graduated autonomy score.

**Stigmergic Routing** -- in stigmergic mode, agents are connected by a weighted topology graph. Pheromone weights evolve each round based on output quality (cosine similarity). High-performing paths get reinforced; low-performing paths decay. The `sequential` strategy is a simpler fallback.

**Knowledge System** -- Bayesian confidence posteriors (`Beta(alpha, beta)`) with Thompson Sampling retrieval. 7-signal composite scoring (semantic, thompson, freshness, status, thread, co-occurrence, graph proximity). Hierarchical domains with materialized paths. Provenance chains tracking every mutation. Personalized PageRank for graph-augmented retrieval. Outcome-weighted reinforcement with geometric credit. Knowledge review flow surfaces problematic entries for operator confirmation.

**Operational Loop** -- a 30-minute operational sweep detects opportunities, queues actions (maintenance, continuation, knowledge review, workflow templates, procedure suggestions), and executes within autonomy guardrails. The operator reviews pending actions in the Operations inbox. Blast radius estimation and daily budget caps gate autonomous dispatch.

**Model Cascade** -- model assignment follows a nullable cascade: thread override > workspace override > system default. Change the model for one workspace without affecting others.

**Protocol surfaces** -- MCP remains the primary external tool surface, while HTTP, WebSocket, AG-UI, and A2A expose the same event-sourced system from different integration angles.

## Project Status

### Core (production-ready)

- **Event-sourced persistence** -- closed 69-event Pydantic union, replay-safe projections, crash-recoverable by design
- **Bayesian knowledge system** -- Beta posteriors, Thompson Sampling retrieval, 7-signal composite scoring, gamma decay, co-occurrence, hierarchical domains, provenance chains, PPR retrieval, outcome-weighted reinforcement, admission scoring, knowledge review governance
- **Queen parallel planning** -- DAG decomposition via `spawn_parallel`, workflow threads/steps, project milestones, 42 built-in tools, MCP-aware chaining
- **Operational loop** -- 30-minute sweeps, durable action queue, journal, procedures, continuation proposals, blast radius estimation, graduated autonomy scoring with daily budget caps
- **MCP developer bridge** -- 29 tools, 12 resources, 8 prompts, `init-mcp` CLI for Claude Code and Claude Desktop integration

### Shipped (functional, evolving)

- **Autonomous agency** -- proactive intelligence (17 deterministic rules), self-maintenance dispatch, idle-time execution with 5 guard rails, workflow pattern recognition, operating procedure auto-suggestions
- **Addon system** -- YAML manifest discovery, tool/handler/trigger registration, 6 built-in addons (codebase-index, docs-index, git-control, mcp-bridge, proactive-intelligence, hello-world)
- **Multi-provider execution** -- per-endpoint adapter factory, per-model concurrency control, local-first inference plus cloud fallback, reasoning and cache token accounting
- **Federation** -- knowledge exchange via Computational CRDTs, Bayesian peer trust hardening, truthful A2A / Agent Card protocol surfaces
- **Economic accountability** -- token metering with chain-hash integrity, tiered fee computation, `billing` CLI, A2A task receipts, revenue-share attribution
- **Operator surfaces** -- 8-tab frontend (Queen, Knowledge, Workspace, Operations, Addons, Playbook, Models, Settings), sandboxed code execution, colony outcome metrics

### Planned (ADR-approved)

- **Cloud-first default deployment** (Wave 77 Track A) -- 3-container stack with cloud API inference, no GPU required, Docker Compose profiles for opt-in local GPU
- **AI Filesystem with amnesiac forking** (Wave 77 Track B, [ADR-052](docs/decisions/052-ai-filesystem.md)) -- state/artifact separation, file-backed working memory, reflection files for failed colony retries, 47.2% vs 30.4% task success improvement (Pan et al. 2026)

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

# Connect Claude Code
python -m formicos init-mcp           # generates .mcp.json
python -m formicos init-mcp --desktop # prints Claude Desktop config snippet
python -m formicos billing status     # current-period token usage and fees
```

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | Project context and rules (loaded by AI agents automatically) |
| [AGENTS.md](AGENTS.md) | File ownership and coordination rules for parallel agents |
| [GOVERNANCE.md](GOVERNANCE.md) | Maintainer authority, contribution flow, and project governance |
| [CLA.md](CLA.md) | Contributor license agreement and revenue-share terms |
| [CORPORATE_CLA.md](CORPORATE_CLA.md) | Corporate contributor agreement for employer-authorized contributions |
| [docs/CONTRIBUTOR_PAYOUT_OPS.md](docs/CONTRIBUTOR_PAYOUT_OPS.md) | Revenue-share payout operations (tax, payments, timing) |
| [docs/A2A_ECONOMICS.md](docs/A2A_ECONOMICS.md) | Machine-readable contracts and receipts for A2A agent participation |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guide: clone to running stack |
| [docs/AUTONOMOUS_OPERATIONS.md](docs/AUTONOMOUS_OPERATIONS.md) | Autonomy operator runbook: levels, budgets, action queue, learning |
| [docs/DEVELOPER_BRIDGE.md](docs/DEVELOPER_BRIDGE.md) | Developer onboarding guide for Claude Code MCP integration |
| [CHANGELOG.md](CHANGELOG.md) | Narrative development history |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture overview, event flow, data model |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Hardware requirements, operations, troubleshooting |
| [docs/LOCAL_FIRST_QUICKSTART.md](docs/LOCAL_FIRST_QUICKSTART.md) | Detailed local setup and first interaction walkthrough |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer guide: setup, testing, adding features |
| [docs/KNOWLEDGE_LIFECYCLE.md](docs/KNOWLEDGE_LIFECYCLE.md) | Knowledge system operator runbook |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records (ADR-001 through ADR-052) |
| [docs/contracts/](docs/contracts/) | Frozen interface definitions (events, ports, types) |
| [docs/specs/](docs/specs/) | Executable specifications and regression scenarios |
| [docs/waves/PROGRESS.md](docs/waves/PROGRESS.md) | Development progress log (Waves 1-76) |
| [addons/README.md](addons/README.md) | Addon development guide |
| [FINDINGS.md](FINDINGS.md) | What 59 waves of measurement proved |
| [METERING.md](METERING.md) | Token metering system specification |
| [COMMERCIAL_TERMS.md](COMMERCIAL_TERMS.md) | Commercial license payment terms |
| [frontend/CHANGELOG.md](frontend/CHANGELOG.md) | Frontend component inventory and bundle stats |

## License

FormicOS is free software. The AGPLv3 base license guarantees your right to
use, study, modify, and share the complete system. Additional permissions
under Section 7 make this even broader: individuals, small businesses
(under $1M revenue), nonprofits, and educators can deploy FormicOS without
any source-disclosure obligations or fees.

Organizations above $1M revenue choosing proprietary deployment can obtain
a commercial license with usage-based pricing (no per-seat or per-machine
fees). Twenty percent of commercial revenue is shared with contributors
proportional to their code contributions, creating a sustainable model
where improving the commons is also building a livelihood.

See [LICENSE](LICENSE) for the full terms,
[COMMERCIAL_TERMS.md](COMMERCIAL_TERMS.md) for payment mechanics,
[METERING.md](METERING.md) for the token metering specification, and
[CLA.md](CLA.md) for the contributor agreement and revenue-share program.
