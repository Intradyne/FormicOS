# FormicOS v2 -- Wave Progress

**Last updated:** 2026-04-01 -- Wave 86 landed. Outcome learning (auto-save candidate patterns from validated success) + graph bridge phase 1 (MODULE nodes, DEPENDS_ON edges, entry-to-module bridging, module-seeded retrieval). 4380 tests green. 70 events. ~45 Queen tools. Unified 35B MoE (5 slots, 160K context). Project binding + 14K-chunk code index live. Wave 85 benchmark baseline: 0.503 avg quality, 5/5, 14 min, 0.836 peak on fast_path.

**Note:** Detailed per-wave docs are on disk through Wave 85. Consolidated numeric metrics further down this file are still historical snapshots from earlier milestones until a dedicated metrics refresh is done.

---

## Current: Wave 86 -- Learn From Validated Success

**Status:** Landed (2 tracks, 4380 tests)
**Theme:** Auto-learning decomposition patterns from validated outcomes + graph bridge phase 1.

### Track A -- Outcome Learning: LANDED.
- `plan_patterns.py`: additive trust fields (`status`, `learning_source`, `evidence`). `verify_outcome()` evaluates quality/validator/productivity/failures. `auto_learn_pattern()` saves candidates from validated success, deduplicates by deterministic bundle, promotes to approved on repeated success.
- `queen_runtime.py`: `_emit_parallel_summary()` calls `verify_outcome()` and `auto_learn_pattern()` on validated completions.
- `planning_signals.py`: approved/operator patterns get +0.1 trust bonus over candidates in retrieval.

### Track B -- Graph Bridge Phase 1: LANDED.
- `indexer.py`: `_post_reindex_graph_reflection()` calls `reflect_structure_to_graph()` after both manual and scheduled reindex.
- `runtime.py`: `_bridge_entry_to_modules()` creates RELATED_TO edges from memory entries to MODULE nodes via structured refs (colony target_files, metadata paths, title file-path patterns).
- `knowledge_catalog.py`: `_resolve_module_seeds()` adds MODULE nodes as PPR graph seeds when queries contain file/module references.
- All best-effort — failures never break reindex or retrieval.

---

## Wave 85 -- Queen Routing and Structural Signal Activation

**Status:** Landed with routing hotfix
**Theme:** Make the planning policy the live routing authority and improve structural signal quality.

### Track A -- Structural Signal Activation: LANDED.
- `structural_planner.py`: phrase-style seed matching (`workspace roots` -> `workspace_roots.py`). Normalization treats `_`, `-`, `.`, `/`, whitespace as equivalent.
- `structural_planner.py`: suppression reasons (no_file_indicators, no_file_matches, low_confidence, analysis_failed) — inspectable in tests and logs.
- `planning_brief.py`: saved-pattern rendering now shows `match=` score always, `q=` only when outcome quality exists, plus match-basis cues.

### Track B -- Live Planning Policy: LANDED.
- `queen_runtime.py`: `decide_planning_route()` is the live routing authority. Replaces scattered `classify_complexity` / `_looks_like_colony_work` / `_prefer_single_colony_route` calls in the routing block.
- `PlanningDecision` drives `_is_colony_turn`, `_prefer_direct_spawn`, `_colony_narrowed`, and directive content.
- `planning_policy.py`: fixed non-colony-work fallthrough and overbroad playbook override.
- Eval harness scores policy decisions, ablation no longer assumes route stability.
- `live_eval` marker registered in pyproject.toml.

### Routing hotfix: LANDED.
- `_prefer_single_colony_route`: file-ref threshold raised from `>1` to `>3` (2-3 file refactors are single-colony tasks, not DAGs).
- `classify_complexity`: character threshold raised from 160 to 200, word threshold from 28 to 35 (descriptive prompts are not complex tasks).
- `_sanitize_dispatch_tool_call`: fast_path enforcement now overrides when `fast_path` is absent OR explicitly False (same enforcement pattern as preview stripping).
- Result: rtp-03 quality recovered from 0.533 (broken routing) to **0.804** in 1 round / 20 seconds.

### Final benchmark: LANDED.
- 5/5 tasks completed, zero hangs, zero failures
- 0.503 average quality, 2.4 average rounds, 14 minutes total
- 4/5 tasks routed to fast_path (1 round each)
- rtp-03t: **0.836** quality, 1 round, 35 seconds (fast_path enforced)
- rtp-01t: 0.514 quality, 8 rounds, 506 seconds (complex multi-round)
- Complexity router correctly separates simple (fast_path) from complex (multi-round)

### Architectural principle confirmed
The session's recurring pattern: model cannot be trusted to make correct execution decisions. The scaffold must enforce the policy's decision at the execution layer. Tool narrowing, preview stripping, escalation handling, and fast_path enforcement are all instances of this principle.

---

## Wave 84.5 -- Planning Eval and Policy Scaffolding

**Status:** Landed (eval + policy framework)
**Theme:** Planning policy consolidation, routing golden tests, eval harness.

- `planning_policy.py` (new): `decide_planning_route()` + `PlanningDecision` dataclass.
- `planning_signals.py`: `_fetch_saved_patterns()` with deterministic bundle matching.
- `planning_brief.py`: structured observability log, saved-pattern line rendering.
- `capability_profiles.json`: behavior flags per model (needs_tool_narrowing, respects_tool_choice, benefits_from_fast_path).
- `test_routing_agreement.py`: 15 golden prompts + 3 coherence invariants.
- `queen_planning_eval.py`: 13 golden prompts, deterministic scoring, live eval stub.
- `test_planning_ablation.py`: 4 ablation configs x 7 prompts, route drift reporting.

---

## Wave 84 -- Runtime Truth + Benchmark Validation

**Status:** Landed and benchmarked
**Theme:** Remove the sustained runtime stall, restore truthful long-run execution, and measure the local production path cleanly.

### Runtime fixes: LANDED.
- `surface/app.py`: opt-in asyncio slow-callback debug wiring (`FORMICOS_ASYNCIO_DEBUG`) added for live event-loop diagnosis.
- `adapters/sandbox_manager.py`: workspace archive/restore hot-path work now runs through `asyncio.to_thread()` instead of blocking the event loop.
- `surface/colony_manager.py`: completion-time memory extraction and transcript harvest now drain through a deferred idle queue instead of competing immediately with live colony work.
- `adapters/llm_openai_compatible.py`: local `httpx` clients now use explicit connection-pool limits on top of the earlier transport hardening.

### Benchmark result: LANDED.
- Qwen3.5-35B is the production local profile again.
- Final Wave 84 benchmark: `0.503` average quality, `5/5` real-repo tasks completed, `0` hangs, about `16` minutes total.
- Complexity routing plus `fast_path` paid off materially on simple work; the standout run was `rtp-03` at `0.879`.
- The earlier forced escalation-abandonment experiment was a regression and was reverted; the stable Wave 84 result keeps the other 83.5 runtime/workflow improvements without that cap.

### Devstral evaluation: COMPLETED.
- Devstral Small 2 was brought up successfully on the local stack and the app remained healthy under the Wave 84 runtime fixes.
- The model followed delegation instructions cleanly and avoided the evasion patterns seen on weaker runs.
- On current consumer hardware, dense-model round speed was too slow for iterative colony execution: the app stayed healthy, but worker rounds were too expensive to make the 5-task pack competitive.
- Production conclusion: keep Devstral as an experiment/reference profile; keep Qwen3.5-35B as the default local production model.

### Architecture conclusion
- Wave 84 validated the current FormicOS scaffold on local hardware: the planning brief, structural context, complexity routing, deterministic reviewed-plan dispatch, and runtime hardening now work together without the sustained stall that blocked earlier task packs.
- The decisive local lever on this machine is iteration speed, not per-token instruction quality. Qwen3.5's MoE throughput beat Devstral's denser but slower worker rounds in the real colony loop.

---

## Wave 83 -- Planning Workbench

**Status:** Landed and audited (4 tracks, targeted validation green)
**Theme:** Turn reviewed plan previews into a bounded operator workbench with validation, comparison, reuse, and deterministic dispatch.

### Track A -- Reviewed-Plan Validation: LANDED.
- `surface/reviewed_plan.py` (new): `normalize_preview()` and `validate_plan()` now define the reviewed-plan contract.
- `commands.py`: `validate_reviewed_plan` dry-run command added.
- `confirm_reviewed_plan` now shares the same normalize + validate pipeline before dispatch.
- Validation covers task/group integrity, dependency ordering/cycles, duplicate file ownership warnings, and empty task text warnings.

### Track B -- Plan Patterns + Honest Compare: LANDED.
- `surface/plan_patterns.py` (new): YAML-backed saved pattern store under `.formicos/plan_patterns/<workspace>/`.
- 3 new routes: `GET/POST .../plan-patterns`, `GET .../plan-patterns/{pattern_id}`.
- `planning-history` entries now carry explicit summary-only labels: `evidence_type="summary_history"` and `has_dag_structure=false`.

### Track C -- DAG Editor UI: LANDED.
- `fc-plan-editor.ts` (new): edits the real preview contract (`taskPreviews` + `groups`) without a shadow plan model.
- Supports task text/caste edits, split/merge, regrouping, dependency changes, file moves, reset, and validation-trigger events.
- `fc-parallel-preview.ts` can now open the editor inline for deeper pre-dispatch edits.

### Track D -- Workbench Shell + Launch Truth: LANDED.
- `plan-workbench.ts` (new): overlay shell that composes the DAG editor, validation bar, comparison sidebar, save-pattern flow, and deterministic dispatch.
- `fc-plan-comparison.ts` (new): shows saved plan patterns plus summary-only planning history with explicit honesty about legacy evidence limits.
- `commands.py`: deterministic `confirm_reviewed_plan` remains the dispatch seam, now paired with reviewed-plan validation before launch.
- `formicos-app.ts`, `queen-chat.ts`, `thread-view.ts`, and `fc-parallel-preview.ts`: operators can open the workbench from preview cards or thread DAGs before launch.
- Workbench dispatch routes to `confirm_reviewed_plan`; save-pattern routes to the new plan-pattern REST endpoints.

### Audit/polish pass
- Workbench validation now uses a real HTTP route: `POST /api/v1/workspaces/{id}/validate-reviewed-plan`.
- `fc-plan-editor.reset()` and workbench reopen flows now resync edited state cleanly with backend validation.
- Comparison sidebar now loads truthful history data (`plans`, not a phantom `results` payload) and queries planning history with the current task text.
- Saved plan patterns normalize legacy `groups` shapes so reused patterns round-trip back into the editor safely.
- Targeted checks green: frontend build, reviewed-plan unit tests, and direct validation-route smoke test.

---

## Wave 81 -- Real Workspace Truth

**Status:** Landed and integrated (4 tracks, 4230 tests at landing)
**Theme:** Bind FormicOS to real code, make runtime tell the truth.

### Track A -- Project Binding: LANDED.
- `surface/workspace_roots.py` (new): 4 helpers for library/project/runtime root.
- `docker-compose.yml`: `PROJECT_DIR` mount at `/project`.
- Colony manager, runner, planning brief all use runtime root.
- 3 new API routes: project-binding, project-files, project-files/{path}.

### Track B -- Operational Truth Bundle: LANDED.
- `surface/parallel_plans.py` (new): deferred group dispatch, honest aggregation.
- `ColonyTask.colony_id`: pre-allocated before dispatch.
- `spawn_parallel`: dispatches Group 0 only, defers later groups.
- Provider error logging: `repr(exc)` instead of `str(exc)`.
- `tool_choice` normalization: dictâ†’"required" for llama.cpp.

### Track C -- Codebase Index Activation: LANDED.
- Durable reindex sidecar (JSON under `.formicos/runtime/`).
- Status endpoint merges sidecar + vector store truth.
- Real-repo task pack: 5 tasks (rtp-01 through rtp-05).

### Track D -- Operator-Visible Workspace Truth: LANDED.
- Workspace browser: Project Files section when bound.
- Settings: Project Binding card with index status + reindex.
- Queen overview: 5-state group bar (completed/running/failed/blocked/pending).
- Preview/result cards: group structure and partial plan truth.

### Runtime fixes (v6-v9 experiment session)
- Unified single-model architecture: 35B MoE on 5 slots, 260K context.
- Colony start stagger (200ms) prevents KV allocation spike.
- Shared-KV budget: `_num_slots = 1` (each slot has full context).
- Scope validation: rejects plans missing operator-named deliverables.
- Recon follow-up: bounded retry when Queen stalls after reconnaissance.
- Colony work markers: "test", "strengthen", "improve", "write", etc.
- First-turn tool narrowing: removes recon tools until spawn happens.
- Codebase index fix: `vector_port` passes raw QdrantVectorStore.
- `data_dir` in addon runtime context for sidecar writes.

---

## Wave 77-80 -- Knowledge, Queen Intelligence, Coder Tuning

**Status:** Landed (consolidated, pre-Wave 81)
**Theme:** Knowledge system improvements, Queen context budget, coder execution quality.

Key deliverables:
- Knowledge graph with entity extraction and co-occurrence.
- 10-slot proportional Queen context budget (ADR-051).
- Planning brief with coupling analysis and capability profiles.
- Wave 80 file handoff (expected_outputs â†’ target_files auto-wiring).
- Coder recipe tuning: execution-first prompt, 4096 max_tokens.
- Worker output cap: `min(recipe.max_tokens, model_rec.max_output_tokens)`.

---

## Wave 76 -- Structural Integrity

**Status:** Landed and integrated (3 teams, 16 tracks)
**Theme:** Fix silent errors and race conditions before first real multi-client
deployment. No new features -- correctness only.

### Team A -- Data Truth: LANDED.
1. `BudgetSnapshot.total_tokens` includes reasoning tokens.
2. Agent-to-colony reverse index for O(1) token attribution.
3. Daily spend persistence to disk with reload on restart.
4. Budget reconciliation (estimated vs actual) wired through `_post_colony_hooks`.

### Team B -- Operational Safety: LANDED.
5. Action queue compaction preserves `pending_review` items.
6. State transition validation with `_VALID_TRANSITIONS` map.
7. Real pending count in operations dashboard.
8. Sweep reentrancy guard via `asyncio.Lock`.
9. Kill/completion race guard at both completion paths.
10. Journal entries for all approval/execution branches.
11. Operator-idle detects Queen thread messages.

### Team C -- Context Integrity: LANDED.
12. Budget caps on memory retrieval injection.
13. Budget caps on notes and thread context injections.
14. Workspace-scoped session/plan paths with migration fallback.
15. Queen chat workspace propagation (4 dispatch sites).
16. Settings + queen-overview workspace resolution.

### Polish pass
- MCP multi-client smoke tests (13 tests): concurrent safety, log_finding
  pipeline, knowledge-for-context retrieval.
- Billing CLI: `_close_store()` for clean aiosqlite shutdown.
- `init-mcp --desktop` flag for Claude Desktop config snippet.
- Empty workspace_id guards on session/plan path construction.
- Race guard reordered before chat message emission.

---

## Wave 75/75.5 -- Economic Agent + Claude Code Force Multiplier

**Status:** Landed and integrated (2 sub-waves)
**Theme:** Token metering, A2A economic contracts, billing CLI,
attribution script, retrieval-backed MCP search, economic MCP prompts.

### Wave 75.0 -- Economic Substrate: LANDED.
- `surface/metering.py`: token aggregation, fee computation, attestation.
- `surface/task_receipts.py`: deterministic receipts for A2A work.
- `scripts/attribution.py`: contributor revenue-share from git history.
- `routes/protocols.py`: agent card economics block.
- `routes/a2a.py`: contract acceptance and receipt generation.
- Billing CLI: `formicos billing {status|estimate|attest|history|self-test}`.

### Wave 75.5 -- Claude Code Force Multiplier: LANDED.
- `search_knowledge` MCP tool (full retrieval pipeline).
- `formicos://billing` and `formicos://receipt/{task_id}` resources.
- `economic-status` and `review-task-receipt` MCP prompts.
- DEVELOPER_BRIDGE.md updated with economic participation guide.

---

## Wave 74 -- Queen Command & Control

**Status:** Landed and integrated (3 teams)
**Theme:** Elevate Queen visibility and operator control. Display board,
behavioral overrides, tool tracking, autonomy card, context budget viz.

### Team A -- Shell + Display Board: LANDED.
- `queen-display-board.ts`: structured observations with attention/urgent.
- `queen-tool-stats.ts`: tool usage counters.
- `post_observation` Queen tool.
- Auto-posting in operational sweep.

### Team B -- Elevation: LANDED.
- `queen-continuations.ts`, `queen-autonomy-card.ts`, `queen-budget-viz.ts`.
- Context budget visualization.

### Team C -- Behavioral Overrides: LANDED.
- `queen-overrides.ts`: disable tools, inject rules, override team/budget.
- Override injection in `queen_runtime.py`.

---

## Wave 73 -- The Developer Bridge

**Status:** Landed and integrated (3 teams)
**Theme:** Make FormicOS usable from Claude Code. MCP composition layer
(prompts that compose existing tools into developer workflows), prose
resources, init-mcp CLI, frontend truth fixes, workspace creation UI.
No new event types â€” event count stays at 69.

### Team A â€” MCP Prompts + Resources + Addon Tools + init-mcp: LANDED.
1. **4 MCP prompts:** `morning-status`, `delegate-task`,
   `review-overnight-work`, `knowledge-for-context` â€” read-only, compose
   existing operational state modules.
2. **2 MCP tools:** `log_finding` (creates knowledge entries),
   `handoff_to_formicos` (creates thread + spawns colony with developer
   context) â€” mutating, use `@mcp.tool(annotations=_MUT)`.
3. **3 MCP resources:** `formicos://plan` (global),
   `formicos://procedures/{workspace_id}`,
   `formicos://journal/{workspace_id}` â€” return prose markdown.
4. **3 addon tools:** `addon_status` (RO), `toggle_addon` (MUT),
   `trigger_addon` (MUT).
5. **init-mcp CLI:** `python -m formicos init-mcp` generates `.mcp.json`
   (type: http) and `.formicos/DEVELOPER_QUICKSTART.md`.
6. **Runtime wiring:** `addon_registrations` exposed on runtime for MCP
   server access.

### Team B â€” Frontend Truth + Workspace Creation: LANDED.
7. **Colony creator governance:** Replaced hardcoded budget=2.0 and
   maxRounds=10 with governance-configured defaults via
   `_applyGovernanceDefaults()`. Removed fabricated tier cost rates.
8. **Template editor governance:** Same pattern â€” replaced hardcoded 1.0/5
   with governance defaults. Governance passed through playbook-view.ts.
9. **Workspace creation:** `POST /api/v1/workspaces` REST endpoint. Frontend
   sidebar button with inline form. Uses fetch (not WS) â€” snapshot
   auto-refreshes via WorkspaceCreated event.
10. **Addon config type coercion:** boolean/integer stringâ†’native coercion
    in `put_addon_config()`.

### Team C â€” Settings Protocol Detail + Addon Polish + Documentation: LANDED.
11. **Protocol detail:** Verified Wave 72.5 protocol summary already complete.
12. **Addon search/filter:** Text filter on sidebar addon list.
13. **Addon health summary:** Aggregate stats card (total, tools, calls,
    errors) at top of detail panel.
14. **DEVELOPER_BRIDGE.md:** 5-minute developer onboarding guide.
15. **CLAUDE.md refresh:** Updated MCP counts, key paths, commands.

### Seam integration
- `MCP_TOOL_NAMES` tuple updated to include all 27 tools (was 19).
- `view_state.py` fallback updated from 19 to 27.
- `formicos://plan` resource URI corrected (global, no workspace_id).
- DEVELOPER_BRIDGE.md jargon removed from Architecture section.

**Post-wave state:** 27 MCP tools, 9 resources, 6 prompts, 4 CLI
subcommands, 69 events, 43 Queen tools. REST workspace creation.

---

## Wave 72.5 -- Topbar Simplification + Addon Lifecycle (landed)

**Status:** Landed (3 teams)
**Theme:** Clean topbar, interactive addon management, protocol detail migration.

- Removed protocol badges and connection indicator from topbar; added
  clickable budget popover.
- Fixed addon trigger handler calling convention; added interactive "Try It"
  tool testing forms and inline config editing.
- Migrated protocol detail (tool counts, event counts, endpoints) from
  topbar badges to Settings Integrations section.
- Addon lifecycle: soft disable toggle, hello-world scaffold hiding.

---

## Wave 72 -- Autonomous Learning + Workflow Patterns (landed)

**Status:** Landed (3 teams)
**Theme:** System improves its own knowledge, learns from patterns, continues
work autonomously, stays legible to the operator.

- Knowledge review lifecycle: scanning, queuing, operator confirmation/
  invalidation of problematic entries.
- Autonomous continuation: Queen proposes and executes low-risk work across
  sessions and during idle time.
- Workflow learning: deterministic pattern recognition for reusable templates
  (`extract_workflow_patterns`) and operator procedure suggestions
  (`detect_operator_patterns`).
- Product polish: trigger fixes, active Knowledge tab, writable Settings,
  addon disable, model filtering.

---

## Wave 71 -- Operational Coherence (landed)

**Status:** 71.0 + 71.5 landed and integrated
**Theme:** Turn operational intelligence into a durable file-backed substrate
(71.0) and surface it in a dedicated Mission Control tab (71.5). No new event
types â€” event count stays at 69.

Split into two dispatches: 71.0 (backend operational state layer) and 71.5
(frontend Operations tab consuming those contracts).

### Wave 71.0 â€” Operational Coherence Substrate (9 tracks, 3 teams)

**Team A â€” Queen Working Memory: LANDED.**
1. **Track 1 -- Queen context budget expansion:** 7-slot â†’ 9-slot
   `QueenContextBudget` frozen dataclass. New slots: `operating_procedures`
   (5%), `queen_journal` (4%), carved from `thread_context` (15â†’13%) and
   `memory_retrieval` (15â†’13%). Remaining slots rebalanced gently (no slot
   loses >2 points). (`queen_budget.py`)
2. **Track 2 -- Operating procedures injection:** File-backed procedures at
   `.formicos/operations/{workspace_id}/procedures.md`. Structured rule parser
   extracts rules from markdown. Injected into Queen context after briefing,
   before deliberation. `GET/PUT /api/v1/workspaces/{id}/operating-procedures`
   endpoints. (`queen_runtime.py`, `routes/api.py`)
3. **Track 3 -- Queen journal injection:** File-backed journal at
   `.formicos/operations/{workspace_id}/journal.md`. Session summary writes
   appended to journal. Injected into Queen context as working-memory block.
   `GET /api/v1/workspaces/{id}/queen-journal` endpoint.
   (`queen_runtime.py`, `routes/api.py`)

**Team B â€” Durable Action Queue: LANDED.**
4. **Track 4 -- Action queue ledger:** Generic typed action envelope with
   `kind` as semantic authority. Statuses: `pending_review`, `approved`,
   `rejected`, `executed`, `self_rejected`, `failed`. JSONL-backed at
   `.formicos/operations/{workspace_id}/action_queue.jsonl`. Size management
   via `compact_action_log()` at 1000 lines. (`routes/api.py`)
5. **Track 5 -- Approve/reject endpoints:**
   `POST .../actions/{id}/approve` and `POST .../actions/{id}/reject`
   (with optional reason). Dispatcher wiring for approved actions.
   (`routes/api.py`)
6. **Track 6 -- 30-minute operational sweep:** Second asyncio task alongside
   24-hour consolidation loop. Processes approved actions, queues medium/high-
   risk work. Configurable via `FORMICOS_OPS_SWEEP_INTERVAL_S` env var.
   (`app.py`)

**Team C â€” Operations Coordinator: LANDED.**
7. **Track 7 -- Thread plan helper:** Shared helper extracts structured thread
   context for the coordinator. Budget-aware truncation via
   `[:budget.thread_context * 2]`. (`queen_runtime.py`)
8. **Track 8 -- Operations coordinator:** Synthesizes project plan, thread
   plans, session summaries, outcomes, and action queue into
   `continuation_candidates`, `sync_issues`, and operator-idle signals.
   `GET /api/v1/workspaces/{id}/operations/summary` endpoint.
   (`routes/api.py`)
9. **Track 9 -- Queen continuity cue:** Coordinator output injected as
   structured context for the Queen to reason about next steps.
   (`queen_runtime.py`)

Integration fixes: Team A operations-view.ts rewired to mount real Team C
leaf components instead of inline previews. Team C `get_operations_summary`
fixed bare `projections` reference â†’ `runtime.projections if runtime else None`.

21 + 17 + 24 = 62 new tests. Queen context budget: 7 â†’ 9 slots.

### Wave 71.5 â€” Mission Control Surface (3 teams)

**Team A â€” Operations Shell: LANDED.**
- `fc-operations-view` Lit component: header with journal-count badge,
  summary row (journal entries, procedures status, pending actions), two-column
  layout mounting Team B and Team C leaf components. 8th nav tab added to
  `formicos-app.ts` (ViewId union, NAV array, grid-template-columns).
  (`operations-view.ts`, `formicos-app.ts`)

**Team B â€” Action Inbox: LANDED.**
- `fc-operations-inbox` Lit component: kind/status-driven rendering with
  sections for pending review, recent automatic, deferred/self-rejected.
  Approve (one-click) and reject (with optional reason) workflow. Blast-radius
  visual language following proposal-card pattern. Extensible for future action
  kinds without inbox redesign.
  (`operations-inbox.ts`)

**Team C â€” Operational Memory Surfaces: LANDED.**
- `fc-queen-journal-panel`: operational log view with load-more, empty state.
- `fc-operating-procedures-editor`: inline text editing with PUT save, success/
  failure feedback, empty template for first-time users.
- `fc-operations-summary-card`: compact at-a-glance orientation â€” pending
  review count, active milestones, operator idle/active state, top continuation
  candidate, top sync issue, recent progress snippet.
  (`queen-journal-panel.ts`, `operating-procedures-editor.ts`,
  `operations-summary-card.ts`)

3870 tests passing. CI: ruff clean, imports clean.

### Post-integration audit

Comprehensive UI/UX seam audit completed. Reference doc at
`docs/waves/wave_72/wave_72_polish_reference.md` catalogs 9 items across model
management, settings editability, document ingestion, addon triggers, and
navigation. Key findings: addon manual trigger bug (docs-index and
codebase-index both miswired to `indexer.py::incremental_reindex` instead
of `search.py::handle_reindex`), model status type contract divergence,
and Settings page structural inversion (too much read-only inventory,
not enough writable controls).

---

## Previous: Wave 70 -- Operational Flexibility

**Status:** 70.0 + 70.5 landed and integrated
**Theme:** Backend contracts (70.0) + operator trust surface (70.5) for MCP
access, project-level intelligence, and earned autonomy.

Split into two dispatches: 70.0 (backend/control-plane contracts) and 70.5
(frontend rendering consuming those contracts). No new event types â€” event
count stays at 69.

### Wave 70.0 â€” Backend Substrate (9 tracks, 3 teams)

**Team A â€” MCP Bridge Substrate: LANDED.**
1. **Track 1 -- MCP bridge addon core:** New `addons/mcp-bridge/` addon with
   FastMCP `>=3.0,<4.0` Client. Bridge registers as addon via existing
   `addon_loader.py` pipeline. Generic capability protocol for health exposure
   (no addon-name branching). `call_mcp_tool` Queen tool for remote tool
   invocation. (`addons/mcp_bridge/`)
2. **Track 2 -- Dynamic MCP tool discovery:** `discover_mcp_tools` Queen tool
   queries connected MCP servers and returns available tools with schemas.
   (`queen_tools.py`)
3. **Track 3 -- Bridge health exposure:** Generic addon health via
   `AddonRegistration.health_status` property. Bridge health visible through
   `/api/v1/addons` endpoint without hardcoded addon-name checks.
   (`addon_loader.py`, `routes/api.py`)

**Team B â€” Project Intelligence Substrate: LANDED.**
4. **Track 4 -- Project plan helper:** `project_plan.py` shared parser/helper
   â€” single source of truth for resolving plan path, parsing milestones,
   rendering compact Queen context text, updating timestamps.
   (`surface/project_plan.py`)
5. **Track 5 -- Milestone tools + endpoint + budget:** `propose_project_milestone`
   and `complete_project_milestone` Queen tools. `GET /api/v1/project-plan`
   returns structured JSON. Dedicated 7th Queen context budget slot
   (`project_plan` at 5%, 400-token fallback, carved from `thread_context`
   which went from 20% to 15%). ADR-051 updated.
   (`queen_tools.py`, `queen_budget.py`, `routes/api.py`)
6. **Track 6 -- Project plan injection:** Parsed project plan injected into
   Queen context as its own system message block, capped by `project_plan`
   budget, labeled `# Project Plan (cross-thread)`. Separate from
   `project_context.md` and thread plans.
   (`queen_runtime.py`)

**Team C â€” Autonomy Trust Substrate: LANDED.**
7. **Track 7 -- Daily autonomy budget:** `check_autonomy_budget` Queen tool
   surfaces daily budget spend, remaining capacity, and recent autonomous
   actions. (`queen_tools.py`)
8. **Track 8 -- Blast radius estimator:** `BlastRadiusEstimate` dataclass with
   6 heuristic factors (task length, caste risk, round count, strategy,
   keywords coder-only, outcome history). Thresholds: >=0.6 escalate,
   >=0.3 notify, <0.3 proceed. Dispatch gate in `evaluate_and_dispatch()`.
   Proposal metadata carries blast-radius truth.
   (`self_maintenance.py`, `queen_tools.py`)
9. **Track 9 -- Autonomy scoring + status endpoint:** `AutonomyScore` with
   4 weighted components (success_rate, volume, cost_efficiency,
   operator_trust). `compute_autonomy_score()` pure function.
   `GET /api/v1/workspaces/{id}/autonomy-status` returns structured trust
   data. (`self_maintenance.py`, `routes/api.py`)

**Integration fix:** Blast radius keyword weight set to 0.0 for non-coder
castes â€” researcher investigating "authentication" is not the same as
modifying it.

### Wave 70.5 â€” Operator Surface (3 teams)

**Team A â€” MCP Settings UX: LANDED.**
- `fc-mcp-servers-card` Lit component: server list with health dots, add/remove
  forms, three empty states. Reads from `/api/v1/addons`, writes through
  `PUT /api/v1/addons/mcp-bridge/config`. Self-contained, no store dependency.
  (`mcp-servers-card.ts`)

**Team B â€” Project Visibility: LANDED.**
- `fc-project-plan-card` Lit component: plan goal, progress bar, milestone
  checklist with status chips, thread links, completion dates. Mounted in
  `queen-overview.ts` after budget panel. Data from `GET /api/v1/project-plan`
  only â€” no frontend markdown parsing.
  (`project-plan-card.ts`, `queen-overview.ts`)

**Team C â€” Trust Integration: LANDED.**
- `fc-autonomy-card` Lit component: grade badge (A-F), trust score, daily
  budget bar, component breakdown, recent autonomous actions table. Mounted
  in `settings-view.ts`.
  (`autonomy-card.ts`, `settings-view.ts`)
- Proposal card blast-radius rendering: score, level pill, recommendation pill,
  factors list. Color-coded border. Additive only â€” unchanged when absent.
  (`proposal-card.ts`, `queen-chat.ts`)
- `system-overview.ts` tool count updated to 43.
- `BlastRadiusData` and `AutonomyStatusData` interfaces added to `types.ts`.

**Integration fix:** Mounted Team A's `fc-mcp-servers-card` in
`settings-view.ts` (Card G, between Addons and Autonomy Trust).

Queen tools: 38 â†’ 43 (+discover_mcp_tools, +call_mcp_tool,
+propose_project_milestone, +complete_project_milestone,
+check_autonomy_budget). Queen context budget: 6 â†’ 7 slots.
3808 tests passing. CI: ruff clean, imports clean.

---

## Earlier: Wave 67 -- The Knowledge Architecture

**Status:** 67.0 landed + polish pass complete, 67.5 landed
**Theme:** Give knowledge structure, integrity, and auditability.

Split into two dispatches: 67.0 (foundation) lands first, 67.5 (surfaces)
builds on it. No new event types â€” all changes are projection-level
enrichments. Event count stays at 69.

### Wave 67.0 â€” Foundation (3 tracks, 2 teams)

1. **Track 1 -- Knowledge Hierarchy (Team A): LANDED.** Materialized paths
   on projections (`hierarchy_path`, `parent_id`). Qdrant payload gains
   keyword-indexed `hierarchy_path` for filtered branch search. Branch
   confidence aggregation caps at ESS 150, filters by workspace.
   `GET /api/v1/workspaces/{id}/knowledge-tree` endpoint. Knowledge
   browser gains tree subview (collapsible branches, confidence bars,
   click-to-filter). LLM-only offline bootstrap script (zero new deps).
   12 new tests. ADR-049 proposed.
   (`projections.py`, `memory_store.py`, `hierarchy.py`, `routes/api.py`,
   `knowledge-browser.ts`, `bootstrap_hierarchy.py`)
   - **Polish:** Fixed `compute_branch_confidence` negative Beta bug (aggregated
     beta could go < 0 when children have conf_beta < prior 5.0, producing
     invalid mean > 1.0). Added floor clamp at 1.0. Added Qdrant keyword
     index for `hierarchy_path` in `vector_qdrant.py`. +1 test.
2. **Track 2 -- Domain Normalization (Team B): LANDED.** Existing domain
   tags from up to 10 similar entries injected into extraction prompt as
   guidance ("use one of these if applicable, do not create synonyms").
   Caps at 20 domains. Fires on all three prompt paths. Call site verified:
   `colony_manager.py:2069` populates via `knowledge_catalog.search()`.
   5 new tests. (`memory_extractor.py`)
3. **Track 3 -- Outcome-Confidence Reinforcement (Team B): LANDED.**
   Geometric credit 0.7^rank (Position-Based Model) replaces flat delta.
   Rank-0 entry gets full credit, rank-5 gets ~17%. ESS capped at 150 via
   `rescale_preserving_mean()` in Engine layer â€” applied after mastery
   restoration, before event emission. Preserves posterior mean. Co-occurrence
   reinforcement unchanged. Auto-promotion verified. 11 new tests.
   (`colony_manager.py`, `scoring_math.py`)

### Wave 67.5 â€” Surfaces (3 tracks, 3 coders)

4. **Track 4 -- Two-Pass Retrieval (Team B):** Replace hardcoded 0.0
   graph proximity in standard retrieval with iterative Personalized
   PageRank (damping=0.5, pure Python, no igraph dep). Entity seeding
   via embedding similarity. Shared `_enrich_with_graph_scores()` method
   refactors thread-boosted path. ADR-050 proposed.
   (`knowledge_graph.py`, `knowledge_catalog.py`)
5. **Track 5 -- Provenance Chains (Team A):** Append-only
   `provenance_chain` list on projection entries from 6 event handlers.
   REST endpoint. Provenance timeline in entry detail UI. Score breakdown
   bar visible by default on search results. **Contract change blocker:**
   `ProvenanceChainItem` interface needs operator approval.
   (`projections.py`, `knowledge_api.py`, `types.ts`, `knowledge-browser.ts`)
6. **Track 6 -- Documentation Indexer Addon (Team C):** New
   `addons/docs-index/` addon. Chunks .md/.rst/.txt/.html on section
   headers. Registers `semantic_search_docs` and `reindex_docs` Queen
   tools. Separate `docs_index` Qdrant collection. Follows codebase-index
   addon pattern and keeps raw corpus chunks out of `memory_entries`.
   (`addons/docs-index/`, `addons/docs_index/`)

### Blockers

- **ADR-049:** Knowledge Hierarchy (proposed, awaiting approval)
- **ADR-050:** Two-Pass Retrieval with PPR (proposed, awaiting approval)
- **Contract change:** ProvenanceChainItem interface (67.5 only)

No new dependencies â€” UMAP+HDBSCAN rejected in favor of LLM-only
bootstrap (entries already carry domain tags, LLM sub-clusters within
domains, ~15 calls for 300 entries).

---

## Previous: Wave 66 -- Addons as First-Class Software

Makes addons visible, configurable, and extensible. Six tracks across
three teams. No new events â€” reuses existing WorkspaceConfigChanged.

1. **Track 1 -- Addons Tab (Team 1):** `GET /api/v1/addons` returns installed
   addons with health summaries (tool call counts, handler errors, trigger
   schedules). `POST /api/v1/addons/{name}/trigger` manually fires trigger
   handlers. `AddonRegistration` tracks health counters updated by tool/handler
   wrappers. (`routes/api.py`, `addon_loader.py`)
2. **Track 2 -- Addon Config Surface:** `AddonConfigParam` model declares
   configurable parameters in addon manifests (key, type, default, label,
   options). `GET /api/v1/addons/{name}/config?workspace_id=X` returns config
   schema + current values. `PUT /api/v1/addons/{name}/config` persists values
   via WorkspaceConfigChanged events at `addon.{name}.{key}` dimension. All
   three shipped addons declare config blocks: git_auto_stage (boolean),
   chunk_size/skip_dirs (integer/string), disabled_rules (string).
   (`addon_loader.py`, `routes/api.py`, addon manifests)
3. **Track 3 -- Addon Panels + Routes:** `register_addon()` now resolves
   `routes` and `panels` manifest fields (previously warned as unimplemented).
   Catch-all route at `/addons/{name}/{path}` mounts addon HTTP endpoints.
   `fc-addon-panel` Lit component renders status_card, table, and log display
   types with 60s auto-refresh. Panel injection zones in knowledge-browser.ts
   and workspace-browser.ts. Status endpoints: codebase-index (chunk count from
   vector store), git-control (branch + modified files).
   (`addon_loader.py`, `app.py`, `addon-panel.ts`, status endpoints, manifests)
4. **S2 -- Knowledge ROI Rule Fix:** Extended `_rule_knowledge_roi` to track
   `entries_accessed` alongside `entries_extracted`. New insight when 3+
   successful colonies access zero knowledge and score below 0.7 quality.
   (`addons/proactive_intelligence/rules.py`)
5. **S4 -- CLAUDE.md Weight Update:** Updated composite retrieval formula to
   7-signal Wave 59.5 values including graph_proximity.

3654 tests passing (+14 net new). CI: ruff clean, imports clean.

## Previous: Wave 65.5 -- Addon Polish Pass

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
   `handle_proactive_configure` â€” previously zero direct coverage.
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
   tool for manual trigger firing. Cron DOW fix (Python Mon=0 â†’ cron Sun=0).
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

1. **Queen deliberation mode** â€” Two-pass intent parser (regex + Gemini) gains
   DELIBERATE category. Queen system prompt enforces deliberation-first, no
   skip-preview escape hatch. (`queen_intent_parser.py`, `caste_recipes.yaml`)
2. **Dashboard-first layout** â€” Chat rail collapsed by default with FAB toggle.
   Dashboard is the landing surface. (`formicos-app.ts`, `queen-overview.ts`)
3. **Colony artifact viewer** â€” Artifacts tab on colony detail, lazy-fetched
   from existing REST endpoint. (`colony-detail.ts`)
4. **Resource grid overhaul** â€” API Spend, Local Compute, Per-Provider
   breakdown cards replace single-metric cards. (`queen-overview.ts`)
5. **Settings editor** â€” Governance settings editable (strategy, max rounds,
   budget, convergence, autonomy) with save to config-overrides. (`settings-view.ts`)
6. **Provider recognition fix** â€” `providerOf()` expanded from 2 to 8 providers.
   Model registry grouped by provider with collapsible sections. (`helpers.ts`,
   `model-registry.ts`)
7. **Model registry update** â€” 51 active entries across 9 providers (OpenAI,
   Anthropic, Gemini, DeepSeek, MiniMax, Mistral, Groq, Ollama, llama-cpp)
   with verified March 2026 pricing. (`formicos.yaml`)

**Reasoning/cache token pipeline** â€” `reasoning_tokens` and `cache_read_tokens`
fields added through the full stack: LLMResponse â†’ TokensConsumed event â†’
runner accumulation â†’ BudgetSnapshot projections â†’ REST API â†’ dashboard.
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

## Waves 36-59 (Hardening â†’ Evaluation â†’ Curation)

- **Wave 36 -- The Glass Colony:** first publicly-ready version. Demo workspace with seeded knowledge, outcome badges, scheduled knowledge refresh.
- **Wave 37 -- The Hardened Colony:** foundation hardening for external trust. Stigmergic loop closure, measurement infrastructure, poisoning defenses.
- **Wave 38 -- The Ecosystem Colony:** NemoClaw + A2A integration, internal benchmarking, bi-temporal knowledge graph. Event union stays at 55.
- **Wave 39 -- The Supervisable Colony:** operator becomes durable co-author. Cognitive audit trail, editable hive state, governance-owned adaptation. Event union 55 â†’ 58.
- **Wave 40 -- The Refined Colony:** health pass â€” no new features, only refinement. Code coherence, speed, testing, failure mode elimination.
- **Wave 41 -- The Capable Colony:** real-world coding power. Mathematical bridge-tightening, production capability for codebases and test suites.
- **Wave 42 -- The Intelligent Colony:** research synthesis at existing seams. Adaptive evaporation, non-LLM intelligence. No new event types.
- **Wave 43 -- The Hardened Colony:** production architecture. Container hardening, persistence rules, budget governance, deterministic testing, docs truth.
- **Wave 44 -- The Foraging Colony:** web acquisition as second compounding source. EgressGateway, fetch pipeline, content quality, search adapter, ForagerService. Event union 58 â†’ 62.
- **Wave 45 -- The Complete Colony:** consolidation â€” proactive foraging wired through maintenance, competing-hypothesis surfacing, source-credibility-aware admission.
- **Wave 46 -- The Proven Colony:** visibility + operability + measured honesty. Forager operator surface, evaluation harness, measurement without bias.
- **Wave 47 -- The Fluent Colony:** coding ergonomics and execution fluency. File editing improvements, fast-path execution, structural context refresh.
- **Wave 48 -- The Operable Colony:** composition and grounding. Specialist castes grounded, thread/colony/knowledge/forager stories connected.
- **Wave 49 -- The Conversational Colony:** Queen chat as primary orchestration surface. Chat-first task entry, inline plan viewing, progress monitoring.
- **Wave 50 -- The Learning Colony:** system improves through experience. Template auto-learning, cross-workspace knowledge sharing, thread compaction.
- **Wave 51 -- Final Polish / UX Truth:** intentionally finished product surface. Durable capabilities made durable, degraded state visible, truth over silence.
- **Wave 52 -- The Coherent Colony:** system describes itself consistently. Control-plane truth, intelligence reach, learning loop visibility. Event union 62 â†’ 64.
- **Wave 53 -- Benchmark Contract:** Phase 0 readiness. Benchmark conditions locked, task calibration, clean-room verification.
- **Wave 54 -- Quality Audit:** gap analysis before Phase 0 evaluation. Reference prompts, Phase 0 v2 preparation.
- **Wave 55 -- Truth-First UX:** progress detection truth (end stall misclassification), operator visibility of existing intelligence, provider/model improvements.
- **Wave 56 -- Semantic Threshold + Extraction Tuning:** threshold optimization, common-mistakes anti-pattern injection, generation stamping. Phase 0 v7: mean quality 0.688 (+0.177 from v4).
- **Wave 57 -- Phase 0 v9 Analysis:** honest interpretation â€” absolute quality improved dramatically, but compounding signal flat within noise. Quality gains from operational knowledge (playbooks, progress detection, coder model), not domain retrieval.
- **Wave 58 -- Integration:** specificity gate, trajectory storage, progressive disclosure. Three parallel coder teams. Event union stays at 64.
- **Wave 59 -- Knowledge Curation:** append-only â†’ curating archivist (CREATE/REFINE/MERGE/NOOP). Archivist sees existing entries before deciding. MemoryEntryRefined event (65th). Phase 1 v1: 19 cross-task accesses, 1 REFINE observed, 0 knowledge_detail calls.

## Waves 16-35 (Alpha â†’ Self-Maintaining)

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
- **Wave 29 -- Workflow Threads:** threads gained goals, completion status, and thread-scoped knowledge. Service colonies gained deterministic handlers (registered Python callables dispatched through `ServiceRouter` without LLM spend). First maintenance services: dedup consolidation and stale sweep. Event union 41 â†’ 45.
- **Wave 30 -- Knowledge Metabolism:** Bayesian confidence (Beta distribution alpha/beta) on `MemoryEntry`, Thompson Sampling for explore/exploit retrieval ranking, workflow steps as Queen scaffolding on threads, thread archival with confidence decay, contradiction detection, LLM-confirmed dedup extension, scheduled maintenance timer, legacy skill system fully deleted. Event union 45 â†’ 48. ADR-039 supersedes ADR-010 fully and ADR-017 partially.
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
| Event types | 22 (closed union â€” opens in Wave 11) |
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
- **T2 -- Gemini + Output Hardening:** `adapters/llm_gemini.py` implements LLMPort via raw httpx to Gemini generateContent API. `adapters/parse_defensive.py` provides 3-stage tool-call parser (native JSON â†’ json_repair â†’ regex extraction) used by all three adapters. Handles `<think>` tags, markdown fences, string-args bug, hallucinated tool names (fuzzy match). Gemini `thoughtSignature` round-trip preserved. RECITATION/SAFETY blocks surface as `finish_reason: "blocked"` with fallback chain. Routing table updated: researcher and archivist route to `gemini/gemini-2.5-flash`. Model registry includes gemini-flash and gemini-flash-lite with pricing.
- **T3 -- Skill Browser + Frontend:** `GET /api/v1/skills` REST endpoint. `skill-browser.ts` Lit component with confidence bars, sort controls, empty state. 3-color routing badges (green/blue/amber for local/Gemini/Claude) on colony cards and detail view. Colony auto-navigation on creation. Compatibility layer for `source_colony` / `source_colony_id` field mismatch.
- Qdrant healthcheck fixed: `bash -c 'echo > /dev/tcp/localhost/6333'` (container lacks curl)
- ADRs 013-014 written and current
- 2 new `.feature` specs: `qdrant_migration.feature`, `gemini_provider.feature`
- Docker/smoke test green: 30/30 gates passed, 3/4 advisory (Gemini `no_key` expected)
- **672 tests**, ruff clean, pyright 0 errors, layer lint clean, frontend build clean
- New dependencies: `qdrant-client>=1.16`, `json-repair>=0.30` (14 total runtime deps)


## Wave 11 -- The Skill Bank Grows Up (2026-03-14)

Opened the event union (22 â†’ 27), upgraded skill confidence to Beta distribution, added LLM-gated deduplication, shipped colony templates, Queen colony naming, and suggest-team. Two phases with 3 parallel coders each.

- **Phase A T1 -- Event Union + Projections:** `core/events.py` expanded from 22 to 27 events (`ColonyTemplateCreated`, `ColonyTemplateUsed`, `ColonyNamed`, `SkillConfidenceUpdated`, `SkillMerged`). `surface/projections.py` handlers for all 5 new events. `TemplateProjection` model with use_count tracking. `ColonyProjection.display_name` field. `frontend/src/types.ts` mirrors all 5 event interfaces plus `TemplateInfo`, `SuggestTeamEntry`, `SkillEntry` with `conf_alpha`/`conf_beta`. Contract parity tests updated.
- **Phase A T2 -- Bayesian Confidence:** `surface/skill_lifecycle.py` migrates flat Â±0.1 confidence to Beta distribution (`conf_alpha`, `conf_beta`, `conf_last_validated` in Qdrant payloads). `engine/context.py` adds UCB exploration bonus to composite scoring (0.50 semantic + 0.25 confidence + 0.20 freshness + 0.05 exploration). `surface/colony_manager.py` emits `SkillConfidenceUpdated` event per colony completion. `/api/v1/skills` returns alpha, beta, uncertainty.
- **Phase A T3 -- LLM Dedup:** New `adapters/skill_dedup.py` with `decide_action()` (two-band: â‰¥0.98 NOOP, [0.82,0.98) LLM classify, <0.82 ADD), `classify()` (ADD/UPDATE/NOOP via Gemini Flash), `merge_texts()` (LLM combines skills), `combine_betas()` (additive merge minus shared prior). `skill_lifecycle.py` ingestion path rewired through dedup pipeline.
- **Phase B T1 -- Colony Templates:** New `surface/template_manager.py` with `ColonyTemplate` Pydantic model, YAML file storage in `config/templates/`, immutable versioning, `load_templates()`/`save_template()`/`list_templates()`. REST: `GET/POST /api/v1/templates`, `GET /api/v1/templates/{id}`. Example `config/templates/code-review.yaml` included. `ColonyTemplateCreated` event emitted on save.
- **Phase B T2 -- Naming + Suggest-Team + Commands:** `surface/queen_runtime.py` `name_colony()` with Gemini Flash (500ms timeout, fallback to UUID). `surface/runtime.py` `suggest_team()` via LLM. `surface/commands.py` spawn accepts `templateId`, resolves template defaults, emits `ColonyTemplateUsed`. `surface/app.py` routes: `/api/v1/suggest-team` POST, `/api/v1/templates` GET/POST. `colony_manager.py` schedules naming task after spawn.
- **Phase B T3 -- Frontend:** `colony-creator.ts` 3-step flow (Describe â†’ Configure â†’ Launch) with parallel suggest-team + template fetch, template selection, caste add/remove, budget config. `template-browser.ts` with caste tags, use counts, strategy badges, source colony links, empty state. `skill-browser.ts` upgraded with uncertainty bars, Î±/Î² display, merged badges. `types.ts` extended with all Wave 11 types.
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
- **Stream C -- Smoke and Validation:** Qdrant v1.16.2 verified. Wave 15 config validation BDD harness (5 scenarios). End-to-end colony smoke: 2 colonies completed with real LLM inference (llama-cpp local + Anthropic cloud). Template save and reuse verified. Provider fallback chain verified (Anthropic 401 â†’ Gemini cooldown â†’ llama-cpp). WebSocket event fan-out verified with full colony lifecycle (spawn â†’ rounds â†’ completion).
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
| Provider fallback | PASS -- Anthropic 401 â†’ Gemini cooldown â†’ llama-cpp |

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
