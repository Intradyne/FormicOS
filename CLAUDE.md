# FormicOS -- Stigmergic Multi-Agent Colony Framework

Open-source Python system: AI agents coordinate through shared environmental
signals (pheromones), not direct messaging. Tree-structured data model.
Event-sourced (70 events, closed union). Single operator. Local-first with
cloud model support. Bayesian knowledge metabolism with Thompson Sampling
retrieval. Federated knowledge exchange via Computational CRDTs.
Multi-colony orchestration via DelegationPlan DAG parallelism with deferred
group dispatch. MCP developer bridge (29 tools, 12 resources, 8 prompts)
for Claude Code integration. Queen Command & Control surface with behavioral
overrides, display board, tool tracking, and context budget visibility.
Planning workbench with structural analysis, replay-derived capability
calibration, deterministic reviewed-plan validation and dispatch, saved plan
patterns, and DAG editing. Live planning policy (`planning_policy.py`) as
the Queen routing authority with fast_path enforcement at the execution
layer. Project binding with real-repo codebase indexing (14K+ chunks).
Production local profile: Qwen3.5-35B MoE (0.804 quality on fast_path
tasks, 5/5 real-repo tasks completed, zero hangs).

## Knowledge base

The FormicOS knowledge system contains 100+ entries covering agent
architecture state of the art (loop patterns, tool calling, context
engineering, multi-agent coordination, production deployment, evaluation).
Before making architectural choices, search the knowledge base via the
`search_knowledge` MCP tool or the Queen's `memory_search` tool. Cite
relevant entries by title when they influence design decisions.

## Architecture

Four layers, strict inward dependency. **ENFORCED BY CI -- backward imports fail the build.**

| Layer | Responsibility | May import |
|----------|--------------------------------------|----------------------|
| Core | Types, events (69), port interfaces, CRDTs | NOTHING |
| Engine | Colony execution, pure computation | Core only |
| Adapters | Tech bindings (LLM, SQLite, Qdrant, MCP) | Core only |
| Surface | Wiring, HTTP/WS/CLI, lifecycle | Core, Engine, Adapters |

Queen orchestration and colony lifecycle live in Surface (they depend on
projections, event broadcasting, and adapter wiring). Engine contains only
pure computation: `runner.py`, `tool_dispatch.py`, `runner_types.py`,
`strategies/`, `context.py`.

### Knowledge system

Current repo state:

- Wave 38 admission scoring and trust rationale are part of the intake and
  retrieval story now.
- Outcome-weighted reinforcement replaced the old flat confidence update.
- Operator overlays are replayable and local-first; pin/unpin, mute/unmute,
  invalidate/reinstate, and annotations do not silently mutate shared Beta
  confidence truth.
- Proactive intelligence now spans 17 deterministic rules across knowledge
  health, performance, evaporation, branching, and earned autonomy.

Colonies produce knowledge entries (skills, experiences) via LLM extraction,
5-axis security scanning (prompt injection, data exfiltration, credential
leakage, code safety, credential detection via detect-secrets), and
transcript harvest (hook position 4.5 -- extracts bug root causes,
conventions, tool configurations). Entries carry Bayesian confidence
posteriors (`Beta(alpha, beta)`) evolved by Thompson Sampling, with
decay classes (ephemeral gamma=0.98, stable gamma=0.995, permanent gamma=1.0) and
a 180-day gamma cap. Entries have granular sub-types within their category:
skills -> technique/pattern/anti_pattern; experiences ->
decision/convention/learning/bug. Retrieval uses a 7-signal composite
score (ADR-044, rebalanced Wave 59.5):
`0.38*semantic + 0.25*thompson + 0.10*freshness + 0.10*status + 0.07*thread + 0.04*cooccurrence + 0.06*graph_proximity`.
All signals normalized to [0, 1]. Co-occurrence uses sigmoid normalization
(`1 - e^{-0.6w}`). Thread-scoped entries get a thread_bonus of 1.0
(weighted at 0.07) when retrieved by same-thread colonies.

Retrieval supports 4 tiers: `summary` (~15 tokens/result), `standard`
(~75 tokens), `full` (~200+ tokens), and `auto` (starts at summary,
escalates if coverage is thin). Budget-aware context assembly enforces
per-scope token budgets: task_knowledge (35%), observations (20%),
structured_facts (15%), round_history (15%), scratch_memory (15%).

Agents can provide explicit quality feedback via the `knowledge_feedback`
tool (coder/reviewer/researcher castes). Positive feedback strengthens
confidence; negative feedback increments prediction_error_count and
reduces confidence.

Proactive intelligence surfaces 17 deterministic rules (no LLM calls):
7 knowledge-health rules (confidence decline, contradiction, federation
trust drop, coverage gap, stale cluster, merge opportunity, federation
inbound), 4 performance rules (strategy efficiency, diminishing rounds,
cost outlier, knowledge ROI), plus evaporation, branching stagnation,
earned autonomy, learned template health, recent outcome digest, and
popular unexamined. Three rules
(contradiction, coverage gap, stale cluster) include `suggested_colony`
configurations for auto-dispatch. Distillation candidates
(dense co-occurrence clusters with >=5 entries and avg weight >3.0)
are identified during maintenance and synthesized by archivist colonies.

### Self-maintenance (ADR-046)

MaintenanceDispatcher connects proactive insights to automatic colony dispatch.
Three autonomy levels: `suggest` (show data only), `auto_notify` (dispatch
opted-in categories, notify operator), `autonomous` (dispatch all eligible).
Policy controls: `auto_actions` list, `max_maintenance_colonies`, and
`daily_maintenance_budget`. Budget tracking resets daily at UTC midnight.

Blast radius estimation gates dispatch: 6 heuristic factors (task length,
caste risk, round count, strategy, keywords coder-only, outcome history)
produce a score. Thresholds: >=0.6 escalate, >=0.3 notify, <0.3 proceed.
`auto_notify` skips both escalate and notify; `autonomous` skips only
escalate.

Autonomy scoring: 4 weighted components (success_rate, volume,
cost_efficiency, operator_trust) produce a grade (A-F) and level
(full/standard/limited/restricted). `check_autonomy_budget` Queen tool
surfaces daily budget truth.

### Workflow learning (Wave 72)

Deterministic extractors in `surface/workflow_learning.py` propose actions
through the existing action queue. No LLM calls, no new events.

**Pattern recognition** (Track 8): `extract_workflow_patterns()` scans colony
outcomes for repeating `(strategy, caste_set)` fingerprints. Requires
`>=3` successful occurrences across `>=2` distinct threads. Proposes
`kind="workflow_template"` actions. On approval, saves a
`ColonyTemplate(learned=True)`.

**Procedure suggestions** (Track 9): `detect_operator_patterns()` finds
repeated rejection or manual approval patterns in the action queue. Proposes
`kind="procedure_suggestion"` actions. On approval, appends a rule to
workspace operating procedures via `append_procedure_rule()`.

See `docs/AUTONOMOUS_OPERATIONS.md` for the full autonomy operator runbook.

### Project plan (Wave 70)

One project plan per data root at `.formicos/project_plan.md`. Shared
parser/helper in `project_plan.py`. Queen gets a dedicated `project_plan`
context budget slot (5%, 400-token fallback). `propose_project_milestone`
and `complete_project_milestone` Queen tools. `GET /api/v1/project-plan`
returns structured JSON for frontend rendering.

### Adaptive evaporation (Wave 42)

Pheromone evaporation in stigmergic mode is bounded adaptive, not fixed.
The rate interpolates linearly from `_EVAPORATE_MAX=0.95` (healthy) to
`_EVAPORATE_MIN=0.85` (stagnating) based on two signals: branching factor
(`exp(entropy)` over pheromone edge weights) and convergence stall count.
High branching (>=2.0) or zero stalls -> normal rate. Low branching + stalls
-> faster evaporation to break attractors. Stall influence capped at 4
rounds. Control law is runner-local (`runner.py`), no surface imports.

### Web foraging (Wave 44)

The Forager adds a second knowledge input channel: bounded web acquisition.
When retrieval exposes a gap, the system can search, fetch, extract, and
admit content through the existing `MemoryEntryCreated` path at `candidate`
status with conservative priors. No separate "proposed knowledge" event.

Architecture: `EgressGateway` adapter enforces rate/size/domain controls.
`FetchPipeline` adapter handles httpx + trafilatura extraction (Level 1)
with optional fallback extractors (Level 2). `ContentQuality` adapter
scores content without LLM. `WebSearch` adapter provides pluggable search.
`Forager` surface module orchestrates the cycle with deterministic query
templates.

Replay surface: 4 foraging event types (59 -> 62):
`ForageRequested`, `ForageCycleCompleted`, `DomainStrategyUpdated`,
`ForagerDomainOverride`. Individual search/fetch/rejection stays log-only.

Trigger modes: `reactive` (live-task gap, highest priority), `proactive`
(briefing rules, background), `operator` (manual). Reactive foraging
detects gaps in `knowledge_catalog.py` but does not perform network I/O
inline -- it hands off to the forager path. Proactive foraging runs
through the scheduled maintenance loop: `proactive_intelligence` emits
bounded `forage_signal` metadata, `MaintenanceDispatcher` evaluates
workspace briefings, and eligible signals are handed to `ForagerService`
for background execution. Reactive, proactive, and operator-triggered
modes are all operational.


Operator domain controls: `trust`, `distrust`, `reset` via
`ForagerDomainOverride` events. Extends the operator co-authorship model.

Domain strategy memory: per-domain preferred fetch level with success/failure
counts, persisted via `DomainStrategyUpdated` events. Survives replay.

### Colony outcome intelligence (ADR-047)

`ColonyOutcome` is a replay-derived projection computed from existing events
(no new event types). Tracks: succeeded, total_rounds, total_cost, duration_ms,
entries_extracted, entries_accessed, quality_score, caste_composition, strategy,
maintenance_source. Four performance rules in `proactive_intelligence.py`
analyze outcomes: strategy efficiency, diminishing rounds, cost outlier,
knowledge ROI. All deterministic, no LLM. Queen references as recommendations.
REST endpoint: `GET /api/v1/workspaces/{id}/outcomes?period=7d`.

### Demo workspace

Pre-seeded workspace template (`config/templates/demo-workspace.yaml`) with
10 knowledge entries across two domains, deliberate contradiction, and
auto_notify maintenance policy. Created via
`POST /api/v1/workspaces/create-demo`.

### Knowledge distillation

Dense co-occurrence clusters (>=5 entries, avg weight >3.0) are flagged as
distillation candidates during maintenance. When policy allows, archivist
colonies synthesize clusters into higher-order entries (KnowledgeDistilled
event). Distilled entries get `decay_class="stable"` and elevated alpha
(capped at 30).

### Multi-colony orchestration (ADR-045)

Queen decomposes complex tasks into DelegationPlan DAGs via `spawn_parallel`.
ColonyTask items are organized into `parallel_groups` -- tasks within a group
run concurrently via `asyncio.gather`, groups execute sequentially.
DAG validated with Kahn's algorithm (no cycles). ParallelPlanCreated event
records the plan, reasoning, knowledge gaps, and estimated cost.

### Operator directives (ADR-045 D3)

Four directive types: `context_update`, `priority_shift`, `constraint_add`,
`strategy_change`. Delivered via ColonyChatMessage metadata. Urgent directives
appear before task description; normal directives appear after task context.

### Mastery restoration

Entries with `decay_class` stable/permanent get a 20% gap-recovery bonus
when re-observed after significant decay (`current_alpha < peak_alpha * 0.5`).
`peak_alpha` tracked in projections via MemoryConfidenceUpdated handler.

### Per-workspace composite weights (ADR-044 D4)

Workspace-scoped weight overrides via `configure_scoring` MCP tool. Stored
in WorkspaceConfigChanged events. Falls back to global defaults. At
standard/full retrieval tier, results include `score_breakdown` and
`ranking_explanation` showing per-signal contributions and dominant signal.

See `docs/KNOWLEDGE_LIFECYCLE.md` for the full operator runbook.

### Federation

Current repo state: federation trust is hardened. Peer failures add `2.0` to
beta, hop discount is `0.7^hop` with a `0.5` cap, and federated retrieval
penalties keep weak foreign entries from outranking strong local verified
knowledge.

Knowledge entries can be exchanged between FormicOS instances via push/pull
replication. Each entry is backed by an ObservationCRDT (core/crdt.py) with
G-Counters for observations, LWW Registers for content, and G-Sets for
domains. Gamma-decay is applied at query time, not stored in the CRDT.
Trust between peers uses Bayesian PeerTrust (10th percentile of Beta
posterior -- penalizes uncertainty). Conflict resolution uses three phases:
Pareto dominance, adaptive threshold, then competing hypotheses.

### Deployment and execution

Deployment guide: `docs/DEPLOYMENT.md`. Default path: Docker Compose with
llama.cpp (GPU), Qwen3-Embedding sidecar, Qdrant, Docker socket proxy,
and FormicOS. Five containers, named volumes for SQLite and Qdrant
persistence.

Execution has two paths: sandbox (`code_execute` tool, Docker containers
with `--network=none`, `--memory=256m`, `--read-only`) and workspace
executor (repo-backed commands, currently runs on backend host process
without container isolation). The workspace executor is the largest
remaining security gap. Docker socket is mounted for sandbox spawning --
this grants daemon access to the FormicOS container.

SQLite persistence rules: named volumes only (no bind-mounts on macOS/Windows
Docker Desktop), `.db`/`.db-wal`/`.db-shm` must stay co-located,
single-writer system.

### Error handling

Current repo state: StructuredError is the desired contract for route and API
surfaces, but a few service/adapter paths still carry legacy string returns.
Treat those as convergence debt, not the intended long-term interface.

All 5 surfaces (MCP, HTTP, WebSocket, A2A, AG-UI) use StructuredError with
a KNOWN_ERRORS registry (35+ entries). Each error includes error_code,
recovery_hint, and suggested_action. MCP tools return structured errors
via `to_mcp_tool_error()` with `isError`, `content`, and
`structuredContent` fields.

### Workflow threads and steps

Work is organized into threads with goals. Threads contain workflow steps --
sequential guidance the Queen uses to structure multi-colony work. Steps are
not a DAG; they are Queen scaffolding. When a colony completes a step, the
system prompts the Queen with the next pending step via the follow_up_colony
summary.

### Metering and billing (Wave 75)

Token metering aggregates `TokensConsumed` events per billing period with
chain-hash integrity. `formicos billing` CLI subgroup (status, estimate,
attest, history, self-test). Attestations are deterministic and stored in
`data_dir/attestations/`. The `metering.py` surface module computes fees
from tiered token thresholds. `scripts/attribution.py` computes contributor
revenue-share proportions from git history.

### A2A economic contracts (Wave 75)

Task receipts (`surface/task_receipts.py`) produce deterministic cost/quality
summaries for completed A2A work. `get_task_receipt` MCP tool and
`formicos://receipt/{task_id}` resource expose receipts to clients.
`search_knowledge` MCP tool provides full-pipeline retrieval from external
clients (semantic + Thompson + freshness + co-occurrence + graph proximity).

### Structural integrity (Wave 76)

16 correctness fixes across 3 teams (data truth, operational safety,
context integrity). No new features -- fixes silent errors and race
conditions that would surface under real multi-client load.

Data truth: `BudgetSnapshot.total_tokens` includes reasoning tokens.
Agent-to-colony reverse index (`_agent_colony_index`) in ProjectionStore
for O(1) token attribution. Daily spend persistence to disk with reload
on restart. Budget reconciliation (estimated vs actual colony cost)
wired through `_post_colony_hooks`.

Operational safety: Action queue compaction preserves `pending_review`
items. State transition validation via `_VALID_TRANSITIONS` map (409 on
invalid). Operational sweep reentrancy guard (`asyncio.Lock`).
Kill/completion race guard at both colony completion paths. Journal
entries for all approval/execution branches. Operator-idle detection
includes Queen thread messages.

Context integrity: Budget caps on memory retrieval, notes, and thread
context injections. Workspace-scoped session and plan paths with
migration fallback. Queen chat workspace propagation across all 4
dispatch sites. Settings and queen-overview workspace resolution via
`activeWorkspaceId` property.

## Tech stack

Use Python 3.12+, uv, Pydantic v2 (sole serialization), asyncio, httpx,
aiosqlite, qdrant-client (>=1.16), sentence-transformers (fallback embedding
path alongside Qwen3-embedding sidecar), FastMCP >=3.0, Starlette, uvicorn,
structlog, sse-starlette, json-repair, opentelemetry-api.
Frontend: Lit Web Components. See `pyproject.toml` for exact pins.

## Commands

```bash
uv sync                    # Install
pytest                     # Test
ruff check src/            # Lint
pyright src/               # Type check
python scripts/lint_imports.py  # Layer check
docker compose up          # Run (or: python -m formicos)
python -m formicos init-mcp  # Generate MCP config for Claude Code
```

**Full CI (run before declaring any task done):**
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Workflow cadence

Use this delivery loop unless the operator explicitly asks for a different one.

Expanded reference:
- `docs/DEVELOPMENT_WORKFLOW.md` -- canonical workflow document with the shared
  delivery loop, prompt checklist, acceptance checklist, and handoff artifacts

### 0. Establish the active coordination source

- `CLAUDE.md` defines the evergreen repo rules and cadence.
- Root `AGENTS.md` may be historical and wave-specific.
- If the active wave docs or dispatch prompts conflict with a stale root `AGENTS.md`, the active wave docs win for that dispatch.
- Say this explicitly in coder prompts instead of silently assuming it.

### 1. Ground the plan in repo truth first

- Read the relevant wave docs, ADRs, and contract docs before changing code.
- Inspect the current code paths that actually carry truth at runtime.
- Prefer identifying the real seam over proposing broad redesigns.
- When a surface looks wrong, check whether the bug is:
  - substrate truth (events, projections, persistence, replay),
  - surface truth (UI/API presentation),
  - or runtime/deployment truth (Docker image, persisted state, GPU routing).

### 2. Split work into bounded parallel tracks

- Use the active wave docs as the source of truth for parallel ownership.
- Use root `AGENTS.md` only when it still matches the active wave.
- Write prompts that assign:
  - explicit file ownership,
  - clear non-goals,
  - exact validation commands,
  - overlap reread rules when needed.
- Keep each track valuable on its own; avoid "half-finished infrastructure" tracks when possible.

### 3. Work in explicit passes

Keep these passes distinct unless the operator asks otherwise:

1. Planning pass
- shape the wave around verified repo seams
- decide what is in-wave, what is not, and what remains uncertain

2. Packet maturity pass
- decide whether the next wave should stay provisional or become a real dispatch packet
- avoid writing fake-precision gates/prompts against unfinished debt

3. Packet audit
- audit the packet against the live repo before dispatch
- patch the smallest set of plan/prompt/gate docs needed to close real findings

4. Coder dispatch
- produce bounded prompts with owned files, do-not-touch lists, validation, and overlap rules

5. Integrator acceptance
- verify replay behavior, fallback behavior, shared seams, and active runtime truth

6. Polish pass
- improve startup UX, docs, naming, and workflow clarity only after substrate truth is sound
- do not smuggle architecture changes into a "cleanup" pass

### 4. Integrate by seam, not by full reread

After parallel work lands, do a seam acceptance pass focused on:

- overlap files,
- additive contract changes,
- replay/persistence truth,
- protocol/shared helper reuse,
- UI/API surfaces that may still be reading old summary-shaped data.

Look first for:

- completion-path asymmetry,
- replay loss,
- stale duplicated logic,
- accidental second sources of truth,
- cleanup that removed a surface but left the old semantics alive elsewhere.

### 5. Prove behavior with a clean-room smoke

- Do not trust an existing local stack by default.
- Confirm the running image/container state actually matches the source wave being evaluated.
- For end-to-end verification, prefer a fresh-state smoke:
  - rebuild the image,
  - isolate or clear disposable runtime state,
  - prove there are no inherited colonies or old knowledge artifacts,
  - then run the smoke task.
- Record whether the smoke is testing:
  - code as written,
  - code as deployed,
  - or an older still-running image.

### 6. Separate acceptance from follow-up polish

- If the substrate is truthful and replay-safe, accept it as such even if the UI still needs a cleanup pass.
- Classify leftover issues explicitly:
  - blocker,
  - product-surface debt,
  - tuning debt,
  - docs debt,
  - deployment/runtime debt.
- Do not collapse all remaining imperfections into "wave failed."

### 7. Use what the wave proved to shape the next one

- Future-wave planning should build on what was actually validated, not just what was intended.
- Remove already-fixed debt from future-wave scope instead of carrying it forward by habit.
- When a wave proves the substrate but exposes surface confusion, the next wave should start by making the substrate legible.
- Prefer sequencing that leaves the system useful at each boundary.
- While the current wave is still in progress, future-wave plans should usually stay provisional until the real leftovers are known.

## Validation truth rules

When reporting status or forming roadmap conclusions:

- Distinguish source-tree truth from running-stack truth.
- Distinguish generated artifacts from uploaded files and shared workspace files.
- Distinguish summary fields from full-output fields.
- Distinguish live-only state from replay-safe persisted state.
- If Docker was not rebuilt, say so explicitly before interpreting UI behavior.
- If a smoke used fresh volumes or a new data root, say so explicitly.

## Hard constraints

IMPORTANT: These are non-negotiable. Violating any of these requires operator approval.

1. Read `docs/contracts/` before modifying any interface.
2. Read `docs/decisions/` before making architectural choices.
3. If your change contradicts an ADR, STOP and flag the conflict.
4. Never modify files outside your ownership list (see `AGENTS.md`).
5. Event types are a CLOSED union -- adding types requires an ADR with operator approval.
6. <=20K LOC soft limit on `core/` + `engine/` + `adapters/` + `surface/` combined. Exceeding requires justification, not blocking.
7. Every state change is an event. No shadow databases. No second stores.
8. Feature flags wrap incomplete work. Merge to main frequently.
9. Knowledge confidence uses Beta(alpha, beta) posteriors evolved by Thompson Sampling. Do not replace with scalar confidence or heuristic scoring.
10. Workflow steps are Queen scaffolding, not an execution pipeline. The Queen always decides whether to proceed.
11. The Queen system prompt's tool inventory is programmatically assembled from `tool_specs()` (the full tool surface: handlers + special-cased + addon tools). Do not manually edit the tool list in `caste_recipes.yaml`.
12. UI components MUST NOT hardcode governance defaults. Read from `runtimeConfig.governance.*` or workspace config props.
13. Prefer computed introspection over hardcoded counts in documentation and UI. Never hardcode what can be derived.

## Prohibited alternatives

| Instead of... | Use... | Why |
|-------------|------|-----|
| msgspec, dataclasses for events | Pydantic v2 | Sole serialization library, project-wide |
| `print()` | `structlog` | Structured logging only |
| Post-alpha doc imports (self-evolving, geometric intelligence, etc.) | Nothing | Not yet approved for use |
| New dependencies | Existing deps | Requires operator approval; check `pyproject.toml` |
| Deleting/disabling tests | Fixing the code | Tests document contracts |
| Scalar confidence fields | Beta(alpha, beta) posteriors | Bayesian confidence is the system of record (ADR-039) |
| Direct step execution | Queen-mediated continuation | Steps are guidance, not a pipeline runner |

## Key paths

| Path | Purpose | Modify? |
|------|---------|---------|
| `docs/contracts/` | Integration seams (events.py, ports.py, types.ts) | NO -- operator approval required |
| `docs/decisions/` | ADRs (001-051, see INDEX.md) | Read before architectural choices |
| `docs/specs/` | Current-state implementation references (8 specs, Wave 59) | Canonical subsystem docs |
| `docs/waves/PROGRESS.md` | Wave progress | Update when completing work |
| `docs/DEPLOYMENT.md` | Deployment guide: clone to running stack | Deployment truth |
| `docs/KNOWLEDGE_LIFECYCLE.md` | Knowledge system operator runbook | Reference for knowledge changes |
| `AGENTS.md` | File ownership + coordination rules | Read before writing any code |
| `surface/knowledge_catalog.py` | Federated knowledge retrieval + Thompson Sampling | Key knowledge path |
| `surface/maintenance.py` | Dedup, stale sweep, contradiction, confidence reset | Maintenance handlers |
| `surface/transcript.py` | Colony transcript assembly | Transcript search source |
| `surface/queen_runtime.py` | Queen orchestration (2300+ lines) | Follow_up, thread context, tools |
| `surface/colony_manager.py` | Colony lifecycle, step continuation | Core execution path |
| `surface/credential_scan.py` | Credential scanning + redaction (detect-secrets) | Security pipeline |
| `surface/trust.py` | Bayesian peer trust scoring (10th percentile) | Federation trust |
| `surface/conflict_resolution.py` | Pareto + adaptive threshold conflict resolution | Federation conflicts |
| `surface/federation.py` | Federation protocol (push/pull replication) | Federation |
| `core/crdt.py` | CRDT primitives + ObservationCRDT | Federation data model |
| `surface/forager.py` | Forager cycle orchestration, query templates, admission bridge | Web foraging |
| `adapters/egress_gateway.py` | Controlled HTTP egress with rate/domain/size limits | Web foraging |
| `adapters/fetch_pipeline.py` | Graduated fetch + content extraction (Level 1-2) | Web foraging |
| `adapters/content_quality.py` | Deterministic content-quality scoring (no LLM) | Web foraging |
| `adapters/web_search.py` | Pluggable web search adapter | Web foraging |
| `surface/self_maintenance.py` | MaintenanceDispatcher, autonomy policy, blast radius, autonomy scoring | Self-maintenance |
| `surface/project_plan.py` | Project plan parser/helper, milestone tools, plan rendering | Project plan |
| `surface/queen_budget.py` | 9-slot proportional Queen context budget (ADR-051) | Queen budget |
| `surface/queen_tools.py` | Queen tool dispatch (~45 tools, dynamic toolsets), spawn_parallel, DelegationPlan | Queen tools |
| `surface/transcript_view.py` | Canonical colony transcript schema | A2A/MCP export |
| `surface/proactive_intelligence.py` | 17 deterministic briefing rules (7 knowledge + 4 performance + evaporation + branching + earned autonomy + template health + outcome digest + popular unexamined) | Proactive intel |
| `surface/routes/api.py` | REST endpoints: outcomes, create-demo, project-plan, autonomy-status, maintenance-policy, add-model | API surface |
| `surface/workflow_learning.py` | Deterministic workflow pattern recognition + procedure suggestions (Wave 72) | Workflow learning |
| `docs/AUTONOMOUS_OPERATIONS.md` | Autonomy operator runbook: action queue, levels, learning, controls | Reference |
| `docs/DEVELOPER_BRIDGE.md` | Developer onboarding guide for Claude Code integration | Reference |
| `surface/mcp_server.py` | MCP server (29 tools, 12 resources, 8 prompts) | MCP surface |
| `config/templates/demo-workspace.yaml` | Demo workspace template with seeded entries | Demo path |
| `surface/workspace_roots.py` | Project/library/runtime root resolution (Wave 81) | Project binding |
| `surface/parallel_plans.py` | Deferred group dispatch, honest plan aggregation (Wave 81) | Parallel execution |
| `surface/planning_signals.py` | Structured planning signal builder (Wave 82) | Planning |
| `surface/structural_planner.py` | File matching, import coupling, grouping hints (Wave 82) | Planning |
| `surface/capability_profiles.py` | Replay-derived capability calibration (Wave 82) | Planning |
| `surface/reviewed_plan.py` | Reviewed-plan validation and normalization (Wave 83) | Planning workbench |
| `surface/plan_patterns.py` | YAML-backed saved plan-pattern store (Wave 83) | Planning workbench |
| `surface/planning_policy.py` | Consolidated routing: `decide_planning_route()` + `PlanningDecision` (Wave 85) | Queen routing |
| `surface/commands.py` | WebSocket command handlers incl. `confirm_reviewed_plan` | WS surface |
| `surface/metering.py` | Token metering, fee computation, attestation generation | Billing |
| `surface/task_receipts.py` | Deterministic task receipts for A2A economic contracts | A2A economics |
| `scripts/attribution.py` | Contributor revenue-share attribution from git history | Billing |
| `docs/waves/wave_81/real_repo_task_pack.md` | Real-repo evaluation tasks (rtp-01 through rtp-05) | Benchmark |

## Common patterns

### Adding a Queen tool

1. Add the tool spec in `tool_specs()` in `queen_tools.py` -- name, description, parameters JSON schema (before the `*self._addon_tool_specs` line).
2. Add the handler in `QueenToolDispatcher.__init__()` `self._handlers` dict in `queen_tools.py` -- maps tool name to an async handler `(inputs, workspace_id, thread_id) -> tuple[str, dict | None]`.
3. The system prompt tool inventory is self-assembled from `tool_specs()` at runtime -- do NOT manually edit the tool list in `caste_recipes.yaml`.

### Adding an agent tool

Five touch points:

1. `engine/tool_dispatch.py` -- Add to `TOOL_SPECS` dict (name, description, parameters JSON schema).
2. `engine/tool_dispatch.py` -- Add to `TOOL_CATEGORY_MAP` (maps tool name to `ToolCategory`).
3. `engine/runner.py` -- Add to `RoundRunner.__init__()` as a new `*_fn` callback parameter, stored as `self._*_fn`.
4. `engine/tool_dispatch.py` -- Add dispatch case in `_execute_tool()` that calls the callback.
5. `surface/runtime.py` -- Add `make_*_fn()` factory method that creates the async callback closure.
6. `config/caste_recipes.yaml` -- Add tool name to relevant castes' tool lists.

### Adding a maintenance handler

1. Create `make_*_handler(runtime)` factory in `maintenance.py` -- returns an async handler function.
2. Register in `app.py` `service_router.register_handler()` block with a `service:consolidation:*` name.
3. Add to `maintenance.py` `__all__`.
