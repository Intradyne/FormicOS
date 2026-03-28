# ADR-050: Two-Pass Retrieval — Personalized PageRank for Graph Proximity

**Status**: Proposed
**Date**: 2026-03-25
**Wave**: 67.5
**Depends on**: ADR-044 (composite scoring — 7-signal weights including graph_proximity at 0.06)

---

## Context

The composite retrieval formula (knowledge_constants.py:33-41) allocates
0.06 weight to `graph_proximity` — the 7th signal added in Wave 59.5.
However, this signal is only active in `_search_thread_boosted()`
(knowledge_catalog.py:540-585), where it seeds from the top-3 results
by semantic score and discovers KG neighbors via 1-hop `get_neighbors()`.

In the standard `_search_vector()` path (non-thread queries),
`_composite_key()` (line 301) hardcodes graph proximity to 0.0 with
an explicit comment: "Wave 59.5: graph_proximity only has real values
in _search_thread_boosted; here it's always 0.0 to keep the weight
dict consistent across both paths."

This means 6% of the composite score is permanently zero for non-thread
queries — the most common retrieval path.

The thread-boosted path's seed strategy (top-3 by semantic score) works
because thread context narrows the result set. For the general path, a
different seed strategy is needed: extract entities from the query itself.

The current graph neighbor discovery (lines 540-585) uses simple 1-hop
expansion with binary scores (1.0 for any neighbor, 0.0 for non-neighbors).
This treats all neighbors equally regardless of graph topology.

## Decision

### D1. Personalized PageRank replaces BFS with hop-decay

**Decision:** Use iterative Personalized PageRank (damping=0.5,
20 iterations) instead of BFS with hop-decay for graph proximity scoring.

HippoRAG (NeurIPS 2024, Ohio State/Stanford) demonstrates this
convincingly. Their ablation study (Table 5) shows:

| Method | R@5 |
|--------|-----|
| No expansion (baseline) | 59.2 |
| 1-hop BFS neighbor expansion | 56.2 (worse than baseline) |
| Personalized PageRank (damping=0.5) | 72.9 |

Simple BFS is **worse than no expansion at all** because it treats all
1-hop neighbors equally, injecting noise. PPR weights neighbors by graph
topology — high-connectivity paths score higher, dead-end branches are
naturally dampened.

**Implementation:** Pure Python iterative power method. No igraph or
networkx dependency.

```python
async def personalized_pagerank(
    self, seed_ids: list[str], workspace_id: str,
    *, damping: float = 0.5, iterations: int = 20,
) -> dict[str, float]:
    """Iterative PPR from seed entities.

    1. Build adjacency list from get_neighbors() for reachable nodes
       within 3 hops of seeds (bounded expansion).
    2. Initialize reset vector: uniform over seed_ids.
    3. Power iteration:
       pr[v] = (1-d)*reset[v] + d*sum(pr[u]/degree[u] for u in neighbors)
    4. Normalize: max score -> 1.0.
    """
```

**Damping = 0.5** (not the standard 0.85): 50% restart probability keeps
the random walk tightly localized around seed nodes. Standard PageRank's
0.85 is designed for web-scale link analysis where global importance
matters. For focused retrieval from specific seeds, 0.5 is the validated
parameter from HippoRAG.

**Performance:** For FormicOS's graph sizes (hundreds to low thousands
of edges), iterative PPR converges in <20ms. The bounded expansion
(3-hop reachability from seeds) prevents the adjacency list from growing
beyond the local neighborhood.

**Rationale:** PPR is the right algorithm for propagating activation
from query-matched seeds across a knowledge graph. It captures the
intuition that entities connected through multiple paths are more
strongly related than entities connected through a single path. The
14-point R@5 improvement over BFS justifies the additional ~30 lines of
implementation.

---

### D2. Entity seeding via embedding similarity for standard path

**Decision:** For the non-thread retrieval path, seed PPR by matching
query terms against KG entity names/summaries using embedding similarity,
not substring matching.

```python
async def match_entities_by_embedding(
    self, query: str, workspace_id: str, *, limit: int = 5,
) -> list[dict[str, Any]]:
    """Find KG entities semantically similar to query.

    Falls back to normalized substring matching on entity names
    if no embedding function is available.
    """
```

**Rationale:** Entity names in the KG are code-level identifiers
(function names, module names, tool names). Substring matching
(`"auth" in "authentication_handler"`) produces false positives and
misses semantic equivalents. Embedding similarity captures that "JWT
validation" is related to the `AuthMiddleware` entity even when no
substring overlap exists.

This uses existing infrastructure: entity summaries are stored on
`kg_nodes`, and the existing search/embedding pipeline can compute
similarity. Zero new dependencies.

The thread-boosted path keeps its existing seed strategy (top-3 results
by semantic score → `entry_kg_nodes` lookup) since thread context
already provides good seeds.

---

### D3. Shared `_enrich_with_graph_scores()` refactors both paths

**Decision:** Extract the inline graph neighbor discovery from
`_search_thread_boosted()` (lines 540-585) into a shared method that
both retrieval paths call:

```python
async def _enrich_with_graph_scores(
    self,
    seed_entity_ids: list[str],
    workspace_id: str,
) -> dict[str, float]:
    """PPR walk from seed entities, return {entry_id: proximity_score}.

    Runs personalized_pagerank(damping=0.5, iterations=20) from seeds.
    Maps KG entity IDs back to knowledge entry IDs via
    self._projections.entry_kg_nodes reverse lookup.
    """
```

**Rationale:** Eliminates code duplication. Both paths use the same PPR
infrastructure with different seed strategies. The thread-boosted path
is upgraded from 1-hop BFS to PPR for free, improving its graph
proximity quality as well.

The entity matching and PPR walk run in parallel with Qdrant vector
search via `asyncio.gather`, adding zero latency to the critical path
when the graph computation completes before the vector search.

## Alternatives rejected

1. **BFS with uniform hop-decay** — empirically worse than no expansion
   per HippoRAG ablation. Hop-decay (score = 0.4^hops) assigns equal
   scores to all entities at the same depth, ignoring graph topology.
   A well-connected entity 2 hops away scores the same as a dead-end
   entity 2 hops away. PPR naturally distinguishes them.

2. **BFS with edge-confidence weighting** — partially captures topology
   (`score = decay^hop * edge_confidence`) but still misses multi-path
   reinforcement. An entity reachable through 3 independent paths should
   score higher than one reachable through 1 path with the same hop
   count. PPR handles this natively.

3. **igraph or networkx dependency for PPR** — igraph's PRPACK solver
   is optimal for large graphs (>50K edges). For FormicOS's graph sizes
   (hundreds to low thousands), pure Python iterative PPR is fast enough
   (<20ms). Adding a C-extension dependency for a ~30-line algorithm is
   unnecessary. If graph sizes grow significantly, igraph can be adopted
   later as a drop-in replacement.

4. **Substring entity matching** — too crude for code-level entity names.
   `"test"` would match `"test_runner"`, `"test_data"`, `"latest_version"`,
   producing noisy seeds that degrade PPR quality. Embedding similarity
   produces semantically relevant matches.

5. **Keeping graph_proximity at 0.0 in standard path** — permanently
   wastes 6% of the composite score. The weight was allocated in Wave
   59.5 specifically to reward graph-connected entries. Leaving it at
   zero undermines the rebalancing rationale from ADR-044.

## Consequences

- KG adapter gains two methods: `personalized_pagerank()` (~30 lines)
  and `match_entities_by_embedding()` (~25 lines). Both are in the
  Adapters layer — pure computation + data access, no Surface imports.
- `knowledge_catalog.py` gains `_enrich_with_graph_scores()` (~30 lines)
  and refactors `_search_thread_boosted()` to use it (net reduction of
  ~20 lines from removing inline code).
- Standard retrieval now produces real graph proximity scores. Score
  breakdown will show non-zero `graph_proximity` for the first time in
  non-thread queries.
- No weight changes. The 0.06 weight from ADR-044 D4 / Wave 59.5
  remains unchanged.
- No new events. No new projection state. No Qdrant schema changes.
- Performance: entity match + PPR adds <50ms to the non-thread retrieval
  path, running in parallel with Qdrant search.
