# Coder 2 — Track B: Thread-Scoped Knowledge + Deterministic Service Handlers

**Wave:** 29 — "Workflow Threads"
**Track:** B — Thread-scoped knowledge retrieval, ServiceRouter deterministic handlers, dead event resurrection, maintenance services
**Dependencies:** Uses event types created by Track A (`MemoryEntryScopeChanged`, `DeterministicServiceRegistered`). Can stub imports until A lands.
**Algorithms reference:** `docs/waves/wave_29/wave_29_algorithms.md` sections S2, S4, S7, S8, S9, S10, S11.

---

## Context

All knowledge lives in a flat workspace-wide pool. `memory_store.search()` filters by `workspace_id` but has no thread concept. The ServiceRouter (engine/service_router.py) is monomorphic — it always injects text into a colony and waits for a text response. `ServiceQuerySent` and `ServiceQueryResolved` events are fully defined with projection handlers wired, but **never emitted anywhere**. This track fixes all three problems.

---

## Your Files (OWNED)

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | `thread_id` field on MemoryEntry |
| `src/formicos/engine/service_router.py` | Handler registry, pre-dispatch bypass, emit_fn, event emission helpers |
| `src/formicos/surface/colony_manager.py` | Tag extracted entries with thread_id |
| `src/formicos/surface/knowledge_catalog.py` | Thread-aware search with boost |
| `src/formicos/surface/memory_store.py` | Thread-aware Qdrant queries |
| `src/formicos/surface/runtime.py` | `thread_id` param on `retrieve_relevant_memory()` and `fetch_knowledge_for_colony()` |
| `src/formicos/surface/projections.py` | `_on_memory_entry_scope_changed` handler + dispatch entry (ONE handler only) |
| `src/formicos/surface/routes/knowledge_api.py` | Thread filter on search endpoint |
| `src/formicos/surface/maintenance.py` | **NEW FILE** — dedup + stale sweep handlers |
| `src/formicos/surface/app.py` | Register handlers at startup, set emit_fn |

## DO NOT TOUCH

- `src/formicos/core/events.py` — Track A owns all event definitions
- `src/formicos/core/ports.py` — Track A owns EventTypeName
- `src/formicos/surface/queen_runtime.py` — Track A owns Queen tools + context
- `src/formicos/engine/runner.py` — No changes in Wave 29
- `src/formicos/engine/context.py` — No changes in Wave 29
- `frontend/` — Track C owns all frontend
- `config/caste_recipes.yaml` — Track A owns this

---

## Tasks

### B1. MemoryEntry gains thread_id

**File: `src/formicos/core/types.py`**

Add to the `MemoryEntry` model:
```python
thread_id: str = Field(
    default="",
    description="Thread scope. Empty = workspace-wide (Wave 29).",
)
```

Backward-compatible — empty default means existing entries are workspace-wide.

### B2. Extraction tags entries with thread_id

**File: `src/formicos/surface/colony_manager.py`**

In the memory extraction flow, after `build_memory_entries()` returns entries, tag each one with the source colony's `thread_id`:

```python
colony_proj = self._runtime.projections.get_colony(colony_id)
thread_id = colony_proj.thread_id if colony_proj else ""
for entry in entries:
    entry["thread_id"] = thread_id
```

See algorithms S10.

### B3. Scope-change handler in projections

**File: `src/formicos/surface/projections.py`**

Add ONE handler — `_on_memory_entry_scope_changed`. See algorithms S3 for implementation:

```python
def _on_memory_entry_scope_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryScopeChanged = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["thread_id"] = e.new_thread_id
```

Add dispatch entry to `_HANDLERS` dict (around line 695):
```python
"MemoryEntryScopeChanged": _on_memory_entry_scope_changed,
```

**Scope limit**: Track A owns all other projection changes (thread fields, colony handler augmentation, goal/status handlers). You add exactly one handler and one dispatch entry.

### B4. Thread-aware knowledge catalog search

**File: `src/formicos/surface/knowledge_catalog.py`**

Add `thread_id: str = ""` parameter to the `search()` method. When non-empty, implement two-phase search with thread boost. See algorithms S7 for exact logic:

- Phase 1: search with `thread_id` filter, boost each score by `THREAD_BONUS = 0.25`
- Phase 2: search workspace-wide (no thread filter)
- Merge, deduplicate (thread-boosted version wins), add legacy, sort descending, return top_k

When `thread_id` is empty, existing behavior is unchanged.

### B5. Thread-aware memory store queries

**File: `src/formicos/surface/memory_store.py`**

Add `thread_id: str = ""` parameter to `search()` (line 115). When non-empty, add a Qdrant `should` filter clause to boost matching entries. Pass through to both `_search_qdrant_filtered` and `_search_fallback`.

### B6. Runtime passes thread_id through retrieval

**File: `src/formicos/surface/runtime.py`**

Modify these two methods ONLY:

- `retrieve_relevant_memory()` (line 948): add `thread_id: str = ""` parameter, pass to `catalog.search()`.
- `fetch_knowledge_for_colony()` (line 1002): add `thread_id: str = ""` parameter, pass to `catalog.search()`.

**Scope limit**: Do NOT modify `create_thread()` (line 462) — Track A owns that.

### B7. Knowledge API thread filter

**File: `src/formicos/surface/routes/knowledge_api.py`**

Add `?thread=<thread_id>` query parameter support on the existing search endpoint. Pass through to `knowledge_catalog.search()`.

**Scope limit**: Do NOT add the promote or maintenance trigger endpoints — Track C owns those.

### B8. ServiceRouter deterministic handler registry

**File: `src/formicos/engine/service_router.py`**

This is the core architectural change. See algorithms S4 for complete pseudocode.

**Extend `__init__`** (line 57): add `_handlers: dict[str, Callable] = {}` and `_emit_fn: Callable | None = None`.

**Add `register_handler()`**: registers an async callable `(query_text: str, ctx: dict) -> str`. Handler takes precedence over colony registration for the same service_type. Log a warning if both a handler and colony are registered for the same type.

**Add `set_emit_fn()`**: stores the event emission callback.

**Modify `query()`** (line 114): Insert the handler check BEFORE `colony_id = self._registry.get(service_type)`. If `service_type in self._handlers`, call the handler directly, emit events, return result — bypass the entire inject/wait/extract path.

Note on `_make_request_id(service_type)`: the static method uses `colony_id[-8:]` as suffix. Passing `service_type` like `"service:consolidation:dedup"` yields suffix `"up:dedup"` — functional and distinguishable from colony-based IDs.

**Add event emission helpers**: `_emit_service_query_sent()` and `_emit_service_query_resolved()`. These use lazy imports from `formicos.core.events` (core→core import is layer-safe). The `emit_fn` callback is injected from surface — no surface imports in engine. See algorithms S4 for exact implementations.

### B9. Emit events from BOTH paths

In the modified `query()`, add `_emit_service_query_sent` before dispatch and `_emit_service_query_resolved` after response — for BOTH the new handler path AND the existing colony path. This fixes the pre-existing bug where `ServiceQuerySent`/`ServiceQueryResolved` were never emitted. The projection handlers at projections.py:573-626 will now receive events and populate colony chat messages.

### B10. Maintenance handlers

**File: `src/formicos/surface/maintenance.py`** (NEW)

Create this file with two handler factories. See algorithms S8 for complete implementations:

- `make_dedup_handler(runtime)` — returns async callable. Scans verified entries, computes cosine similarity via `memory_store.search()`. **Important**: `memory_store.search()` returns cosine *similarity* (higher = more similar), NOT distance. Use `hit.get("score", 0.0)` directly. Auto-merge at ≥0.98 (emit `MemoryEntryStatusChanged` with status="rejected"). Flag pairs in [0.82, 0.98).

- `make_stale_handler(runtime)` — returns async callable. Entries unaccessed for 90+ days transition to stale via `MemoryEntryStatusChanged`. No confidence decay — deferred to Wave 30 Bayesian model.

### B11. Register handlers at startup

**File: `src/formicos/surface/app.py`**

In the lifespan startup, after `ColonyManager` and `ServiceRouter` are available:

1. Register both maintenance handlers on `service_router`
2. Call `service_router.set_emit_fn(runtime.emit_and_broadcast)`
3. Emit `DeterministicServiceRegistered` events for operator visibility

See algorithms S9 for exact startup code.

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify:
1. `python scripts/lint_imports.py` passes — engine/service_router.py has NO surface imports (only core imports + callback injection)
2. `MemoryEntry` has `thread_id` field with empty default
3. `ServiceRouter` has `_handlers` dict and `register_handler()` method
4. `query()` checks handlers before colony lookup
5. Both handler path and colony path emit `ServiceQuerySent`/`ServiceQueryResolved`
6. `maintenance.py` exists with both handler factories
7. Existing service router tests still pass

---

## Coordination Notes

- Track A creates the event types you import (`MemoryEntryScopeChanged`, `DeterministicServiceRegistered`). If working in parallel, stub the imports:
  ```python
  try:
      from formicos.core.events import MemoryEntryScopeChanged
  except ImportError:
      pass  # Track A lands first
  ```
  But prefer waiting for A's event union to land.
- You and Track A both modify `projections.py` — you add one handler + one dispatch entry, they add thread fields + augment colony handlers. Different sections, both additive.
- You and Track A both modify `runtime.py` — you modify `retrieve_relevant_memory()` (line 948) and `fetch_knowledge_for_colony()` (line 1002). They modify `create_thread()` (line 462). Disjoint methods.
- Track C will add promote and maintenance trigger endpoints to `routes/knowledge_api.py`. You add the thread filter param to the existing search endpoint. Different routes, no conflict.
- If `CLAUDE.md` and active wave docs conflict with root `AGENTS.md`, the wave docs win for this dispatch.
