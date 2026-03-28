# Wave 67.0 — Team A: Knowledge Hierarchy with Materialized Paths

**Track:** 1
**Mission:** Give knowledge entries structural organization via hierarchy
paths on projections. Ship a tree view in the knowledge browser and a
REST endpoint for the hierarchy. No new event types. No core model changes.

---

## Coordination Context

- `CLAUDE.md` defines the evergreen repo rules (4-layer architecture,
  69-event closed union, Pydantic v2, Beta posteriors).
- This prompt is the authority for Team A's scope. If `AGENTS.md` conflicts
  with this prompt, this prompt wins for this dispatch.
- Team B works in parallel on Tracks 2+3 (memory_extractor.py,
  colony_manager.py, scoring_math.py). No file overlap.
- **Merge order:** Team A merges first. Team B rebases on Team A's landing.

---

## ADR Reference

Read `docs/decisions/049-knowledge-hierarchy.md` before writing code. Key
decisions:

- Materialized path, not closure table (250x write amplification rejected)
- `hierarchy_path` and `parent_id` are projection-level fields only — NOT
  on `core/types.py` MemoryEntry model
- Topic nodes are synthetic projection entries (`entry_type="topic"`), not
  event-sourced
- ESS cap at 150 for branch confidence aggregation
- Bootstrap is LLM-only, zero new dependencies

---

## Owned Files

| File | Action | Est. Lines |
|------|--------|------------|
| `src/formicos/surface/projections.py` | Add hierarchy_path/parent_id in `_on_memory_entry_created` handler (line 1584) | ~8 |
| `src/formicos/surface/memory_store.py` | Add hierarchy_path to Qdrant payload metadata (lines 57–79) | ~3 |
| `src/formicos/surface/hierarchy.py` | **New file** — branch confidence aggregation (`compute_branch_confidence`) | ~40 |
| `src/formicos/surface/routes/api.py` | Add `GET /api/v1/workspaces/{id}/knowledge-tree` endpoint | ~45 |
| `frontend/src/components/knowledge-browser.ts` | Add tree subview, branch rendering, path filter | ~120 |
| `scripts/bootstrap_hierarchy.py` | **New file** — offline LLM-only hierarchy bootstrap | ~100 |
| `tests/unit/surface/test_hierarchy.py` | **New file** — hierarchy tests | ~80 |

---

## Do Not Touch

- `core/types.py` — No new MemoryEntry fields. Hierarchy is projection-only.
- `core/events.py` — No new events. The 69-event union is closed.
- `queen_runtime.py` — Queen orchestration, not in scope.
- `queen_tools.py` — Queen tools, not in scope.
- `knowledge_catalog.py` — Team B owns retrieval (Wave 67.5).
- `colony_manager.py` — Team B owns outcome confidence path.
- `memory_extractor.py` — Team B owns domain normalization.
- `scoring_math.py` — Team B owns ESS helper.

---

## Implementation Steps

### Step 1: hierarchy_path on projections

In `projections.py`, `_on_memory_entry_created()` handler (line 1584).
Before `store.memory_entries[entry_id] = data` (line 1595), after the
scope default (line 1594), add hierarchy path computation:

```python
# Wave 67: hierarchy path from primary domain
domains = data.get("domains", [])
primary_domain = domains[0] if domains else "uncategorized"
# Normalize (same logic as memory_extractor._normalize_domain, line 31-33)
import re
normalized = re.sub(r"[\s\-]+", "_", primary_domain.strip()).lower()
data["hierarchy_path"] = f"/{normalized}/"
data["parent_id"] = ""
```

**Why inline normalization instead of importing?** `_normalize_domain` is in
`memory_extractor.py` (line 31–33). Both files are Surface layer, so the
import is legal. But the function is 3 lines — inlining avoids a dependency
on an unrelated module. Either approach is acceptable.

**Note:** `parent_id` is scaffolding for future topic-level nesting. Nothing
reads it yet — it exists so the field is present from day one when topic
assignment is added later.

### Step 2: Qdrant payload field

In `memory_store.py`, where metadata is assembled for `VectorDocument`
(lines 57–79). Add `hierarchy_path` to the metadata dict:

```python
"hierarchy_path": entry.get("hierarchy_path", "/"),
```

This goes alongside the existing metadata fields (domains, status, decay_class,
etc.). Qdrant automatically indexes string payload fields as keyword indexes,
enabling filtered search via `must: [{key: "hierarchy_path", match: {value: "/engineering/"}}]`.

### Step 3: Branch confidence aggregation

Create `src/formicos/surface/hierarchy.py`:

```python
"""Knowledge hierarchy utilities — branch confidence aggregation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore


def compute_branch_confidence(
    store: "ProjectionStore",
    path_prefix: str,
) -> dict[str, Any]:
    """Aggregate Beta confidence for entries under a hierarchy branch.

    Returns {"alpha": float, "beta": float, "count": int, "mean": float}.
    Sums children's evidence (subtracting the Beta(5,5) prior from each),
    re-adds a single prior, and caps effective sample size at 150.

    ESS 150 is mathematically equivalent to exponential decay with
    gamma ≈ 0.993. Balances stability with responsiveness per production
    Thompson Sampling literature.
    """
    total_alpha = 0.0
    total_beta = 0.0
    count = 0
    for entry in store.memory_entries.values():
        if entry.get("entry_type") == "topic":
            continue  # don't count synthetic nodes
        hp = entry.get("hierarchy_path", "/")
        if hp.startswith(path_prefix):
            total_alpha += entry.get("conf_alpha", 5.0) - 5.0
            total_beta += entry.get("conf_beta", 5.0) - 5.0
            count += 1
    agg_alpha = 5.0 + total_alpha
    agg_beta = 5.0 + total_beta
    ess = agg_alpha + agg_beta
    if ess > 150:
        scale = 150.0 / ess
        agg_alpha *= scale
        agg_beta *= scale
    mean = agg_alpha / (agg_alpha + agg_beta) if (agg_alpha + agg_beta) > 0 else 0.5
    return {"alpha": agg_alpha, "beta": agg_beta, "count": count, "mean": mean}
```

This is called on-demand by the API, not stored in projection state. Pure
computation over existing data. The `ProjectionStore` type hint is
forward-referenced to avoid circular imports.

### Step 4: REST endpoint

In `routes/api.py`, add:

```
GET /api/v1/workspaces/{id}/knowledge-tree
```

Build a tree from all `memory_entries` for the workspace by grouping on
`hierarchy_path` segments. For each branch node, call
`compute_branch_confidence()` to get aggregated posteriors.

Response shape:

```json
{
  "branches": [
    {
      "path": "/engineering/",
      "label": "engineering",
      "entryCount": 42,
      "confidence": {"alpha": 28.3, "beta": 12.1, "mean": 0.70},
      "children": [
        {
          "path": "/engineering/auth/",
          "label": "auth",
          "entryCount": 12,
          "confidence": {"alpha": 15.2, "beta": 4.8, "mean": 0.76},
          "children": []
        }
      ]
    }
  ]
}
```

Place this near the existing knowledge endpoints. Use `_err_response()` for
errors (follow the existing api.py patterns — do NOT return raw JSONResponse
for errors).

### Step 5: Knowledge browser tree view

In `knowledge-browser.ts` (1,225 lines):

**5a. Extend SubView type** (line 12):
```typescript
// Current: type SubView = 'catalog' | 'graph';
// New:
type SubView = 'catalog' | 'graph' | 'tree';
```

**5b. Add tree toggle button** alongside existing catalog/graph buttons.

**5c. Add `_renderTreeView()` method:**
- Fetch from `GET /api/v1/workspaces/{wsId}/knowledge-tree`
- Render collapsible tree with branch name, entry count, and confidence bar
- Each branch is clickable → filters catalog to that hierarchy path prefix
- Use existing `_renderConfidenceBar()` patterns for branch confidence display

**5d. Existing `_renderScoreBar` (line 885)** is NOT moved in this track.
Score bar visibility changes are Track 5 (Wave 67.5).

### Step 6: Bootstrap script

Create `scripts/bootstrap_hierarchy.py`:

- **Offline tool**, not imported by the runtime
- Reads entries from REST API (`GET /api/v1/workspaces/{id}/knowledge`)
- Groups entries by existing domain tag (~20 entries per batch)
- For each domain batch, calls the LLM to identify 2–5 topic sub-clusters
- Assigns `hierarchy_path` values (e.g., `/python/testing/`, `/python/async/`)
- Persists by writing updated `hierarchy_path` values back via a PATCH or
  PUT endpoint on entries, or by replaying with a modified extraction
  prompt that includes hierarchy hints. The simplest approach: the script
  directly updates the projection dict via the REST API and the updated
  paths are picked up on next Qdrant sync. Since this is a one-time offline
  tool, exact persistence mechanism is left to the implementer — just
  ensure the result is visible in `GET /api/v1/workspaces/{id}/knowledge-tree`
- ~15 LLM calls for 300 entries across 15 domains
- Zero new dependencies

This script is a one-time bootstrap. Going forward, extraction-time domain
suggestion (Team B, Track 2) keeps new entries aligned organically.

---

## Tests

Write in `tests/unit/surface/test_hierarchy.py`:

1. **`test_memory_entry_created_sets_hierarchy_path`** —
   Process a `MemoryEntryCreated` event with `domains=["Python Testing"]`.
   Verify the projection entry has `hierarchy_path="/python_testing/"` and
   `parent_id=""`.

2. **`test_memory_entry_created_no_domains_gets_uncategorized`** —
   Process a `MemoryEntryCreated` event with `domains=[]`. Verify
   `hierarchy_path="/uncategorized/"`.

3. **`test_qdrant_payload_includes_hierarchy_path`** —
   Verify that `sync_entry()` includes `hierarchy_path` in the
   `VectorDocument.metadata` dict.

4. **`test_branch_confidence_aggregation`** —
   Create 3 entries under `/engineering/` with known alpha/beta values.
   Call `compute_branch_confidence(store, "/engineering/")`. Verify the
   aggregated alpha/beta are correct and the mean is right.

5. **`test_branch_confidence_ess_cap`** —
   Create entries whose combined ESS exceeds 150. Verify the result is
   capped at 150 while preserving the mean ratio.

6. **(Optional) `test_knowledge_tree_endpoint`** —
   If time allows, test the REST endpoint returns a valid tree structure.

---

## Acceptance Gates

All must pass before declaring done:

- [ ] Entry projections include `hierarchy_path` derived from primary domain
- [ ] `hierarchy_path` uses normalized domain (lowercase, underscores)
- [ ] Entries with no domains get `hierarchy_path="/uncategorized/"`
- [ ] `parent_id` is set to empty string (flat start)
- [ ] Qdrant payload includes `hierarchy_path` field
- [ ] `compute_branch_confidence()` aggregates children correctly
- [ ] ESS cap at 150 preserves mean ratio
- [ ] `GET /api/v1/workspaces/{id}/knowledge-tree` returns valid tree
- [ ] Knowledge browser shows catalog/graph/tree toggle
- [ ] Tree view shows collapsible branches with entry counts
- [ ] Hierarchy paths survive replay (derived from existing event data)
- [ ] Bootstrap script exists at `scripts/bootstrap_hierarchy.py`
- [ ] No new event types (stays at 69)
- [ ] No changes to `core/types.py` MemoryEntry model

---

## Validation

Run the full CI suite before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass clean. Target: 3654 + 5 = 3659+ tests.

---

## Overlap Reread Rules

After completing your work, reread:

- `src/formicos/surface/projections.py` lines 1580–1610 (your changes)
- `src/formicos/surface/memory_store.py` lines 55–85 (your payload change)
- `src/formicos/surface/routes/api.py` (your new endpoint)

Verify your changes don't break existing projection replay or Qdrant sync.
