# Wave 29 Plan -- Workflow Threads

**Wave:** 29 -- "Workflow Threads"
**Theme:** Threads become workflow scopes with goals, progress tracking, and thread-scoped knowledge. Service colonies gain deterministic handlers -- registered Python callables that dispatch through the existing `ServiceRouter` without LLM token spend. Dead service query events are brought to life. The first maintenance services (dedup consolidation, stale sweep) prove the pattern.
**Architectural thesis:** A thread is a workflow. A service colony can be a deterministic function. Both extend existing infrastructure rather than creating parallel concepts.
**Contract changes:** Event union opens from 41 to 45. Four new event types: `ThreadGoalSet`, `ThreadStatusChanged`, `MemoryEntryScopeChanged`, `DeterministicServiceRegistered`. Additive `thread_id` field on `MemoryEntry`. Additive fields on `ThreadCreated` (optional `goal`, `expected_outputs`). No new ports.
**Estimated LOC delta:** ~550 Python, ~250 TypeScript

---

## Why This Wave

After Wave 28, FormicOS has a unified knowledge lifecycle but two structural gaps:

**Gap 1: All knowledge lives in a flat workspace-wide pool.** Thread-scoped knowledge would make retrieval precise -- Python API experiences shouldn't pollute React colony context. The Queen reasons about "what does the workspace know" rather than "what does this workflow need."

**Gap 2: Maintenance operations have no infrastructure.** Dedup, stale decay, and health reporting either run as fire-and-forget tasks or don't exist. These deserve the audit trail and operator visibility of the service colony system without LLM token spend.

These gaps reinforce each other: thread-scoped knowledge is more valuable when the system can maintain it, and maintenance services are more precise when they operate on well-scoped knowledge rather than a flat pool.

---

## Current Repo Truth: What Exists Today

### Service colonies are real but incomplete

The service colony system has substantial infrastructure:

- `ColonyServiceActivated` event -- activates a completed colony as a persistent service
- `ServiceQuerySent` / `ServiceQueryResolved` events -- **defined in core/events.py with full schemas, projection handlers wired at projections.py lines 573-626, but never emitted anywhere in runtime code**
- `engine/service_router.py` -- 200 LOC router with registry, inject/wait/extract protocol, async request/response matching
- Agent tool `query_service` dispatches through the router
- Colony detail has a service banner in the frontend

`ServiceRouter.query()` is monomorphic: it always formats a text message, injects it into a running service colony via `inject_fn`, and waits for the colony's agent to emit a `[Service Response: id]` text block. There is no dispatch abstraction, no handler type concept, no way to execute a Python callable instead.

The Queen **cannot query services**. No `query_service` tool exists in `queen_runtime.py`.

### Threads are named containers with no operational semantics

`ThreadProjection` has exactly 5 fields:

```python
class ThreadProjection:
    id: str           # same as name
    workspace_id: str
    name: str
    colonies: dict[str, ColonyProjection]
    queen_messages: list[QueenMessageProjection]
```

Thread `id` IS the thread `name` (confirmed: `_on_thread_created` at projections.py:288 uses `e.name` as both key and id). No goal, no status, no progress tracking.

`thread_id` appears **nowhere** in the engine layer. No retrieval, routing, governance, or chaining logic uses it.

---

## Critical Design Decisions

### D1. Threads gain goal, expected outputs, and status

`ThreadGoalSet` event carries goal and expected output types. `ThreadStatusChanged` transitions between active/completed/archived. Progress is derived from existing colony events by augmenting their projection handlers.

### D2. Thread-scoped knowledge is preferential, not exclusive

Entries from colonies within a thread are tagged with `thread_id`. Retrieval hierarchy: thread-scoped (score boosted) -> workspace-wide (normal) -> legacy (lowest). Thread entries remain discoverable outside their thread. Operator can promote to workspace-wide via `MemoryEntryScopeChanged`.

### D3. Deterministic handlers extend ServiceRouter with a pre-dispatch bypass

`ServiceRouter` gains `_handlers: dict[str, Callable]`. In `query()`, before the inject-wait-extract path, check handlers first:

```
query(service_type, query_text, ...)
  -> if service_type in _handlers: await handler(query_text, ctx) and return
  -> else: existing inject-wait-extract colony path
```

This is a ~15-line change to `query()`. Handler takes precedence. Handler registration and colony registration are mutually exclusive per service_type.

### D4. Dead service events come to life

`ServiceQuerySent` and `ServiceQueryResolved` have full schemas (request_id, service_type, target_colony_id, sender_colony_id, query_preview, response_preview, latency_ms, artifact_count) and wired projection handlers. Wave 29 emits these from `ServiceRouter.query()` for BOTH deterministic handler dispatch AND existing colony dispatch. This fixes a pre-existing bug and makes the full service audit trail functional.

The router gains an `emit_fn` callback (same injection pattern as `inject_fn`) set from `surface/app.py` at startup.

### D5. Queen gains service query capability

Add `query_service` to the Queen's tool list and dispatch in `queen_runtime.py`. Uses the same `ServiceRouter.query()` path that agents already use, accessed via `runtime.colony_manager.service_router` (colony_manager.py:225). Enables the Queen to trigger maintenance services and query any active service colony.

### D6. First deterministic services: consolidation and stale sweep

Two handlers registered at startup:
- `service:consolidation:dedup` -- cosine similarity scan, auto-merge >= 0.98, flag [0.82, 0.98)
- `service:consolidation:stale_sweep` -- 90-day stale transition (confidence decay deferred to Wave 30 Bayesian model)

### D7. No engine layer changes for threads

Thread scoping resolves in the surface layer. `context.py` and `runner.py` are unchanged.

---

## New Events (41 -> 45)

### ThreadGoalSet

```python
class ThreadGoalSet(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ThreadGoalSet"] = "ThreadGoalSet"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    goal: str = Field(..., description="Workflow objective.")
    expected_outputs: list[str] = Field(default_factory=list)
```

### ThreadStatusChanged

```python
class ThreadStatusChanged(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["ThreadStatusChanged"] = "ThreadStatusChanged"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    old_status: str = Field(...)
    new_status: str = Field(..., description="active | completed | archived")
    reason: str = Field(default="")
```

### MemoryEntryScopeChanged

```python
class MemoryEntryScopeChanged(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["MemoryEntryScopeChanged"] = "MemoryEntryScopeChanged"
    entry_id: str = Field(...)
    old_thread_id: str = Field(default="")
    new_thread_id: str = Field(default="", description="Empty = workspace-wide.")
    workspace_id: str = Field(...)
```

### DeterministicServiceRegistered

```python
class DeterministicServiceRegistered(EventEnvelope):
    model_config = FrozenConfig
    type: Literal["DeterministicServiceRegistered"] = "DeterministicServiceRegistered"
    service_name: str = Field(...)
    description: str = Field(default="")
    workspace_id: str = Field(default="system")
```

### Additive on ThreadCreated

```python
goal: str = Field(default="")
expected_outputs: list[str] = Field(default_factory=list)
```

### Additive on MemoryEntry

```python
thread_id: str = Field(default="")
```

All backward-compatible.

---

## Tracks

### Track A -- Thread Model + Queen Awareness

**Goal:** Threads carry goals, track progress, and influence Queen reasoning. The Queen can set thread goals, complete threads, and query services.

**A1. Thread projection upgrade.** Extend the 5-field `ThreadProjection` with: `goal`, `expected_outputs`, `status`, `colony_count`, `completed_colony_count`, `failed_colony_count`, `artifact_types_produced`. Add handlers for new events. Augment `_on_colony_spawned`, `_on_colony_completed`, `_on_colony_failed` to track thread progress. Populate goal from additive `ThreadCreated` fields in `_on_thread_created`.

**A2. Thread lifecycle events + additive fields.** Four new events in `core/events.py`. Additive fields on `ThreadCreated`. Union 41 -> 45. Update `ports.py`.

**A3. Queen thread context injection.** Thread context block before conversation history showing goal, progress, missing outputs.

**A4. Queen thread management tools.** `set_thread_goal` and `complete_thread`.

**A5. Queen gains query_service.** Add to Queen tool list, dispatch, and `caste_recipes.yaml`.

**A6. Thread goal on create_thread.** `runtime.create_thread()` accepts optional `goal` and `expected_outputs`.

| File | Action |
|------|--------|
| `src/formicos/core/events.py` | 4 new events, additive ThreadCreated fields, union 41->45 |
| `src/formicos/core/ports.py` | add 4 event names |
| `src/formicos/surface/projections.py` | thread progress fields, new handlers, augment colony handlers |
| `src/formicos/surface/queen_runtime.py` | thread context, thread tools, query_service |
| `src/formicos/surface/runtime.py` | thread goal on create_thread |
| `config/caste_recipes.yaml` | add query_service to Queen tools |

---

### Track B -- Thread-Scoped Knowledge + Deterministic Service Handlers

**Goal:** Knowledge retrieval becomes hierarchical by thread. ServiceRouter gains deterministic handler dispatch. Dead service events come to life. First maintenance services prove the pattern.

**B1. MemoryEntry gains thread_id.** Additive field in `core/types.py`.

**B2. Extraction tags entries with thread_id.** In `colony_manager._extract_institutional_memory()`.

**B3. Projection handler for MemoryEntryScopeChanged.** Updates entry thread_id. Existing sync_entry pushes to Qdrant.

**B4. Knowledge catalog thread-aware search.** Two-phase: thread-boosted + workspace-wide, merged with `THREAD_BONUS = 0.25`.

**B5. Memory store thread-aware queries.** Qdrant `should` clause to boost matching thread_id.

**B6. Runtime and colony manager pass thread_id.** Through fetch and callbacks.

**B7. Knowledge API thread filter.** `?thread=...` parameter.

**B8. Deterministic handler registry on ServiceRouter.** `_handlers` dict. Pre-dispatch bypass in `query()`. Handler takes precedence over colony registration.

**B9. Emit ServiceQuerySent/ServiceQueryResolved.** From BOTH deterministic and colony paths. Add `emit_fn` callback to ServiceRouter. Fixes dead-event bug for existing colony services too.

**B10. Maintenance handlers.** New `surface/maintenance.py` with dedup and stale sweep.

**B11. Register handlers at startup.** In `app.py` lifespan. Set `emit_fn`. Emit `DeterministicServiceRegistered`.

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | thread_id on MemoryEntry |
| `src/formicos/surface/colony_manager.py` | tag entries with thread_id, thread_id in knowledge fetch |
| `src/formicos/surface/knowledge_catalog.py` | thread-aware search |
| `src/formicos/surface/memory_store.py` | thread-aware Qdrant queries |
| `src/formicos/surface/runtime.py` | thread_id in fetch + callbacks |
| `src/formicos/surface/projections.py` | scope-change handler |
| `src/formicos/surface/routes/knowledge_api.py` | thread filter |
| `src/formicos/engine/service_router.py` | handler registry, pre-dispatch bypass, emit ServiceQuery events |
| `src/formicos/surface/maintenance.py` | new -- dedup + stale handlers |
| `src/formicos/surface/app.py` | register handlers, set emit_fn |

---

### Track C -- Thread UX + Maintenance Operator Surface

**Goal:** Operator sees workflow progress, filters knowledge by thread, promotes entries, and triggers maintenance.

**C1. Thread view workflow progress.** Goal display, expected/produced checklist, colony counts, status badge, complete action.

**C2. Knowledge browser thread filter.** "All" / "This Thread" / "Workspace-wide" pills. Thread badges. Promote action.

**C3. Promote API endpoint.** `POST /api/v1/knowledge/{id}/promote`.

**C4. Maintenance trigger.** "Run Maintenance" button in knowledge browser. Calls service router via API.

**C5. Service query results display.** Verify colony chat renders ServiceQuerySent/Resolved chat messages.

**C6. Frontend types.** Expand QueenThread type with goal, status, progress fields.

| File | Action |
|------|--------|
| `frontend/src/components/thread-view.ts` | workflow progress display |
| `frontend/src/components/knowledge-browser.ts` | thread filter + promote + maintenance trigger |
| `frontend/src/types.ts` | thread types expansion |
| `src/formicos/surface/routes/knowledge_api.py` | promote + maintenance endpoints |

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | Dependencies |
|------|-------|-------------|
| Coder 1 | A (Thread model + Queen) | None -- starts immediately |
| Coder 2 | B (Thread knowledge + deterministic services) | Uses events from Track A union expansion |
| Coder 3 | C (Thread UX + maintenance UI) | Uses thread projection from A, knowledge API from B |

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `core/events.py` | A owns (4 events + ThreadCreated fields + union) | B uses what A creates |
| `projections.py` | A (thread fields + handlers + augment colony handlers), B (`_on_memory_entry_scope_changed` handler only) | Both additive, different sections. B adds one handler + one dispatch entry. |
| `runtime.py` | A owns `create_thread()` (line 462). B owns `retrieve_relevant_memory()` (line 948) and `fetch_knowledge_for_colony()` (line 1002) — add `thread_id` param to both. | Disjoint methods. No collision. |
| `routes/knowledge_api.py` | B (thread filter on existing search endpoint), C (new promote + maintenance endpoints) | Both additive, different routes |
| `caste_recipes.yaml` | A (add query_service to Queen) | Single owner |

---

## Acceptance Criteria

1. Threads have goals. ThreadGoalSet is emitted and projection carries goal/expected_outputs.
2. Threads track progress. Colony count, completed count, artifact types produced.
3. Threads have status. Completed or archived via ThreadStatusChanged.
4. Queen sees thread context before spawning. Goal, progress, missing outputs.
5. Queen can manage threads. set_thread_goal and complete_thread work.
6. Queen can query services. query_service dispatches through ServiceRouter.
7. Colonies inherit thread affinity from spawn context.
8. Memory entries carry thread_id from source colony.
9. Thread-scoped retrieval ranks thread entries above workspace entries.
10. Workspace-wide entries remain visible from any thread.
11. Knowledge browser shows thread filter with promote action.
12. Deterministic handlers dispatch through ServiceRouter. query() checks handlers before inject/wait/extract.
13. ServiceQuerySent/ServiceQueryResolved fire for ALL service queries -- both deterministic and colony. Projection handlers (lines 573-626) are no longer dead code.
14. Dedup consolidation runs. Entries above 0.98 auto-merged. [0.82, 0.98) flagged.
15. Stale sweep runs. 90-day unaccessed entries transition to stale.
16. Engine layer stable. `context.py` and `runner.py` have zero changes. `service_router.py` is modified (handler registry + event emission) but remains a pure-engine component with no surface imports.
17. Full CI green.

---

## Not In Wave 29

| Item | Reason |
|------|--------|
| Bayesian confidence evolution | Wave 30 |
| Thompson Sampling for retrieval | Wave 30 |
| Workflow step declarations | Wave 30 |
| Contradiction detection | Wave 30 |
| LLM-confirmed dedup [0.82, 0.98) | Wave 30 |
| Knowledge health dashboard | Wave 30 |
| Scheduled maintenance timer | Wave 30 |

---

## What This Enables Next

**Wave 30: Knowledge Metabolism + Composable Workflows.** Bayesian confidence from colony outcomes (Beta distribution on MemoryEntry). Thompson Sampling for retrieval (sample from Beta(alpha, beta) to balance exploitation vs exploration of uncertain entries). Workflow step declarations. Contradiction surfacing. Scheduled maintenance timer. Knowledge health dashboard.

**Wave 31: Ship Polish.** Automatic pipeline execution. Thread archival with decay. LLM-confirmed dedup. Documentation. Performance. Edge cases. Ready for real users.
