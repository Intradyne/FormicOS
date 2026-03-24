# Wave 60 Dispatch Prompts

**Date**: 2026-03-23
**Source**: `wave_60_plan.md` (audited, 6 findings applied)
**Track 6** (Thompson ablation): runs after both teams land — measurement, not code
**Track 8** (GitHub launch): runs after all code + measurement — packaging, not code

---

## Team Split Rationale

| | Team A | Team B |
|--|--------|--------|
| **Theme** | Make internals correct | Make everything visible |
| **Tracks** | T1 + T2 + T4 | T3 + T5 + T7 |
| **Lines** | ~70 | ~165 + eval infra |
| **Sub-parallel** | 3 tracks, zero file overlap | 3 tracks, one shared file (additive) |

Team A is smaller in lines but touches more files across more layers.
Team B is larger but mostly additive (new endpoints, new eval configs).
Both teams can dispatch all sub-tracks in parallel internally.

**Zero file overlap between teams.** Verified below.

---

## Team A: Knowledge Pipeline Completion + Cost Truth

### Mission

Fix three correctness gaps in the knowledge and budget internals. After
this team lands, graph retrieval actually discovers neighbors (bug fix),
REFINE actions are quality-gated, and budget enforcement reflects real
money spent.

### Sub-tracks (all parallel — zero file overlap between A1, A2, A3)

#### A1: Temporal Queries + Bug Fix (T1) — ~15 lines

**Files owned**:
- `adapters/knowledge_graph.py` — add `valid_before` kwarg to `get_neighbors()`
- `surface/knowledge_catalog.py` — fix `node_id` bug, pass `valid_before`

**Do NOT touch**: `routes/api.py`, `engine/context.py`, `projections.py`,
any UI files, any eval files.

**Exact changes**:

1. `knowledge_graph.py:345-399` — extend `get_neighbors()` signature:

```python
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

In the SQL query builder, add:

```python
if valid_before:
    conditions.append("(e.valid_at IS NULL OR e.valid_at <= ?)")
    params.append(valid_before)
```

2. `knowledge_catalog.py` — in `_search_thread_boosted()`, the graph
neighbor expansion block (~line 554-570):

**Bug fix**: Replace `nbr.get("node_id", "")` with correct from/to logic.
The current code silently returns zero matches because `get_neighbors()`
returns `from_node` and `to_node`, not `node_id`:

```python
for nbr in neighbors:
    # Determine which end is the neighbor (not the seed)
    other_node = (nbr["to_node"] if nbr["from_node"] == node_id
                  else nbr["from_node"])
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

**Temporal pass-through**: In the same block, pass `valid_before` to
`get_neighbors()`:

```python
neighbors = await self._kg_adapter.get_neighbors(
    node_id,
    workspace_id=workspace_id,
    valid_before=retrieval_timestamp,  # from colony context if available
)
```

If `retrieval_timestamp` is not available in the current calling context,
pass `None` (temporal filtering becomes a no-op). The parameter is
optional; the bug fix is the priority.

**Validation**:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify: after the bug fix, graph neighbor discovery returns actual entries
(not empty). Write a unit test that constructs a KG with 2 linked nodes,
calls `_search_thread_boosted()`, and asserts the neighbor appears in
results with `graph_scores[eid] == 1.0`.

---

#### A2: Semantic Preservation Gate on REFINE (T2) — ~20 lines

**Files owned**:
- The file that dispatches REFINE actions (extraction/curation path —
  locate where `MemoryEntryRefined` is emitted)

**Do NOT touch**: `knowledge_catalog.py` (A1), `knowledge_graph.py` (A1),
`routes/api.py` (Team B), `projections.py` (A3), `runtime.py` (A3),
any UI files.

**Exact changes**:

1. Add a module-private `_cosine_similarity()` helper in the file that
hosts the gate. Two identical implementations exist elsewhere
(`knowledge_graph.py:555`, `runner.py:2550`) — duplicate the 5-line
function. Do NOT import from those files (layer violation: surface cannot
import from adapters or engine).

```python
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

2. Before emitting `MemoryEntryRefined`, add the gate:

```python
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

**Critical**: `embed_fn` is **synchronous** — `(texts: list[str]) ->
list[list[float]]`, built at `app.py:133`. Do NOT use `await`.

**Critical**: Embeddings are NOT stored on projection entries. Embed old
content fresh via `embed_fn`.

**Validation**:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Write a unit test: mock `embed_fn` to return two vectors with cosine
< 0.75, assert `MemoryEntryRefined` is NOT emitted. Another test with
cosine > 0.75, assert it IS emitted.

---

#### A3: Cost Truth — S1 + S2 + S6 (T4) — ~35 lines

**Files owned**:
- `surface/projections.py` — BudgetSnapshot properties
- `surface/runtime.py` — BudgetEnforcer
- `engine/context.py` — `build_budget_block()` at lines 339-375
- `surface/queen_runtime.py` — colony completion summary text
- `surface/queen_tools.py` — colony info display at lines 1519-1521
- `surface/self_maintenance.py` — daily spend tracking at lines 72-77

**Do NOT touch**: `core/events.py`, `engine/runner.py`, `surface/app.py`,
`config/formicos.yaml`, `routes/api.py` (Team B),
`knowledge_catalog.py` (A1), `knowledge_graph.py` (A1).

**S1** — Add to `BudgetSnapshot` at `projections.py:293-320`:

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

**S2** — `BudgetEnforcer` at `runtime.py:1619-1718`. Change utilization:

```python
# Before:
utilization = ws.budget.total_cost / ws.budget_limit
# After:
utilization = ws.budget.api_cost / ws.budget_limit if ws.budget_limit > 0 else 0.0
```

Warn (80%), downgrade (90%), hard-stop (100%) thresholds unchanged.

**S3** — Budget display at `context.py:339-375` (`build_budget_block()`):

```
[API Budget: $4.50 remaining (90%) — comfortable]
[Local: 450K tokens processed]
```

When `api_cost == 0`: omit `$0.00 API`, show only local tokens and full
budget remaining.

Queen follow-up at `queen_runtime.py` (colony completion summary text):
```
Cost: $0.23 API / 450K local tokens
```

Colony info at `queen_tools.py:1519-1521`:
```
Cost: $0.23 API / 450K local tokens / $5.00 budget
```

When `api_cost == 0`: `Cost: 450K local tokens / $5.00 budget`

**S6** — `self_maintenance.py:72-77`: accumulate `api_cost` only in
`_daily_spend`. Local-only maintenance colonies don't decrement budget.

**Validation**:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Write tests:
1. BudgetSnapshot with mixed model_usage: `api_cost` returns cloud-only
   total, `local_tokens` returns local-only total.
2. BudgetEnforcer with pure-local workspace (api_cost == $0.00): 10
   colonies completed, enforcer NEVER fires warn/downgrade/hard-stop.
   This is by-design — no money spent = no budget concern. Document in
   test docstring.
3. Budget display: pure-local shows `[API Budget: $5.00 remaining (100%)]`
   + `[Local: 450K tokens processed]`, no `$0.00` noise.

---

### Team A file ownership (complete)

| File | Sub-track | Changes |
|------|-----------|---------|
| `adapters/knowledge_graph.py` | A1 | `valid_before` kwarg on `get_neighbors()` |
| `surface/knowledge_catalog.py` | A1 | Bug fix (`from_node`/`to_node`), pass `valid_before` |
| Extraction/curation dispatch file | A2 | Cosine gate + `_cosine_similarity()` helper |
| `surface/projections.py` | A3 | `api_cost` + `local_tokens` properties |
| `surface/runtime.py` | A3 | BudgetEnforcer uses `api_cost` |
| `engine/context.py` | A3 | `build_budget_block()` shows split cost |
| `surface/queen_runtime.py` | A3 | Follow-up summary shows split cost |
| `surface/queen_tools.py` | A3 | Colony info shows split cost |
| `surface/self_maintenance.py` | A3 | Daily spend tracks `api_cost` only |

---

## Team B: Operator Surfaces + Evaluation

### Mission

Add two new API endpoints (graph relationships, operator feedback), build
the HumanEval benchmark harness, and prepare all visibility artifacts for
GitHub launch. After this team lands, the operator can inspect knowledge
graph relationships, give feedback on entries, and the project has a
standard benchmark number.

### Sub-tracks (all parallel — T3 and T5 share routes/api.py but are additive)

#### B1: Graph Relationships API + UI (T3) — ~25 lines

**Files owned**:
- `surface/routes/api.py` — new endpoint
- UI component (knowledge browser relationships section)

**Do NOT touch**: `knowledge_catalog.py` (Team A), `knowledge_graph.py`
(Team A), `projections.py` (Team A), `runtime.py` (Team A),
`engine/context.py` (Team A).

**Exact changes**:

1. New endpoint in `routes/api.py`:

```python
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

    # Build reverse index for this request
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

Helper to get workspace_id from entry:

```python
def _ws_from_entry(runtime: Any, entry_id: str) -> str:
    return runtime.projections.memory_entries.get(
        entry_id, {}).get("workspace_id", "")
```

2. **UI**: In the knowledge browser, add a "Relationships" section below
each entry. Fetch from `/api/v1/knowledge/{entry_id}/relationships`.
Show each relationship as: `SUPERSEDES → "Entry Title"` (clickable link
to that entry). Group by predicate type. Show empty state if no
relationships.

**Note**: This endpoint uses `get_neighbors()` which Team A (A1) is
extending with `valid_before`. The endpoint does NOT pass `valid_before`
— it returns all active relationships. This is correct for the UI (show
all current relationships, not time-scoped).

**Note**: Team A's bug fix (A1) changes how `get_neighbors()` results are
interpreted. This endpoint uses `from_node`/`to_node` correctly (see
`other_node` logic above). If Team A's bug fix hasn't landed yet, the
neighbor data will still contain the correct fields — they were always
returned, just not read correctly by the catalog code.

**Overlap**: B2 also adds an endpoint to `routes/api.py`. Both are
additive at different URL paths. Either sub-track can merge first.

**Validation**:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Write a test: mock `runtime.kg_adapter.get_neighbors()` to return a
neighbor dict with `from_node`/`to_node`/`predicate`, mock
`entry_kg_nodes`, assert response contains the relationship with correct
predicate and title.

---

#### B2: Operator Feedback Loop (T5) — ~40 lines

**Files owned**:
- `surface/routes/api.py` — new endpoint
- UI component (knowledge browser thumbs up/down)

**Do NOT touch**: `knowledge_catalog.py` (Team A), `projections.py`
(Team A), `runtime.py` (Team A), `engine/context.py` (Team A),
`knowledge_graph.py` (Team A).

**Exact changes**:

1. New endpoint in `routes/api.py`:

```python
@router.post("/api/v1/knowledge/{entry_id}/feedback")
async def submit_entry_feedback(entry_id: str, request: Request):
    body = await request.json()
    is_positive = body.get("positive", True)
    runtime = request.app.state.runtime

    entry = runtime.projections.memory_entries.get(entry_id)
    if entry is None:
        return JSONResponse({"error": "Entry not found"}, status_code=404)

    old_alpha = float(entry.get("conf_alpha", 5.0))  # default prior Beta(5,5)
    old_beta = float(entry.get("conf_beta", 5.0))    # per types.py:411-420

    # ±1.0 per click (colony outcome uses +1.0 for successful access)
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

    return JSONResponse({
        "entry_id": entry_id,
        "feedback": "positive" if is_positive else "negative",
    })
```

**Event note**: `MemoryConfidenceUpdated` uses absolute old/new values,
not deltas. `reason` field accepts string values — existing values are
`"colony_outcome"` and `"archival_decay"`. Adding `"operator_feedback"`
requires no schema change.

**Confidence delta note**: ±1.0 per click. At default prior Beta(5,5),
one thumbs-down shifts confidence from 0.50 to 5/6 ≈ 0.45. This matches
the weight of a single colony outcome (+1.0 on successful access).

2. **UI**: In the knowledge browser, add thumbs-up / thumbs-down icons on
each entry row. POST to `/api/v1/knowledge/{entry_id}/feedback` with
`{"positive": true}` or `{"positive": false}`. After response, update
the confidence bar to reflect `new_confidence`.

**Import**: The endpoint needs `MemoryConfidenceUpdated` from
`core/events.py`. Check existing imports in `routes/api.py` — if not
already imported, add it.

**Overlap**: B1 also adds an endpoint to `routes/api.py`. Both are
additive at different URL paths. Either sub-track can merge first.

**Validation**:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Write tests:
1. Thumbs-up: assert `MemoryConfidenceUpdated` emitted with
   `new_alpha == old_alpha + 1.0`, `reason == "operator_feedback"`.
2. Thumbs-down: assert `new_beta == old_beta + 1.0`.
3. Entry not found: assert 404 response.
4. Default prior: entry missing `conf_alpha` field uses 5.0 fallback.

---

#### B3: HumanEval Benchmark (T7) — ~100 lines eval infra

**Files owned**:
- `scripts/import_humaneval.py` — dataset import script
- `config/eval/suites/humaneval.yaml` — suite config
- `config/eval/tasks/humaneval/` — generated task configs (164 files)
- Eval pass/fail evaluator (new file or extension of existing scorer)

**Do NOT touch**: Any source file under `src/formicos/`. This sub-track
is pure eval infrastructure — no engine, adapter, or surface changes.

**Deliverables**:

1. **Import script** (`scripts/import_humaneval.py`):
   - Downloads HumanEval dataset from `openai/human-eval` GitHub repo
   - Generates 164 task YAML files in `config/eval/tasks/humaneval/`
   - Each task: function signature + docstring as task description
   - Standard HumanEval format for comparability with published benchmarks
   - Generated configs are checked in for reproducibility

2. **Suite config** (`config/eval/suites/humaneval.yaml`):
   - References all 164 task configs
   - Single-colony config: 1 coder, sequential strategy, 3 rounds, $1 budget
   - Knowledge mode: empty (baseline — no cross-task knowledge)

3. **Pass/fail evaluator**:
   - Post-colony evaluation: colony writes the function, harness tests it
   - Execute generated code + HumanEval test cases in sandbox
     (`code_execute` Docker container, `--network=none`)
   - Binary pass/fail per problem
   - Report pass@1 as `passed / 164`

4. **Run and record**: Execute the suite on local Qwen3-Coder-30B. Record
   results. The number will be modest (30B model) but establishes a floor
   on the same scale as published benchmarks.

**Design decisions** (already resolved in plan):
- All 164 problems (subset runs are not citable)
- Post-colony sandbox evaluation (not in-colony execution)
- Standard HumanEval input format (signature + docstring)
- 1 coder / sequential / 3 rounds / $1 budget per problem

**Validation**: The import script runs, generates 164 task configs, suite
config references them all, evaluator produces a pass@1 number.

---

### Team B file ownership (complete)

| File | Sub-track | Changes |
|------|-----------|---------|
| `surface/routes/api.py` | B1 + B2 | Two new endpoints (additive, no conflict) |
| UI knowledge browser component | B1 + B2 | Relationships section + feedback buttons |
| `scripts/import_humaneval.py` | B3 | New script |
| `config/eval/suites/humaneval.yaml` | B3 | New suite config |
| `config/eval/tasks/humaneval/*.yaml` | B3 | 164 generated task configs |
| Eval pass/fail evaluator | B3 | New evaluator file |

---

## Cross-Team Verification

### Zero file overlap between Team A and Team B

| Team A owns | Team B owns |
|-------------|-------------|
| `adapters/knowledge_graph.py` | `surface/routes/api.py` |
| `surface/knowledge_catalog.py` | UI components |
| Extraction/curation dispatch file | `scripts/import_humaneval.py` |
| `surface/projections.py` | `config/eval/` |
| `surface/runtime.py` | Eval evaluator |
| `engine/context.py` | |
| `surface/queen_runtime.py` | |
| `surface/queen_tools.py` | |
| `surface/self_maintenance.py` | |

No file appears in both columns.

### Team B reads Team A's code but doesn't modify it

- B1's endpoint reads `runtime.projections.entry_kg_nodes` (populated by
  Team A's A1 bug fix) and calls `runtime.kg_adapter.get_neighbors()`
  (extended by A1). Both work with or without A1's changes — the endpoint
  uses the correct `from_node`/`to_node` field names regardless.
- B2's endpoint reads `runtime.projections.memory_entries` (unchanged by
  Team A) and calls `runtime.emit_and_broadcast()` (Team A modifies the
  BudgetEnforcer section of runtime.py, not `emit_and_broadcast`).

### Merge order

Both teams can merge independently. No ordering constraint. Team B's
endpoints work correctly whether Team A has landed or not.

After both teams merge: run full CI, then proceed to Track 6 (Thompson
ablation) and Track 8 (GitHub launch).

---

## Post-Merge: Track 6 + Track 8

### Track 6: Thompson Ablation (measurement, 0 code)

`FORMICOS_DETERMINISTIC_SCORING` already exists in `engine/scoring_math.py`.
Run Phase 1 twice:
- `FORMICOS_DETERMINISTIC_SCORING=1` (posterior mean, no Thompson)
- Without (stochastic Thompson draws)

Compare quality across 8 tasks. Document results in `docs/waves/wave_60/`.

### Track 8: GitHub Launch (packaging, 0 engine code)

1. **FINDINGS.md** at repo root
2. **README refresh**
3. **Docs cleanup** (archive stale files, create index)
4. **Architecture diagram** (9-layer pipeline visual)
5. **Demo recording** (2-minute video)
6. **CI/CD** (GitHub Actions: ruff + pyright + pytest)

Track 8 runs last — it packages everything else.

---

## Full CI gate (both teams, all sub-tracks)

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Every sub-track runs this independently. After merge, run it once more
on the combined result.
