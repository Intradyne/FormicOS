# Wave 40 1A: Backend Profiling Report

## Methodology

Lightweight wall-clock profiling via `tests/benchmark/profiling_harness.py`.
Each path measured 5–20 iterations with warmup. Python 3.12, Windows 10, local dev machine.

## Results

| Path | Min (ms) | Mean (ms) | Max (ms) | Verdict |
|------|----------|-----------|----------|---------|
| `generate_briefing` (100 entries) | 0.83 | 0.95 | 1.21 | Fast |
| `generate_briefing` (500 entries) | 14.4 | 16.7 | 20.3 | Acceptable (<100ms budget) |
| `_composite_key` scoring (200 items) | 0.35 | 0.44 | 1.15 | Fast |
| `_composite_key` sort (200 items) | 0.37 | 0.37 | 0.38 | Fast |
| `build_snapshot` (20 colonies × 5 rounds) | <0.01 | <0.01 | 0.01 | Fast |
| Event construction (Pydantic frozen models) | <0.01 | <0.01 | 0.04 | Fast |
| Projection replay (10 rounds, 20 events) | <0.01 | 0.01 | 0.03 | Fast |
| Projection replay (50 rounds, 100 events) | 0.01 | 0.01 | 0.01 | Fast |

## Analysis

### No performance bottleneck found

All five required paths complete in <20ms even at 500-entry scale. The system's
<100ms target for `generate_briefing` is met with headroom. Retrieval scoring,
view-state snapshots, event construction, and projection replay are all
sub-millisecond.

### Known O(n²) patterns — accepted

Two rules in `proactive_intelligence.py` have O(n²) worst-case:

1. **`_rule_contradiction()`** — pairwise comparison of high-confidence entries.
   Pre-filtered to verified/stable entries with alpha > 5 (typically <10% of corpus).
   At 500 entries, still <20ms total briefing time. Not worth optimizing.

2. **`_rule_merge_opportunity()`** — pairwise similarity on all entries.
   Same pre-filtering applies. Negligible at realistic scale.

The co-occurrence pre-computation in `knowledge_catalog.py` is also O(n²) over
result sets, but result sets are capped at 10–20 items by retrieval limits.

### Thompson Sampling per-item draw — accepted

`random.betavariate()` is called per-item during sort in `knowledge_catalog.py`.
This is intentional (exploration budget) and adds ~0.002ms/item. Not worth
caching — the non-determinism is the feature.

### View-state snapshot — fast

`build_snapshot` rebuilds the full tree on every call. At 20 colonies it's
sub-millisecond. For much larger workspaces (100+ colonies), consider caching
the tree and invalidating on colony state changes. Not needed now.

### Projection replay — fast

Dict-dispatch handler map (`_HANDLERS`) provides O(1) event routing.
50 rounds × 2 events each = 100 events replayed in 0.01ms. Linear scaling
is fine for the expected event volumes (<10K events per workspace).

One O(N) lookup exists in `_on_tokens_consumed()` which scans all colonies
to find an agent. Adding an agent→colony index would help at scale but
is not a current bottleneck.

## Refactoring decisions

Based on profiling, no refactor is motivated by performance. All refactors
in 1B–1F are motivated by **navigability and coherence**, not speed.

| Refactor | Motivation | Performance impact |
|----------|------------|-------------------|
| Extract tool dispatch from `runner.py` | Navigability — 2314-line file | None (same code paths) |
| Extract runner data types | Navigability — 5 models mixed into execution code | None |
| Extract colony hooks from `colony_manager.py` | Navigability — 500+ lines of post-colony hooks | None |
| Extract memory extraction pipeline | Navigability — 175-line pipeline buried in manager | None |
| `proactive_intelligence.py` — keep sequential calls | Coherence — registry would add indirection for no gain | None |
| `queen_tools.py` — extract shared helpers | DRY — 2 duplicated patterns (colony lookup, caste parsing) | None |
| `projections.py` — document organization | Coherence — file is large but structurally sound | None |

## File split decisions — rejected and why

- **colony_manager.py hooks** — Considered extracting ~500 lines of post-colony
  hooks to `colony_hooks.py`. Rejected: all hooks use `self._runtime` extensively
  (projections, event broadcasting, LLM ports, memory stores). Extracting would
  require passing 5+ params per function, hurting readability. Instead: added
  section headers (Sections 1–4) for navigability.

- **proactive_intelligence.py registry** — Considered a rule registry pattern to
  replace explicit sequential calls in `generate_briefing()`. Rejected: 12 rules
  are called in sequence with clear section comments. A registry adds indirection
  for no gain at this scale. The file is coherent as-is.

- **projections.py split** — 1655 lines but structurally sound. Event handlers
  follow a consistent pattern (`_on_<event_type>`), the handler map is a clean
  dict dispatch, and models are grouped logically. No split justified.

## Error handling audit (1F)

- **HTTP routes (api.py)**: All endpoints now use `_err_response()` with
  StructuredError. Fixed one violation (get_colony_audit was returning raw JSON).
- **A2A routes**: Fully consistent with StructuredError.
- **Tool execution (runner.py)**: Returns `ToolExecutionResult` with plain string
  errors. This is intentional — tool errors are consumed by LLM agents, not
  operators. Wrapping in StructuredError would add overhead with no consumer.
- **Queen tools**: Same — plain string errors consumed by the Queen LLM. No
  change needed.
- **MCP server**: 4 endpoints return raw `{"error": "..."}` dicts. These are
  noted but not changed in this wave (Team 3 owns MCP surface).

## Accepted and why

- O(n²) rules: practical impact <1ms at realistic scale
- Per-item Thompson draws: intentional non-determinism
- No-index agent lookups: <100 colonies typical; not a hot path
- Full snapshot rebuilds: sub-millisecond at current scale
