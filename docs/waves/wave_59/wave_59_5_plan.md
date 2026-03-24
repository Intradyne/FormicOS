# Wave 59.5: Knowledge Graph Bridge + Progressive Disclosure Fix

**Date**: 2026-03-23
**Status**: Planning — ready for dispatch
**Depends on**: Wave 59 (curating archivist, MemoryEntryRefined event)
**Validates with**: Phase 1 v2 (curating archivist + graph retrieval)

---

## Thesis

FormicOS has two knowledge systems that don't talk to each other. The
vector pipeline (`knowledge_catalog.py`, ~500 lines) handles retrieval with
6-signal composite scoring. The knowledge graph (`adapters/knowledge_graph.py`,
559 lines) stores entities, relationships, and bi-temporal edges from archivist
colony output. They were built independently across Waves 13-14 and 26-59.

The `RetrievalPipeline` class at `engine/context.py:115-188` was designed to
bridge them — it does entity extraction, 1-hop BFS, and parallel vector search.
But it only runs when `skip_legacy_skills=False`, which is never true in the
modern pipeline (line 597 sets it `True` when knowledge items exist). The graph
is populated but never read during retrieval.

Meanwhile, Phase 1 v1 revealed a second gap: 0 calls to `knowledge_detail`
across 8 tasks. Progressive disclosure shows index-only entries (~50 tokens
each) with a passive instruction to call `knowledge_detail` for full content.
30B local models don't stop mid-task to call optional tools. The entire
progressive disclosure architecture is inert.

Wave 59.5 connects these two systems in ~120 lines across three parallel teams.
After this wave, entries have graph relationships (SUPERSEDES, DERIVED_FROM),
retrieval discovers neighbors via graph traversal, and the best-match entry
gets full content injected automatically.

### What this addresses

1. **Novelty gap #3**: "Flat vector memory in a graph world" — the biggest
   architectural gap identified by the novelty assessment. Graphiti's 18.5%
   accuracy improvement with temporal knowledge graphs is the benchmark.

2. **Phase 1 finding #3**: 0 knowledge_detail calls — progressive disclosure
   is inert. Agents get index-only summaries they cannot act on.

3. **Integration density**: After this wave, FormicOS has Bayesian confidence +
   Thompson Sampling + curating archivist + graph relationships + bi-temporal
   edges + asymmetric extraction + specificity gate + progressive disclosure +
   domain boundaries, all event-sourced. No published system matches this
   integration density.

---

## Architecture Overview

```
MemoryEntryCreated ──────────────────────────────────────────┐
  │                                                          │
  ├── runtime.py emit_and_broadcast():                       │ Team 1
  │   resolve_entity() → entry_kg_nodes[entry_id] = node_id  │
  │   (async, after sync projection handler completes)       │
  │                                                          │
MemoryEntryRefined ──> add_edge(SUPERSEDES)  ────────────────┘
MemoryEntryMerged ───> add_edge(DERIVED_FROM) ───────────────┘

KnowledgeCatalog.search()                                    │
  │                                                          │
  ├── vector search top-K (existing)                         │ Team 2
  ├── 1-hop BFS from top-3 via kg_adapter.get_neighbors()    │
  ├── merge graph-discovered entries into candidates         │
  └── composite scoring with graph_proximity signal          │

context.py: assemble_context()                               │
  │                                                          │ Team 3
  ├── top-1 entry: full content (~200 tokens)                │
  └── remaining entries: index-only (~50 tokens each)        │
      budget: ~510 tokens (up from ~250 pure index)          │
```

---

## Team 1: Entry-Node Bridge + Lifecycle Edges

**Type**: Code (surface/runtime.py, surface/projections.py,
adapters/knowledge_graph.py, surface/app.py)
**Owner**: Team 1
**Estimated delta**: ~45 lines

### Predicate expansion

The KG adapter's `DEFAULT_PREDICATES` at `knowledge_graph.py:38` is a
`frozenset` containing: `DEPENDS_ON, ENABLES, IMPLEMENTS, VALIDATES,
MIGRATED_TO, FAILED_ON`. Add three lifecycle predicates using frozenset
union:

```python
DEFAULT_PREDICATES = frozenset({
    "DEPENDS_ON", "ENABLES", "IMPLEMENTS",
    "VALIDATES", "MIGRATED_TO", "FAILED_ON",
    "SUPERSEDES",     # Refinement: new content replaces old
    "DERIVED_FROM",   # Merge: merged entry derives from sources
    "RELATED_TO",     # Extraction co-occurrence within same colony
})
```

These are string constants in a frozenset. No schema change required — the
`kg_edges` table stores predicates as text.

### Projection bridge (data field only)

Add `entry_kg_nodes: dict[str, str]` field to `ProjectionStore.__init__()` at
`projections.py:663`. This maps `entry_id → kg_node_id`, populated at runtime
by the surface layer.

Do NOT modify any projection handler functions (`_on_memory_entry_created`,
`_on_memory_entry_refined`, `_on_memory_entry_merged`). Projection handlers
are sync (`def`, not `async def`) and must remain pure state machines for
event-sourcing determinism (hard constraint #7). `resolve_entity()` and
`add_edge()` are `async def` — calling them from sync handlers would crash.

### KG bridge in emit_and_broadcast() (runtime.py:491-506)

The async KG bridge lives in `runtime.py:emit_and_broadcast()`, which IS
async. This is exactly where the existing Qdrant sync block lives (lines
491-506). The pattern is identical: after the projection processes the event
synchronously, the surface layer performs async side effects.

Add a KG bridge block AFTER the existing Qdrant sync block:

```python
        # Wave 59.5: bridge memory entries to knowledge graph
        if self.kg_adapter is not None:
            if etype == "MemoryEntryCreated":
                entry = getattr(event_with_seq, "entry", {})
                entry_id = str(entry.get("id", "") if isinstance(entry, dict)
                               else getattr(entry, "id", ""))
                title = str(entry.get("title", "") if isinstance(entry, dict)
                            else getattr(entry, "title", ""))
                ws_id = str(entry.get("workspace_id", "") if isinstance(entry, dict)
                            else getattr(entry, "workspace_id", ""))
                canonical_type = str(
                    entry.get("canonical_type", "skill") if isinstance(entry, dict)
                    else getattr(entry, "canonical_type", "skill")
                )
                if entry_id and title:
                    try:
                        entity_type = "SKILL" if canonical_type == "skill" else "CONCEPT"
                        node_id = await self.kg_adapter.resolve_entity(
                            name=title,
                            entity_type=entity_type,
                            workspace_id=ws_id,
                            source_colony=str(
                                entry.get("source_colony_id", "")
                                if isinstance(entry, dict)
                                else getattr(entry, "source_colony_id", "")
                            ),
                        )
                        self.projections.entry_kg_nodes[entry_id] = node_id
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.create_failed", entry_id=entry_id)

            elif etype == "MemoryEntryRefined":
                entry_id = str(getattr(event_with_seq, "entry_id", ""))
                source_colony = str(getattr(event_with_seq, "source_colony_id", ""))
                node_id = self.projections.entry_kg_nodes.get(entry_id, "")
                if node_id:
                    try:
                        ws_id = str(getattr(event_with_seq, "workspace_id", ""))
                        await self.kg_adapter.add_edge(
                            from_node=node_id, to_node=node_id,
                            predicate="SUPERSEDES",
                            workspace_id=ws_id,
                            source_colony=source_colony,
                            confidence=0.9,
                        )
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.refine_edge_failed", entry_id=entry_id)

            elif etype == "MemoryEntryMerged":
                target_id = str(getattr(event_with_seq, "target_id", ""))
                source_id = str(getattr(event_with_seq, "source_id", ""))
                t_node = self.projections.entry_kg_nodes.get(target_id, "")
                s_node = self.projections.entry_kg_nodes.get(source_id, "")
                if t_node and s_node:
                    try:
                        ws_id = str(getattr(event_with_seq, "workspace_id", ""))
                        await self.kg_adapter.add_edge(
                            from_node=t_node, to_node=s_node,
                            predicate="DERIVED_FROM",
                            workspace_id=ws_id,
                            confidence=0.9,
                        )
                    except Exception:  # noqa: BLE001
                        log.warning("kg_bridge.merge_edge_failed")
```

Self-referential SUPERSEDES on MemoryEntryRefined captures "this node's
content was upgraded." The KG adapter's `add_edge()` at
`knowledge_graph.py:286` auto-invalidates the prior version of the same
relationship via bi-temporal bookkeeping.

### Replay safety: _rebuild_entry_kg_nodes()

During event replay, `apply()` is called (sync) but `emit_and_broadcast()`
is NOT called. This means `entry_kg_nodes` is empty after replay. The KG
database itself persists (SQLite), but the in-memory mapping dict doesn't.

Add a startup rebuild method on Runtime:

```python
async def _rebuild_entry_kg_nodes(self) -> None:
    """Rebuild entry_kg_nodes mapping from KG database after replay."""
    if self.kg_adapter is None:
        return
    for entry_id, entry in self.projections.memory_entries.items():
        title = entry.get("title", "")
        ws_id = entry.get("workspace_id", "")
        if title and ws_id:
            try:
                node_id = await self.kg_adapter.resolve_entity(
                    name=title,
                    entity_type=(
                        "SKILL" if entry.get("canonical_type") == "skill"
                        else "CONCEPT"
                    ),
                    workspace_id=ws_id,
                )
                self.projections.entry_kg_nodes[entry_id] = node_id
            except Exception:  # noqa: BLE001
                pass
```

Call this in the `lifespan()` async context manager at `app.py:467-479`,
after the memory store rebuild (line 479) and before the backfill block
(line 483). The insertion point is exact:

```python
        # line 479: log.info("app.memory_store_rebuilt", entries=mem_count)

        # Wave 59.5: rebuild entry_kg_nodes mapping after replay
        await runtime._rebuild_entry_kg_nodes()

        # line 483: if memory_store is not None:  (backfill block)
```

This is O(n) where n = number of memory entries. At current scale (<200
entries), it takes <1 second. `resolve_entity()` does exact-match first
(line 166), so existing KG nodes are found without creating duplicates.

### Files owned

| File | Changes |
|------|---------|
| `adapters/knowledge_graph.py:38` | Expand DEFAULT_PREDICATES frozenset with SUPERSEDES, DERIVED_FROM, RELATED_TO |
| `surface/projections.py:663` | Add `entry_kg_nodes: dict[str, str] = {}` field (data only, NO handler changes) |
| `surface/runtime.py:491-506` | Add KG bridge block after existing Qdrant sync |
| `surface/runtime.py` (new method) | `_rebuild_entry_kg_nodes()` |
| `surface/app.py` (startup) | Call `_rebuild_entry_kg_nodes()` after replay |

### Do NOT touch

- `surface/projections.py` HANDLERS — do not modify any `_on_memory_*`
  handler function. Handlers remain pure sync state machines.
- `surface/knowledge_catalog.py` (Team 2)
- `engine/context.py` (Team 3)
- `surface/knowledge_constants.py` (Team 2)
- Event definitions in `core/events.py`

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify: after a colony completes extraction, `entry_kg_nodes` contains mappings
for all newly created entries. After a REFINE action, a SUPERSEDES edge exists
in the KG. After a MERGE action, a DERIVED_FROM edge exists. After a restart
with replay, `entry_kg_nodes` is repopulated from the KG database.

---

## Team 2: Graph-Augmented Retrieval

**Type**: Code (surface/knowledge_catalog.py, surface/knowledge_constants.py,
surface/app.py, eval/run.py)
**Owner**: Team 2
**Estimated delta**: ~50 lines

### KnowledgeCatalog constructor

Add `kg_adapter` parameter to `KnowledgeCatalog.__init__()` at line 307:

```python
def __init__(
    self,
    memory_store: MemoryStore | None,
    vector_port: VectorPort | None,
    skill_collection: str,
    projections: ProjectionStore | None = None,
    kg_adapter: Any = None,  # KnowledgeGraphAdapter, optional
) -> None:
```

Default `None` preserves backward compatibility for all existing call sites
(~20 test files construct `KnowledgeCatalog` without KG adapter).

### Call site updates

Two production call sites need `kg_adapter` passed:

1. `surface/app.py:316` — `kg_adapter` is already available as a local variable
   (created at line 244). Add `kg_adapter=kg_adapter` to the constructor call.

2. `eval/run.py:207` — pass `kg_adapter=None` explicitly. The eval runtime
   does not construct a `KnowledgeGraphAdapter` (no KG database in eval).
   This is a no-op passthrough that keeps the constructor call consistent.

### Graph neighbor discovery

In `_search_thread_boosted()`, after the merge + overlay step (line 533) and
before composite scoring (line 535), add graph neighbor discovery:

```python
# Wave 59.5: graph-augmented retrieval — discover neighbors of top-3
graph_scores: dict[str, float] = {}
if self._kg_adapter is not None and self._projections is not None:
    # Use top-3 by raw semantic similarity as seed nodes
    seed_items = sorted(merged, key=lambda x: -float(x.get("score", 0.0)))[:3]
    for seed in seed_items:
        seed_entry_id = seed.get("id", "")
        node_id = self._projections.entry_kg_nodes.get(seed_entry_id, "")
        if not node_id:
            continue
        try:
            neighbors = await self._kg_adapter.get_neighbors(
                node_id,
                workspace_id=workspace_id,
            )
            for nbr in neighbors:
                # Map KG node back to entry_id via reverse lookup
                for eid, nid in self._projections.entry_kg_nodes.items():
                    if nid == nbr["node_id"] and eid not in seen:
                        # Add to candidate pool if not already present
                        entry_data = self._projections.memory_entries.get(eid)
                        if entry_data:
                            item = _normalize_institutional(entry_data, score=0.0)
                            merged.append(item)
                            seen.add(eid)
                            graph_scores[eid] = 1.0
                            break
        except Exception:  # noqa: BLE001
            log.debug("knowledge_catalog.graph_neighbor_lookup_failed",
                       seed_id=seed_entry_id)
    # Also mark seeds' direct neighbors with partial proximity
    for item in merged:
        eid = item.get("id", "")
        if eid not in graph_scores:
            graph_scores[eid] = 0.0
```

### Composite scoring: graph_proximity signal

The 6-signal composite weights at `knowledge_constants.py:31-38` currently
total ~1.0:

```
semantic: 0.38, thompson: 0.25, freshness: 0.15,
status: 0.10, thread: 0.07, cooccurrence: 0.05
```

Add `graph_proximity` as the 7th signal by redistributing from freshness
and cooccurrence:

```python
COMPOSITE_WEIGHTS: dict[str, float] = {
    "semantic": 0.38,         # unchanged
    "thompson": 0.25,         # unchanged — exploration budget is sacred
    "freshness": 0.10,        # was 0.15 (-0.05)
    "status": 0.10,           # unchanged
    "thread": 0.07,           # unchanged
    "cooccurrence": 0.04,     # was 0.05 (-0.01)
    "graph_proximity": 0.06,  # NEW — Wave 59.5
}
```

Rationale: freshness at 0.10 remains meaningful (10% of composite), and the
graph signal gets enough weight (0.06) to promote neighbors without dominating
semantic or Thompson signals. Co-occurrence drops minimally (0.05→0.04) since
graph proximity captures a related but richer relationship signal.

### Integration into _keyfn

In `_search_thread_boosted()._keyfn()` at line 553, add graph_proximity
alongside the existing co-occurrence computation:

```python
graph_prox = graph_scores.get(item.get("id", ""), 0.0)
raw_composite = (
    _W["semantic"] * semantic
    + _W["thompson"] * thompson
    + _W["freshness"] * freshness
    + _W["status"] * status_bonus
    + _W["thread"] * thread_bonus
    + _W["cooccurrence"] * cooc
    + _W.get("graph_proximity", 0.0) * graph_prox
    + pin_boost
)
```

Using `_W.get("graph_proximity", 0.0)` ensures backward compatibility if
workspace-scoped weight overrides don't include the new signal.

Also add to `_composite_key()` at line 263 (the non-thread path) as a no-op
term (always 0.0 when no graph context is available). `_composite_key()`
deliberately excludes contextual signals like co-occurrence and thread bonus
— it's the simple path for non-thread-boosted retrieval. Graph proximity
only has real values in `_search_thread_boosted()` where the KG adapter and
projections are available. The 0.0 term in `_composite_key()` keeps the
weight dictionary consistent across both paths.

Also add to the `_score_breakdown` dict at line 594:

```python
"graph_proximity": item.get("_graph_proximity", 0.0),
```

### Files owned

| File | Changes |
|------|---------|
| `surface/knowledge_catalog.py:307` | Add `kg_adapter` parameter to constructor |
| `surface/knowledge_catalog.py:467-589` | Graph neighbor discovery + scoring in _search_thread_boosted |
| `surface/knowledge_catalog.py:263-301` | Add graph_proximity term to _composite_key |
| `surface/knowledge_constants.py:31-38` | Add graph_proximity weight, adjust freshness/cooccurrence |
| `surface/app.py:316` | Pass kg_adapter to KnowledgeCatalog |
| `eval/run.py:207` | Pass kg_adapter to KnowledgeCatalog |

### Do NOT touch

- `surface/projections.py` (Team 1)
- `engine/context.py` (Team 3)
- `adapters/knowledge_graph.py` (Team 1)
- `core/events.py`

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify: composite weights sum to ~1.0. Existing tests that construct
`KnowledgeCatalog` without `kg_adapter` still pass (default `None`). Score
breakdown includes `graph_proximity` field.

---

## Team 3: Progressive Disclosure Fix

**Type**: Code (engine/context.py)
**Owner**: Team 3
**Estimated delta**: ~15 lines

### The problem

Phase 1 v1: 0 calls to `knowledge_detail` across 8 tasks, 7 of which had
entries injected. The index-only format at `context.py:538-582` shows entries
as:

```
[Available Knowledge] (use knowledge_detail tool to retrieve full content)
- [SKILL, VERIFIED] "CSV parsing patterns" -- Uses csv.DictReader... (conf: 0.72, id: mem-xxx)
```

This is a passive hint. 30B local models executing multi-round coding tasks
don't stop to call optional tools. The knowledge pipeline produces entries,
retrieval surfaces them, but agents can't use them because they only see
50-token summaries.

### The fix: auto-inject top-1 full content

After the similarity gate filters at line 549, before building the index
lines, identify the highest-similarity entry and inject its full content
inline. Remaining entries keep index-only format.

```python
# Wave 59.5: auto-inject full content for top-1 entry (highest similarity)
# Addresses Phase 1 finding: 0 knowledge_detail calls across 8 tasks
injected_items = [
    item for item in knowledge_items[:8]
    if float(item.get("similarity", item.get("score", 0.0)))
       >= _MIN_KNOWLEDGE_SIMILARITY
]

if injected_items:
    top_entry = injected_items[0]  # Already sorted by composite score
    top_content = str(top_entry.get("content", ""))[:500]
    # Truncate at last sentence boundary if possible
    last_period = top_content.rfind(". ")
    if last_period > 200:  # Don't truncate too aggressively
        top_content = top_content[:last_period + 1]
    top_title = top_entry.get("title", "")
    top_id = top_entry.get("id", "")
    top_conf = float(top_entry.get("confidence", 0.5))

    lines = ["[Available Knowledge]"]
    lines.append(
        f'**{top_title}** (conf: {top_conf:.2f}, id: {top_id})\n'
        f'{top_content}'
    )

    # Remaining entries: index-only format
    for item in injected_items[1:]:
        # ... existing index format logic (lines 559-582)
```

### Token budget

- Top-1 full content: ~200 tokens (content[:500] ≈ 150-200 tokens + header)
- Remaining 7 entries × ~50 tokens index: ~350 tokens
- Total: ~510 tokens (up from ~250 pure index, down from ~800 pre-Wave-58
  full-content injection)

This stays well within the `TierBudgets.skill_bank` budget (default 800
tokens, `context.py:93`).

### Backward compatibility

The `knowledge_detail` tool remains available — agents can still pull full
content for any index entry. The fix simply ensures the most relevant entry
doesn't require a tool call to be actionable.

### Header change

Remove the passive `"(use knowledge_detail tool to retrieve full content)"`
parenthetical from the header. Replace with just `"[Available Knowledge]"`.
The tool remains available but the header no longer makes a request that
agents ignore.

### Files owned

| File | Changes |
|------|---------|
| `engine/context.py:537-596` | Auto-inject top-1 full content, simplify header |

### Do NOT touch

- `surface/knowledge_catalog.py` (Team 2)
- `surface/projections.py` (Team 1)
- `adapters/knowledge_graph.py` (Team 1)
- `config/caste_recipes.yaml`

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify: when knowledge items are injected, the first entry includes full
content (up to 500 chars), remaining entries show index-only format. Total
injection stays under 600 tokens for 8 entries.

---

## Merge Order

All three teams can develop in parallel — zero file overlap. But merge order
is constrained:

1. **Team 1 must merge BEFORE Team 2 can run integration tests.** Team 2's
   graph neighbor discovery reads `entry_kg_nodes`, which is populated by
   Team 1's `runtime.py` bridge code. Without Team 1's code, `entry_kg_nodes`
   is always empty and graph discovery is a silent no-op — unit tests pass
   but the feature doesn't work end-to-end.
2. **Team 2 merges after Team 1.** Graph-augmented retrieval depends on the
   bridge mapping being populated at runtime.
3. **Team 3 merges any time** — progressive disclosure fix is fully
   independent. No dependency on Team 1 or Team 2.

### Overlap reread rules

- Team 2 must reread `projections.py` after Team 1 lands to verify
  `entry_kg_nodes` field name and accessor pattern.
- Team 2 must reread `runtime.py` after Team 1 lands to verify the bridge
  block fires correctly for `MemoryEntryCreated` events.
- No other cross-team rereads required.

---

## Acceptance Criteria

| Gate | Criterion |
|------|-----------|
| CI passes | `ruff check && pyright && lint_imports && pytest` |
| Bridge populates | `entry_kg_nodes` has entries after extraction via emit_and_broadcast |
| Replay rebuild | `entry_kg_nodes` repopulated after restart via `_rebuild_entry_kg_nodes()` |
| Lifecycle edges | SUPERSEDES edge after REFINE, DERIVED_FROM after MERGE |
| Graph retrieval | Neighbors of top-3 appear in merged candidates |
| Weight consistency | COMPOSITE_WEIGHTS sums to ~1.0 |
| Score breakdown | `_score_breakdown` includes `graph_proximity` |
| Backward compat | All existing KnowledgeCatalog tests pass without kg_adapter |
| Top-1 injection | Highest-scoring entry has full content in context |
| Token budget | Total knowledge injection ≤ 600 tokens for 8 entries |
| Passive header removed | No "(use knowledge_detail tool...)" in injected context |
| Sentence truncation | Top-1 content truncates at sentence boundary when possible |

---

## What This Wave Does NOT Do

- **Add new event types** — no ADR needed. Uses existing events +
  projection-side bookkeeping.
- **Change retrieval thresholds** — the 0.50 similarity gate is unchanged.
  Within-domain calibration is a Phase 1 v2 question.
- **Add temporal queries** — the KG adapter supports bi-temporal edges, but
  retrieval doesn't use time-scoped queries yet. Defer to Wave 60.
- **Add SPLIT operation** — decomposing compound entries. No production system
  implements this.
- **Add semantic preservation gate on REFINE** — cosine > 0.75 between old and
  new embeddings. Deferred from Wave 59, still deferred pending Phase 1 data.
- **Run Phase 1 v2** — requires this wave to land first. v2 measures curating
  archivist + graph retrieval + disclosure fix vs v1 append-only baseline.
- **Expose graph relationships in the API** — the bridge is internal. REST
  endpoints for graph traversal are future work.
- **Reverse-index entry_kg_nodes** — Team 2's reverse lookup
  (`for eid, nid in entry_kg_nodes.items()`) is O(n) per neighbor. At current
  scale (< 100 entries per workspace), this is acceptable. If scale increases,
  add a `kg_node_entries: dict[str, str]` reverse mapping.

---

## Key Source Files (Pre-Wave State)

| File | Current State | Wave 59.5 Changes |
|------|---------------|-------------------|
| `adapters/knowledge_graph.py` (559 lines) | SQLite-backed graph, entity resolution, BFS, TKG ingestion | +3 predicates (Team 1) |
| `surface/projections.py` | 65-event projection store | +entry_kg_nodes dict field only, NO handler changes (Team 1) |
| `surface/runtime.py:491-506` | Qdrant sync in emit_and_broadcast | +KG bridge block after Qdrant sync, +_rebuild_entry_kg_nodes() (Team 1) |
| `surface/app.py` | Runtime startup, KnowledgeCatalog construction | +_rebuild_entry_kg_nodes() call after replay (Team 1), +kg_adapter passthrough (Team 2) |
| `surface/knowledge_catalog.py` | 6-signal composite, thread-boosted search | +kg_adapter param, +graph neighbor discovery, +graph_proximity signal (Team 2) |
| `surface/knowledge_constants.py` | COMPOSITE_WEIGHTS (6 signals) | +graph_proximity weight, adjust freshness/cooccurrence (Team 2) |
| `engine/context.py:537-596` | Index-only progressive disclosure | +top-1 full content injection with sentence truncation (Team 3) |
| `eval/run.py:207` | KnowledgeCatalog construction | +kg_adapter passthrough (Team 2) |

---

## Design Rationale

### Why not revive RetrievalPipeline?

The `RetrievalPipeline` at `engine/context.py:115-188` does entity extraction
→ 1-hop BFS → parallel vector search. It's architecturally sound but
lives on the dead legacy path (`skip_legacy_skills=False`). Reviving it would
require either (a) moving it to the catalog layer (architectural change) or
(b) running both old and new retrieval paths (complexity). The bridge approach
adds graph neighbor discovery directly in `KnowledgeCatalog.search()` where
the modern pipeline already runs. ~50 lines vs ~200 to resurrect and rewire.

### Why redistribute from freshness?

Freshness at 0.15 was the largest "soft" weight — it doesn't carry the
theoretical guarantees of Thompson (0.25) or the strong empirical validation
of semantic similarity (0.38). Reducing to 0.10 keeps freshness meaningful
while creating budget for graph proximity. Co-occurrence drops from 0.05 to
0.04 because graph proximity captures a richer version of the "entries that
appear together" signal that co-occurrence approximates.

### Why auto-inject top-1 instead of improving the tool hint?

Three options were considered:
1. **Better tool hint** — "IMPORTANT: call knowledge_detail for entry X" —
   still requires tool-call behavior from a 30B model mid-task.
2. **Auto-inject all entries** — returns to pre-Wave-58 full injection
   (~1,440 tokens), which caused the v11 regression.
3. **Auto-inject top-1** — the most relevant entry gets full content (~200
   tokens), rest stay as index. Best match gets used; others discoverable.

Option 3 is the only approach that delivers actionable content without
recreating the v11 token-rot problem.

---

## Related Documents

- [wave_59_plan.md](wave_59_plan.md) — Curating archivist, MemoryEntryRefined
  event, Phase 1 eval design
- [wave_58_5_plan.md](../wave_58/wave_58_5_plan.md) — Domain boundaries,
  specificity gate validation, progressive disclosure baseline
- [phase1_v1_results.md](phase1_v1_results.md) — Phase 1 v1 Arm 1 results
  (19 entries accessed, 0 knowledge_detail calls)
- [docs/specs/knowledge_system.md](../../specs/knowledge_system.md) —
  Knowledge system spec (composite scoring, retrieval tiers)
- [docs/specs/extraction_pipeline.md](../../specs/extraction_pipeline.md) —
  Extraction spec (curating prompt, action dispatch)
- [docs/decisions/044-composite-scoring.md](../../decisions/044-composite-scoring.md) —
  ADR for 6-signal composite scoring
