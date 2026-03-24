# Wave 8 Dispatch — "Close the Loop"

**Date:** 2026-03-13
**Goal:** Make colonies learn from each other. Real tools, real costs, real skills, real quality scores.
**Exit gate:** `docker compose build && docker compose up`, spawn a tool-capable colony, verify:
skills written to LanceDB, cost non-zero in events, quality score in snapshot, frontend renders
new fields. Full `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest` green.

---

## Read Order (mandatory before writing any code)

1. `CLAUDE.md` — project rules
2. `AGENTS.md` — ownership and coordination
3. `docs/decisions/001-event-sourcing.md` — single mutation path
4. `docs/decisions/002-pydantic-only.md` — serialization rules
5. `docs/decisions/005-mcp-sole-api.md` — MCP vs WS boundary
6. `docs/decisions/007-agent-tool-system.md` — NEW: agent tool design
7. `docs/decisions/008-context-window-management.md` — NEW: tiered context
8. `docs/decisions/009-cost-tracking.md` — NEW: cost model
9. `docs/decisions/010-skill-crystallization.md` — NEW: learning loop
10. `docs/decisions/011-quality-scoring.md` — NEW: fitness signal
11. `docs/waves/wave_08/algorithms.md` — NEW: pseudocode for all subsystems
12. `docs/contracts/events.py` — 22-event union (DO NOT MODIFY)
13. `docs/contracts/ports.py` — 5 port interfaces (DO NOT MODIFY)
14. Current implementations: `engine/runner.py`, `engine/context.py`,
    `surface/colony_manager.py`, `surface/app.py`, `surface/projections.py`,
    `surface/view_state.py`, `config/formicos.yaml`, `config/caste_recipes.yaml`

---

## Scope Locks

| Stream | Owns (may modify) | Does NOT touch |
|--------|-------------------|----------------|
| T1-A — Backend: Tools + Crystallization | `engine/runner.py`, `engine/context.py`, `surface/colony_manager.py`, `config/caste_recipes.yaml`, tests for these | `core/*`, `frontend/*`, `docs/contracts/*` |
| T1-B — Backend: Cost + Quality + Wiring | `surface/app.py`, `surface/runtime.py`, `surface/colony_manager.py`, `surface/projections.py`, `surface/view_state.py`, `config/formicos.yaml`, `core/settings.py`, tests for these | `frontend/*`, `docs/contracts/*` |
| T2 — Frontend | `frontend/src/types.ts`, `frontend/src/components/queen-overview.ts`, `frontend/src/components/colony-detail.ts` | `src/formicos/*` |

T1-A and T1-B can prepare in parallel, but **must merge in sequence**. T2 depends
on T1-B completing (needs the snapshot shape to be finalized). T1-A and T1-B share
`surface/colony_manager.py` — the orchestrator must sequence their changes to that
file (T1-A writes crystallization, T1-B writes quality scoring, both affect
`_run_colony`).

**Merge order:** T1-A first, T1-B second (quality scoring references the
crystallization count), T2 last.

---

## Task A: Agent Tools + Skill Crystallization (T1-A)

### What changes

1. **`engine/runner.py`** — Add tool spec registry, tool handler functions,
   tool call loop in `_run_agent`, and constructor pass-through for both
   `cost_fn` and tiered context budget config on `RoundRunner.__init__`.
   See `algorithms.md §1` for complete pseudocode.
   **Do not use provider-native tool result messages.** The live `LLMMessage`
   contract is still `{role, content}`. Feed tool results back as plain text
   follow-up messages, the same way `surface/queen_runtime.py` already does.

2. **`engine/context.py`** — Implement tiered context assembly per `algorithms.md §2`.
   Add `_compact_summary()`, `_truncate_preserve_edges()`, tier budget support.
   Change skill bank collection from `colony_context.workspace_id` to `"skill_bank"`.
   Keep engine code config-agnostic: accept typed budgets from the caller instead of
   importing settings directly.

3. **`surface/colony_manager.py`** — Add `_crystallize_skills()` method per
   `algorithms.md §4`. **⚠ CRITICAL SEQUENCING: Call `_crystallize_skills()` BEFORE
   emitting `ColonyCompleted`, not after. The event carries `skills_extracted`
   and must contain the real count at emission time (ADR-001: the event is the
   source of truth, replay must produce correct state).** The current code emits
   `ColonyCompleted` at the bottom of `_run_colony()` in two places (governance
   "complete" and max-rounds-exhausted). In both places, insert crystallization
   before the emit, then pass the returned count into `skills_extracted=count`.
   Add `_parse_skills_json()` helper.

4. **`config/caste_recipes.yaml`** — Remove tools that have no handler.
   Keep only `memory_search` and `memory_write` for reviewer/researcher/archivist.
   Remove all phantom tools from worker castes, and remove `query_memory` from the
   queen recipe because it is not implemented in `surface/queen_runtime.py`.
   Queen runtime tool specs remain surface-defined; this task only aligns recipes
   with the live backend.

### Acceptance Criteria

- [ ] Agent with `memory_search` tool makes at least one tool call in a round
- [ ] Agent with `memory_write` tool stores a document in LanceDB
- [ ] Tool call loop terminates after MAX_TOOL_ITERATIONS (3)
- [ ] Tool call errors return to LLM as text, do not raise
- [ ] Tool results are fed back via plain text `LLMMessage` entries, not provider-native tool payloads
- [ ] After colony completion, `skill_bank` collection has entries
- [ ] `ColonyCompleted.skills_extracted` is > 0 for successful colonies
- [ ] Context assembly respects tier budgets (test with >4000 token inputs)
- [ ] Prev round summary compacted when over threshold
- [ ] `surface/colony_manager.py` emits `ColonyCompleted` only after crystallization count is known
- [ ] All existing tests still pass

### New Tests Required

- `tests/unit/engine/test_tool_loop.py` — tool call iteration, max iterations, error handling
- `tests/unit/engine/test_context_tiers.py` — tier budget enforcement, compaction, edge truncation
- `tests/unit/surface/test_crystallization.py` — skill extraction, JSON parsing, LanceDB upsert

### Validation Command

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Task B: Cost Tracking + Quality Scoring + Snapshot Wiring (T1-B)

### What changes

1. **`surface/app.py`** — Build `cost_fn` from model registry and pass to
   `Runtime`. See `algorithms.md §3.1`.

2. **`surface/runtime.py`** — Store `cost_fn` and typed context budget config
   so the live runtime can inject both into `RoundRunner` / context assembly.
   This file is part of T1-B scope even though the original draft omitted it.

3. **`surface/colony_manager.py`** — Pass `cost_fn` and context budgets through
   to `RoundRunner`. Add governance warning counter and quality score computation
   in `_run_colony`. Add budget enforcement (fail colony if
   `total_cost >= budget_limit`).
   See `algorithms.md §5.2`.
   **Replay note:** no new events are allowed. If part of the quality score uses
   live-only counters (for example governance warnings or stall counters) that are
   not replay-derivable from existing events, compute them live for the running
   colony and document the replay limitation rather than inventing persistence.

4. **`surface/projections.py`** — Add `quality_score: float = 0.0` and
   `skills_extracted: int = 0` to `ColonyProjection`. Update
   `_on_colony_completed` to store `skills_extracted` from the event.

5. **`surface/view_state.py`** — Add `qualityScore` and `skillsExtracted`
   to colony node in `_build_tree`.

6. **`config/formicos.yaml`** — Add `cost_per_input_token` and
   `cost_per_output_token` to each model registry entry. Add `context`
   section with tier budgets.

7. **`core/settings.py`** — Parse the new `context` section so the live app can
   load it without falling back to raw dict access. Add tests for the new settings
   model / loader behavior.

### Acceptance Criteria

- [ ] `TokensConsumed.cost` is non-zero for cloud model calls
- [ ] `RoundCompleted.cost` reflects real token costs
- [ ] Colony fails with "Budget exhausted" when cost exceeds limit
- [ ] `quality_score` is a float in (0, 1] for completed colonies
- [ ] `quality_score` is 0.0 for failed colonies
- [ ] State snapshot includes `qualityScore` and `skillsExtracted` per colony
- [ ] `config/formicos.yaml` loads cleanly through `core/settings.py` with the new `context` section
- [ ] All existing tests still pass

### New Tests Required

- `tests/unit/surface/test_cost_tracking.py` — cost function, budget enforcement
- `tests/unit/surface/test_quality_scoring.py` — formula correctness, edge cases
- `tests/unit/surface/test_snapshot_fields.py` — new fields in snapshot
- `tests/unit/core/test_settings.py` — context config parsing / defaults / validation

### Validation Command

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Task C: Frontend Wiring (T2)

### Depends on: T1-B complete (snapshot shape finalized)

### What changes

1. **`frontend/src/types.ts`** — Add `qualityScore: number` and
   `skillsExtracted: number` to the colony node interface.

2. **`frontend/src/components/queen-overview.ts`** — Add quality dot
   (green/amber/red/gray) to colony cards. Add skills badge showing count.

3. **`frontend/src/components/colony-detail.ts`** — Show quality score
   as numeric value. Show skills extracted count. Cost display already
   exists — it will now show real numbers (no code change needed, just
   verify it renders correctly with non-zero values).

`frontend/src/state/store.ts` should not need structural changes for this wave
because the store already replaces itself from backend snapshots. Only touch it
if the finalized snapshot shape forces a narrow typing or render fix.

### Acceptance Criteria

- [ ] Colony cards show colored quality dot
- [ ] Colony cards show skills badge (if > 0)
- [ ] Colony detail shows numeric quality score
- [ ] Colony detail shows real cost (already wired, verify non-zero display)
- [ ] TypeScript compiles clean (`npx tsc --noEmit` or vite build)
- [ ] No console errors in browser

### Validation Command

```bash
cd frontend && npm run build
```

---

## Integration Test (exit gate)

After all tasks merge:

```bash
# Build and start
docker compose build formicos && docker compose up -d

# Wait for startup
sleep 10 && curl http://localhost:8080/health

# Open browser and trigger a tool-capable colony path.
# Use a task that actually exercises memory tools, for example:
#   "Review the last completed colony summary and store reusable lessons."
# or another task that explicitly routes to a reviewer / researcher / archivist colony.
# Verify in browser console / network tab:
#   1. Colony runs (round events appear)
#   2. Agent turn events show tool_calls for a tool-capable agent
#   3. RoundCompleted events show non-zero cost (or 0.0 for local — acceptable)
#   4. ColonyCompleted shows skills_extracted > 0
#   5. State snapshot includes qualityScore > 0 for the completed colony
#   6. Queen overview shows quality dot and skills badge

# Check LanceDB for skill entries
docker compose exec formicos python -c "
import lancedb
db = lancedb.connect('/app/data/vectors')
print(db.table_names())
if 'skill_bank' in db.table_names():
    t = db.open_table('skill_bank')
    print(f'Skills: {t.count_rows()}')
    print(t.to_pandas().head())
"

# Full CI
docker compose exec formicos bash -c "ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest"
```

---

## Constraints Reminder

1. **No contract changes.** Event union is closed. No new event types.
2. **No new dependencies.** Everything uses existing packages.
3. **Pydantic v2 only.** No dataclasses for serialized types.
4. **structlog only.** No print().
5. **Layer boundaries.** engine/ imports only core/. surface/ imports all.
6. **Tests required.** Every behavioral change needs a test.
7. **Feature flags** wrap incomplete work if needed. But everything in this
   wave should be complete — no partial features.

---

## What This Wave Does NOT Include

- Compute Router (caste-aware model routing) — next wave
- Temporal Knowledge Graph — next wave
- Experimentation Engine — requires Compute Router + quality scoring (this wave provides the scoring)
- LLM-as-judge quality assessment — deferred, proxy metrics first
- `code_execute`, `file_read`, `file_write` tools — require SandboxPort adapter
- `web_search` tool — requires outbound HTTP adapter with safety constraints
- Queen dashboard composition — requires more frontend maturity
- Gemini tie-in — requires model registry extension
