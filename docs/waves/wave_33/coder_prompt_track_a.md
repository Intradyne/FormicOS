# Wave 33 Track A — Knowledge Pipeline Intelligence

## Role

You are a coder implementing 5 features in the FormicOS knowledge pipeline. All changes are internal to the knowledge extraction, retrieval, and maintenance subsystems. You do NOT touch API surfaces, CRDT types, or federation code.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/041-knowledge-tuning.md` (approved) and `docs/decisions/043-cooccurrence-data-model.md` (approved) before writing code.
- Read `docs/contracts/events.py` to understand the event union. You do NOT add events — Track C owns event additions.
- The composite scoring weights do NOT change. ADR-041 D3 values (0.40/0.25/0.15/0.12/0.08) remain unchanged.

## File ownership

You OWN these files (create or modify freely):

| File | Status | Changes |
|------|--------|---------|
| `surface/colony_manager.py` | MODIFY | Hook position 4.5, inline dedup, co-occurrence reinforcement, max_elapsed_days cap |
| `surface/memory_extractor.py` | MODIFY | `build_harvest_prompt()`, `parse_harvest_response()`, decay_class in extraction prompt |
| `surface/knowledge_catalog.py` | MODIFY | Prediction error detection, query-result co-occurrence reinforcement |
| `surface/maintenance.py` | MODIFY | Prediction error in stale_sweep, co-occurrence decay pass |
| `surface/projections.py` | MODIFY | CooccurrenceEntry, cooccurrence_weights, harvest tracking suffix |
| `surface/knowledge_constants.py` | MODIFY | GAMMA_RATES dict, MAX_ELAPSED_DAYS |
| `surface/queen_thread.py` | MODIFY | max_elapsed_days cap in archival decay |
| `core/types.py` | MODIFY | DecayClass StrEnum, decay_class field on MemoryEntry |
| `surface/app.py` | MODIFY | Register cooccurrence_decay handler *(shared with Track B — see overlap rules)* |
| `tests/unit/surface/test_transcript_harvest.py` | CREATE | Transcript harvest tests |
| `tests/unit/surface/test_inline_dedup.py` | CREATE | Inline dedup tests |
| `tests/unit/surface/test_prediction_errors.py` | CREATE | Prediction error counter tests |
| `tests/unit/surface/test_cooccurrence.py` | CREATE | Co-occurrence collection tests |
| `tests/unit/core/test_decay_class.py` | CREATE | DecayClass + gamma hardening tests |

## DO NOT TOUCH

- `surface/mcp_server.py` — Track B owns
- `surface/structured_error.py` — Track B owns
- `surface/memory_scanner.py` — Track B owns (credential scanning)
- `core/events.py` — Track C owns (new event types)
- `docs/contracts/events.py` — Track C owns
- `surface/trust.py` — Track C owns
- `surface/federation.py` — Track C owns
- `core/crdt.py` — Track C owns
- Any file in `surface/routes/` — Track B owns
- Any file in `adapters/` — Track C owns

## Overlap rules

- `surface/app.py`: You register `cooccurrence_decay` handler (A5). Track B registers `credential_sweep` handler (B3). Both are `service_router.register_handler()` calls in the handler registration block (lines 519-534). Add yours AFTER the existing handlers. No conflict — different handler names and different service types.
- `surface/maintenance.py`: You add `make_cooccurrence_decay_handler()` (new function) + prediction error criteria to `_handle_stale()` (line 204). Track B adds `make_credential_sweep_handler()` (new function). Track C modifies `_handle_dedup()` (line 25, replacing `MemoryEntryStatusChanged` emission with `MemoryEntryMerged`). All three touch different functions — no conflict, but verify after integration.
- `surface/projections.py`: You add CooccurrenceEntry + harvest tracking. Track C adds CRDT state handlers. Different projection fields — no conflict.
- `core/types.py`: You add DecayClass StrEnum + decay_class on MemoryEntry. Track C adds ProvenanceChain + CRDT-related types. Different classes — no conflict.

---

## A1. Transcript harvest at hook position 4.5

### What

A second extraction pass on the full colony transcript that catches bug root causes, operator conventions, and tool configurations the compressed summary misses.

### Where

**Hook dispatcher** at `colony_manager.py:649` (`_post_colony_hooks`). Current hook order:
```
Line 666: _hook_observation_log()
Line 670: _hook_step_detection()
Line 671: _hook_follow_up()
Line 672: _hook_memory_extraction()     ← position 4
Line 673: _hook_confidence_update()     ← position 5
Line 674: _hook_step_completion()
```

Add `_hook_transcript_harvest()` between lines 672 and 673 (position 4.5). This is a SEPARATE hook from `_hook_memory_extraction` — different failure modes, different contract.

### Implementation

```python
async def _hook_transcript_harvest(
    self,
    colony_id: str,
    workspace_id: str,
    colony_proj: ColonyProjection,
    succeeded: bool,
) -> None:
```

**Data source:** `colony_proj.chat_messages` (structured list of dicts with agent_id, caste, content, event_kind, tool calls). NOT `build_transcript()` (formatted text for display).

**Flow:**
1. Check `memory_extractions_completed` for `"{colony_id}:harvest"` — skip if already harvested (replay safety)
2. Filter chat_messages to agent turns only (skip system/operator messages)
3. Build harvest prompt via `build_harvest_prompt(turns)` in `memory_extractor.py`
4. Call LLM (same model as extraction) with the harvest prompt
5. Parse response via `parse_harvest_response(text)` — returns list of `{type, summary, agent_id, round_number}`
6. For each KEEP result: check embedding cosine similarity against Qdrant institutional_memory collection. Skip if >= 0.82 similarity to any existing entry
7. Emit `MemoryEntryCreated` for each passing entry with `entry_type` based on harvest classification (bug→experience, decision→experience, convention→skill, learning→experience)
8. Emit `MemoryExtractionCompleted` with colony_id and entries_created count
9. Add `"{colony_id}:harvest"` to `memory_extractions_completed`

**In memory_extractor.py** — add two new functions (do NOT modify existing `build_extraction_prompt` or `build_memory_entries`):

```python
def build_harvest_prompt(turns: list[dict[str, Any]]) -> str:
    """Build LLM prompt for transcript harvest classification."""
    # Number each turn. Include agent_id, caste, round_number per turn.
    # Ask LLM to classify each as KEEP (with type: bug/decision/convention/learning
    # and one-sentence summary) or SKIP.
    # No regex pre-filter — LLM classifies all turns.

def parse_harvest_response(text: str) -> list[dict[str, Any]]:
    """Parse harvest LLM response into classified entries."""
    # Returns list of {turn_index, type, summary, agent_id, round_number}
    # Use json_repair for robustness (already a dependency)
```

**In projections.py** — extend the `_on_memory_extraction_completed` handler (near line 727) to recognize the `:harvest` suffix on colony_id tracking:
```python
# Existing: memory_extractions_completed.add(colony_id)
# New: also handle "{colony_id}:harvest" for harvest-specific tracking
```

### Tests

- Colony with tool-call failure + fix sequence → harvest extracts bug-type entry
- Colony with operator correction in chat → harvest extracts convention-type entry
- Already-harvested colony (`:harvest` suffix in set) → skips
- Harvest entry with >= 0.82 similarity to existing → skipped (not emitted)
- Empty transcript → no entries, no error

---

## A2. Inline dedup check at extraction time

### What

Before emitting `MemoryEntryCreated`, check the current projection for entries with cosine similarity > 0.92. If found, reinforce the existing entry's confidence instead of creating a duplicate.

### Where

`colony_manager.py` — in the extraction flow at `_hook_memory_extraction` (line 772). The current flow calls `extract_institutional_memory()` which eventually emits events. The inline dedup check goes INSIDE the extraction pipeline, after `build_memory_entries()` constructs entry dicts but BEFORE the security scan and event emission.

### Implementation

Add a helper function in `colony_manager.py`:

```python
async def _check_inline_dedup(
    self,
    entry_content: str,
    workspace_id: str,
    succeeded: bool,
) -> str | None:
    """Check if a near-duplicate exists. Returns existing entry_id or None."""
    # Compare entry_content embedding against projection memory_entries
    # Use the same embedding function as the Qdrant adapter
    # Threshold: cosine > 0.92 (auto-merge threshold from maintenance handler)
    # If match found: emit MemoryConfidenceUpdated for the existing entry
    # (reinforce its confidence based on colony outcome)
    # Return the existing entry_id (caller skips this entry)
```

Wire this into the extraction flow. For each entry produced by `build_memory_entries()`, call `_check_inline_dedup()`. If it returns an entry_id, log the dedup and skip. Otherwise proceed with scan + emit.

### Tests

- Two entries with cosine > 0.92 → second one skipped, first one's confidence reinforced
- Two entries with cosine < 0.92 → both emitted normally
- Empty projection → all entries emitted

---

## A3. Prediction error counters

### What

When top search results have low semantic similarity to the query, increment a prediction_error_count on those entries in the projection. Feed this into stale_sweep.

### Where

`knowledge_catalog.py` — in `_search_thread_boosted()` (line 300), after the composite sort at line 365.

### Implementation

After the sort, check only the top-k results (same top_k as the function parameter). For each result, check the RAW semantic score (the `score` field from Qdrant, before composite weighting). If raw semantic < 0.38:

```python
# In _search_thread_boosted(), after merged.sort(key=_composite_key) at line 365:
for item in merged[:top_k]:
    raw_semantic = item.get("score", 0.0)  # Qdrant cosine score
    if raw_semantic < 0.38:
        entry_id = item.get("id", "")
        if entry_id and entry_id in self._projections.memory_entries:
            proj = self._projections.memory_entries[entry_id]
            proj["prediction_error_count"] = proj.get("prediction_error_count", 0) + 1
            proj["last_prediction_error_at"] = datetime.utcnow().isoformat()
            errors = proj.get("prediction_error_queries", [])
            errors.append(query[:200])
            proj["prediction_error_queries"] = errors[-3:]  # keep last 3
```

This is fire-and-forget on the projection. No events emitted. Lossy on replay (rebuilt from zero). Non-blocking — never raises.

**In maintenance.py** — add prediction_error_count to `_handle_stale()` (line 204) criteria. Currently uses age > 90 days + not in accessed_ids. Add:

```python
# Additional staleness signal: high prediction error count with low access
prediction_errors = entry.get("prediction_error_count", 0)
if prediction_errors >= 5 and access_count < 3:
    # Strong staleness signal — entry keeps appearing in results but
    # with low semantic relevance. Drifting out of relevance.
    stale_candidates.append(entry_id)
```

### Tests

- Search returns result with raw semantic < 0.38 → prediction_error_count incremented
- Search returns result with raw semantic >= 0.38 → no increment
- prediction_error_queries capped at 3 entries
- Entry with prediction_error_count >= 5 and access_count < 3 → included in stale candidates

---

## A4. Gamma-decay hardening

### What

Two changes: cap max_elapsed_days at 180, and add DecayClass to MemoryEntry.

### Part 1: MAX_ELAPSED_DAYS cap

**In knowledge_constants.py** (line 6 area):
```python
MAX_ELAPSED_DAYS: float = 180.0
```

**In colony_manager.py** — `_hook_confidence_update()` (line 789). Find where elapsed_days is computed and add the cap:
```python
elapsed_days = min((event_ts - last_update) / 86400.0, MAX_ELAPSED_DAYS)
```

**In queen_thread.py** — archival decay (line 137-167). The archival gamma-burst uses `ARCHIVAL_EQUIVALENT_DAYS` which is already 30, well under 180. But add defensive cap for any future changes:
```python
archival_days = min(ARCHIVAL_EQUIVALENT_DAYS, MAX_ELAPSED_DAYS)
```

### Part 2: DecayClass StrEnum

**In core/types.py** — add near the other StrEnums (around line 296-330):
```python
class DecayClass(StrEnum):
    ephemeral = "ephemeral"    # gamma=0.98, half-life ~34 days
    stable = "stable"          # gamma=0.995, half-life ~139 days
    permanent = "permanent"    # gamma=1.0, no decay
```

**In core/types.py** — add field to MemoryEntry (line 331+):
```python
decay_class: DecayClass = Field(
    default=DecayClass.ephemeral,
    description="Decay rate class. Ephemeral (default) = standard gamma. Stable = 4x slower. Permanent = no decay.",
)
```

**In knowledge_constants.py** — add decay rates dict:
```python
GAMMA_RATES: dict[str, float] = {
    "ephemeral": 0.98,    # half-life ~34 days (default, current behavior)
    "stable": 0.995,      # half-life ~139 days (domain knowledge)
    "permanent": 1.0,     # no decay (verified definitions)
}
```

**In colony_manager.py** — `_hook_confidence_update()`: look up decay_class from the entry and use `GAMMA_RATES[decay_class]` instead of `GAMMA_PER_DAY`:
```python
decay_class = entry.get("decay_class", "ephemeral")
gamma = GAMMA_RATES.get(decay_class, GAMMA_PER_DAY)
gamma_eff = gamma ** elapsed_days
```

**In memory_extractor.py** — add decay_class instruction to `build_extraction_prompt()` (line 29):
```
Add to the prompt: "For each entry, classify decay_class:
- ephemeral: task-specific observations, temporary workarounds
- stable: domain knowledge, established patterns, architectural decisions
- permanent: verified definitions, mathematical facts, immutable truths
Default to ephemeral if uncertain."
```

### Tests

- Entry not observed for 180 days → alpha capped (at alpha=500: `0.98^180 * 500 + (1-0.98^180) * 5 ≈ 18.04`)
- Entry not observed for 365 days → same result as 180 (cap applied)
- decay_class="permanent" → gamma_eff=1.0, no decay applied
- decay_class="stable" → gamma_eff = 0.995^elapsed, slower decay
- Default decay_class is "ephemeral"
- Extraction prompt includes decay_class instruction

---

## A5. Co-occurrence data collection (NO scoring integration)

### What

Build the co-occurrence reinforcement + decay infrastructure. Data collection only — the composite scoring formula does NOT change. See ADR-043.

### Implementation

**In projections.py** — add data structure (near line 249, alongside other projection state):
```python
@dataclass
class CooccurrenceEntry:
    weight: float = 1.0
    last_reinforced: str = ""
    reinforcement_count: int = 0

# In ProjectionStore.__init__:
self.cooccurrence_weights: dict[tuple[str, str], CooccurrenceEntry] = {}
```

Canonical pair ordering helper:
```python
def _cooccurrence_key(id_a: str, id_b: str) -> tuple[str, str]:
    return (min(id_a, id_b), max(id_a, id_b))
```

**In colony_manager.py** — result-result reinforcement in `_hook_confidence_update()` (line 789), after the per-entry confidence update loop:

```python
# After updating individual entry confidences:
if succeeded:
    accessed_ids = list(retrieved_skill_ids)
    now_iso = datetime.utcnow().isoformat()
    for i, id_a in enumerate(accessed_ids):
        for id_b in accessed_ids[i + 1:]:
            key = _cooccurrence_key(id_a, id_b)
            entry = self._projections.cooccurrence_weights.get(key)
            if entry is None:
                entry = CooccurrenceEntry(weight=1.0, last_reinforced=now_iso, reinforcement_count=1)
            else:
                entry.weight = min(entry.weight * 1.1, 10.0)
                entry.last_reinforced = now_iso
                entry.reinforcement_count += 1
            self._projections.cooccurrence_weights[key] = entry
```

**In knowledge_catalog.py** — query-result reinforcement in `_search_thread_boosted()` (line 300), after the sort at line 365. Fire-and-forget:

```python
# After ranking, reinforce query-result co-occurrence at 0.5x weight
try:
    result_ids = [item["id"] for item in merged[:top_k] if "id" in item]
    now_iso = datetime.utcnow().isoformat()
    for i, id_a in enumerate(result_ids):
        for id_b in result_ids[i + 1:]:
            key = _cooccurrence_key(id_a, id_b)
            entry = self._projections.cooccurrence_weights.get(key)
            if entry is None:
                entry = CooccurrenceEntry(weight=0.5, last_reinforced=now_iso, reinforcement_count=1)
            else:
                entry.weight = min(entry.weight * 1.05, 10.0)  # 0.5x rate
                entry.last_reinforced = now_iso
                entry.reinforcement_count += 1
            self._projections.cooccurrence_weights[key] = entry
except Exception:
    pass  # Never block search for co-occurrence bookkeeping
```

**In maintenance.py** — co-occurrence decay pass (new function, register alongside stale_sweep):

```python
COOCCURRENCE_GAMMA_PER_DAY = 0.995  # half-life ~138 days
COOCCURRENCE_PRUNE_THRESHOLD = 0.1

def make_cooccurrence_decay_handler(runtime: Runtime):
    async def _handle_cooccurrence_decay(query_text: str, ctx: dict[str, Any]) -> str:
        now = datetime.utcnow()
        pruned = 0
        decayed = 0
        to_prune = []
        for key, entry in runtime.projections.cooccurrence_weights.items():
            last = datetime.fromisoformat(entry.last_reinforced)
            elapsed_days = (now - last).total_seconds() / 86400.0
            gamma_eff = COOCCURRENCE_GAMMA_PER_DAY ** elapsed_days
            entry.weight *= gamma_eff
            entry.last_reinforced = now.isoformat()
            decayed += 1
            if entry.weight < COOCCURRENCE_PRUNE_THRESHOLD:
                to_prune.append(key)
        for key in to_prune:
            del runtime.projections.cooccurrence_weights[key]
            pruned += 1
        return f"Decayed {decayed} co-occurrence pairs, pruned {pruned}"
    return _handle_cooccurrence_decay
```

Register in `app.py` (line 519-534 area) alongside the other maintenance handlers. Use service name `"service:consolidation:cooccurrence_decay"`.

### Tests

- Successful colony with 3 accessed entries → 3 co-occurrence pairs reinforced (3 choose 2)
- Failed colony → no reinforcement
- Weight capped at 10.0
- Canonical pair ordering: (B, A) == (A, B)
- Decay pass: weight drops by gamma^elapsed_days
- Pairs below 0.1 after decay → pruned from dict
- Query-result reinforcement uses 0.5x rate (1.05 multiplier vs 1.1)

---

## Validation

Run after all changes:
```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass. The layer check is critical — `core/types.py` must not import from surface or engine. `DecayClass` is a StrEnum in core, `GAMMA_RATES` is in surface (knowledge_constants.py).
