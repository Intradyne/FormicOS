# Wave 67: The Knowledge Architecture

**Status:** 67.0 landed, 67.5 dispatch prep
**Predecessor:** Wave 66 (Addons as First-Class Software)
**Theme:** Give knowledge structure, integrity, and auditability.

The thesis: hierarchy is the organizing principle that makes everything else
work. Domains become hierarchy nodes. Provenance becomes navigable through
the tree. The doc indexer's output slots into the hierarchy naturally. Ship
them together and they reinforce each other.

## Contract Change Blocker (Wave 67.5)

Track 5 requires operator approval to add `ProvenanceChainItem` to:

- `docs/contracts/types.ts`
- `frontend/src/types.ts`

Proposed interface:

```typescript
interface ProvenanceChainItem {
  event_type: string;
  timestamp: string;
  actor_id: string;
  detail: string;
  confidence_delta: number | null;
}
```

Use snake_case to match the existing knowledge API payload style. If Track 5
adds a dedicated provenance endpoint response interface, mirror that in the
contract docs at the same time.

Approve before 67.5 dispatch. Wave 67.0 is already landed and unaffected.

---

## Scope Split: Wave 67.0 + Wave 67.5

Combined scope is too large for a single dispatch. Split at the natural seam:

- **Wave 67.0** (foundation): Hierarchy data model, domain normalization,
  outcome-confidence reinforcement. Changes the data model and feedback
  loops. Three parallel teams.
- **Wave 67.5** (surfaces): Two-pass retrieval with graph proximity, provenance
  chains, documentation indexer addon, UI surfaces. Builds on the 67.0
  data model. Three parallel teams.

67.0 has landed and passed a polish pass. 67.5 is the active dispatch prep.
Both halves respect
the 69-event closed union -- all changes are projection-level enrichments.

## Dependency Decision: Zero New Dependencies (Resolved)

**UMAP+HDBSCAN rejected.** Entries already carry domain tags — there is
no structure discovery problem. What's needed is sub-clustering within
existing domains into topics, and an LLM does that better than HDBSCAN
because it produces human-readable topic names directly (vs "cluster 7"
that still needs LLM labeling).

**Going forward (Track 2):** Extraction-time domain suggestion is the
real solution. Every new entry gets "use one of these existing domains
if applicable" in the prompt. Hierarchy converges organically.

**Existing entries (bootstrap script):** Batch by existing domain tag
(~20 entries per batch), ask the LLM to identify 2-5 topic sub-clusters
within each domain, assign hierarchy paths. For 300 entries across 15
domains, that's ~15 LLM calls — trivial cost, runs once. The script is
offline (`scripts/bootstrap_hierarchy.py`, not imported by runtime).

No new dependencies. No approval gate.

## ADR Requirements

### ADR-049: Knowledge Hierarchy Data Model (Required)

New projection-level fields on `memory_entries`: `hierarchy_path` and
`parent_id`. Qdrant payload gains a keyword-indexed `hierarchy_path`
field for filtered search within branches. Upward confidence aggregation
derives topic posteriors from children's evidence.

**Why this needs an ADR:** Changes the knowledge data model, adds a new
Qdrant payload index, introduces aggregated confidence (new concept).
Affects retrieval, extraction, and UI.

**Key decisions for the ADR:**
- Hierarchy lives on knowledge entry projections, NOT on the KG entity
  model. KG tracks code-level entities (MODULE, TOOL, PERSON). Hierarchy
  tracks knowledge organization (domain -> topic -> entry). Different
  taxonomies. Keep them separate.
- Path format: `/domain/topic/` (no entry-level path segment; entries are
  leaves). Example: `/engineering/auth/jwt-validation/`.
- `parent_id` points to a synthetic topic entry (or empty for root-level).
- No new event types. `hierarchy_path` is computed at projection time from
  existing `MemoryEntryCreated` event data + extraction-time domain tags.

### ADR-050: Two-Pass Retrieval (Required)

Changes the retrieval algorithm: entity extraction from query via
embedding similarity, iterative Personalized PageRank (replacing BFS),
and shared graph scoring method across both retrieval paths. Currently
graph proximity is active only in `_search_thread_boosted()` (using
top-3 seed items from KG neighbor lookup). Extending to the standard
`_search_vector()` path with query-based entity extraction and PPR
is a meaningful algorithm change. ADR-050 proposed.

## Algorithmic Design Notes (Research-Informed)

These decisions are grounded in published research and production system
analysis. See the research reference document for full citations.

**1. Materialized path over closure table (Track 1).** Benchmark data:
250x slower writes for closure table at 5,912 nodes. FormicOS's hierarchy
is shallow (3-4 levels), append-heavy, and rarely reparented. Materialized
path is the clear winner. Reparenting (if needed) is a single UPDATE with
string REPLACE.

**2. Personalized PageRank over BFS (Track 4).** HippoRAG (NeurIPS 2024)
ablation: 1-hop BFS is *worse than no expansion* (R@5: 56.2 vs 59.2
baseline), while PPR reaches 72.9. The difference: PPR weights neighbors
by graph topology instead of treating all 1-hop neighbors equally. For
FormicOS's graph sizes (<50K edges), iterative PPR in pure Python with
damping=0.5 converges in <20ms. No igraph dependency needed.

**3. Geometric credit (0.7^rank) over harmonic (1/(rank+1)) (Track 3).**
The Position-Based Model (PBM) from production recommendation systems
models examination probability as a geometric decay: [1.0, 0.7, 0.49,
0.34, 0.24...]. This better captures declining attention patterns than
harmonic decay [1.0, 0.5, 0.33, 0.25...]. Validated by Udemy and Scribd
production deployments.

**4. ESS cap at 150 (Track 3).** Mathematically equivalent to exponential
decay with gamma = 1 - 1/150 ≈ 0.993. Russo et al.'s TS tutorial
recommends N_eff ≈ 200 for nonstationary environments. 150 balances
stability with responsiveness — 100 would be too aggressive for entries
with genuine high evidence.

**5. Topic nodes as synthetic projection entries (Track 1).** Derived
from children's hierarchy paths, not event-sourced. They exist in the
projection dict and in Qdrant (with LLM-generated topic summaries) but
don't require MemoryEntryCreated events. Replay-safe: projection rebuild
re-derives them from child entries.

**6. Wave 68 note (not in scope).** Manus's todo.md pattern wastes ~33%
of actions on plan file updates. For the Queen's plan recitation: READ
the plan at context assembly time (cheap), only WRITE when
`propose_plan` creates/modifies a plan. Read-heavy, write-light.

---

# WAVE 67.0: Foundation

## Pre-existing State

### Knowledge entry projection (projections.py)

`ProjectionStore.memory_entries` (line 694) is a `dict[str, dict[str, Any]]`
keyed by entry ID. Each entry is a mutable dict populated by event handlers:

**Core fields (from MemoryEntryCreated handler, lines 1585-1603):**
- `id`, `title`, `content`, `summary`, `status`, `domains` (list),
  `tool_refs` (list), `source_colony_id`, `thread_id`, `scope`,
  `created_at`, `entry_type`, `polarity`, `sub_type`, `decay_class`

**Confidence fields (from MemoryConfidenceUpdated handler, lines 1661-1691):**
- `conf_alpha`, `conf_beta`, `confidence` (posterior mean),
  `last_confidence_update`, `peak_alpha` (highest alpha ever, line 1677)

**Missing fields (not yet present):**
- `hierarchy_path` -- does not exist
- `parent_id` -- does not exist
- `provenance_chain` -- does not exist (provenance is only on frontend
  `KnowledgeProvenance` interface, not in projection)

### MemoryEntry core model (core/types.py:383-446)

Pydantic model with 20+ fields. Key fields for Wave 67:
- `domains: list[str]` (line 405) -- domain tags, currently free-form
- `conf_alpha` (line 415, default 5.0), `conf_beta` (line 420, default 5.0)
- `decay_class` (line 425) -- ephemeral | stable | permanent
- `sub_type` (line 432) -- technique | pattern | anti_pattern | trajectory |
  decision | convention | learning | bug
- No `hierarchy_path` or `parent_id` fields on the core model

### Domain normalization (memory_extractor.py)

`_normalize_domain()` (line 31-33): lowercase, spaces/hyphens to underscores.
`_normalize_domains()` (line 36-45): applies to lists, deduplicates.

`build_extraction_prompt()` (line 88-94): Three paths based on existing
entries and colony status. Domain handling is minimal -- line 214-215 sets
`primary_domain` to `task_class` parameter (defaults to "generic"). **No
semantic domain suggestion from existing entries.** The LLM chooses domains
independently.

### Colony outcome confidence path (colony_manager.py)

`_hook_confidence_update()` (line 1476): Already implemented. For each
knowledge item accessed by a completed colony:
- Success: `delta_alpha = clip(0.5 + quality_score, 0.5, 1.5)` (line 1542)
- Failure: `delta_beta = clip(0.5 + failure_penalty, 0.5, 1.5)` (line 1562)
- Mastery restoration: 20% gap-recovery bonus for stable/permanent entries
  with >50% decay (lines 1547-1556)
- Emits `MemoryConfidenceUpdated` with `reason="colony_outcome"` (line 1573)
- Auto-promotes candidate -> verified when alpha >= threshold (line 1592)
- Reinforces co-occurrence weights between accessed entries (line 1618)

**Gap identified:** The outcome confidence update does NOT use retrieval
rank for credit assignment. All accessed entries get the same delta
regardless of whether they were the #1 result or #10. The prompt says
an earlier version mentioned credit = 1/(rank+1) -- now superseded by
geometric 0.7^rank (Track 3). Either way, rank-based credit is new work.

### Quality score computation (colony_manager.py:284-320)

`compute_quality_score()`: geometric mean of 5 weighted signals:
- `round_efficiency` (0.20), `convergence_score` (0.25),
  `governance_score` (0.20), `stall_score` (0.15),
  `productive_ratio` (0.20)
- Returns 0.0 on failure, range [0.20, 1.0] on success

### ColonyOutcome projection (projections.py:88-118)

`entries_accessed` computed from `colony.knowledge_accesses` (lines 1060-1065).
Each access records the items retrieved. `KnowledgeAccessRecorded` event
handler appends to `colony.knowledge_accesses` (line 1566).

**The access records include retrieval order** -- items within each access
dict preserve their ranked position. This means rank-based credit
assignment is possible without new events.

### Composite scoring (knowledge_catalog.py)

Seven signals, weights from `knowledge_constants.py:33-41`:
```
semantic: 0.38, thompson: 0.25, freshness: 0.10, status: 0.10,
thread: 0.07, cooccurrence: 0.04, graph_proximity: 0.06
```

`_composite_key()` (line 263-304): Used by `_search_vector()` non-thread
path. **graph_proximity hardcoded to 0.0** at line 301 with comment:
"Wave 59.5: graph_proximity only has real values in _search_thread_boosted;
here it's always 0.0 to keep the weight dict consistent across both paths."

`_search_thread_boosted()` (lines 472-710): graph proximity is ACTIVE.
Seeds from top-3 items by semantic score (lines 543-545). For each seed:
looks up KG node ID via `entry_kg_nodes` projection, calls
`kg_adapter.get_neighbors()`, reverse-maps neighbor node IDs to entry IDs,
sets `graph_scores[eid] = 1.0` (lines 540-585).

### Knowledge graph adapter (adapters/knowledge_graph.py)

Entity table: `kg_nodes` (id, name, entity_type, summary, source_colony,
workspace_id, created_at). Indexes on name, type, workspace_id.

Edge table: `kg_edges` (id, from_node, to_node, predicate, confidence,
valid_at, invalid_at, source_colony, source_round, workspace_id).
Bi-temporal validity. Predicates include `DERIVED_FROM`.

`get_neighbors()` (lines 345-404): 1-hop only. `depth` parameter exists
but is **ignored**. Simple JOIN query, no recursive CTE. Returns edge
dicts with `from_node`/`to_node` fields.

`search_entities()` (lines 443-466): Substring match on entity names
within a workspace. Returns list of `{id, name, entity_type, summary}`.

**No BFS traversal capability.** No recursive CTE. Multi-hop discovery
would need to be added.

### Scoring math (engine/scoring_math.py)

`exploration_score()` (lines 32-75): Thompson Sampling via
`random.betavariate(alpha, beta)` (stochastic) or `alpha/(alpha+beta)`
(deterministic when `FORMICOS_DETERMINISTIC_SCORING=1`). Optional UCB
bonus.

**No effective sample size capping.** Alpha+beta can grow unbounded.
The prompt mentions capping at ~100 -- this is new work.

### Frontend knowledge interfaces (frontend/src/types.ts)

`KnowledgeItemPreview` (lines 430-453): 20+ fields including `domains`,
`conf_alpha`, `conf_beta`, `score`, `score_breakdown`, `decay_class`,
`usage_count`, `thread_id`, `scope`.

`KnowledgeItemDetail` (lines 488-492): Extends preview with `content`,
`provenance` (`KnowledgeProvenance`), `trust_rationale` (`TrustRationale`).

`KnowledgeProvenance` (lines 468-479): source_colony_id, source_round,
source_agent, source_peer, is_federated, created_at, workspace_id,
thread_id, decay_class, forager_provenance.

### Frontend knowledge browser (knowledge-browser.ts)

Score bar (lines 884-902): Renders 7-signal stacked bar with color-coded
segments. Segment width proportional to weighted contribution.

Entry detail (lines 1117-1127): Confidence bar, confidence summary,
trust panel, power panel. Score breakdown bar exists but is rendered
only on hover/expand of search results at standard/full tier.

**No tree view.** Catalog is a flat list with filters (skill/experience,
domain dropdown, search). No hierarchy navigation.

### Codebase-index addon (addons/codebase-index/)

Chunking infrastructure in `indexer.py`: structural splitting on
function/class boundaries, sliding-window fallback. `CodeChunk` dataclass
with id (sha256), text, path, line_start, line_end. Converts to
`VectorDocument` for Qdrant. Collection name: `"code_index"`.

Runtime context keys: `vector_port`, `workspace_root_fn`, `projections`,
`embed_fn`, `event_store`, `settings`.

**No `addons/docs-index/` directory exists yet.**

---

## Track 1: Knowledge Hierarchy with Materialized Paths

### Problem

Knowledge entries are flat. 300 entries across 15 domains have no
organization beyond free-form domain tags. The knowledge browser shows a
single scrollable list. There's no way to see "I have 40 entries about
auth, 12 about testing, 3 are contradicting" at a glance. Domain tags
drift -- "python_testing" vs "python_test_patterns" vs "testing_python"
all mean the same thing.

### Fix

**1. Add `hierarchy_path` and `parent_id` to entry projection.**

**Storage model: materialized path.** For a shallow (3-4 level), append-heavy
hierarchy with 5K-50K entries, materialized path beats closure table
decisively. Benchmarks show closure table has 250x slower writes (O(depth)
rows per insert into junction table). Materialized path needs 1 table, no
joins for subtree queries, and trivial reparenting via
`UPDATE ... SET path = REPLACE(path, old_prefix, new_prefix)`.

**Topic nodes are synthetic projection entries.** Topic nodes (e.g.,
`/engineering/auth/`) are real entries in the `memory_entries` projection
dict with a synthetic `entry_type="topic"`. They don't require
`MemoryEntryCreated` events. They're derived from the hierarchy paths of
their children — on replay, the projection rebuild can re-derive them.
They exist in Qdrant with LLM-generated topic summaries as embeddings,
enabling filtered search within branches.

In `projections.py`, `_on_memory_entry_created()` handler (lines 1585-1603):

```python
# After line 1602 (data["scope"] = ...)
# Wave 67: hierarchy path from primary domain
domains = data.get("domains", [])
primary_domain = domains[0] if domains else "uncategorized"
data["hierarchy_path"] = f"/{_normalize_domain(primary_domain)}/"
data["parent_id"] = ""
```

Import `_normalize_domain` from `memory_extractor` (or inline the same
3-line logic to avoid cross-layer import -- prefer inline since projections
is Surface importing from Surface, which is allowed).

The hierarchy path is initially flat: `/{domain}/`. Topic-level nesting
(`/{domain}/{topic}/`) comes from the extraction-time clustering or
operator-driven reclassification. Start simple, deepen later.

**2. Add Qdrant payload field.**

In `memory_store.py`, `sync_entry()`: when upserting to Qdrant, include
`hierarchy_path` in the payload metadata dict. Qdrant payload fields are
automatically indexed as keyword fields when present.

Check `memory_store.py` for where payload is assembled -- the
`VectorDocument.metadata` dict. Add `"hierarchy_path": entry.get("hierarchy_path", "/")`
alongside existing metadata fields.

**3. Projection-level upward confidence aggregation.**

New function in `projections.py` (or a new `hierarchy.py` in surface/):

```python
def compute_branch_confidence(
    store: ProjectionStore,
    path_prefix: str,
) -> dict[str, float]:
    """Aggregate Beta confidence for entries under a hierarchy branch.

    Returns {"alpha": float, "beta": float, "count": int, "mean": float}.
    Sum children's evidence, cap effective sample size at 150.
    """
    total_alpha = 0.0
    total_beta = 0.0
    count = 0
    for entry in store.memory_entries.values():
        hp = entry.get("hierarchy_path", "/")
        if hp.startswith(path_prefix):
            total_alpha += entry.get("conf_alpha", 5.0) - 5.0  # subtract prior
            total_beta += entry.get("conf_beta", 5.0) - 5.0
            count += 1
    # Re-add single prior and cap
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

Called on-demand by the API, not on every event. No new projection state
needed -- it's a pure computation over existing data.

**4. REST endpoint for hierarchy tree.**

In `routes/api.py`, add:

```
GET /api/v1/workspaces/{id}/knowledge-tree
```

Returns a tree structure built from `memory_entries` hierarchy paths:

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

**5. Knowledge browser tree view.**

Add a `SubView` option: `'catalog' | 'graph' | 'tree'`. New
`_renderTreeView()` method that fetches from the knowledge-tree endpoint
and renders a collapsible tree. Each branch shows: name, entry count,
aggregated confidence bar. Clicking a branch filters the catalog to that
path prefix.

**6. Bootstrap script (offline, not imported by runtime).**

`scripts/bootstrap_hierarchy.py`: LLM-only, zero new dependencies.
Groups existing entries by domain tag (~20 entries per batch), asks
the LLM to identify 2-5 topic sub-clusters within each domain, and
assigns `hierarchy_path` values. For 300 entries across 15 domains,
that's ~15 LLM calls — trivial cost, runs once.

The script reads entries from the projection (via a REST endpoint or
direct SQLite read), computes topic assignments, and emits
`WorkspaceConfigChanged` events to persist the hierarchy path updates.
It is a one-time bootstrap tool. Going forward, extraction-time domain
suggestion (Track 2) keeps new entries aligned organically.

### Files

| File | Change | Lines |
|------|--------|-------|
| `src/formicos/surface/projections.py` | hierarchy_path/parent_id in MemoryEntryCreated handler | ~8 |
| `src/formicos/surface/memory_store.py` | Add hierarchy_path to Qdrant payload metadata | ~3 |
| `src/formicos/surface/hierarchy.py` | **new** -- branch confidence aggregation | ~40 |
| `src/formicos/surface/routes/api.py` | knowledge-tree endpoint | ~45 |
| `frontend/src/components/knowledge-browser.ts` | Tree subview, branch rendering, path filter | ~120 |
| `scripts/bootstrap_hierarchy.py` | **new** -- offline clustering script | ~100 |

### Tests

5 new:
- MemoryEntryCreated projection handler sets hierarchy_path from domains
- Qdrant payload includes hierarchy_path
- Branch confidence aggregation caps effective sample size at 150
- GET knowledge-tree returns valid tree structure
- Tree view filters catalog when branch clicked

### Acceptance Gates

- Entry projections include `hierarchy_path` derived from primary domain
- Knowledge browser shows tree/catalog/graph toggle
- Tree view shows collapsible domain branches with entry counts
- Branch confidence aggregates from children, capped at ESS 150
- Hierarchy paths survive replay (derived from existing event data)
- Qdrant filtered search by hierarchy_path works

### Owner

Team A. Merge first among tracks (other teams may depend on hierarchy_path).

### Do Not Touch

`core/types.py` (no new MemoryEntry fields -- hierarchy is projection-only),
`core/events.py` (no new events), `queen_runtime.py`, `queen_tools.py`,
`knowledge_catalog.py` (Team B owns retrieval), `colony_manager.py`
(Team B owns outcome path).

---

## Track 2: Domain Normalization at Extraction Time

### Problem

Domain tags drift. The same concept gets multiple names:
"python_testing", "python_test_patterns", "testing_python",
"test_patterns". `_normalize_domain()` handles case/whitespace but not
semantic equivalence. With hierarchy in place, this creates orphan
branches that should be the same node.

### Fix

**1. Inject existing domain suggestions into extraction prompt.**

In `memory_extractor.py`, `build_extraction_prompt()` (after line 94):

Before building the prompt, query existing entries for the top-5 most
similar by embedding, pull their unique domain tags, and inject them
into the prompt:

```python
# Wave 67: domain normalization via existing entry suggestion
existing_domains: set[str] = set()
if existing_entries:
    for e in existing_entries[:10]:
        for d in e.get("domains", []):
            existing_domains.add(d)
# Add to prompt (after task context, before field schemas):
if existing_domains:
    domain_hint = (
        "Use one of these existing domain tags if applicable "
        "(do not create synonyms): "
        + ", ".join(sorted(existing_domains)[:20])
    )
```

This is ~15 lines in `build_extraction_prompt()`. The existing entries
are already passed to the function (parameter `existing_entries`); we
just need to extract and present their domains.

**2. Add hierarchy path suggestion.**

When Track 1 lands, extend the domain hint to include hierarchy paths:

```python
if existing_domains:
    domain_hint = (
        "Existing knowledge branches (use one if applicable, "
        "do not create synonyms):\n"
        + "\n".join(f"  - {d}" for d in sorted(existing_domains)[:20])
    )
```

This naturally aligns new entries with the existing hierarchy.

### Files

| File | Change | Lines |
|------|--------|-------|
| `src/formicos/surface/memory_extractor.py` | Domain hint injection in build_extraction_prompt | ~15 |

### Tests

2 new:
- Extraction prompt includes existing domains when entries provided
- Domain hint limits to 20 domains max

### Acceptance Gates

- Extraction prompt shows "Use one of these existing domain tags" when
  existing entries have domains
- New extractions converge on existing domain names instead of creating
  synonyms
- No regression in extraction quality (domains still free-form if no
  existing entries match)

### Owner

Team B. Independent of Team A (domain hint doesn't require hierarchy_path).
But when Team A's hierarchy_path is present, domain normalization
prevents orphan branches from forming.

### Do Not Touch

`core/types.py`, `core/events.py`, `projections.py` (Team A owns),
`knowledge_catalog.py` (retrieval is Team B Wave 67.5 scope).

---

## Track 3: Outcome-Confidence Reinforcement with Rank Credit

### Problem

`_hook_confidence_update()` (colony_manager.py:1476) gives equal
credit to all accessed entries regardless of retrieval rank. The #1
result and the #10 result get the same alpha/beta delta. This dilutes
the reinforcement signal -- entries that were actually relevant (high
rank) should get stronger updates than entries that happened to be in
the result set but weren't central to the colony's work.

Additionally, there is no effective sample size cap. Alpha+beta can grow
unbounded, making entries increasingly resistant to confidence updates
over time.

### Fix

**1. Rank-based credit assignment.**

In `colony_manager.py`, `_hook_confidence_update()`: The access
records in `colony.knowledge_accesses` preserve item order. Use position
for credit:

```python
# Current (line 1542):
delta_alpha = min(max(0.5 + quality_score, 0.5), 1.5)

# New: geometric credit = 0.7^rank (Position-Based Model examination probs)
# Yields [1.0, 0.7, 0.49, 0.34, 0.24, ...] — models declining attention
# better than harmonic 1/(rank+1) per HippoRAG/Udemy production findings.
for rank, item in enumerate(access.get("items", [])):
    credit = 0.7 ** rank
    if succeeded:
        base_delta = min(max(0.5 + quality_score, 0.5), 1.5)
        delta_alpha = base_delta * credit
    else:
        base_delta = min(max(0.5 + failure_penalty, 0.5), 1.5)
        delta_beta = base_delta * credit
```

**2. Effective sample size cap.**

After computing `new_alpha` and `new_beta`, cap the effective sample
size at 150. This is mathematically equivalent to exponential decay
with gamma = 1 - 1/150 ≈ 0.993. Cap of 150 (not 100) lets
high-evidence entries stabilize without becoming immovable — 100 is
too aggressive per production Thompson Sampling literature (Russo et al.
recommend N_eff ≈ 200 for nonstationary environments; 150 balances
stability with responsiveness for FormicOS's update frequency).

```python
ess = new_alpha + new_beta
if ess > 150.0:
    scale = 150.0 / ess
    new_alpha *= scale
    new_beta *= scale
```

This preserves the mean (alpha/alpha+beta ratio) while preventing
posterior collapse. Add this to `_hook_confidence_update()` right
before emitting the `MemoryConfidenceUpdated` event.

**3. Add `rescale_preserving_mean()` helper to scoring_math.py.**

```python
def rescale_preserving_mean(
    alpha: float, beta: float, max_ess: float = 150.0,
) -> tuple[float, float]:
    """Rescale Beta parameters to cap effective sample size.

    Equivalent to exponential decay with gamma = 1 - 1/max_ess.
    Default 150 balances stability with responsiveness.
    """
    ess = alpha + beta
    if ess <= max_ess:
        return alpha, beta
    scale = max_ess / ess
    return alpha * scale, beta * scale
```

This is Engine layer -- pure computation, no Surface imports.

### Files

| File | Change | Lines |
|------|--------|-------|
| `src/formicos/surface/colony_manager.py` | Rank credit + ESS cap in _hook_confidence_update | ~25 |
| `src/formicos/engine/scoring_math.py` | rescale_preserving_mean helper | ~12 |

### Tests

4 new:
- Rank 0 entry gets higher delta than rank 5 entry
- ESS cap rescales preserving mean ratio
- Auto-promotion still works after ESS cap
- rescale_preserving_mean returns unchanged when under cap

### Acceptance Gates

- Top-ranked retrieved entries get stronger confidence reinforcement
- Alpha+beta never exceeds 150 after outcome update
- Mean confidence ratio preserved after rescaling
- Mastery restoration still works correctly with capped entries
- Co-occurrence reinforcement unchanged

### Owner

Team B. Independent of Team A. Merge after Team A if hierarchy_path
is used in access records (it isn't -- independent).

### Do Not Touch

`core/events.py`, `core/types.py`, `projections.py` (Team A owns
hierarchy additions), `knowledge_catalog.py` (retrieval changes are
Wave 67.5), `memory_extractor.py` (Team B Track 2 owns extraction).

---

## Team Assignment (Wave 67.0)

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A (Hierarchy) | Track 1 | Heaviest track. Projection changes, Qdrant payload, tree API, tree view UI, bootstrap script. |
| Team B (Feedback) | Track 2, Track 3 | Domain normalization + outcome reinforcement. Both modify the knowledge feedback loop. Separate files, no conflicts. |

Team A has more work. If a Team C is available, split Track 1's UI
(tree view in knowledge-browser.ts) from Track 1's backend (projections,
API, Qdrant payload) and assign Team C the frontend.

## Merge Order (Wave 67.0)

```
Track 1 (hierarchy data model)     -- merge first
    |
    +---> Track 2 (domain normalization)  -- benefits from hierarchy_path
    |
    +---> Track 3 (rank credit + ESS cap) -- independent
```

Track 2 and Track 3 are independent of each other. Both can merge in
either order after Track 1. Track 3 is fully independent of Track 1
(touches different files), but merge order ensures hierarchy_path is
available if we want to log it in confidence update events.

---

# WAVE 67.5: Surfaces

**Prerequisite:** Wave 67.0 merged and stable.

## Pre-existing State (after 67.0)

Entries have `hierarchy_path` on projections. Domain normalization is
active at extraction time. Outcome confidence uses rank credit with ESS
cap. The knowledge browser has a tree view.

## Track 4: Two-Pass Retrieval for Graph Proximity

### Problem

The `graph_proximity` signal (weight 0.06) is dead weight in the
standard retrieval path. `_composite_key()` (knowledge_catalog.py:301)
hardcodes it to 0.0 with an explicit comment. Only
`_search_thread_boosted()` computes real graph scores, using top-3
result items as KG seeds (lines 540-585). This means 6% of the composite
score is always zero for non-thread queries.

The thread-boosted path's seed strategy (top-3 by semantic score) works
because thread context narrows the result set. For the general path, we
need a different seed strategy: extract entity names from the query
itself.

### Algorithm Decision: PPR over BFS

**HippoRAG's own ablation (NeurIPS 2024) shows simple 1-hop BFS is
worse than no expansion at all** (R@5: 56.2 for BFS vs 59.2 baseline
vs 72.9 for Personalized PageRank). BFS treats all neighbors equally;
PPR weights by graph topology, propagating activation through
high-connectivity paths.

For FormicOS's graph sizes (hundreds to low thousands of edges),
iterative PPR in pure Python is fast enough (<50ms). No igraph
dependency needed. The key parameter: **damping = 0.5** (not the
standard 0.85), which keeps the random walk tightly localized around
seed nodes — exactly what focused retrieval needs.

### Algorithm Decision: Entity Embedding Seeds over Substring Matching

The plan originally proposed fuzzy substring matching of query terms
against KG entity names. This is too crude — entity names are often
abbreviated or context-dependent. Better approach: embed the query,
search KG entity summaries via existing Qdrant infrastructure (entity
summaries are already stored on `kg_nodes`). This gives semantic
matching with zero new dependencies and better precision than string
containment checks.

### Fix

**1. Add `match_entities_by_embedding()` to the KG adapter.**

In `adapters/knowledge_graph.py`, add a method that finds entities
semantically similar to the query:

```python
async def match_entities_by_embedding(
    self, query: str, workspace_id: str, *, limit: int = 5,
) -> list[dict[str, Any]]:
    """Find KG entities semantically similar to query.

    Primary: compute cosine similarity between query embedding and
    entity name/summary embeddings via existing Qdrant infrastructure.
    Fallback: normalized substring overlap on entity names if no
    embedding function is available.

    Returns [{id, name, entity_type, score}, ...] sorted by score.
    """
```

Uses the existing `kg_nodes` table. Falls back to normalized substring
matching if no embedding function is available. The entity name index
(`idx_kg_nodes_name`) keeps this fast.

**2. Add `personalized_pagerank()` to the KG adapter.**

```python
async def personalized_pagerank(
    self, seed_ids: list[str], workspace_id: str,
    *, damping: float = 0.5, iterations: int = 20,
) -> dict[str, float]:
    """Iterative Personalized PageRank from seed entities.

    Parameters
    ----------
    damping : float
        Probability of following an edge (0.5 = 50% restart).
        Lower than standard PageRank's 0.85 to keep the walk
        tightly localized around seeds.
    iterations : int
        Power iteration rounds. 20 is sufficient for convergence
        on graphs under 50K edges.

    Returns {entity_id: proximity_score} normalized to [0, 1].
    """
    # 1. Build adjacency list from get_neighbors() for all reachable
    #    nodes within 3 hops of seeds (bounded expansion).
    # 2. Initialize reset vector: uniform over seed_ids.
    # 3. Power iteration:
    #    pr[v] = (1-damping) * reset[v] + damping * sum(pr[u]/degree[u])
    # 4. Normalize: max score -> 1.0.
```

Pure Python, ~30 lines. Uses existing `get_neighbors()` iteratively
to build the local adjacency list. No igraph, no networkx, no new deps.
For FormicOS's graph sizes this converges in <20ms.

**3. Add `_enrich_with_graph_scores()` shared method.**

In `knowledge_catalog.py`, extract a shared method from the existing
inline code in `_search_thread_boosted()` (lines 540-585):

```python
async def _enrich_with_graph_scores(
    self,
    seed_entity_ids: list[str],
    workspace_id: str,
) -> dict[str, float]:
    """PPR walk from seed entities, return {entry_id: proximity_score}.

    Runs Personalized PageRank (damping=0.5, 20 iterations) from seeds.
    Maps KG entity IDs back to knowledge entry IDs via
    self._projections.entry_kg_nodes reverse lookup.
    """
```

Both `_search_vector()` and `_search_thread_boosted()` call this method.
The thread-boosted path continues to use top-3 items as seeds (via
entry_kg_nodes lookup). The standard path uses
`match_entities_by_embedding()` on the query text.

**4. Wire into `_search_vector()` non-thread path.**

Replace the hardcoded 0.0 at line 301 with actual graph scores:

```python
# Before: + W.get("graph_proximity", 0.0) * 0.0
# After:
query_entity_ids = [e["id"] for e in await self._kg_adapter.match_entities_by_embedding(
    query, workspace_id, limit=5,
)]
graph_scores = await self._enrich_with_graph_scores(
    query_entity_ids, workspace_id,
)
# ... then in _composite_key:
+ W.get("graph_proximity", 0.0) * graph_scores.get(entry_id, 0.0)
```

The entity matching and PPR walk run in parallel with the Qdrant
vector search via `asyncio.gather`.

**5. Refactor `_search_thread_boosted()` to use shared method.**

Replace lines 540-585 (inline graph neighbor discovery) with a call
to `_enrich_with_graph_scores()`. Keep the same seed strategy (top-3
by semantic score -> entry_kg_nodes lookup). This reduces duplication
and upgrades the thread-boosted path from 1-hop BFS to PPR for free.

### Files

| File | Change | Lines |
|------|--------|-------|
| `src/formicos/adapters/knowledge_graph.py` | match_entities_by_embedding + personalized_pagerank | ~60 |
| `src/formicos/surface/knowledge_catalog.py` | _enrich_with_graph_scores shared method, wire into both paths | ~60 |

### Tests

5 new:
- match_entities_by_embedding finds semantically relevant entities
- personalized_pagerank returns topology-weighted scores (seed nodes highest)
- _search_vector non-thread path populates graph_proximity scores
- Graph proximity affects final ranking in standard retrieval
- _search_thread_boosted still works after refactor (upgraded to PPR)

### Acceptance Gates

- Standard retrieval (non-thread) computes real graph proximity scores
- Entity matching from query runs in parallel with Qdrant search
- PPR scores reflect graph topology (high-connectivity nodes rank higher)
- Thread-boosted path continues to work unchanged (refactored + upgraded)
- No performance regression: entity match + PPR < 50ms total
- Score breakdown shows non-zero graph_proximity in standard results

### Owner

Team B (retrieval team). This is the continuation of Team B's 67.0 work.

### Do Not Touch

`core/types.py`, `core/events.py`, `projections.py`, `colony_manager.py`,
`memory_extractor.py`, any frontend files.

---

## Track 5: Provenance Chain on Projections

### Problem

Entry provenance is incomplete. The existing `KnowledgeProvenance`
metadata already shows source colony/peer plus temporal fields, but it
does not expose the full lifecycle. When was an entry's confidence updated?
Who merged it? Was it refined? Which operator acted on it? The entry detail
view can't answer
"how did this entry get to this state?"

### Fix

**1. Add `provenance_chain` to projection entries.**

In `projections.py`, extend the following event handlers to append to
a provenance chain list on each entry:

```python
# In each handler, after updating the entry:
chain = entry.setdefault("provenance_chain", [])
chain.append({
    "event_type": "MemoryEntryCreated",  # or whichever event
    "timestamp": str(event.timestamp),
    "actor_id": str(getattr(event, "source_colony_id", "")),
    "detail": "...",  # human-readable summary
    "confidence_delta": None,  # float delta on confidence updates only
})
```

Events to instrument:
- `MemoryEntryCreated` (line 1585) -- "Created by colony {id}"
- `MemoryConfidenceUpdated` (line 1661) -- "Confidence {old} -> {new}, reason: {reason}"
- `MemoryEntryMerged` (line 1820, target entry) -- "Merged with {source_id}"
- `MemoryEntryRefined` (line 1841) -- "Refined by {source}, refinement #{count}"
- `KnowledgeEntryOperatorAction` (grep for handler) -- "Operator: {action}"
- `KnowledgeEntryAnnotated` (grep for handler) -- "Annotated: {note}"

Each handler adds ~5 lines. Total: ~30 lines across 6 handlers.

**2. REST endpoint for entry provenance.**

Prefer `routes/knowledge_api.py` so the new read endpoint lives beside the
existing `GET /api/v1/knowledge/{item_id}` detail route.

```
GET /api/v1/knowledge/{entry_id}/provenance
```

Returns the `provenance_chain` list from the projection entry. Simple
read from `projections.memory_entries[entry_id].get("provenance_chain", [])`.

**3. Provenance timeline in entry detail view.**

In `knowledge-browser.ts`, add `_renderProvenance(chain)` method to the
entry detail expanded view. Renders a vertical timeline with:
- Timestamp (formatted relative: "3 days ago")
- Event type icon/label
- Detail text
- Confidence delta (if present, shown as +0.3α / +0.2β)

**4. Score breakdown default visibility.**

Repo truth: `_renderScoreBar()` already exists, but the browser currently
renders it inside the confidence hover detail and the raw search payload may
carry `_score_breakdown` rather than `score_breakdown`. Track 5 should make
the bar visible in the main list item body and teach the component to read
either key so it can light up as soon as retrieval data is present.

### Files

| File | Change | Lines |
|------|--------|-------|
| `src/formicos/surface/projections.py` | provenance_chain append in 6 event handlers | ~30 |
| `src/formicos/surface/routes/knowledge_api.py` | GET provenance endpoint | ~15 |
| `frontend/src/types.ts` | ProvenanceChainItem interface | ~8 |
| `docs/contracts/types.ts` | ProvenanceChainItem interface (mirror) | ~8 |
| `frontend/src/components/knowledge-browser.ts` | Provenance timeline + score bar default visibility | ~60 |

### Tests

3 new:
- MemoryEntryCreated adds provenance chain item to projection
- MemoryConfidenceUpdated appends to existing provenance chain
- GET provenance endpoint returns chain for existing entry

### Acceptance Gates

- Every relevant event appends to the provenance chain
- Entry detail view shows provenance timeline
- Provenance survives replay (fully event-sourced projection data)
- Score breakdown bar visible on search results by default
- No new event types added

### Owner

Team A. Independent of Teams B and C.

### Do Not Touch

`core/events.py`, `core/types.py`, `colony_manager.py`,
`knowledge_catalog.py`, `memory_extractor.py`, `memory_store.py`.

---

## Track 6: Documentation Indexer Addon

### Problem

FormicOS knowledge comes from colony work -- but operators often have
existing documentation (architecture docs, runbooks, API references)
that should be searchable alongside extracted knowledge. Currently
there's no way to import documentation. The codebase-index addon indexes
code but not docs.

### Fix

**1. New addon at `addons/docs-index/`.**

Manifest follows the codebase-index pattern:

```yaml
name: docs-index
version: "1.0.0"
description: "Semantic search over project documentation"
author: "formicos-core"

tools:
  - name: semantic_search_docs
    description: "Search documentation by meaning"
    handler: search.py::handle_semantic_search
    parameters:
      type: object
      properties:
        query:
          type: string
          description: "Natural language search query"
        top_k:
          type: integer
          description: "Number of results (default 10)"
        file_pattern:
          type: string
          description: "Glob filter (e.g. '*.md')"

  - name: reindex_docs
    description: "Rebuild documentation index"
    handler: search.py::handle_reindex
    parameters:
      type: object
      properties:
        changed_files:
          type: array
          items: { type: string }
          description: "Files to reindex (omit for full)"

config:
  - key: doc_extensions
    type: string
    default: ".md,.rst,.txt,.html"
    label: "File extensions to index (comma-separated)"
  - key: skip_dirs
    type: string
    default: "node_modules,.git,.venv,__pycache__"
    label: "Directories to skip"

panels:
  - target: knowledge
    display_type: status_card
    path: /status
    handler: status.py::get_status

routes:
  - path: /status
    handler: status.py::get_status

triggers:
  - type: manual
    handler: indexer.py::incremental_reindex
```

**2. Python package at `src/formicos/addons/docs_index/`.**

Three modules following codebase-index pattern:

`indexer.py`: Chunks documentation files on section headers (H1/H2/H3
for Markdown, `===`/`---` for RST). Each chunk preserves parent section
title as metadata context. Uses same `VectorDocument` pattern as
codebase-index.

```python
COLLECTION_NAME = "docs_index"
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".html"}

@dataclass
class DocChunk:
    id: str          # sha256 of filepath:section_path
    text: str
    path: str        # file path relative to workspace
    section: str     # parent section title
    line_start: int
    line_end: int
```

Chunking strategy: split on Markdown headers (`^#{1,3} `), preserve
the header as section context. For `.rst`, split on `===` / `---`
underlines. For `.txt`, split on blank-line-separated paragraphs.
For `.html`, split on `<h1>` through `<h3>` tags.

`search.py`: Handler for `semantic_search_docs` and `reindex_docs`
tools. Same pattern as codebase-index/search.py. Uses `runtime_context`
for `vector_port` and `workspace_root_fn`.

`indexer.py` should mirror the codebase-index addon shape:
`full_reindex()`, `incremental_reindex()`, and an optional
`on_scheduled_reindex()` wrapper if we decide to add a cron trigger later.

`status.py`: Returns status_card with doc count, last indexed timestamp.

**3. With hierarchy in place, imported docs create hierarchy nodes.**

If Track 1 is landed, the indexer can set `hierarchy_path` on doc
chunks to match existing knowledge branches. For example, a doc at
`docs/auth/jwt-setup.md` gets `hierarchy_path: /auth/` if that branch
exists. This is optional and deferred to a polish pass.

### Files

| File | Change | Lines |
|------|--------|-------|
| `addons/docs-index/addon.yaml` | **new** manifest | ~45 |
| `src/formicos/addons/docs_index/__init__.py` | **new** empty | ~1 |
| `src/formicos/addons/docs_index/indexer.py` | **new** chunker | ~120 |
| `src/formicos/addons/docs_index/search.py` | **new** handlers | ~80 |
| `src/formicos/addons/docs_index/status.py` | **new** status card | ~30 |

### Tests

4 new:
- Markdown chunking splits on H1/H2/H3 boundaries
- Chunk metadata includes parent section title
- semantic_search_docs handler returns results from docs_index collection
- reindex_docs handler indexes .md files from workspace root

### Acceptance Gates

- `addons/docs-index/addon.yaml` loads without errors
- `semantic_search_docs` Queen tool searches documentation
- `reindex_docs` Queen tool rebuilds the doc index
- Knowledge tab shows docs-index status panel (via Wave 66 panel system)
- Doc chunks include section context in metadata
- Separate Qdrant collection (`docs_index`) from code_index

### Owner

Team C. Independent of retrieval and provenance changes.

### Do Not Touch

`core/events.py`, `core/types.py`, `colony_manager.py`,
`knowledge_catalog.py`, `memory_extractor.py`.
`addons/codebase-index/` (parallel addon, don't modify).

---

## Team Assignment (Wave 67.5)

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A (Provenance) | Track 5 | Projection + route + frontend detail work is a coherent vertical slice and leaves retrieval/addon work untouched. |
| Team B (Retrieval) | Track 4 | Continues from 67.0 feedback work. Owns `knowledge_catalog.py` and KG adapter seams. |
| Team C (Docs Indexer) | Track 6 | New addon slice with isolated write set and established codebase-index pattern to follow. |

Dispatch 67.5 as three bounded coder prompts, one per track. Do not split
Track 5 across separate frontend/backend coders unless staffing changes force it.

## Merge Order (Wave 67.5)

```
Track 4 (two-pass retrieval)       -- merge first (refactors shared code)
    |
Track 5 (provenance)              -- independent, merge any time
    |
Track 6 (doc indexer)             -- independent, merge any time
```

Track 5 and Track 6 are fully independent of each other and of Track 4.
Merge in any order. Track 4 merges first only because it refactors
`_search_thread_boosted()` which other developers should rebase against.

---

## Post-67.5 Extension Contract (Reference Only, Not In Scope)

Wave 67.5 is the foundation for future flexibility, but it should not absorb
that flexibility work directly. The structural rules below are the intended
follow-on contract for later waves.

### 1. Distilled Memory vs Raw Corpora

`memory_entries` remain the home for distilled institutional knowledge:
curated skills, experiences, and other replay-safe memory objects that
participate in Beta confidence evolution, Thompson Sampling, co-occurrence,
hierarchy, and provenance.

Raw corpora do **not** belong in `memory_entries`:

- documentation chunks
- code chunks
- structured data rows or records
- large imported reference sets

These should live in addon-owned indices such as `docs_index` and
`code_index`, with their own chunking and search logic. This keeps the
institutional memory pipeline high-signal and prevents raw chunk corpora from
polluting confidence evolution and composite retrieval scoring.

### 2. Future Flexibility Comes from More Indexing Strategies, Not More Core Types

The right extension path is new addon indexing strategies for new content
shapes, all feeding into the existing retrieval/tooling surface:

- prose docs -> docs-index addon
- source code -> codebase-index addon
- structured datasets / schemas -> future data-index addon

The wrong path is expanding the core knowledge model with custom entry types,
entry-specific retrieval rules, or per-shape confidence logic. Keep the core
memory model narrow; expand via addons.

### 3. Capability Metadata Before Hardcoded Queen Routing

When we add content-routing later, do not hardcode addon names or file-shape
rules into Queen prompt prose.

Instead, extend addon manifests with declarative capability metadata such as:

```yaml
capabilities:
  content_kinds: ["markdown", "rst", "html"]
  path_globs: ["docs/**", "*.md", "*.rst"]
  search_tool: semantic_search_docs
  reindex_tool: reindex_docs
```

The Queen can then route by inspecting installed addon capabilities rather
than by hardcoded addon-specific logic. This makes new indexers additive.

### 4. Taxonomy Should Be Workspace-Scoped and Soft

Wave 67.0's domain normalization is the correct starting point: suggest known
domains without rejecting new ones. If we add richer taxonomy later, it
should be workspace config and guidance, not hard validation.

Future shape:

```yaml
knowledge_schema:
  domains: [engineering, product, operations, security]
  tag_dimensions:
    language: [python, typescript, rust, go]
    layer: [core, engine, adapters, surface]
    priority: [critical, standard, exploratory]
  aliases:
    python_testing: testing
    ts: typescript
```

Desired behavior:

- prefer configured values
- canonicalize obvious aliases
- allow genuinely new values when nothing matches
- optionally flag drift for operator review

Do not block memory extraction on schema misses.

### 5. Queen-Mediated Addon Search, Not Automatic Colony Cross-Index Retrieval

Colony retrieval should continue to search institutional memory through the
existing `memory_search` / knowledge catalog path.

Do **not** auto-search every addon index during colony retrieval. That would:

- inflate retrieval cost
- inject irrelevant corpus hits
- force incompatible scoring models into one composite ranker

The intended future boundary is:

- **Queen** searches addon-owned corpora when planning / deliberating
- **Queen** curates the relevant excerpts into colony task context
- **Colonies** continue using institutional-memory retrieval during work

This keeps corpus routing in the orchestration layer and avoids conflating raw
corpus search with curated memory retrieval.

### 6. Wave 68 Design-Note Hook

After Wave 67.5 lands, write a small design note covering:

- distilled memory vs raw corpora
- addon capability metadata for content routing
- soft workspace taxonomy
- Queen-mediated addon search during deliberation / plan composition

That note should align with Wave 68 deliberation-frame work so addon indices
become part of Queen context assembly rather than automatic colony retrieval.

---

## What Wave 67 Does NOT Do

- No session continuity (Wave 68)
- No Queen deliberation frame changes (Wave 68)
- No todo.md attention pattern (Wave 68)
- No dynamic context caps (Wave 68)
- No new event types (stays at 69) -- hierarchy and provenance are
  projection-level enrichments
- No A2A outbound, no metering, no IDE/CLI, no multi-user
- No RL/self-evolution
- No hot-reload for addons
- No raw doc/code/data corpora in `memory_entries`
- No hardcoded Queen routing by addon name
- No hard validation of taxonomy values during extraction
- No automatic colony retrieval across addon-owned indices
- No hierarchy_path on the core MemoryEntry model (projection-only)
- No recursive CTE (iterative PPR via existing get_neighbors)
- No UMAP/HDBSCAN (LLM-only bootstrap, zero new dependencies)

## Validation Commands

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All tracks must pass this. Target: 3670+ tests (16+ net new from 3654).

## Acceptance Criteria (Combined)

**Wave 67.0:**
- Knowledge entries have `hierarchy_path` on projections
- Knowledge browser has tree view with collapsible domain branches
- Extraction prompt suggests existing domains to prevent drift
- Outcome confidence uses rank-based credit assignment
- Effective sample size capped at 150 (preserving mean)
- All hierarchy data replay-safe (no new events, no shadow state)

**Wave 67.5:**
- Standard retrieval computes real graph proximity (not hardcoded 0.0)
- Entity extraction from query seeds Personalized PageRank walk
- Every knowledge entry has a provenance chain
- Entry detail shows provenance timeline
- Score breakdown visible by default on search results
- Documentation indexer addon indexes .md/.rst/.txt/.html
- `semantic_search_docs` Queen tool operational
- 3670+ tests passing
- CI: ruff clean, pyright clean, imports clean

## Estimated Scope

**Wave 67.0:** ~200 lines backend (projections, hierarchy, memory_store,
colony_manager, scoring_math, memory_extractor). ~120 lines frontend
(tree view). ~100 lines bootstrap script. 11 new tests.

**Wave 67.5:** ~110 lines backend (KG adapter, knowledge_catalog,
projections, API). ~70 lines frontend (provenance timeline, score bar).
~275 lines new addon (docs-index). ~16 lines contract types. 12 new
tests.

**Combined:** ~875 lines new/modified code. 23 new tests. 0 new events.
