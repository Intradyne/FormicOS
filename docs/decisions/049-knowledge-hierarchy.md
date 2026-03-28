# ADR-049: Knowledge Hierarchy — Materialized Paths on Projections

**Status**: Proposed
**Date**: 2026-03-25
**Wave**: 67.0
**Depends on**: ADR-039 (knowledge metabolism — Beta posteriors and Thompson Sampling)

---

## Context

Knowledge entries are flat. A workspace with 300 entries across 15 domains
has no structural organization beyond free-form domain tags. The knowledge
browser renders a single scrollable list. There is no way to see "40 entries
about auth, 12 about testing, 3 contradicting" at a glance.

Domain tags drift without constraint. The same concept gets multiple names:
"python_testing", "python_test_patterns", "testing_python". The existing
`_normalize_domain()` function (memory_extractor.py:31-33) handles
case/whitespace normalization but not semantic equivalence. This creates
orphan categories that should be the same node.

The codebase has 69 event types (closed union). `MemoryEntry`
(core/types.py:383-446) carries `domains: list[str]` but no hierarchy
fields. The `memory_entries` projection dict (projections.py:694) stores
flat entry dicts with no `hierarchy_path` or `parent_id`.

The knowledge graph adapter (adapters/knowledge_graph.py) tracks code-level
entities (MODULE, TOOL, PERSON, CONCEPT) with relationship edges. This is
a different taxonomy from knowledge organization. Conflating code entities
with knowledge topics would pollute both systems.

## Decision

Add `hierarchy_path` and `parent_id` as projection-level fields on
`memory_entries` dict entries. These are computed from existing event data
at projection time. No changes to `core/types.py` MemoryEntry model. No
new event types. The 69-event closed union is preserved.

### Storage model: materialized path

Store the full ancestor chain as a delimited string on each entry:

```python
# In _on_memory_entry_created() projection handler:
domains = data.get("domains", [])
primary_domain = domains[0] if domains else "uncategorized"
data["hierarchy_path"] = f"/{_normalize_domain(primary_domain)}/"
data["parent_id"] = ""
```

Path format: `/{domain}/` for leaf entries, `/{domain}/{topic}/` when
topic-level nesting is added via extraction-time suggestion or bootstrap
clustering. Entries are leaves; path segments above them are topic nodes.

### Why materialized path over closure table

For a shallow (3-4 level), append-heavy hierarchy with 5K-50K entries:

| Operation | Materialized Path | Closure Table |
|-----------|------------------|---------------|
| Insert | 1 statement (concat parent path + id) | SELECT ancestors + INSERT depth+1 rows |
| Subtree query | `WHERE path LIKE '/eng/%'` (single index scan) | JOIN between 2 tables |
| Reparent | `UPDATE SET path = REPLACE(path, old, new)` | DELETE cross-boundary + CROSS JOIN INSERT |
| Write amplification | O(1) per insert | O(depth) per insert |

Benchmark data (5,912 nodes): populating nodes takes 0.03s; nodes plus
closure table takes ~8s — approximately 250x slower writes. For FormicOS's
append-heavy workload (entries created far more often than reparented),
this settles the decision.

A denormalized `depth` column eliminates the one weakness of materialized
path (depth queries without string functions).

### Topic nodes are synthetic projection entries

Topic nodes (e.g., the `/engineering/` branch) are real entries in the
`memory_entries` projection dict with `entry_type="topic"`. They:

- Exist in the projection dict alongside regular entries
- Are indexed in Qdrant with LLM-generated topic summaries as embeddings
- Are NOT event-sourced — no `MemoryEntryCreated` events for topics
- Are derived from the hierarchy paths of their children on replay
- Carry aggregated Beta confidence from their children's evidence

This makes them replay-safe: projection rebuild re-derives topic nodes
from child entries.

### Qdrant payload

`hierarchy_path` is added to the `VectorDocument.metadata` dict in
`memory_store.py:sync_entry()`. Qdrant automatically indexes string
payload fields as keyword indexes, enabling filtered search within
hierarchy branches via `must: [{key: "hierarchy_path", match: {value: "/engineering/"}}]`.

### Upward confidence aggregation

A topic's Beta posterior derives from its children's evidence:

```python
def compute_branch_confidence(store, path_prefix):
    total_alpha = sum(e.get("conf_alpha", 5.0) - 5.0
                      for e in store.memory_entries.values()
                      if e.get("hierarchy_path", "/").startswith(path_prefix))
    total_beta = sum(e.get("conf_beta", 5.0) - 5.0
                     for e in store.memory_entries.values()
                     if e.get("hierarchy_path", "/").startswith(path_prefix))
    agg_alpha = 5.0 + total_alpha
    agg_beta = 5.0 + total_beta
    ess = agg_alpha + agg_beta
    if ess > 150:
        scale = 150.0 / ess
        agg_alpha *= scale
        agg_beta *= scale
    return {"alpha": agg_alpha, "beta": agg_beta,
            "mean": agg_alpha / (agg_alpha + agg_beta)}
```

Computed on-demand by the API, not stored in projection state. ESS capped
at 150 (mathematically equivalent to exponential decay with gamma ≈ 0.993;
chosen to balance stability with responsiveness per production TS
literature).

### Hierarchy starts flat

Initial paths are `/{primary_domain}/`. Topic-level nesting comes from:
1. Extraction-time domain suggestion (Track 2) aligning new entries with
   existing branches
2. Optional offline bootstrap script clustering entries by embedding
   similarity and LLM-labeling clusters as topic nodes

This gets the tree view working immediately without waiting for a
clustering pipeline.

## Alternatives rejected

1. **New event type for hierarchy assignment** — violates the 69-event
   closed union (hard constraint #5). Hierarchy path is derivable from
   existing `MemoryEntryCreated` event data (the `domains` field).
   Adding an event for what is a projection-level enrichment would set
   a precedent for projection fields to have their own events.

2. **Hierarchy on the KG entity model** — the knowledge graph tracks
   code-level entities (MODULE, TOOL, PERSON) with relationship edges
   (DEPENDS_ON, ENABLES, IMPLEMENTS). Knowledge hierarchy tracks
   organizational structure (domain -> topic -> entry). These are
   different taxonomies with different lifecycles. Conflating them would
   pollute entity search with organizational nodes and make the KG
   harder to reason about.

3. **Closure table** — 250x write amplification at 5,912 nodes. For a
   3-level hierarchy that is mostly append-only, the closure table's
   O(depth) rows per insert into the junction table is unnecessary
   overhead. Materialized path handles all operations with O(1) writes.

4. **Nested sets** — efficient range-based reads but catastrophic for
   insertions: every INSERT requires renumbering all right-hand values
   after the insertion point. For an append-heavy workload, this is
   worse than closure table.

## Consequences

- Projection handlers grow ~8 lines (hierarchy_path assignment in
  MemoryEntryCreated handler).
- Qdrant payload gains one field (`hierarchy_path`). Existing sync
  path handles it automatically.
- REST API gains one endpoint (`GET /api/v1/workspaces/{id}/knowledge-tree`).
- Frontend knowledge browser gains tree subview (~120 lines).
- Bootstrap script (`scripts/bootstrap_hierarchy.py`) is an offline tool,
  not imported by the runtime. Uses LLM-only approach: batch entries by
  domain tag, LLM identifies topic sub-clusters, assigns hierarchy paths.
  Zero new dependencies.
- Event count: unchanged (69). No new event types.
- Core model: unchanged. `hierarchy_path` and `parent_id` are projection-only.
- Replay-safe: hierarchy paths are computed from existing event data
  (domains field on MemoryEntryCreated). Replaying the event stream
  reproduces the hierarchy deterministically.
