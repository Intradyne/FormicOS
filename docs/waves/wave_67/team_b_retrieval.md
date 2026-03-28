# Wave 67.5 - Team B: Two-Pass Retrieval with Personalized PageRank

**Wave:** 67.5 (surfaces)
**Track:** 4 - Two-Pass Retrieval for Graph Proximity
**ADR:** `docs/decisions/050-two-pass-retrieval.md` (proposed - read before coding)
**Prerequisite:** Wave 67.0 landed and stable

---

## Mission

The `graph_proximity` signal is still dead weight in the standard retrieval
path. `_composite_key()` in `knowledge_catalog.py` hardcodes that term to
`0.0`, so non-thread retrieval never benefits from the knowledge graph even
though the weight exists. Only `_search_thread_boosted()` computes graph
scores today, and it does so with a 1-hop binary neighbor lookup.

Your job: make graph proximity real in both retrieval paths using
Personalized PageRank (PPR), with embedding-based entity seeding for the
standard path and a shared enrichment helper for both paths.

---

## Owned Files

| File | Change |
|------|--------|
| `src/formicos/adapters/knowledge_graph.py` | Add `match_entities_by_embedding()` and `personalized_pagerank()` |
| `src/formicos/surface/knowledge_catalog.py` | Add shared graph-scoring helpers and wire them into both retrieval paths |
| `tests/unit/surface/test_two_pass_retrieval.py` | New retrieval tests |

---

## Do Not Touch

- `core/types.py`, `core/events.py` - closed union, no changes
- `projections.py` - Team A owns provenance additions
- `colony_manager.py` - landed in 67.0
- `memory_extractor.py` - landed in 67.0
- `memory_store.py` - no Qdrant schema changes needed here
- Any frontend files - Team A owns the 67.5 browser work
- Any addon files - Team C owns the docs indexer

---

## Repo Truth You Must Read First

### `src/formicos/surface/knowledge_catalog.py`

Read these paths before editing:

- `_composite_key()` - the non-thread scorer still hardcodes `graph_proximity`
  to `0.0`
- `_search_vector()` - the standard retrieval path that needs real graph scores
- `_search_thread_boosted()` - the thread path that already computes graph
  scores inline and should be refactored to the shared helper

Important constraint:

- `_composite_key()` is a module-level function, not a method
- It only sees the item dict and weights
- So the clean pattern is to inject `_graph_proximity` onto each item before
  sorting, matching existing `_thread_bonus` / `_pin_boost` behavior

Repo-truth caveat for 67.5 coordination:

- The knowledge browser score bar is already implemented
- The browser will be easier to wire if the non-thread path also emits
  `_score_breakdown` metadata using the same signal names as the thread path
- Team A will handle the UI; do not edit frontend here

### `src/formicos/adapters/knowledge_graph.py`

Read these methods first:

- `_embed_for_similarity()` - existing async/sync embedding helper
- `get_neighbors()` - existing 1-hop edge fetch you will reuse to build the
  local adjacency list
- `search_entities()` - existing substring fallback

Relevant data shape:

- `kg_nodes`: `id, name, entity_type, summary, source_colony, workspace_id, created_at`
- `entry_kg_nodes` in projections maps `entry_id -> kg_node_id`

---

## Implementation Steps

### Step 1: Add embedding-based entity matching

In `knowledge_graph.py`, add:

```python
async def match_entities_by_embedding(
    self,
    query: str,
    workspace_id: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
```

Behavior:

1. Try `_embed_for_similarity([query])`
2. If no embedding function is available, fall back to `search_entities()`
3. If embeddings are available:
   - load workspace entities from `kg_nodes`
   - embed `query` plus candidate `name + summary` strings
   - compute cosine similarity
   - return top-k `{id, name, entity_type, score}` sorted descending
4. Bound cost:
   - if the workspace has more than ~500 entities, skip full embedding and
     fall back to substring matching for this first version

### Step 2: Add localized Personalized PageRank

In `knowledge_graph.py`, add:

```python
async def personalized_pagerank(
    self,
    seed_ids: list[str],
    workspace_id: str,
    *,
    damping: float = 0.5,
    iterations: int = 20,
) -> dict[str, float]:
```

Requirements:

- Pure Python, no new dependencies
- Build a bounded local adjacency list by expanding outward from seeds up to
  3 hops with repeated `get_neighbors()` calls
- Use a restart-biased PPR update:

```python
pr[v] = (1 - damping) * reset[v] + damping * incoming_mass
```

- Normalize max score to `1.0`
- Return `{entity_id: score}`
- Return `{}` on empty seeds or no reachable edges

### Step 3: Add shared graph scoring on `KnowledgeCatalog`

In `knowledge_catalog.py`, add:

```python
async def _enrich_with_graph_scores(
    self,
    seed_entity_ids: list[str],
    workspace_id: str,
) -> dict[str, float]:
```

Behavior:

- Guard on missing KG adapter / projections
- Run `personalized_pagerank()`
- Reverse-map entity ids back to entry ids via `self._projections.entry_kg_nodes`
- Return `{entry_id: proximity_score}`

Also add:

```python
async def _compute_graph_scores(
    self,
    query: str,
    workspace_id: str,
) -> dict[str, float]:
```

This helper should:

1. call `match_entities_by_embedding()`
2. extract seed entity ids
3. call `_enrich_with_graph_scores()`

### Step 4: Wire graph scoring into `_search_vector()`

In `_search_vector()`:

- start the graph work in parallel with the existing institutional and legacy
  searches
- after merge + overlay application, inject `_graph_proximity` onto each item
- update `_composite_key()` so the `graph_proximity` weight reads from
  `item.get("_graph_proximity", 0.0)`

Pattern:

```python
item["_graph_proximity"] = graph_scores.get(item.get("id", ""), 0.0)
```

If practical, also emit `_score_breakdown` parity on the non-thread results
using the same signal names as the thread path:

```python
item["_score_breakdown"] = {
    "semantic": ...,
    "thompson": ...,
    "freshness": ...,
    "status": ...,
    "thread": 0.0,
    "cooccurrence": 0.0,
    "graph_proximity": float(item.get("_graph_proximity", 0.0)),
    "composite": ...,
    "weights": dict(ws_weights),
}
```

That keeps Team A from needing retrieval-specific frontend branching.

### Step 5: Refactor `_search_thread_boosted()` to the shared helper

Replace the inline neighbor walk with:

1. top-3 semantic seed entries
2. map those entries to KG node ids via `entry_kg_nodes`
3. call `_enrich_with_graph_scores()`

Keep the rest of the thread-path ranking flow intact. The goal is:

- one graph-scoring implementation
- continuous PPR scores instead of binary `1.0` / `0.0`

---

## Tests

Create `tests/unit/surface/test_two_pass_retrieval.py`.

Required tests:

1. `test_match_entities_by_embedding_returns_semantically_relevant`
2. `test_match_entities_falls_back_to_substring`
3. `test_personalized_pagerank_seed_nodes_highest`
4. `test_search_vector_populates_graph_proximity`
5. `test_search_thread_boosted_uses_shared_graph_enrichment`

Strongly recommended sixth test:

6. `test_search_vector_emits_score_breakdown_parity`

What to verify:

- embedding path sorts by cosine similarity
- substring fallback still works when embeddings are unavailable
- PPR favors seed / better-connected nodes over distant nodes
- non-thread results now carry non-zero `_graph_proximity`
- thread path no longer relies on the old inline 1-hop block

---

## Acceptance Gates

1. `_composite_key()` no longer hardcodes graph proximity to `0.0`
2. Standard retrieval computes real graph proximity scores
3. Entity matching from the query runs in parallel with vector search
4. Thread retrieval uses the shared graph-scoring helper
5. Thread retrieval upgrades from binary neighbor scores to continuous PPR scores
6. Standard-path results carry non-zero `_graph_proximity` when graph context exists
7. If `_score_breakdown` parity is emitted, the `graph_proximity` term is populated there too
8. Graceful degradation: if KG adapter is unavailable, graph scoring falls back to `0.0`
9. No new events, no new projection state, no Qdrant schema changes
10. Typical graph scoring stays comfortably below the existing retrieval budget

---

## Validation

Run before declaring done:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

The import lint matters here:

- `knowledge_graph.py` is Adapters layer
- `knowledge_catalog.py` is Surface layer
- do not create Adapters -> Surface imports

---

## Merge Order

Team B should merge first among the 67.5 tracks because `_search_thread_boosted()`
is a shared retrieval seam.

Teams A and C are otherwise independent and can merge after this track.

---

## Track Summary Template

When done, report:

1. Which seed path worked: embedding, substring fallback, or both?
2. How you bounded the entity-matching cost
3. Whether non-thread `_score_breakdown` parity was added
4. Whether thread retrieval now uses the shared helper end-to-end
5. Any measured timing notes from tests or local instrumentation
6. Any low-risk audit fixes found inside the owned files
