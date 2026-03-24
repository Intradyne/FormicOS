# Wave 34 Team 1 — Retrieval Intelligence + Co-occurrence Activation

## Role

You are implementing tiered retrieval with auto-escalation, budget-aware context assembly, and co-occurrence scoring activation. These are the three features that make FormicOS token-efficient and retrieval-intelligent. You run in parallel with Teams 2 and 3.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/044-cooccurrence-scoring.md` (approved) before implementing A3. Follow the exact weight values and sigmoid normalization.
- Read `docs/decisions/041-knowledge-tuning.md` for the existing composite scoring context.
- Read `docs/decisions/043-cooccurrence-data-model.md` for the co-occurrence data structure.
- The event union does NOT change. No new events.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `surface/knowledge_catalog.py` | MODIFY | `search_tiered()`, `_format_tier()`, co-occurrence in `_composite_key()`, sigmoid normalization |
| `engine/runner.py` | MODIFY | Wire tiered search into `_handle_memory_search()`, budget-aware context assembly, `detail` param on memory_search tool spec |
| `surface/knowledge_constants.py` | MODIFY | `COMPOSITE_WEIGHTS` dict (6 signals) |
| `tests/unit/surface/test_tiered_retrieval.py` | CREATE | Tiered search tests |
| `tests/unit/surface/test_budget_assembly.py` | CREATE | Budget allocation tests |
| `tests/unit/surface/test_cooccurrence_scoring.py` | CREATE | Co-occurrence signal + invariant tests |

## DO NOT TOUCH

- `config/caste_recipes.yaml` — Team 2 owns (Queen prompt + knowledge_feedback tool arrays)
- `surface/queen_runtime.py` — Team 2 owns (insight injection)
- `surface/proactive_intelligence.py` — Team 2 owns
- `surface/mcp_server.py` — Team 2 + Team 3 own (briefing resource, knowledge_feedback, sub_type filter)
- `surface/routes/api.py` — Team 2 owns (briefing endpoint)
- `core/types.py` — Team 3 owns (EntrySubType)
- `surface/memory_extractor.py` — Team 3 owns (sub-type classification)
- `surface/routes/knowledge_api.py` — Team 3 owns (sub_type filter)
- `frontend/*` — Team 3 owns
- `docs/demos/*` — Team 3 owns
- All integration test files — Validation track owns
- All documentation — Validation track owns

## Overlap rules

- `engine/runner.py`: You own this file for tiered search wiring + budget assembly. **Team 2's B7 (knowledge_feedback dispatch) is GATED on your changes landing first.** Team 2 will add a ~15-line tool dispatch after your restructured runner is verified. You do NOT need to accommodate B7 — just implement clean.

---

## A1. Tiered retrieval with auto-escalation

### What

Start cheap (~15 tokens/result), escalate when coverage is thin. Based on NeuroStack's `tiered_search()`, adapted for FormicOS. Target: 40-50% of queries resolve at summary tier.

### Where

`surface/knowledge_catalog.py` — new public method `search_tiered()` and private `_format_tier()`. The existing `_search_thread_boosted()` (line 300) does the actual retrieval + composite scoring. `search_tiered()` wraps it with tier logic.

### Implementation

```python
# In knowledge_catalog.py, after _search_thread_boosted:

async def search_tiered(
    self,
    query: str,
    *,
    workspace_id: str,
    thread_id: str = "",
    source_colony_id: str = "",
    top_k: int = 5,
    tier: str = "auto",
) -> list[dict[str, Any]]:
    """Tiered retrieval with auto-escalation.

    Tiers:
      summary: ~15-20 tokens/result (title + one-line summary + confidence annotation)
      standard: ~75 tokens/result (title + summary + 200-char excerpt + domains + decay)
      full: ~200+ tokens/result (full content + metadata + provenance + co-occurrence)
      auto: start at summary, escalate if coverage is thin
    """
    # Fetch 2x top_k to have escalation headroom
    results = await self._search_thread_boosted(
        query,
        source_system="institutional_memory",
        canonical_type="",  # all types
        workspace_id=workspace_id,
        thread_id=thread_id,
        source_colony_id=source_colony_id,
        top_k=top_k * 2,
    )

    if tier != "auto":
        return self._format_tier(results[:top_k], tier)

    # Auto-escalation logic
    unique_sources = len(set(r.get("source_colony_id", "") for r in results if r.get("source_colony_id")))
    top_score = max((r.get("score", 0.0) for r in results), default=0.0)

    if unique_sources >= 2 and top_score > 0.5:
        return self._format_tier(results[:top_k], "summary")
    if unique_sources >= 1 and top_score > 0.35:
        return self._format_tier(results[:top_k], "standard")
    return self._format_tier(results[:top_k], "full")

def _format_tier(self, results: list[dict[str, Any]], tier: str) -> list[dict[str, Any]]:
    """Format results at the specified detail tier."""
    formatted = []
    for r in results:
        item: dict[str, Any] = {
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "confidence_tier": r.get("_confidence_tier", ""),  # from 33.5 annotation
            "tier": tier,
        }
        if tier in ("summary", "standard", "full"):
            item["summary"] = r.get("summary", "")[:100] if tier == "summary" else r.get("summary", "")

        if tier in ("standard", "full"):
            item["content_preview"] = r.get("content_preview", "")[:200]
            item["domains"] = r.get("domains", [])
            item["decay_class"] = r.get("decay_class", "ephemeral")

        if tier == "full":
            item["content"] = r.get("content_preview", "")  # full content
            item["conf_alpha"] = r.get("conf_alpha", 5.0)
            item["conf_beta"] = r.get("conf_beta", 5.0)
            item["merged_from"] = r.get("merged_from", [])
            item["co_occurrence_cluster"] = self._get_cooccurrence_cluster(r.get("id", ""), results)

        formatted.append(item)
    return formatted
```

### Wire into runner.py

In `_handle_memory_search()` (line 454), add `detail` parameter to tool arguments:

```python
detail = arguments.get("detail", "auto")  # "auto", "summary", "standard", "full"
```

Pass to catalog search. Format the results using the tier-specific format. The `_confidence_tier()` and `_format_confidence_annotation()` functions (lines 388-451) from Wave 33.5 should be used within the formatted output at all tiers.

Also update the `memory_search` entry in `TOOL_SPECS` (line 54) to include the `detail` parameter:
```python
"detail": {
    "type": "string",
    "enum": ["auto", "summary", "standard", "full"],
    "description": "Retrieval detail level. auto (default) starts cheap and escalates. summary (~15 tokens/result), standard (~75), full (~200+).",
    "default": "auto",
}
```

### Tests

- Query with 2+ unique sources and top_score > 0.5 → resolves at summary tier
- Query with 1 source and top_score 0.35-0.5 → escalates to standard
- Query with no good matches → escalates to full
- Explicit `detail="full"` → always returns full tier
- Summary tier results have title + summary + confidence annotation only
- Full tier results include content, alpha/beta, provenance, co-occurrence

---

## A2. Budget-aware context assembly

### What

Explicit token budget allocation per knowledge scope prevents any single scope from dominating the agent's context window.

### Where

`engine/runner.py` — restructure the context assembly in `_handle_memory_search()` and the broader agent context injection path.

### Implementation

```python
# Token budget allocation
SCOPE_BUDGETS = {
    "task_knowledge": 0.35,    # Via tiered retrieval
    "observations": 0.20,      # Colony observations from current thread
    "structured_facts": 0.15,  # Domain tags, co-occurrence clusters, metadata
    "round_history": 0.15,     # Compressed summaries from prior rounds
    "scratch_memory": 0.15,    # Colony-local scratch entries
}

def _estimate_tokens(text: str) -> int:
    """1 token per 4 characters (rough estimate, matches NeuroStack)."""
    return len(text) // 4

def _budget_aware_assembly(
    total_budget: int,
    task_results: list[dict[str, Any]],
    observations: list[str],
    structured_facts: list[str],
    round_history: list[str],
    scratch: list[str],
) -> dict[str, str]:
    """Assemble context with per-scope token budgets. Early-exit when exhausted."""
    assembled = {}
    for scope_name, items in [
        ("task_knowledge", [_format_result(r) for r in task_results]),
        ("observations", observations),
        ("structured_facts", structured_facts),
        ("round_history", round_history),
        ("scratch_memory", scratch),
    ]:
        budget = int(total_budget * SCOPE_BUDGETS[scope_name])
        used = 0
        scope_items = []
        for item in items:
            tokens = _estimate_tokens(item)
            if used + tokens > budget:
                break  # Early-exit: tier budget exhausted
            scope_items.append(item)
            used += tokens
        assembled[scope_name] = "\n".join(scope_items)
    return assembled
```

Wire this into the agent context injection. The total_budget comes from the colony's configured max context window minus the system prompt and tool definitions.

### Tests

- 4000-token budget → no scope exceeds its 35% allocation
- Task knowledge with 10 results at ~200 tokens each → early-exit after ~7 (35% of 4000 = 1400 tokens)
- Empty scope → 0 tokens used, no error
- All scopes combined fit within total budget

---

## A3. Co-occurrence scoring activation (ADR-044)

### What

Activate co-occurrence as the 6th signal in `_composite_key()`. Follow ADR-044 exactly.

### Where

`surface/knowledge_catalog.py` — modify `_composite_key()` at line 130. Add sigmoid normalization helper. Update `surface/knowledge_constants.py`.

### Implementation

**In knowledge_constants.py** — add `COMPOSITE_WEIGHTS` (replace the inline constants in `_composite_key`):
```python
COMPOSITE_WEIGHTS: dict[str, float] = {
    "semantic": 0.38,
    "thompson": 0.25,
    "freshness": 0.15,
    "status": 0.10,
    "thread": 0.07,
    "cooccurrence": 0.05,
}
```

**In knowledge_catalog.py** — sigmoid normalization:
```python
import math

def _sigmoid_cooccurrence(raw_weight: float) -> float:
    """Normalize co-occurrence weight to [0, 1]. ADR-044 D1."""
    if raw_weight <= 0.0:
        return 0.0
    return 1.0 - math.exp(-0.6 * raw_weight)
```

**Modify `_composite_key()`** (line 130):

The function currently takes `item: dict[str, Any]` and returns a float. It needs access to co-occurrence weights and the other result IDs. Two options:

**Option A (closure):** Make `_composite_key` a closure that captures the projection store and the current result set. The sort call at line 365 (`merged.sort(key=_composite_key)`) becomes:
```python
# Before sorting, compute co-occurrence scores for all results
cooccurrence_scores = {}
result_ids = [r.get("id", "") for r in merged]
for r in merged:
    rid = r.get("id", "")
    other_ids = [oid for oid in result_ids if oid != rid]
    cooccurrence_scores[rid] = _cooccurrence_score(rid, other_ids, self._projections)

def _keyfn(item: dict[str, Any]) -> float:
    rid = item.get("id", "")
    cooc = cooccurrence_scores.get(rid, 0.0)
    return -( W["semantic"] * semantic
            + W["thompson"] * thompson
            + W["freshness"] * freshness
            + W["status"] * status_bonus
            + W["thread"] * thread_bonus
            + W["cooccurrence"] * cooc)

merged.sort(key=_keyfn)
```

Where `W = COMPOSITE_WEIGHTS` from knowledge_constants.

**Co-occurrence score helper:**
```python
def _cooccurrence_score(entry_id: str, other_ids: list[str], projections: Any) -> float:
    """Max sigmoid-normalized co-occurrence weight with any other result."""
    from formicos.surface.projections import cooccurrence_key
    max_weight = 0.0
    for other_id in other_ids:
        key = cooccurrence_key(entry_id, other_id)
        entry = projections.cooccurrence_weights.get(key)
        if entry:
            max_weight = max(max_weight, entry.weight)
    return _sigmoid_cooccurrence(max_weight)
```

### Tests (6 invariants from ADR-044)

1. Equal semantic + freshness → verified outranks stale (status 0.10 dominates)
2. Equal everything → thread-matched outranks non-matched (thread 0.07 > cooc 0.05)
3. Thompson produces different rankings on successive calls (thompson 0.25 unchanged)
4. Very old entry (freshness=0) can still rank highly if verified + semantically relevant
5. **NEW:** Co-accessed entries score higher than identical entries without co-occurrence
6. **NEW:** No single cluster takes all top-5 >30% of the time (property-based test with 100 random queries)

Also test sigmoid normalization values:
- raw=0.0 → 0.0
- raw=1.0 → ~0.45
- raw=3.0 → ~0.83
- raw=5.0 → ~0.95
- raw=10.0 → ~1.0

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass. Layer check: `knowledge_constants.py` is in surface (fine for surface-layer consumers). `_composite_key()` in knowledge_catalog.py reads from the module constant (fine). No core→surface imports.
