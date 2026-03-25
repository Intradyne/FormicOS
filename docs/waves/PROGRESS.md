# FormicOS v2 -- Wave Progress

**Last updated:** 2026-03-25 -- Wave 65.5 landed (Addons Made Real + Polish). 3640 tests green. Addon runtime context injection, real codebase index + git control, trigger wiring, Queen autonomous agency (36 tools), addon dev guide, polish pass (porcelain parsing, forbidden ops, cron DOW, trigger loop, schema validation).

**Note:** Detailed per-wave docs are on disk through Wave 65. Consolidated numeric metrics further down this file are still historical snapshots from earlier milestones until a dedicated metrics refresh is done.

---

## Current: Wave 65.5 -- Addon Polish Pass

Bug fixes and test hardening for the addon system shipped in Wave 65.
No new features, events, or tools. Six fixes:

1. **Fix 1 -- Git porcelain parsing:** Rewrote auto-stage file detection to
   check worktree column (Y position), handle quoted paths with special
   characters, and correctly skip untracked/ignored files.
   (`addons/git_control/handlers.py`)
2. **Fix 2 -- Forbidden ops safety:** Replaced string-join matching with
   consecutive-arg tuple matching. `push --force` blocked, `log --format=force`
   allowed. Added `push -f` and `clean -fd` variants.
   (`addons/git_control/tools.py`)
3. **Fix 3 -- Git control happy-path tests:** Expanded from 6 error-only tests
   to 34 tests covering smart commit phases, branch analysis strategies,
   create branch, stash operations, auto-stage, and forbidden ops.
   (`tests/unit/addons/test_git_control.py`)
4. **Fix 4 -- Proactive intelligence handler tests:** 13 new tests for
   `handle_query_briefing`, `on_scheduled_briefing`, and
   `handle_proactive_configure` — previously zero direct coverage.
   (`tests/unit/addons/test_proactive_intelligence.py`)
5. **Fix 5 -- Trigger loop dead code:** Removed `elif len >= 3` fallback that
   would call cron handlers with wrong args. Replaced with warning log for
   unsupported handler signatures. (`app.py`)
6. **Fix 6 -- Addon loader guardrails:** Warns on unused manifest fields
   (panels, templates, routes). Validates tool parameter schemas (must have
   `type: object` and `properties`). (`addon_loader.py`)

3640 tests passing (+36 net new). CI: ruff clean, imports clean.

## Previous: Wave 65 -- Addons Made Real + Queen Agency

Seven tracks across three teams. Made addon stubs into real implementations,
wired trigger dispatch, added Queen autonomous agency tools, and shipped
addon developer documentation.

1. **Track 1 -- Addon runtime context:** `register_addon()` accepts
   `runtime_context` dict. Tool and event handler wrappers use
   `inspect.signature()` to detect handlers that accept it. Context includes
   `vector_port`, `embed_fn`, `workspace_root_fn`, `event_store`, `settings`,
   `projections`, `runtime`. (`addon_loader.py`, `app.py`)
2. **Track 2 -- Codebase index made real:** `handle_semantic_search` calls
   `vector_port.search()` for real results. `handle_reindex` triggers
   incremental or full reindex. `on_scheduled_reindex` cron wrapper iterates
   all workspaces. (`addons/codebase_index/search.py`, `indexer.py`)
3. **Track 3 -- Git control made real:** Two-phase smart commit (inspect staged
   diff, then execute). Real `git merge-base` branch analysis. Create branch
   and stash tools. Auto-stage event handler uses `git status --porcelain`.
   (`addons/git_control/tools.py`, `handlers.py`)
4. **Track 4 -- Trigger wiring:** `TriggerDispatcher` instantiated in app
   startup, addon triggers registered, 60s background loop fires cron
   triggers and emits `ServiceTriggerFired` events. `trigger_addon` Queen
   tool for manual trigger firing. Cron DOW fix (Python Mon=0 → cron Sun=0).
   (`app.py`, `trigger_dispatch.py`, `queen_tools.py`)
5. **Track 5 -- Queen autonomous agency:** 4 new Queen tools: `batch_command`
   (sequential command execution, stop-on-error), `summarize_thread`
   (structured thread overview), `draft_document` (file write with
   overwrite/prepend/append), `list_addons` (addon tool/handler inventory).
   MCP chaining guidance in Queen system prompt. (`queen_tools.py`)
6. **Track 6 -- Proactive intelligence polish:** `on_scheduled_briefing` cron
   wrapper. `handle_proactive_configure` tool for per-workspace rule
   enable/disable via `WorkspaceConfigChanged` events.
   (`addons/proactive_intelligence/handlers.py`)
7. **Track 7 -- Addon dev guide + launch docs:** Complete addon development
   guide (addons/README.md, ~300 lines). TEMPLATE addon scaffold with
   manifest + handler examples. README.md updated with current feature list,
   event count (69), tool count (36), and docs table.

Event union: 69 (unchanged). Queen tools: 31 -> 36 (+batch_command,
+summarize_thread, +draft_document, +list_addons, +trigger_addon).
Caste recipes synced to 36 tools. 3599 tests passing pre-polish.

## Previous: Wave 64 -- Parallel Execution + Addon Infrastructure

Eight tracks across three teams. Multi-provider parallel execution (Tracks
1-5) and addon system infrastructure (Tracks 6-8).

1. **Track 1 -- Generalized adapter factory + per-provider concurrency:**
   Adapter keys changed from bare `provider` to `provider:endpoint`,
   enabling multiple endpoints per provider. `max_concurrent` field on
   ModelRecord controls per-model semaphore. Unknown provider prefixes
   with endpoints auto-create OpenAI-compatible adapters.
   (`app.py`, `runtime.py`, `llm_openai_compatible.py`, `core/types.py`)
2. **Track 2 -- Optimistic file locking:** Content-hash locking detects
   concurrent file modification between read and write. Atomic writes via
   temp+`os.replace()` (cross-platform). CONFLICT error on hash mismatch.
   (`engine/runner.py`)
3. **Track 3 -- Queen smart fan-out:** `retry_colony` tool re-spawns failed
   colonies with failure context and optional model/strategy override.
   `propose_plan` enriched with per-provider model availability.
   Colony escalation messages include model suggestion with cost estimate.
   (`queen_tools.py`, `colony_manager.py`)
4. **Track 4 -- Heuristic cloud routing:** Five heuristics for Queen cloud
   routing: message complexity (>500 tokens), `@cloud` tag, propose_plan,
   system token budget (>2000), parse failure auto-escalation. Model badge
   in chat UI. (`queen_runtime.py`, `queen-chat.ts`)
5. **Track 5 -- UI parallel execution dashboard:** Provider cost breakdown
   in budget panel. Plan progress bar with colored segments (done/active/
   pending). Provider health REST endpoint.
   (`budget-panel.ts`, `queen-overview.ts`, `routes/api.py`)
6. **Track 6a -- Addon loader:** 3 new events (#67-69): AddonLoaded,
   AddonUnloaded, ServiceTriggerFired. Manifest parser, handler resolver,
   component registration. Hello-world addon. Queen tool integration via
   `_addon_tool_specs`. (`addon_loader.py`, `core/events.py`, `app.py`)
7. **Track 6b -- Proactive intelligence extraction:** 1980-line module
   extracted to `formicos/addons/proactive_intelligence/rules.py`. 52-line
   backward-compatible shim at `surface/proactive_intelligence.py`.
8. **Track 7 -- Trigger dispatch + codebase index:** Built-in cron parser,
   TriggerDispatcher with double-fire prevention. Codebase index addon with
   structural chunking and incremental reindex (search is v1 placeholder).
   (`trigger_dispatch.py`, `addons/codebase-index/`)
9. **Track 8 -- Git control addon:** Smart commit context, branch analysis,
   auto-stage handler (v1 stubs). (`addons/git-control/`)

Event union: 66 -> 69 (+AddonLoaded, +AddonUnloaded, +ServiceTriggerFired).
Queen tools: 30 -> 31 (+retry_colony).
3588 tests passing. CI: ruff clean, imports clean.

## Previous: Wave 63 -- The Queen Remembers, The Operator Controls

Eight tracks: cross-turn tool memory, failed colony notifications, Queen write
tools, negative signal extraction, edit proposal cards, operator knowledge CRUD,
operator workflow step CRUD, and project context seeding.

1. **Track 1 -- Cross-turn tool memory:** Queen tool results persist across
   conversation turns. Previously, tool outputs were lost between turns;
   now the Queen can reference prior search results, command outputs, and
   analysis across the full conversation.
2. **Track 2 -- Failed colony notifications:** Failed colony outcomes surface
   as notifications in the Queen follow-up path. Parallel aggregation collects
   results from concurrent colonies and presents them coherently.
3. **Track 3 -- Queen write tools:** `edit_file`, `run_tests`, and `delete_file`
   tools let the Queen make direct codebase modifications without spawning
   colonies. (`queen_tools.py`, `caste_recipes.yaml`)
4. **Track 4 -- Negative signal extraction:** Anti-pattern and bug knowledge
   entries receive a status bonus during retrieval scoring, ensuring negative
   signals (what NOT to do) surface alongside positive patterns.
5. **Track 5 -- Edit proposal cards + parallel result cards + failure retry:**
   UI gains editable proposal cards, parallel result aggregation cards, and
   failure retry buttons for re-dispatching failed colonies.
   (`proposal-card.ts`, `queen-chat.ts`)
6. **Track 6 -- Operator knowledge CRUD:** Full create/edit/delete lifecycle
   for knowledge entries via REST API and UI. Operators can directly author
   and curate the knowledge base. (`routes/api.py`, frontend components)
7. **Track 7 -- Operator workflow step CRUD:** `WorkflowStepUpdated` event
   (66th event type) enables step creation, editing, reordering, and deletion
   via REST and UI. Steps are no longer immutable after creation.
   (`core/events.py`, `routes/api.py`)
8. **Track 8 -- Project context seeding:** `.formicos/project_context.md`
   files are auto-detected and injected into colony context, giving operators
   a persistent, file-based channel for project-specific instructions.

Event union: 65 -> 66 (+WorkflowStepUpdated).
Queen tools: 27 -> 30 (+edit_file, +run_tests, +delete_file).
3486 tests passing. CI: ruff clean, imports clean, pyright unchanged.

## Previous: Wave 62 -- The Working Queen

Seven tracks: retrieval correctness, outcome-informed proposals, Queen direct
work tools, three-stage intent classification, cloud routing for planning,
stall-based escalation proposals, and registry refactor.

1. **Track 1 -- Retrieval correctness (3 bugs):** Over-fetch multiplier
   increased from 2x to 4x for composite re-ranking (`knowledge_catalog.py`).
   Round-aware knowledge re-fetch using previous round summary as context hint
   (`colony_manager.py`). Stricter 0.60 similarity threshold for untagged
   entries in domain filter (`context.py`).
2. **Track 1.5 -- Outcome-informed proposals:** `outcome_stats()` method on
   projections aggregates colony outcomes by (strategy, caste_mix).
   `propose_plan` now includes empirical basis section citing success rates,
   avg rounds, and avg cost from prior colonies. (`projections.py`,
   `queen_tools.py`)
3. **Track 2 -- Queen direct work tools:** `search_codebase` (grep with regex
   fallback) and `run_command` (allowlisted shell commands: git, pytest, ruff,
   ls, cat, etc.) let the Queen answer codebase questions without spawning
   colonies. Security: command allowlist, metacharacter blocking, no
   shell=True. (`queen_tools.py`, `caste_recipes.yaml`)
4. **Track 3 -- Three-stage intent classification:** Queen system prompt
   rewritten to 3-stage flowchart (CLASSIFY -> CAN YOU ANSWER DIRECTLY ->
   IS THIS COLONY WORK). Intent parser gains `_DIRECT_WORK_RE` category.
   DIRECT_WORK is the preferred action mode; SPAWN is the escalation path.
   (`caste_recipes.yaml`, `queen_intent_parser.py`)
5. **Track 4 -- Cloud routing for planning:** `queen_planning_model` workspace
   config routes `propose_plan` follow-up LLM calls to a cloud model. Opt-in
   only, default stays local. (`queen_runtime.py`)
6. **Track 5 -- Stall-based escalation proposals:** When a colony stalls (0
   productive tool calls over multiple rounds), emits
   `ColonyChatMessage(event_kind="escalation_proposal")` suggesting cloud
   retry. Proposal only -- operator decides. (`colony_manager.py`)
7. **Track 6 -- Registry refactor (Addon Phase 0):** `QueenToolDispatcher`
   dispatch replaced 23-branch if/elif chain with `_handlers` dict registry.
   `formicos-app.ts` `renderView()` replaced switch with `_viewRegistry`
   component map. Net-negative LOC. (`queen_tools.py`, `formicos-app.ts`)

Queen tools: 25 -> 27 (+search_codebase, +run_command). 15 new tests.
24 files changed, +1680 / -302 lines.

## Previous: Wave 61 -- Queen Deliberation + Operator Visibility

Five tracks: deliberation mode, proposal cards, analytical tools, workspace
browser, and budget panel.

1. **Track 1 -- Deliberation mode:** `propose_plan` tool with runtime-computed
   cost estimates. Safety net in `queen_runtime.py` intercepts spawn calls when
   operator message matches `_DELIBERATION_RE`, rewrites to propose_plan.
   (`queen_tools.py`, `queen_runtime.py`, `queen_intent_parser.py`,
   `caste_recipes.yaml`)
2. **Track 2 -- Proposal card UI:** `<fc-proposal-card>` component with "Go
   ahead" / "Let me adjust" actions. `queen-chat.ts` renders on
   `render="proposal_card"`. (`proposal-card.ts`, `queen-chat.ts`, `types.ts`)
3. **Track 3 -- Analytical tools:** `query_outcomes` (colony outcomes with
   filtering/sorting), `analyze_colony` (deep single-colony analysis),
   `query_briefing` (proactive intelligence drill-down). (`queen_tools.py`,
   `caste_recipes.yaml`)
4. **Track 4 -- Workspace browser:** `<fc-workspace-browser>` component with
   file tree. Workspace tab in nav. Colony detail gains "Files Changed"
   section. (`workspace-browser.ts`, `formicos-app.ts`, `colony-detail.ts`)
5. **Track 5 -- Budget panel:** `GET /api/v1/workspaces/{id}/budget` endpoint.
   `<fc-budget-panel>` with per-model spend breakdown and utilization bar.
   (`routes/api.py`, `budget-panel.ts`, `queen-overview.ts`)

Queen tools: 21 -> 25 (+propose_plan, +query_outcomes, +analyze_colony,
+query_briefing). 20 new tests.

## Previous: Wave 60.5 -- UX Cockpit Pass + Reasoning Token Accounting

Seven UX tracks plus reasoning/cache token pipeline:

1. **Queen deliberation mode** — Two-pass intent parser (regex + Gemini) gains
   DELIBERATE category. Queen system prompt enforces deliberation-first, no
   skip-preview escape hatch. (`queen_intent_parser.py`, `caste_recipes.yaml`)
2. **Dashboard-first layout** — Chat rail collapsed by default with FAB toggle.
   Dashboard is the landing surface. (`formicos-app.ts`, `queen-overview.ts`)
3. **Colony artifact viewer** — Artifacts tab on colony detail, lazy-fetched
   from existing REST endpoint. (`colony-detail.ts`)
4. **Resource grid overhaul** — API Spend, Local Compute, Per-Provider
   breakdown cards replace single-metric cards. (`queen-overview.ts`)
5. **Settings editor** — Governance settings editable (strategy, max rounds,
   budget, convergence, autonomy) with save to config-overrides. (`settings-view.ts`)
6. **Provider recognition fix** — `providerOf()` expanded from 2 to 8 providers.
   Model registry grouped by provider with collapsible sections. (`helpers.ts`,
   `model-registry.ts`)
7. **Model registry update** — 51 active entries across 9 providers (OpenAI,
   Anthropic, Gemini, DeepSeek, MiniMax, Mistral, Groq, Ollama, llama-cpp)
   with verified March 2026 pricing. (`formicos.yaml`)

**Reasoning/cache token pipeline** — `reasoning_tokens` and `cache_read_tokens`
fields added through the full stack: LLMResponse → TokensConsumed event →
runner accumulation → BudgetSnapshot projections → REST API → dashboard.
Covers OpenAI o-series/GPT-5.4, DeepSeek reasoner, Gemini thinking, Anthropic
cache reads. All default=0, replay-safe.

## Previous: Wave 59.5 -- Knowledge Graph Bridge + Progressive Disclosure Fix

Three parallel teams: (1) entry-node bridge linking memory entries to KG
nodes via `emit_and_broadcast()`, (2) graph-augmented retrieval with 7-signal
composite scoring (`graph_proximity` at 0.06 weight), (3) auto-inject top-1
full content (~200 tokens) to fix Phase 1 v1's 0 `knowledge_detail` calls.
Phase 1 v2 validates the full stack: curating archivist + graph retrieval +
multi-provider routing. Event union stays at 65.

---

## Waves 36-59 (Hardening → Evaluation → Curation)

- **Wave 36 -- The Glass Colony:** first publicly-ready version. Demo workspace with seeded knowledge, outcome badges, scheduled knowledge refresh.
- **Wave 37 -- The Hardened Colony:** foundation hardening for external trust. Stigmergic loop closure, measurement infrastructure, poisoning defenses.
- **Wave 38 -- The Ecosystem Colony:** NemoClaw + A2A integration, internal benchmarking, bi-temporal knowledge graph. Event union stays at 55.
- **Wave 39 -- The Supervisable Colony:** operator becomes durable co-author. Cognitive audit trail, editable hive state, governance-owned adaptation. Event union 55 → 58.
- **Wave 40 -- The Refined Colony:** health pass — no new features, only refinement. Code coherence, speed, testing, failure mode elimination.
- **Wave 41 -- The Capable Colony:** real-world coding power. Mathematical bridge-tightening, production capability for codebases and test suites.
- **Wave 42 -- The Intelligent Colony:** research synthesis at existing seams. Adaptive evaporation, non-LLM intelligence. No new event types.
- **Wave 43 -- The Hardened Colony:** production architecture. Container hardening, persistence rules, budget governance, deterministic testing, docs truth.
- **Wave 44 -- The Foraging Colony:** web acquisition as second compounding source. EgressGateway, fetch pipeline, content quality, search adapter, ForagerService. Event union 58 → 62.
- **Wave 45 -- The Complete Colony:** consolidation — proactive foraging wired through maintenance, competing-hypothesis surfacing, source-credibility-aware admission.
- **Wave 46 -- The Proven Colony:** visibility + operability + measured honesty. Forager operator surface, evaluation harness, measurement without bias.
- **Wave 47 -- The Fluent Colony:** coding ergonomics and execution fluency. File editing improvements, fast-path execution, structural context refresh.
- **Wave 48 -- The Operable Colony:** composition and grounding. Specialist castes grounded, thread/colony/knowledge/forager stories connected.
- **Wave 49 -- The Conversational Colony:** Queen chat as primary orchestration surface. Chat-first task entry, inline plan viewing, progress monitoring.
- **Wave 50 -- The Learning Colony:** system improves through experience. Template auto-learning, cross-workspace knowledge sharing, thread compaction.
- **Wave 51 -- Final Polish / UX Truth:** intentionally finished product surface. Durable capabilities made durable, degraded state visible, truth over silence.
- **Wave 52 -- The Coherent Colony:** system describes itself consistently. Control-plane truth, intelligence reach, learning loop visibility. Event union 62 → 64.
- **Wave 53 -- Benchmark Contract:** Phase 0 readiness. Benchmark conditions locked, task calibration, clean-room verification.
- **Wave 54 -- Quality Audit:** gap analysis before Phase 0 evaluation. Reference prompts, Phase 0 v2 preparation.
- **Wave 55 -- Truth-First UX:** progress detection truth (end stall misclassification), operator visibility of existing intelligence, provider/model improvements.
- **Wave 56 -- Semantic Threshold + Extraction Tuning:** threshold optimization, common-mistakes anti-pattern injection, generation stamping. Phase 0 v7: mean quality 0.688 (+0.177 from v4).
- **Wave 57 -- Phase 0 v9 Analysis:** honest interpretation — absolute quality improved dramatically, but compounding signal flat within noise. Quality gains from operational knowledge (playbooks, progress detection, coder model), not domain retrieval.
- **Wave 58 -- Integration:** specificity gate, trajectory storage, progressive disclosure. Three parallel coder teams. Event union stays at 64.
- **Wave 59 -- Knowledge Curation:** append-only → curating archivist (CREATE/REFINE/MERGE/NOOP). Archivist sees existing entries before deciding. MemoryEntryRefined event (65th). Phase 1 v1: 19 cross-task accesses, 1 REFINE observed, 0 knowledge_detail calls.

## Waves 16-35 (Alpha → Self-Maintaining)

- **Wave 16 -- Operator Control:** bug fixes, rename cleanup, playbook/template authoring improvements, colony file I/O, export, and smoke polish.
- **Wave 17 -- Nothing Lies:** runtime truth, safe evolution, truthful displays, validated controls, and local inference tuning.
- **Wave 18 -- Eyes and Hands:** the Queen gained stronger read tools, safe config proposals, and larger local-context support.
- **Wave 19 -- The Queen Steers:** strategic steering, safe carry-forward of results, and human-approved learning.
- **Wave 20 -- Open + Grounded:** external agent discovery/streaming/tool-calling, real colony code execution, and more truthful operator surfaces.
- **Wave 21 -- Alpha Complete:** the system became more mechanically self-describing, the Queen became a stronger interface, and stigmergy became testable with real artifacts.
- **Wave 22 -- Trust the Product:** better Queen decisions, scratch-memory isolation, and more truthful, usable UI surfaces.
- **Wave 23 -- Operator Smoothness + External Handshake:** smoother alpha operation, improved Queen behavior, and a cleaner inbound external-task lifecycle.
- **Wave 24 -- Trust the Surfaces:** operator numbers, labels, and controls were tightened so they mean exactly what they say, with stronger external-task observability.
- **Wave 25 -- Typed Transformations:** colonies started producing typed artifacts, templates gained task-contract semantics, and the Queen began reasoning about transformations instead of only teams.
- **Wave 26 -- Institutional Memory:** colonies began producing durable, provenance-carrying knowledge entries that survive restart and can be retrieved by future colonies.
- **Wave 27 -- Unified Knowledge Workflow:** operator, Queen, and API surfaces converged on one unified knowledge catalog over institutional memory plus legacy skills.
- **Wave 28 -- Knowledge Runtime Unification:** agents were bridged onto the unified knowledge catalog, `KnowledgeAccessRecorded` made access traces replay-safe, progressive disclosure began with `knowledge_detail` and `artifact_inspect`, and legacy skill writes/confidence updates were disabled.
- **Wave 29 -- Workflow Threads:** threads gained goals, completion status, and thread-scoped knowledge. Service colonies gained deterministic handlers (registered Python callables dispatched through `ServiceRouter` without LLM spend). First maintenance services: dedup consolidation and stale sweep. Event union 41 → 45.
- **Wave 30 -- Knowledge Metabolism:** Bayesian confidence (Beta distribution alpha/beta) on `MemoryEntry`, Thompson Sampling for explore/exploit retrieval ranking, workflow steps as Queen scaffolding on threads, thread archival with confidence decay, contradiction detection, LLM-confirmed dedup extension, scheduled maintenance timer, legacy skill system fully deleted. Event union 45 → 48. ADR-039 supersedes ADR-010 fully and ADR-017 partially.
- **Wave 31 -- Ship Polish:** the system became more demonstrable. Workflow steps auto-continued, transcript search landed for agents, post-30 docs were refreshed, and edge cases that would embarrass a demo were hardened without new contracts.
- **Wave 32 -- Knowledge Tuning + Structural Hardening:** gamma-decay and structural cleanup landed. Replay idempotency became an explicit invariant, and the post-30 system was hardened rather than expanded.
- **Wave 33 -- Intelligent Federation:** transcript harvest, inline dedup, prediction-error detection, structured errors, MCP resource/prompt surfaces, credential scanning, and bidirectional computational-CRDT federation all became first-class.
- **Wave 34 -- Ship Ready:** proactive intelligence, tiered retrieval auto-escalation, confidence visualization, co-occurrence scoring, and operator-facing knowledge/federation dashboards made the system explainable to non-builders.
- **Wave 35 -- The Self-Maintaining Colony:** the Queen gained parallel planning, proactive insights could dispatch maintenance work under policy, knowledge clusters could be distilled, operator directives could steer live colonies, and reasoning became more explainable.

## Historical Detail (Phases 0-15)

## Phase 0 -- Repo Bootstrap

CLAUDE.md, AGENTS.md, pyproject.toml, directory structure, lint_imports.py, CI pipeline, Dockerfile, docker-compose.yml, ADRs 001-006, contract stubs, 5 executable specs, config files.

## Phase 1 -- UI Prototype

Interactive React prototype (7 views, Void Protocol design system, merge/prune/broadcast controls). Frontend build chain (Vite + Lit shell). Prototype at `docs/prototype/ui-spec.jsx`.

## Phase 2 -- Architecture Lock

Frozen contracts: `events.py` (22-event Pydantic union), `ports.py` (5 Protocol interfaces), `types.ts` (full TS mirror with typed WS commands). Algorithm spec in `algorithms.md`. Wave plans 01-07. Expanded specs to 12 `.feature` files covering S1-S9.

## Wave 1 -- Core Types + Config + Scaffold

- **Stream A:** `core/types.py` (15 models), `core/events.py` (22 events), `core/ports.py` (5 protocols), `core/__init__.py`
- **Stream G:** `core/settings.py` (config loading with env interpolation)
- **Stream H:** `__main__.py` (CLI stubs), contract bootstrap tests, pytest-bdd scaffold
- **81 tests**, ruff clean, pyright strict clean, layer lint clean

## Wave 2 -- Adapters + Engine

- **Stream B:** `adapters/store_sqlite.py` (WAL, append/query/replay), `adapters/vector_lancedb.py` (async wrapper, injected embed_fn)
- **Stream C:** `adapters/llm_anthropic.py` (Messages API, tool use, SSE, retry), `adapters/llm_openai_compatible.py` (chat/completions, configurable base_url)
- **Stream E:** `engine/runner.py` (5-phase loop, convergence, governance, pheromone update), `engine/context.py` (priority-ordered assembly, token trimming), `engine/strategies/sequential.py`, `engine/strategies/stigmergic.py` (DyTopo routing)
- Gate 5 fixes applied: pheromone update wired into run_round, convergence progress formula corrected, cost/tool accounting plumbed, store_sqlite query signature narrowed
- **113 tests**, all gates green

## Waves 3-5 -- Surface Layer (Stream F, Terminal 1)

- `surface/projections.py` (420 LOC) -- ProjectionStore, 22 event handlers
- `surface/view_state.py` (236 LOC) -- OperatorStateSnapshot builder
- `surface/mcp_server.py` (228 LOC) -- 12 FastMCP tools
- `surface/ws_handler.py` (171 LOC) -- WS subscribe, fan-out, command dispatch
- `surface/app.py` (182 LOC) -- Starlette factory, adapter wiring, lifespan replay, first-run bootstrap
- `surface/commands.py` (235 LOC) -- 9 WS command handlers
- `surface/view_models.py` (112 LOC) -- Colony detail, approval queue, round history
- `surface/config_endpoints.py` (101 LOC) -- Config mutation, model assignment
- `surface/model_registry_view.py` (70 LOC) -- Registry status derivation
- Surface total: ~1,750 LOC source + ~500 LOC tests
- **148 tests** at Stream F completion

## Waves 3-5 -- Frontend (Stream D, Terminal 2)

- 19 custom elements across 14 component files + transport + state store
- Void Protocol design system (shared.ts tokens, atoms.ts primitives)
- WebSocket client with auto-reconnect, reactive state store
- All 7 views: Queen overview, colony detail, thread view, workspace config, model registry, castes, settings
- Auto-subscribe to workspaces on connect, workspace-scoped command routing
- Frontend total: 2,262 LOC source, 100.83 KB bundle (25.14 KB gzip)
- `npm run build` clean

## Waves 6-7 -- Integration + Hardening (Stream I, Terminal 3)

- All 12 `.feature` files enabled in test_specs.py
- 42 feature scenarios with real ProjectionStore + handle_command assertions
- Contract parity tests (Python <-> TypeScript event/field alignment)
- LOC elegance guideline (~15K target for core+engine+adapters+surface)
- Layer boundary test (AST-based import analysis)
- Restart recovery test (SQLite store survives close/reopen)
- **350 tests total**, all green, layer lint clean

## Backend Completion Pass (2026-03-12)

- **Runtime service layer** (`surface/runtime.py`): single `emit_and_broadcast()` mutation path, LLMRouter, model cascade resolution, agent building
- **Queen orchestration** (`surface/queen_runtime.py`): LLM loop with tool execution (`spawn_colony`, `get_status`, `kill_colony`), up to 3 tool iterations
- **Colony lifecycle** (`surface/colony_manager.py`): `asyncio.Task` per colony, round loop, governance termination, best-effort rehydration on restart
- **MCP/WS parity** (ADR-005): both paths schedule Queen responses and colony starts identically
- **ModelAssignmentChanged emission:** `update_config` emits correct event for caste model overrides
- **Workspace/thread creation:** unified in Runtime, used by MCP, WS, and first-run bootstrap
- Ollama `/v1` endpoint fix (`_ensure_v1` in `app.py`)
- Config defaults changed to `llama-cpp/gpt-4` (local-first via llama.cpp alias)
- Unicode caste icons and prototype colors in `view_state.py`
- `projections.py` `_on_model_assignment_changed` now updates workspace config
- First-run bootstrap uses Runtime operations
- Docker multi-stage build: Node frontend + Python runtime, health check, `.env` optional

## Documentation

- `README.md`: full project README with quick start, architecture, and status
- `CONTRIBUTING.md`: developer guide with setup, testing, and extension instructions
- `docs/ARCHITECTURE.md`: one-page architecture overview
- `docs/LOCAL_FIRST_QUICKSTART.md`: detailed local-first setup guide
- Wave summaries: `wave_01` through `wave_10`
- `frontend/CHANGELOG.md` with per-wave component inventory and bundle stats
- All ADRs current through ADR-039

---

## Historical Metrics (as of Wave 10)

| Metric | Value |
|--------|-------|
| Python source LOC (core+engine+adapters+surface) | ~5,000+ |
| Frontend source LOC | ~2,600+ |
| Total tests | 672 |
| Feature scenarios | 57+ (19 `.feature` files) |
| Contract tests | 3 suites (event parity, TS sync, LOC elegance) |
| Event types | 22 (closed union — opens in Wave 11) |
| MCP tools | 12 |
| WS command types | 9 |
| Frontend components | 20 |
| Runtime dependencies | 14 |
| LLM providers | 3 (llama.cpp, Anthropic, Gemini) |
| Docker smoke gates | 30/30 + 3/4 advisory |

---

## CI Gates

All gates pass:
1. `ruff check src/` -- clean
2. `pyright src/` -- 0 errors (strict)
3. `python scripts/lint_imports.py` -- 0 layer violations
4. `pytest` -- 672 tests green
5. `npm run build` -- clean
6. LOC elegance within target
7. Docker/smoke gates green through Wave 10

## Known Limitations (Alpha)

- Queen LLM loop is wired and schedules autonomously from both MCP and WS, but requires a running LLM endpoint (Ollama or Anthropic API key)
- Queen tool-calling reliability remains model-dependent on weaker local models; smoke tests treat Queen spawn as advisory, not a hard acceptance gate
- Sandbox execution port is defined but has no adapter implementation
- AG-UI and A2A protocols are interface-only (adapter + discovery status)
- Embedding model downloads on first boot (~100MB), adding to startup time
- Docker image is large (~4GB) due to PyTorch/CUDA dependencies from sentence-transformers
- Colony rehydration is best-effort: pheromone weights and round summaries are lost on restart
- Gemini provider requires `GEMINI_API_KEY`; without it, Gemini models show `no_key` status (graceful degradation)

---

## Wave 8 -- Close the Loop (2026-03-13)

Closed the colony feedback loop: agents now learn from past work, cost tracks against real model rates, and quality scoring gives a fitness signal per colony.

- **T1-A -- Tools + Crystallization:** Agent tool call loop in `engine/runner.py` (`memory_search`, `memory_write`, `MAX_TOOL_ITERATIONS=3`). Skill crystallization in `surface/colony_manager.py` -- LLM extracts 1-3 transferable skills at colony completion, stored in `skill_bank` LanceDB collection. `ColonyCompleted.skills_extracted` carries the real count. Tiered context assembly in `engine/context.py` with per-source caps, compaction, edge-preserving truncation. `caste_recipes.yaml` cleaned to match live tool handlers.
- **T1-B -- Cost + Quality + Wiring:** Real cost tracking via `cost_fn` built from model registry rates. Budget enforcement kills overspending colonies. Quality scoring via weighted geometric mean of round efficiency, convergence, governance warnings, and stall ratio. Stored on `ColonyProjection.quality_score`. `formicos.yaml` gains `context` section and per-model cost rates.
- **T2 -- Frontend:** `qualityScore` and `skillsExtracted` in state snapshot. Quality dot (green/amber/red/gray) on colony cards. Skills badge. Cost renders real values.
- ADRs 007-011 written and current
- Docker/smoke test validated end-to-end
- **504 tests**, all green, all CI gates pass

## Wave 9 -- Smart Routing + Living Skills (2026-03-13)

See `docs/waves/wave_09/plan.md` for dispatch and `docs/waves/wave_09/algorithms.md` for implementation reference.

- **T1 -- Compute Router:** ADR-012 implemented in `surface/runtime.py`, `engine/runner.py`, `core/settings.py`, and `config/formicos.yaml`. Caste x phase routing is now config-driven, local-first, budget-aware, and logs `compute_router.route` decisions with explicit reason codes. `AgentTurnStarted.model` reflects the routed model, not the static assignment.
- **T2 -- Skill Lifecycle:** `engine/context.py` now performs composite skill retrieval using semantic similarity, confidence, and freshness. `assemble_context()` returns messages plus `retrieved_skill_ids`. New `surface/skill_lifecycle.py` handles ingestion quality gates, confidence updates, and skill bank summaries. `surface/colony_manager.py` logs `colony_observation` and updates retrieved skill confidence on colony success/failure.
- **T3 -- Snapshot + Frontend:** `view_state.py` and `ws_handler.py` now surface `skillBankStats` and per-colony `modelsUsed`. The frontend shows routing badges (local/cloud/mixed), skill bank summary stats, and routed model context in colony detail. Store wiring updated to carry the new snapshot fields.
- **Integration hardening:** Colony-scoped agent IDs prevent cross-colony collisions. Wave 9 Docker smoke gate now uses deterministic WS colony spawns for hard gates and treats Queen tool-calling as advisory when running on weaker local models.
- ADR-012 written and current
- 2 new `.feature` specs: `compute_routing.feature`, `skill_lifecycle.feature`
- Docker/smoke test green: 24 hard gates + 1 advisory passed, exit code 0
- **579 tests**, ruff clean, pyright 0 errors, layer lint clean, frontend build clean

## Wave 10 -- Real Infrastructure (2026-03-14)

Replaced placeholder infrastructure with production components. Qdrant replaced LanceDB for vector storage. Gemini added as third LLM provider. Defensive structured-output parsing hardened all three adapters. Frontend gained skill browser and 3-provider routing visualization.

- **T1 -- Qdrant Migration:** `adapters/vector_qdrant.py` implements VectorPort via `qdrant-client` v1.16+ (`query_points()` API). Single `skill_bank` collection with payload-filtered multitenancy (`namespace` as tenant-indexed field). Payload indexes on confidence, algorithm_version, extracted_at, source_colony, and source_colony_id. Config-driven embedding dimensions. Graceful degradation (empty results on Qdrant failure). Feature flag `vector.backend: "qdrant"` in formicos.yaml. Migration script `scripts/migrate_lancedb_to_qdrant.py` transfers data with zero re-embedding. LanceDB retained as fallback.
- **T2 -- Gemini + Output Hardening:** `adapters/llm_gemini.py` implements LLMPort via raw httpx to Gemini generateContent API. `adapters/parse_defensive.py` provides 3-stage tool-call parser (native JSON → json_repair → regex extraction) used by all three adapters. Handles `<think>` tags, markdown fences, string-args bug, hallucinated tool names (fuzzy match). Gemini `thoughtSignature` round-trip preserved. RECITATION/SAFETY blocks surface as `finish_reason: "blocked"` with fallback chain. Routing table updated: researcher and archivist route to `gemini/gemini-2.5-flash`. Model registry includes gemini-flash and gemini-flash-lite with pricing.
- **T3 -- Skill Browser + Frontend:** `GET /api/v1/skills` REST endpoint. `skill-browser.ts` Lit component with confidence bars, sort controls, empty state. 3-color routing badges (green/blue/amber for local/Gemini/Claude) on colony cards and detail view. Colony auto-navigation on creation. Compatibility layer for `source_colony` / `source_colony_id` field mismatch.
- Qdrant healthcheck fixed: `bash -c 'echo > /dev/tcp/localhost/6333'` (container lacks curl)
- ADRs 013-014 written and current
- 2 new `.feature` specs: `qdrant_migration.feature`, `gemini_provider.feature`
- Docker/smoke test green: 30/30 gates passed, 3/4 advisory (Gemini `no_key` expected)
- **672 tests**, ruff clean, pyright 0 errors, layer lint clean, frontend build clean
- New dependencies: `qdrant-client>=1.16`, `json-repair>=0.30` (14 total runtime deps)


## Wave 11 -- The Skill Bank Grows Up (2026-03-14)

Opened the event union (22 → 27), upgraded skill confidence to Beta distribution, added LLM-gated deduplication, shipped colony templates, Queen colony naming, and suggest-team. Two phases with 3 parallel coders each.

- **Phase A T1 -- Event Union + Projections:** `core/events.py` expanded from 22 to 27 events (`ColonyTemplateCreated`, `ColonyTemplateUsed`, `ColonyNamed`, `SkillConfidenceUpdated`, `SkillMerged`). `surface/projections.py` handlers for all 5 new events. `TemplateProjection` model with use_count tracking. `ColonyProjection.display_name` field. `frontend/src/types.ts` mirrors all 5 event interfaces plus `TemplateInfo`, `SuggestTeamEntry`, `SkillEntry` with `conf_alpha`/`conf_beta`. Contract parity tests updated.
- **Phase A T2 -- Bayesian Confidence:** `surface/skill_lifecycle.py` migrates flat ±0.1 confidence to Beta distribution (`conf_alpha`, `conf_beta`, `conf_last_validated` in Qdrant payloads). `engine/context.py` adds UCB exploration bonus to composite scoring (0.50 semantic + 0.25 confidence + 0.20 freshness + 0.05 exploration). `surface/colony_manager.py` emits `SkillConfidenceUpdated` event per colony completion. `/api/v1/skills` returns alpha, beta, uncertainty.
- **Phase A T3 -- LLM Dedup:** New `adapters/skill_dedup.py` with `decide_action()` (two-band: ≥0.98 NOOP, [0.82,0.98) LLM classify, <0.82 ADD), `classify()` (ADD/UPDATE/NOOP via Gemini Flash), `merge_texts()` (LLM combines skills), `combine_betas()` (additive merge minus shared prior). `skill_lifecycle.py` ingestion path rewired through dedup pipeline.
- **Phase B T1 -- Colony Templates:** New `surface/template_manager.py` with `ColonyTemplate` Pydantic model, YAML file storage in `config/templates/`, immutable versioning, `load_templates()`/`save_template()`/`list_templates()`. REST: `GET/POST /api/v1/templates`, `GET /api/v1/templates/{id}`. Example `config/templates/code-review.yaml` included. `ColonyTemplateCreated` event emitted on save.
- **Phase B T2 -- Naming + Suggest-Team + Commands:** `surface/queen_runtime.py` `name_colony()` with Gemini Flash (500ms timeout, fallback to UUID). `surface/runtime.py` `suggest_team()` via LLM. `surface/commands.py` spawn accepts `templateId`, resolves template defaults, emits `ColonyTemplateUsed`. `surface/app.py` routes: `/api/v1/suggest-team` POST, `/api/v1/templates` GET/POST. `colony_manager.py` schedules naming task after spawn.
- **Phase B T3 -- Frontend:** `colony-creator.ts` 3-step flow (Describe → Configure → Launch) with parallel suggest-team + template fetch, template selection, caste add/remove, budget config. `template-browser.ts` with caste tags, use counts, strategy badges, source colony links, empty state. `skill-browser.ts` upgraded with uncertainty bars, α/β display, merged badges. `types.ts` extended with all Wave 11 types.
- ADRs 015-017 written and current
- 2 new `.feature` specs: `colony_templates.feature`, `skill_maturity.feature`
- All CI gates green


## Wave 12-14 -- Contract Expansion + Safety + Services (2026-03-14)

Expanded event union from 27 to 35 events. Added colony chat (ColonyChatMessage), service colonies (ServiceQuerySent/Resolved, ColonyServiceActivated), code sandbox (CodeExecuted), budget regime injection (ADR-022), per-caste iteration caps and tool permissions (ADR-023), CasteSlot migration. Frontend absorbed all mechanics: per-colony chat with event_kind colors, service colony banner, Colony Creator 4-step flow with tier pills. 34 Wave 14 BDD scenarios. Full Docker smoke verified.

- ADRs 018-023 written and current
- 10 new `.feature` specs: `wave_14_chat_*.feature`, `wave_14_service_*.feature`, `wave_14_budget_regime.feature`, `wave_14_iteration_caps.feature`, `wave_14_tool_permissions.feature`, `wave_14_sandbox.feature`
- **1064 tests**, ruff clean, pyright 0 errors, layer lint clean, frontend build clean


## Wave 15 -- Out of the Box (2026-03-15)

Hardening and productization wave. No contract changes (35 events, 5 ports frozen). Three parallel streams.

- **Stream A -- First-Run and Defaults:** First-run bootstrap emits welcome QueenMessage with getting-started instructions. All 7 built-in templates audited and corrected (CasteSlot format, governance defaults, budget limits). Caste recipes have iteration caps (`max_iterations`, `max_execution_time_s`), tool lists, and temperature/token defaults per caste. `.env.example` and README quickstart updated. `docs/RUNBOOK.md` written with hardware requirements, model downloads, Docker setup, first colony walkthrough, troubleshooting.
- **Stream B -- Shell and UX Polish:** 5-tab nav (Fleet replaces Models + Castes). Click-to-toggle sidebar (no hover). `formicOS v3` branding. Empty states for Queen overview, Thread view, Knowledge view. Budget regime colors on cost ticker (green/yellow/orange/red). Code execution result cards. Connection state indicator (green/yellow/red dot). Frontend build: 184.19 KB (43.60 KB gzip).
- **Stream C -- Smoke and Validation:** Qdrant v1.16.2 verified. Wave 15 config validation BDD harness (5 scenarios). End-to-end colony smoke: 2 colonies completed with real LLM inference (llama-cpp local + Anthropic cloud). Template save and reuse verified. Provider fallback chain verified (Anthropic 401 → Gemini cooldown → llama-cpp). WebSocket event fan-out verified with full colony lifecycle (spawn → rounds → completion).
- **1069 tests**, ruff clean, pyright 0 errors, 0 layer violations, frontend build clean
- Docker: all 4 containers healthy, health endpoint returns `{"status":"ok"}`, frontend bundle matches build

### Smoke Results

| Step | Result |
|------|--------|
| Stack starts cleanly | PASS -- all 4 containers healthy |
| App loads | PASS -- HTML served with correct bundle hash |
| WebSocket connects | PASS -- initial state snapshot received |
| First-run experience | PASS -- welcome QueenMessage, default workspace/thread |
| Templates visible | PASS -- 7 built-in + 1 saved = 8 templates via API |
| Colony spawn | PASS -- 2 colonies completed (6 rounds each) |
| Colony progress | PASS -- chat messages, phase milestones, governance warnings |
| Template reuse | PASS -- ColonyTemplateUsed event emitted on spawn from template |
| Provider fallback | PASS -- Anthropic 401 → Gemini cooldown → llama-cpp |

### Known Limitations

- Legacy skill extraction removed in Wave 30; institutional memory extraction is the sole knowledge write path
- Template `use_count` tracked in-memory projection only (YAML file not updated)
- Colony naming via LLM depends on Gemini Flash availability (falls back to UUID)
- Convergence stall detection triggers on repeated agent output (low-quality local model responses)
- Thompson Sampling makes retrieval non-deterministic by design; tests requiring deterministic ranking must mock `random.betavariate`
- pyright reports ~70 pre-existing `reportUnknownMemberType` / `reportUnknownVariableType` errors (all in surface layer dict-typed code, no regressions)

---

## Historical Metrics (as of Wave 30)

| Metric | Value |
|--------|-------|
| Python source LOC (core+engine+adapters+surface) | ~18,300 |
| Frontend source LOC | ~8,800 |
| Total tests | 1,363 |
| Feature scenarios | 35 `.feature` files |
| Event types | 48 (closed union) |
| Queen tools | 19 (+1 archive_thread in Wave 30) |
| Frontend components | 32 `.ts` files |
| Built-in templates | 7 |
| LLM providers | 3 (llama.cpp, Anthropic, Gemini) |
| Docker containers | 4 (app, LLM, embed, Qdrant) |
| ADRs | 39 (through ADR-039) |
