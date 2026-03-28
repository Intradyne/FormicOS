# Wave 67.5 - Team A: Provenance Chain and Browser Detail Surface

**Wave:** 67.5 (surfaces)
**Track:** 5 - Provenance Chain on Projections
**Prerequisite:** Wave 67.0 landed and stable
**Dispatch note:** This track is a single vertical slice. Do not split the
backend and frontend work across separate coders unless staffing changes force it.

---

## Mission

The knowledge browser can show where an entry came from, but it still cannot
show how that entry evolved over time. Operators cannot answer:

- when confidence changed
- whether the entry was merged or refined
- which operator actions touched it

Your job: add an append-only `provenance_chain` to projection entries, expose
it through a dedicated knowledge API endpoint, and surface it in the browser
detail view. While you are in the browser, make the existing score bar visible
in the default list item body instead of hiding it inside the confidence hover.

---

## Contract Blocker

Operator approval is required before changing:

- `docs/contracts/types.ts`
- `frontend/src/types.ts`

Use snake_case to match the existing knowledge API payload style:

```typescript
export interface ProvenanceChainItem {
  event_type: string;
  timestamp: string;
  actor_id: string;
  detail: string;
  confidence_delta: number | null;
}
```

If you add a typed response interface for the new endpoint, mirror that in
both contract files in the same patch.

---

## Owned Files

| File | Change |
|------|--------|
| `src/formicos/surface/projections.py` | Append provenance items from the relevant event handlers |
| `src/formicos/surface/routes/knowledge_api.py` | Add `GET /api/v1/knowledge/{item_id}/provenance` |
| `frontend/src/components/knowledge-browser.ts` | Fetch and render provenance timeline; move score bar into default card body |
| `frontend/src/types.ts` | Add `ProvenanceChainItem` mirror |
| `docs/contracts/types.ts` | Add `ProvenanceChainItem` contract mirror |
| `tests/unit/surface/test_provenance_chain.py` | New backend tests |

---

## Do Not Touch

- `core/events.py`, `core/types.py` - no new events and no model changes
- `knowledge_catalog.py` - Team B owns retrieval changes
- `memory_extractor.py`, `colony_manager.py`, `memory_store.py` - landed in 67.0
- Any addon files - Team C owns the docs indexer

---

## Repo Truth You Must Read First

### `src/formicos/surface/projections.py`

Relevant handlers already exist:

- `_on_memory_entry_created()`
- `_on_memory_confidence_updated()`
- `_on_memory_entry_merged()`
- `_on_memory_entry_refined()`
- `_on_knowledge_entry_operator_action()`
- `_on_knowledge_entry_annotated()`

Important repo-truth detail:

- `MemoryEntryMerged` should update both the target and source entry chains
- if you only annotate the surviving target, the absorbed source entry loses
  part of its lifecycle

### `src/formicos/core/events.py`

Read the event payloads before writing details:

- `MemoryConfidenceUpdated`
- `MemoryEntryMerged`
- `MemoryEntryRefined`
- `KnowledgeEntryOperatorAction`
- `KnowledgeEntryAnnotated`

### `frontend/src/components/knowledge-browser.ts`

Repo truth today:

- `_toggleDetail()` already fetches entry detail and relationships
- `_renderScoreBar()` already exists
- the score bar currently looks for `score_breakdown`, but search payloads may
  still expose `_score_breakdown`
- the bar is rendered inside the confidence hover detail, not in the main card body

Your UI work should stay compatible with both `score_breakdown` and
`_score_breakdown`.

---

## Implementation Steps

### Step 1: Add a small helper in `projections.py`

Avoid repeating the same list-append logic in six handlers. Add a local helper
near the knowledge-entry handlers, for example:

```python
def _append_provenance_item(
    entry: dict[str, Any],
    *,
    event_type: str,
    timestamp: str,
    actor_id: str,
    detail: str,
    confidence_delta: float | None = None,
) -> None:
    chain = entry.setdefault("provenance_chain", [])
    chain.append({
        "event_type": event_type,
        "timestamp": timestamp,
        "actor_id": actor_id,
        "detail": detail,
        "confidence_delta": confidence_delta,
    })
```

Keep it append-only. Do not create separate shadow state.

### Step 2: Instrument the relevant handlers

Append a provenance item from these handlers:

1. `MemoryEntryCreated`
2. `MemoryConfidenceUpdated`
3. `MemoryEntryMerged`
4. `MemoryEntryRefined`
5. `KnowledgeEntryOperatorAction`
6. `KnowledgeEntryAnnotated`

Suggested details:

- `MemoryEntryCreated`: `"Created by colony <id>"`
- `MemoryConfidenceUpdated`: `"Confidence updated (<reason>)"`
- `MemoryEntryMerged` target: `"Merged entry <source_id> into this entry"`
- `MemoryEntryMerged` source: `"Merged into entry <target_id>"`
- `MemoryEntryRefined`: `"Refined via <refinement_source>"`
- `KnowledgeEntryOperatorAction`: `"Operator action: <action>"`
- `KnowledgeEntryAnnotated`: `"Annotation added"` plus tag when present

Use `actor_id` consistently:

- source colony id for colony-driven events when available
- operator `actor` for operator events
- empty string for maintenance/system events with no actor id

For `confidence_delta`, use a single numeric delta in posterior mean:

```python
old_mean = e.old_alpha / (e.old_alpha + e.old_beta)
new_mean = e.new_confidence
confidence_delta = round(new_mean - old_mean, 4)
```

Do not try to encode both alpha and beta deltas into the typed field. Put any
extra alpha/beta context into the human-readable `detail` string if useful.

### Step 3: Add the provenance endpoint

In `routes/knowledge_api.py`, add:

```text
GET /api/v1/knowledge/{item_id}/provenance
```

Return shape:

```json
{
  "entry_id": "mem-123",
  "chain": [...],
  "total": 6
}
```

Guidance:

- use the existing `_err_response()` helper
- return `KNOWLEDGE_ITEM_NOT_FOUND` when the entry is absent
- keep the endpoint read-only and projection-backed

### Step 4: Mirror the frontend contract

Add `ProvenanceChainItem` to:

- `docs/contracts/types.ts`
- `frontend/src/types.ts`

If you add a typed endpoint response, mirror that too.

### Step 5: Render the browser timeline

In `knowledge-browser.ts`:

1. add provenance cache state, for example:

```typescript
@state() private _provCache: Record<string, ProvenanceChainItem[]> = {};
```

2. add `_fetchProvenance(entryId)` alongside `_fetchRelationships()`
3. call it from `_toggleDetail()` when an entry expands
4. render a timeline block in the expanded detail area

Suggested rendering:

- `timeAgo(item.timestamp)`
- event label from `event_type`
- detail text
- optional confidence delta badge such as `+0.07` / `-0.03`

Keep the UI compact. This is an audit trail, not a second full detail page.

### Step 6: Make score bars visible by default

Move the score bar into the main card body so it is visible without hovering.

Update `_renderScoreBar()` to read either field:

```typescript
const sb =
  e.score_breakdown ??
  (e as Record<string, unknown>)._score_breakdown as Record<string, number> | undefined;
```

Do not add retrieval logic here. Team B owns the backend scoring changes.

---

## Tests

Create `tests/unit/surface/test_provenance_chain.py`.

Required tests:

1. `test_memory_entry_created_seeds_provenance_chain`
2. `test_memory_confidence_updated_appends_delta`
3. `test_memory_entry_merged_updates_target_and_source_chains`
4. `test_provenance_endpoint_returns_chain`

Optional fifth test if time allows:

5. `test_operator_annotation_appends_provenance_item`

You do not need frontend unit tests unless there is already a nearby pattern,
but the browser change should be exercised manually by code review and local run.

---

## Acceptance Gates

1. Relevant events append to `provenance_chain`
2. `MemoryEntryMerged` annotates both target and source entries
3. Provenance survives replay because it is projection-derived from events
4. `GET /api/v1/knowledge/{item_id}/provenance` returns the chain
5. Browser detail view shows a provenance timeline
6. Score bar is visible in the default result card body
7. `_renderScoreBar()` works with either `score_breakdown` or `_score_breakdown`
8. No new events and no core model changes

---

## Validation

Run before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## Merge Order

This track is independent of Team C's addon work.

Prefer Team B landing first because retrieval changes may improve the score-bar
payloads this browser work can display, but this track should not block on Team B.

---

## Track Summary Template

When done, report:

1. Which handlers append provenance items
2. Whether `MemoryEntryMerged` updates both source and target chains
3. Which route file owns the provenance endpoint
4. Whether the browser now reads both `score_breakdown` and `_score_breakdown`
5. Any small audit fixes found within the owned files
