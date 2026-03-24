# Wave 60: The Final Wave

**Date**: 2026-03-23
**Status**: Planning
**Depends on**: Wave 59.5 (graph bridge, progressive disclosure fix)
**Theme**: Everything that's claimed works. Everything that works is visible.

---

## Why this is the last wave

FormicOS has shipped 12 waves of capability (54-59.5). The knowledge
pipeline has 9 layers. The composition table is fully checked. Every
additional feature wave that doesn't produce users is diminishing returns.

Wave 60 resolves every deferred item, closes every credibility gap the
novelty assessment identified, and prepares the platform for public
inspection. After this wave, the project needs users, not code.

---

## Eight tracks in three tiers

### Tier 1: Knowledge pipeline completion (3 deferred items)

Three small items deferred across Waves 59 and 59.5 that take the
knowledge pipeline from "works" to "works correctly with safeguards and
inspectability."

### Tier 2: Platform coherence (3 fixes)

Make existing machinery truthful and close the feedback loop. No new
concepts — just making what's built actually function end-to-end.

### Tier 3: Visibility (2 tracks)

Make the work inspectable and credible to the outside world. No engine
code — packaging, measurement, and presentation.

---

## Tier 1: Knowledge Pipeline Completion

### Track 1: Temporal queries in graph retrieval (~15 lines)

**Deferred from**: Wave 59.5
**Files**: `surface/knowledge_catalog.py`, `adapters/knowledge_graph.py`

The KG adapter stores `valid_at` and `invalid_at` on every edge
(`knowledge_graph.py:268-286`). `get_edge_history()` exists at
`knowledge_graph.py:401-436`. The Wave 59.5 graph-augmented retrieval
calls `get_neighbors()` which already filters invalidated edges via
`include_invalidated=False` (the default). But there's no time-scoped
query: "what did the hive know when colony X ran?"

**The fix**: Add `valid_before` parameter to `get_neighbors()` at
`knowledge_graph.py:345-399`. When provided, the SQL WHERE clause adds
`AND (valid_at IS NULL OR valid_at <= ?)` to filter edges by creation
time. Then pass it from `_search_thread_boosted()`:

```python
# knowledge_graph.py, get_neighbors() signature change:
async def get_neighbors(
    self,
    entity_id: str,
    depth: int = 1,
    workspace_id: str | None = None,
    *,
    include_invalidated: bool = False,
    valid_before: str | None = None,  # NEW: ISO timestamp
) -> list[dict[str, Any]]:
```

```python
# knowledge_graph.py, in the SQL WHERE clause:
if valid_before:
    conditions.append("(e.valid_at IS NULL OR e.valid_at <= ?)")
    params.append(valid_before)
```

```python
# knowledge_catalog.py, in the graph neighbor expansion:
neighbors = await self._kg_adapter.get_neighbors(
    node_id,
    workspace_id=workspace_id,
    valid_before=retrieval_timestamp,  # NEW
)
```

**Bug fix (Wave 59.5)**: The neighbor lookup at `knowledge_catalog.py:559`
uses `nbr.get("node_id", "")` but `get_neighbors()` returns `from_node`
and `to_node`, not `node_id`. Graph neighbor discovery is currently
silently broken — every reverse lookup gets empty string, finds zero
matches. The exact fix:

```python
# Replace the inner loop in the graph neighbor expansion:
for nbr in neighbors:
    # Determine which end is the neighbor (not the seed)
    other_node = (nbr["to_node"] if nbr["from_node"] == node_id
                  else nbr["from_node"])
    # Map KG node back to entry_id via reverse lookup
    for eid, nid in self._projections.entry_kg_nodes.items():
        if nid == other_node and eid not in seen:
            entry_data = self._projections.memory_entries.get(eid)
            if entry_data:
                item = _normalize_institutional(entry_data, score=0.0)
                merged.append(item)
                seen.add(eid)
                graph_scores[eid] = 1.0
                break
```

**Why this matters**: This is the Graphiti capability that benchmarks at
18.5% accuracy improvement. The data model has supported it since Wave 14.
The query path is ~15 lines including the bug fix. Without the bug fix,
Wave 59.5's graph_proximity signal is dead weight — entries are bridged
to the KG but never discovered via graph traversal.

### Track 2: Semantic preservation gate on REFINE (~20 lines)

**Deferred from**: Wave 59, re-deferred from Wave 59.5
**Files**: Extraction/curation path (where REFINE action is dispatched)

When the curating archivist REFINEs an entry, there is currently no check
that the new content preserves the original meaning. A bad rewrite could
over-generalize specific, actionable knowledge into vague platitudes.

**The fix**: Before emitting `MemoryEntryRefined`, compute cosine
similarity between old and new content embeddings. If cosine < 0.75,
reject the rewrite and log a warning.

```python
# In the REFINE action dispatch path:
old_content = existing_entry.get("content", "")
if old_content and embed_fn:
    old_emb = embed_fn([old_content])   # sync — built at app.py:133
    new_emb = embed_fn([new_content])   # no await
    if old_emb and new_emb:
        sim = _cosine_similarity(old_emb[0], new_emb[0])
        if sim < 0.75:
            log.warning(
                "curation.refine_rejected",
                entry_id=entry_id,
                similarity=round(sim, 3),
                reason="semantic_drift",
            )
            continue  # skip this REFINE action
```

**Important**: Embeddings are NOT stored on projection entries — they live
in Qdrant. The runtime's `embed_fn` is synchronous (`(texts: list[str])
-> list[list[float]]`, built at `app.py:133`). Embed old content fresh —
simpler than a Qdrant round-trip, and the local embedding model is fast.

**Cosine similarity**: Two identical `_cosine_similarity` implementations
exist (`knowledge_graph.py:555`, `runner.py:2550`), both module-private.
The REFINE gate lives in the surface layer, which cannot import from
adapters or engine without a layer violation. Add a third copy in the
file that hosts the gate (matches the codebase's existing tolerance for
duplicated 5-line helpers). Extracting to `core/math_utils.py` is cleaner
but introduces a new core file for a single function — not worth it for
Wave 60.

**Why this matters**: The research doc found "no production system has
formal quality gates on rewrites." This is a genuine first. The gate
prevents the experience-following problem (Xiong et al.) from being
amplified by bad rewrites that corrupt entries used by future colonies.

### Track 3: Graph relationships in the API + UI (~25 lines)

**Deferred from**: Wave 59.5
**Files**: `routes/api.py`, UI component

The REST API serves knowledge entries and KG stats but has no endpoint
that returns an entry's graph neighbors or typed relationship edges.
Without this, the UI cannot show "this entry SUPERSEDES that entry" or
"these three entries are DERIVED_FROM the same source."

**The fix**: One new endpoint:

```python
# routes/api.py
@router.get("/api/v1/knowledge/{entry_id}/relationships")
async def get_entry_relationships(entry_id: str, request: Request):
    runtime = request.app.state.runtime
    kg_node_id = runtime.projections.entry_kg_nodes.get(entry_id)
    if not kg_node_id or not runtime.kg_adapter:
        return JSONResponse({"relationships": [], "entry_id": entry_id})

    neighbors = await runtime.kg_adapter.get_neighbors(
        kg_node_id,
        workspace_id=_ws_from_entry(runtime, entry_id),
    )

    # Map KG node IDs back to entry IDs via reverse lookup
    node_to_entry = {nid: eid for eid, nid in
                     runtime.projections.entry_kg_nodes.items()}
    relationships = []
    for nbr in neighbors:
        # Determine which end is the neighbor (not the seed)
        other_node = (nbr.get("to_node") if nbr.get("from_node") == kg_node_id
                      else nbr.get("from_node"))
        other_eid = node_to_entry.get(other_node, "")
        if other_eid:
            relationships.append({
                "entry_id": other_eid,
                "predicate": nbr.get("predicate", "RELATED_TO"),
                "confidence": nbr.get("confidence", 0.0),
                "title": runtime.projections.memory_entries.get(
                    other_eid, {}).get("title", ""),
            })

    return JSONResponse({"relationships": relationships,
                         "entry_id": entry_id})
```

**UI component**: In the knowledge browser, add a "Relationships" section
below each entry that shows connected entries with their predicate type
(SUPERSEDES, DERIVED_FROM, DEPENDS_ON, etc.) as clickable links. This
makes the graph bridge VISIBLE to the operator — they can trace how
knowledge evolved.

**Why this matters**: This turns the graph from internal infrastructure
into operator-inspectable provenance. The operator can see WHY an entry
was surfaced (graph proximity in the score breakdown) and HOW it evolved
(relationship chain). No other system makes knowledge graph relationships
visible to the operator through a live UI.

---

## Tier 2: Platform Coherence

### Track 4: Cost coherence (~35 lines)

**Source**: `docs/specs/cost_tracking.md`
**Files**: `surface/projections.py`, `surface/runtime.py`,
`engine/context.py`, `surface/queen_runtime.py`, `surface/queen_tools.py`,
`surface/self_maintenance.py`

Four sub-changes from the cost tracking spec:

**S1**: Add `api_cost` and `local_tokens` properties to `BudgetSnapshot`
at `projections.py:293-320` (~10 lines). Derived from existing
`model_usage` dict — no schema changes, no event changes.

```python
@property
def api_cost(self) -> float:
    """Real USD cost from cloud providers only."""
    return sum(
        v.get("cost", 0.0) for v in self.model_usage.values()
        if v.get("cost", 0.0) > 0
    )

@property
def local_tokens(self) -> int:
    """Total tokens processed by local models (cost == 0)."""
    return sum(
        int(v.get("input_tokens", 0) + v.get("output_tokens", 0))
        for v in self.model_usage.values()
        if v.get("cost", 0.0) == 0
    )
```

**S2**: `BudgetEnforcer` at `runtime.py:1619-1718` gates on `api_cost`
instead of `total_cost` (~5 lines). Budget warnings/downgrades/hard-stops
reflect real money spent. Local-only workloads never trigger budget gates
(correct — no money is being spent).

**S3**: Budget display shows both dimensions (~15 lines across
context.py:339-375 (`build_budget_block()`), queen_runtime.py (colony
completion summary text), queen_tools.py:1519-1521 (colony info)):

```
[API Budget: $4.50 remaining (90%) — comfortable]
[Local: 450K tokens processed]
```

When `api_cost == 0` (pure local): omit `$0.00 API`, show only token count
and full budget remaining.

**S6**: Maintenance dispatcher at `self_maintenance.py:72-77` tracks
`api_cost` only (~3 lines). Local-only maintenance colonies don't
decrement the daily maintenance budget.

**Why this matters**: Phase 1 v2 is the first run with real cloud costs
across three providers. The budget system must be truthful for
mixed-provider workloads. "$0.00 comfortable" while spending real money on
cloud calls is a credibility gap for anyone evaluating the platform.

### Track 5: Operator feedback loop (~40 lines)

**Files**: `routes/api.py` (~15 lines), `surface/runtime.py` (~10 lines),
UI component (~15 lines)

Add thumbs-up/thumbs-down on knowledge entries in the browser:

```python
# routes/api.py
@router.post("/api/v1/knowledge/{entry_id}/feedback")
async def submit_entry_feedback(entry_id: str, request: Request):
    body = await request.json()
    is_positive = body.get("positive", True)
    runtime = request.app.state.runtime

    entry = runtime.projections.memory_entries.get(entry_id)
    if entry is None:
        return JSONResponse({"error": "Entry not found"}, status_code=404)

    # Use existing MemoryConfidenceUpdated event
    # Event uses old/new alpha/beta (not deltas)
    old_alpha = float(entry.get("conf_alpha", 5.0))  # default prior Beta(5,5)
    old_beta = float(entry.get("conf_beta", 5.0))    # per types.py:411-420
    # ±1.0 per click (colony outcome uses +1.0 for successful access).
    # At default prior Beta(5,5): one thumbs-down → 5/6 ≈ 0.45 (5-point
    # drop). Intentionally weaker than ±2.0 to avoid one misclick
    # dominating the posterior.
    delta = 1.0
    new_alpha = old_alpha + (delta if is_positive else 0.0)
    new_beta = old_beta + (0.0 if is_positive else delta)

    await runtime.emit_and_broadcast(MemoryConfidenceUpdated(
        seq=0, timestamp=_now(),
        address=f"{entry.get('workspace_id', '')}/feedback",
        entry_id=entry_id,
        old_alpha=old_alpha,
        old_beta=old_beta,
        new_alpha=new_alpha,
        new_beta=new_beta,
        new_confidence=new_alpha / (new_alpha + new_beta),
        workspace_id=entry.get("workspace_id", ""),
        reason="operator_feedback",
    ))

    return JSONResponse({"entry_id": entry_id,
                         "feedback": "positive" if is_positive else "negative"})
```

**Note**: `MemoryConfidenceUpdated.reason` field accepts string values
(currently `"colony_outcome"` or `"archival_decay"`). Adding
`"operator_feedback"` as a new reason value requires no schema change.

**Overlap note**: Track 3 also adds an endpoint to `routes/api.py`. Both
are additive (new routes at different URL paths). No merge conflict
expected — either track can merge first.

**UI component**: In the knowledge browser, add thumbs-up/thumbs-down
icons on each entry. After clicking, the confidence bar updates to
reflect the new posterior.

**Why this matters**: Every competitor has a human feedback signal. Cursor
has accept/reject. Windsurf has Rule thumbs. Devin has corrections.
FormicOS has the richest confidence model (Beta posteriors with composite
retrieval) but no human input channel. This closes the loop.

`_rule_popular_unexamined()` (rule 17, already shipped in Wave 58.5)
surfaces entries accessed 5+ times without feedback. The operator reviews,
gives thumbs up/down, confidence updates, retrieval ranking shifts. The
hive learns from the operator.

### Track 6: Thompson ablation (0 code, measurement only)

**Source**: Novelty assessment
**Files**: None (config-only measurement)

`FORMICOS_DETERMINISTIC_SCORING` already exists in `engine/scoring_math.py`.
When set to `"1"`, Thompson Sampling is replaced with expected value
(posterior mean). No code changes needed.

Run Phase 1 twice after all code tracks land:
- Once with `FORMICOS_DETERMINISTIC_SCORING=1` (expected value, no Thompson)
- Once without (stochastic Thompson draws)

Compare quality across 8 tasks. If delta is measurable, Thompson Sampling
on knowledge entries is validated — the strongest individual technical
novelty in the project. If quality is identical, Thompson is dead weight
at current pool sizes — document the honest finding.

**Why this matters**: This is the single most publishable experiment in
the project. Either outcome is valuable. The Bayesian confidence machinery
is the most technically defensible novelty claim — but without ablation
evidence, a reviewer would ask "does this actually matter?" This run
answers that question.

---

## Tier 3: Visibility

### Track 7: Standard benchmark baseline (~100 lines eval infra)

**Files**: `config/eval/suites/humaneval.yaml`, eval task configs,
pass/fail evaluator

Run HumanEval pass@1 on single-colony execution with the local
Qwen3-Coder-30B model. The results will be modest (30B model), but they
establish a floor on the same scale as MetaGPT (85.9%), Mem0 (LOCOMO
67.13%), and Zep (DMR 94.8%).

The implementation wraps HumanEval problems as FormicOS colonies. The
sequential runner already supports custom suites. The quality scorer needs
a pass/fail evaluator (does the generated code pass the test cases?)
instead of the composite quality formula.

**Stretch goal**: Multi-colony HumanEval. The Queen decomposes a problem,
spawns parallel analysis + implementation colonies, aggregates. If
multi-colony scores higher than single-colony, that demonstrates the
colony architecture's value on a standard benchmark. Nobody has published
multi-colony HumanEval numbers.

**Design decisions** (resolved):

1. **Problem count**: All 164 for comparability with published benchmarks.
   Subset runs are not citable.
2. **Pass/fail evaluation**: Post-colony. The colony's job is "write the
   function." The eval harness runs HumanEval's test cases in a sandbox
   (`code_execute` Docker container, `--network=none`) after the colony
   completes. This separates generation from evaluation and matches how
   other systems report pass@1.
3. **Single-colony config**: 1 coder, sequential strategy, 3 rounds, $1
   budget. Throughput matters (164 problems × ~2 min = ~5.5 hours on
   local GPU). Heavier configs can be a follow-up comparison.
4. **Input format**: Standard HumanEval format — function signature +
   docstring as task description. This is what every published benchmark
   uses; anything else is non-comparable.
5. **Source**: Bundle as `config/eval/tasks/humaneval/` generated from
   `openai/human-eval` dataset. A script (`scripts/import_humaneval.py`)
   downloads the dataset and generates 164 task YAML files + a suite
   config. The generated configs are checked in for reproducibility.

### Track 8: GitHub launch preparation (0 engine code)

**Deliverables**:

1. **FINDINGS.md** at repo root
   - Headline: operational knowledge >> domain knowledge
   - Measurement arc story (6 bottleneck layers)
   - Compounding data table (clean runs)
   - Proven vs hypothesized (honest separation)

2. **README refresh** — add knowledge pipeline description, link to
   FINDINGS.md, update feature list to reflect Waves 54-60

3. **Docs cleanup**
   - Archive stale handoff files
   - Move session memo + research prompts to internal/
   - Create `docs/README.md` index

4. **Architecture diagram** — the 9-layer knowledge pipeline as a visual,
   showing flow from extraction through curation through retrieval through
   injection

5. **Demo recording** — 2-minute video: operator gives Queen a task,
   colonies execute, knowledge extracts, entry refines, next colony uses
   refined knowledge, operator gives feedback via thumbs up/down

6. **CI/CD** — GitHub Actions running `ruff check`, `pyright`, and `pytest`
   on the 3500+ test suite

---

## Dependency Graph

```
Tier 1 (knowledge pipeline):
  [T1] Temporal queries + bug fix  ──┐
  [T2] Semantic gate on REFINE    ───┼── all parallel, no file overlap
  [T3] Graph relationships API    ───┘

Tier 2 (platform coherence):
  [T4] Cost coherence             ───┐
  [T5] Operator feedback loop     ───┼── T3 and T5 both add to routes/api.py
  [T6] Thompson ablation          ───┘── (additive, no conflict, either merges first)

Tier 3 (visibility):
  [T7] Standard benchmarks        ───┐
  [T8] GitHub launch              ───┼── parallel with everything
                                     │
                              AFTER T1-T8: GitHub goes public
```

Tracks 1-5 are code. Track 6 is measurement. Tracks 7-8 are packaging.
All Tier 1 and Tier 2 code tracks can run in parallel (no file overlap
between tracks within a tier, minimal overlap between tiers).

Track 6 (Thompson ablation) must run AFTER all code tracks land to
measure the final stack.

Track 8 (GitHub launch) should be the last thing — it packages everything
else.

---

## Code delta estimate

| Track | Files | Lines |
|-------|-------|-------|
| T1: Temporal queries + bug fix | knowledge_catalog.py, knowledge_graph.py | ~15 |
| T2: Semantic gate | Extraction/curation dispatch path | ~20 |
| T3: Graph API + UI | routes/api.py, UI component | ~25 |
| T4: Cost coherence | projections.py, runtime.py, context.py, queen_*.py, self_maintenance.py | ~35 |
| T5: Operator feedback | routes/api.py, runtime.py, UI component | ~40 |
| T6: Thompson ablation | none (measurement) | 0 |
| T7: Standard benchmarks | eval configs, evaluator | ~100 |
| T8: GitHub launch | docs only | 0 |
| **Total engine code** | | **~135** |
| **Total eval infra** | | **~100** |
| **Total docs/packaging** | | **FINDINGS.md + README + cleanup** |

---

## Acceptance Criteria

### Knowledge pipeline completion
- Temporal queries: graph retrieval respects `valid_before` parameter;
  `get_neighbors()` signature extended, SQL clause added
- Bug fix: neighbor lookup uses correct field names (`from_node`/`to_node`
  not `node_id`)
- Semantic gate: REFINE rejected when cosine < 0.75, logged with reason
  `semantic_drift`
- Graph API: `GET /api/v1/knowledge/{entry_id}/relationships` returns
  typed edges with predicates, confidence, and entry titles
- UI: knowledge browser shows relationship links on entries

### Platform coherence
- Cost: `BudgetSnapshot.api_cost` returns cloud-only USD;
  `BudgetSnapshot.local_tokens` returns local token volume
- Cost: `BudgetEnforcer` gates on `api_cost` (local-only = no budget
  warnings). **By-design test case**: local-only workload with 10
  completed colonies, `api_cost == $0.00` — BudgetEnforcer never fires
  warn/downgrade/hard-stop. This is intentional: no money spent = no
  budget concern. Document in test to prevent "budget gates never fire"
  bug reports.
- Cost: budget display shows `[API Budget: ...]` + `[Local: ... tokens]`
- Cost: Queen displays show split cost; pure-local omits `$0.00`
- Cost: maintenance daily spend ignores local-only colony costs
- Feedback: thumbs up/down on entries emits `MemoryConfidenceUpdated`
  with `reason="operator_feedback"`
- Feedback: confidence shifts observable in knowledge browser after
  feedback
- Thompson: ablation results documented (validates or removes Thompson)

### Visibility
- HumanEval pass@1 number published (even if modest)
- FINDINGS.md at repo root with honest results
- README updated to reflect current state
- Docs cleaned (archive stale, index current)
- GitHub Actions CI green on push

### The meta-criterion

After Wave 60, a senior engineer at an AI lab can:
1. Find the repo on GitHub
2. Read FINDINGS.md and understand what FormicOS proved
3. Read ARCHITECTURE.md and understand the 9-layer pipeline
4. Look at the knowledge browser and see entries with confidence,
   relationships, and operator feedback
5. Run the test suite and see 3500+ tests pass
6. Run HumanEval and see a benchmark number
7. Form their own assessment of whether this is interesting

If all seven are true, the project is ready. Everything after that is
iteration driven by user feedback, not internal development.

---

## What Wave 60 Does NOT Do

- Add new event types (65 is the final count unless a future ADR says
  otherwise)
- Add new agent castes (6 castes are sufficient)
- Add new Queen tools (21 tools are sufficient)
- Add new proactive rules beyond the 17 already shipped
- Migrate from SQLite KG to Neo4j/FalkorDB (SQLite is sufficient at
  current scale)
- Add SPLIT operation (no production system does this — not a credibility
  gap)
- Add multi-hop graph traversal beyond 1-hop (defer until evidence shows
  need)
- Change the composite scoring weights (Thompson ablation decides this)
- Add time-based local complexity budget (S4 from cost tracking spec —
  round limits provide adequate local-workload gating for now)
- Build a marketing site (GitHub README + FINDINGS.md is the MVP)

---

## Technical Notes

### get_neighbors() signature (current)

```python
async def get_neighbors(
    self,
    entity_id: str,
    depth: int = 1,
    workspace_id: str | None = None,
    *,
    include_invalidated: bool = False,
) -> list[dict[str, Any]]:
```

Returns dicts with: `id`, `subject`, `predicate`, `object`, `from_node`,
`to_node`, `confidence`, `valid_at`, `invalid_at`, `transaction_time`.
Track 1 adds `valid_before: str | None = None` kwarg.

### MemoryConfidenceUpdated fields (current)

```python
class MemoryConfidenceUpdated(EventEnvelope):
    entry_id: str
    colony_id: str = ""
    colony_succeeded: bool = True
    old_alpha: float
    old_beta: float
    new_alpha: float
    new_beta: float
    new_confidence: float  # alpha / (alpha + beta)
    workspace_id: str
    thread_id: str = ""
    reason: str = "colony_outcome"
```

Uses absolute old/new values, not deltas. `reason` field (not `source`)
accepts string values: `"colony_outcome"`, `"archival_decay"`. Track 5
adds `"operator_feedback"`.

### Wave 59.5 bug: neighbor field name mismatch

`knowledge_catalog.py:559` uses `nbr.get("node_id", "")` in the reverse
lookup, but `get_neighbors()` returns `from_node` and `to_node`, not
`node_id`. This means graph neighbor discovery silently finds zero
matches. Track 1 fixes this as part of the temporal query work.

### Embeddings not stored on projection entries

`projections.memory_entries` stores entry metadata but not embeddings.
Embeddings live in Qdrant. Track 2's semantic gate must embed old content
fresh via the embed function (available in the extraction context) rather
than reading a stored embedding.

### FORMICOS_DETERMINISTIC_SCORING already exists

`engine/scoring_math.py` reads `FORMICOS_DETERMINISTIC_SCORING` env var.
When `"1"`, Thompson draws are replaced with posterior mean. Track 6
requires no code changes — just two eval runs with different env config.

---

## After Wave 60

The project doesn't need more waves. It needs:
- Users who deploy it on real projects
- Feedback that drives iteration
- Blog posts that make the findings visible
- Conference submissions if the Thompson ablation or Phase 1 delta
  produce publishable results
- Community contributions that extend what one developer built

Wave 60 is the bridge from "building" to "shipping."

---

## Related Documents

- [cost_tracking.md](../../specs/cost_tracking.md) — End-to-end cost flow
  analysis with 6 suggestions (S1-S6)
- [wave_59_5_plan.md](../wave_59/wave_59_5_plan.md) — Graph bridge,
  progressive disclosure fix, 7-signal composite scoring
- [wave_59_plan.md](../wave_59/wave_59_plan.md) — Curating archivist,
  MemoryEntryRefined event
- [phase1_v1_results.md](../wave_59/phase1_v1_results.md) — Phase 1 v1
  results (19 accesses, 0 knowledge_detail calls, 889 fallback events)
- [knowledge_system.md](../../specs/knowledge_system.md) — Knowledge
  system spec (7-signal composite scoring, retrieval tiers)
