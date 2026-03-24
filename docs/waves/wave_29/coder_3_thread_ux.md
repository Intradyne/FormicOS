# Coder 3 — Track C: Thread UX + Maintenance Operator Surface

**Wave:** 29 — "Workflow Threads"
**Track:** C — Thread workflow display, knowledge browser thread filter, promote/maintenance endpoints, frontend types
**Dependencies:** Depends on Track A (ThreadProjection fields) and Track B (knowledge API thread filter, maintenance handlers). Start after A and B land their core changes, OR build against the documented interfaces.
**Algorithms reference:** `docs/waves/wave_29/wave_29_algorithms.md` section S11 (promote endpoint). Plan doc sections C1–C6.

---

## Context

The frontend renders threads as plain named containers via `<fc-thread-view>` (thread-view.ts) and `<fc-tree-nav>` (tree-nav.ts). `QueenThread` TypeScript type has `id`, `name`, `workspaceId`, `messages`. No goal, status, progress, or knowledge filtering. After Tracks A and B land, ThreadProjection carries goal/status/progress and knowledge entries carry thread_id — this track surfaces all of that to the operator.

---

## Your Files (OWNED)

| File | Action |
|------|--------|
| `frontend/src/components/thread-view.ts` | Workflow progress display |
| `frontend/src/components/knowledge-browser.ts` | Thread filter, promote action, maintenance trigger |
| `frontend/src/types.ts` | Thread + service type expansion |
| `src/formicos/surface/routes/knowledge_api.py` | Promote endpoint + maintenance trigger endpoint |

## DO NOT TOUCH

- `src/formicos/core/` — Track A owns events and types
- `src/formicos/engine/` — Track B owns service_router changes
- `src/formicos/surface/projections.py` — Tracks A and B own this
- `src/formicos/surface/queen_runtime.py` — Track A owns Queen tools
- `src/formicos/surface/colony_manager.py` — Track B owns this
- `src/formicos/surface/maintenance.py` — Track B creates this
- `src/formicos/surface/runtime.py` — Tracks A and B own this
- `src/formicos/surface/app.py` — Track B owns startup registration
- `src/formicos/surface/memory_store.py` — Track B owns this
- `src/formicos/surface/knowledge_catalog.py` — Track B owns this
- `config/` — Track A owns caste_recipes

---

## Tasks

### C1. Frontend types expansion

**File: `frontend/src/types.ts`**

Extend `QueenThread` interface (line 168) with fields matching Track A's extended ThreadProjection:

```typescript
export interface QueenThread {
  id: string;
  name: string;
  workspaceId: string | null;
  messages: QueenChatMessage[];
  // Wave 29 additions:
  goal?: string;
  expectedOutputs?: string[];
  status?: 'active' | 'completed' | 'archived';
  colonyCount?: number;
  completedColonyCount?: number;
  failedColonyCount?: number;
  artifactTypesProduced?: Record<string, number>;
}
```

All new fields are optional for backward-compatibility with existing state snapshots.

### C2. Thread view workflow progress

**File: `frontend/src/components/thread-view.ts`**

Extend `<fc-thread-view>` to display workflow information when the thread has a goal:

1. **Goal display**: Show `thread.goal` prominently below the thread name. If empty, don't render (existing behavior preserved).
2. **Expected/produced checklist**: For each `expectedOutputs` entry, show a check/missing indicator based on `artifactTypesProduced`. Format: `✓ code (2)` or `○ test (0)`.
3. **Colony counts**: Show `completedColonyCount / colonyCount` with failed count if non-zero.
4. **Status badge**: Render `thread.status` as a colored badge (active=blue, completed=green, archived=gray).
5. **Complete action**: Add a "Complete Thread" button that dispatches a `complete-thread` event with `{ threadId }`. Only show when status is `active` and `completedColonyCount > 0`.

Keep the existing rename, spawn, and broadcast functionality untouched.

### C3. Knowledge browser thread filter

**File: `frontend/src/components/knowledge-browser.ts`**

Add filter pills to the knowledge browser: "All" / "This Thread" / "Workspace-wide".

- "All" (default): existing behavior, no thread filter
- "This Thread": pass current thread_id to the search API (`?thread=<id>`)
- "Workspace-wide": pass `?thread=` (empty = workspace-wide only, no thread boost)

Add thread badges on knowledge entries that have a `thread_id` field.

Add a "Promote to workspace" action on thread-scoped entries. Calls `POST /api/v1/knowledge/{id}/promote`.

Add a "Run Maintenance" button that triggers dedup/stale services. Calls the service query endpoint — format TBD based on Track B's final API. Initial approach: `POST /api/v1/services/query` with body `{"service_type": "service:consolidation:dedup", "query": "run"}`.

### C4. Promote endpoint

**File: `src/formicos/surface/routes/knowledge_api.py`**

Add endpoint: `POST /api/v1/knowledge/{item_id}/promote`

See algorithms S11 for exact implementation:
- Look up entry in `projections.memory_entries`
- 404 if not found
- 400 if already workspace-wide (empty `thread_id`)
- Emit `MemoryEntryScopeChanged` event with `new_thread_id=""`
- Return `{"promoted": true, "entry_id": item_id}`

Import `MemoryEntryScopeChanged` from `formicos.core.events` (Track A creates this).

### C5. Maintenance trigger endpoint

**File: `src/formicos/surface/routes/knowledge_api.py`**

Add endpoint: `POST /api/v1/services/query`

Body: `{"service_type": "...", "query": "..."}`

Dispatches through `runtime.colony_manager.service_router.query()`. Returns the handler response as JSON. This is a thin HTTP wrapper over the same ServiceRouter.query() that agents and Queen use.

### C6. Service query chat display verification

Verify that `ServiceQuerySent` and `ServiceQueryResolved` events (now emitted by Track B) render correctly in colony chat views. The projection handlers at projections.py:573-626 add `ChatMessageProjection` entries with `event_kind="service"`. Confirm the existing `<fc-colony-detail>` or chat renderer displays these without changes. If styling is needed, add minimal CSS for service-kind messages.

---

## Validation

```bash
# Backend
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Frontend (if build tooling exists)
# Check for TypeScript compilation errors in frontend/
```

Verify:
1. `QueenThread` type has all 7 new optional fields
2. Thread view shows goal, progress, status when data is present
3. Thread view degrades gracefully (no goal = existing behavior)
4. Knowledge browser filter pills work with `?thread=` parameter
5. Promote endpoint returns 200 and emits `MemoryEntryScopeChanged`
6. Maintenance trigger dispatches through ServiceRouter
7. No regressions in existing thread-view or knowledge-browser behavior

---

## Coordination Notes

- You depend on Track A's `ThreadProjection` expansion for the data your UI renders. If building ahead, use the `QueenThread` type definition above and trust that the WebSocket state snapshot will populate these fields once A lands.
- You depend on Track B's `?thread=` search parameter and maintenance handlers. The promote endpoint is self-contained (just emits an event). The maintenance trigger endpoint depends on B's handler registration in app.py.
- Your `routes/knowledge_api.py` changes add NEW routes (promote, maintenance). Track B adds a query parameter to an existing route. No file-level conflicts.
- If `CLAUDE.md` and active wave docs conflict with root `AGENTS.md`, the wave docs win for this dispatch.
