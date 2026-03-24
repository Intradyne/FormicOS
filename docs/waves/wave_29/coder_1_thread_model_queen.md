# Coder 1 — Track A: Thread Model + Queen Awareness

**Wave:** 29 — "Workflow Threads"
**Track:** A — Thread model, Queen context injection, Queen thread + service tools
**Dependencies:** None — starts immediately.
**Algorithms reference:** `docs/waves/wave_29/wave_29_algorithms.md` sections S1, S3, S5, S6.

---

## Context

Threads are currently empty containers. `ThreadProjection` (projections.py:192) has 5 fields: `id`, `workspace_id`, `name`, `colonies`, `queen_messages`. No goal, no status, no progress. The Queen has 12+ tools (spawn_colony, redirect_colony, kill_colony, etc.) but no thread management tools and no service query capability.

This track makes threads into workflow scopes and gives the Queen the tools to manage them.

---

## Your Files (OWNED)

| File | Action |
|------|--------|
| `src/formicos/core/events.py` | 4 new events, additive ThreadCreated fields, union 41→45 |
| `src/formicos/core/ports.py` | 4 event type names to EventTypeName literal |
| `src/formicos/surface/projections.py` | Thread fields, 3 new handlers, augment 3 colony handlers |
| `src/formicos/surface/queen_runtime.py` | Thread context builder, 3 new tools + dispatch |
| `src/formicos/surface/runtime.py` | `create_thread()` accepts goal + expected_outputs |
| `config/caste_recipes.yaml` | Add `query_service` to Queen tool list |

## DO NOT TOUCH

- `src/formicos/engine/service_router.py` — Track B owns this
- `src/formicos/surface/maintenance.py` — Track B creates this
- `src/formicos/surface/colony_manager.py` — Track B modifies this
- `src/formicos/surface/memory_store.py` — Track B modifies this
- `src/formicos/surface/knowledge_catalog.py` — Track B modifies this
- `src/formicos/surface/app.py` — Track B modifies this
- `frontend/` — Track C owns all frontend files
- `src/formicos/surface/routes/knowledge_api.py` — Tracks B and C own this

---

## Tasks

### A1. Thread lifecycle events + additive fields

**File: `src/formicos/core/events.py`**

Add four new event classes. Exact schemas in algorithms S1 — copy them verbatim:
- `ThreadGoalSet` — workspace_id, thread_id, goal, expected_outputs
- `ThreadStatusChanged` — workspace_id, thread_id, old_status, new_status, reason
- `MemoryEntryScopeChanged` — entry_id, old_thread_id, new_thread_id, workspace_id
- `DeterministicServiceRegistered` — service_name, description, workspace_id

Add additive fields to existing `ThreadCreated` (backward-compatible defaults):
```python
goal: str = Field(default="", description="Optional workflow goal (Wave 29).")
expected_outputs: list[str] = Field(
    default_factory=list,
    description="Optional expected artifact types (Wave 29).",
)
```

Add all four new events to the `FormicOSEvent` union (lines 719-764). Union grows from 41 to 45 members.

**File: `src/formicos/core/ports.py`**

Add `"ThreadGoalSet"`, `"ThreadStatusChanged"`, `"MemoryEntryScopeChanged"`, `"DeterministicServiceRegistered"` to the `EventTypeName` literal.

### A2. Thread projection upgrade

**File: `src/formicos/surface/projections.py`**

Extend `ThreadProjection` (line 192) with 7 new fields. See algorithms S3 for exact dataclass.

Add 3 new event handlers (algorithms S3):
- `_on_thread_goal_set` — sets thread.goal and thread.expected_outputs
- `_on_thread_status_changed` — sets thread.status
- `_on_memory_entry_scope_changed` — updates entry thread_id in `store.memory_entries`

Register all three plus a no-op for `DeterministicServiceRegistered` in `_HANDLERS` dict (around line 695).

Augment existing `_on_thread_created` (line 288) to populate `goal` and `expected_outputs` from the additive event fields.

Augment existing `_on_colony_spawned` (line 306): increment `thread.colony_count`. **Important**: `ColonySpawned` has typed `thread_id` and `workspace_id` fields — use `e.thread_id` and `e.workspace_id` directly, not address parsing.

Augment existing `_on_colony_completed` (line 334): increment `thread.completed_colony_count`, populate `thread.artifact_types_produced` from `e.artifacts`.

Augment existing `_on_colony_failed` (line 343): increment `thread.failed_colony_count`.

### A3. Queen thread context injection

**File: `src/formicos/surface/queen_runtime.py`**

Add `_build_thread_context(self, thread_id, workspace_id) -> str` method. See algorithms S5 for exact implementation. Returns a formatted block showing goal, status, progress, missing outputs.

Inject in `respond()` method: after system prompt, before conversation history, insert the thread context block as a system message.

### A4. Queen thread management tools

**File: `src/formicos/surface/queen_runtime.py`**

Add two tools to `_queen_tools()`: `set_thread_goal` and `complete_thread`. See algorithms S6 for exact tool specs and dispatch code.

`set_thread_goal` dispatch: emit `ThreadGoalSet` event.
`complete_thread` dispatch: read current thread status from projection, emit `ThreadStatusChanged` with new_status="completed".

### A5. Queen gains query_service

**File: `src/formicos/surface/queen_runtime.py`**

Add `query_service` tool to `_queen_tools()`. See algorithms S6 for tool spec.

Dispatch: access the ServiceRouter via `self._runtime.colony_manager.service_router` (the router lives on ColonyManager at colony_manager.py:225 — there is no `runtime.service_router` shortcut). Call `router.query()` with the same pattern the agent tool uses in runner.py:1269.

**File: `config/caste_recipes.yaml`**

Add `query_service` to the Queen's tool list.

### A6. Thread goal on create_thread

**File: `src/formicos/surface/runtime.py`**

Modify `create_thread()` (line 462) to accept optional `goal: str = ""` and `expected_outputs: list[str] | None = None`. Pass them through to the `ThreadCreated` event constructor.

**Scope limit**: Only modify `create_thread()`. Do NOT modify `retrieve_relevant_memory()` (line 948) or `fetch_knowledge_for_colony()` (line 1002) — Track B owns those.

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify:
1. Event union has exactly 45 members
2. `ThreadProjection` has 12 fields (5 original + 7 new)
3. `_HANDLERS` dict has entries for all 4 new event types
4. Queen's `_queen_tools()` returns 3 additional tools
5. `create_thread()` signature accepts `goal` and `expected_outputs`
6. Existing tests still pass — no regressions

---

## Coordination Notes

- Track B depends on your event definitions. Land the 4 new events + union expansion first if possible so B can import them. If working truly in parallel, B can stub the imports.
- Track B will add one handler (`_on_memory_entry_scope_changed`) and one dispatch entry to projections.py. Your handler additions and theirs touch different sections — no conflict expected.
- Track B will modify `runtime.py` but only `retrieve_relevant_memory()` and `fetch_knowledge_for_colony()`. Your change to `create_thread()` is in a completely different section.
- If `CLAUDE.md` and active wave docs conflict with root `AGENTS.md`, the wave docs win for this dispatch.
