# Wave 59: Knowledge Curation — From Append-Only to Curating Archivist

**Date**: 2026-03-22 (revised 2026-03-23)
**Status**: Complete — all 3 code tracks landed, Phase 1 v1 running
**Depends on**: Wave 58.5 (gate validated, domain boundaries enforced)
**Validates with**: Phase 1 eval (same-domain task sequences)

---

## Thesis

The knowledge pipeline was append-only. Every extraction call produced new
entries. Over N tasks, the store grew linearly with no refinement, no
consolidation, and no quality improvement. v11 proved that richer extraction
(Gemini archivist) makes this worse — more entries = more contamination.

Wave 59 transforms extraction from "produce new entries" to "improve the
knowledge store." The archivist sees what already exists before deciding what
to create. It can CREATE new entries, REFINE existing ones, MERGE duplicates,
or NOOP when the store already covers the colony's output. The knowledge
store gets better over time instead of just bigger.

### Empirical motivation

The research literature is unambiguous: **unrefined memory accumulation
degrades agent performance below a no-memory baseline** (Xiong et al.,
arXiv:2505.16067). Agents exhibit experience-following — when task input is
similar to a stored memory, output converges to the stored output. One bad
entry propagates errors to all semantically similar future tasks. Only
selective addition with quality criteria enables self-improvement.

Mem0's production pipeline confirms the pattern: for each candidate fact,
retrieve the top-10 similar existing memories, present them to an LLM, and
classify as ADD/UPDATE/DELETE/NOOP. No hardcoded similarity threshold — the
LLM decides whether existing coverage is sufficient.

### v12 context: relevance is the bottleneck, not quality

v12 showed that the 0.50 similarity threshold blocks all cross-domain
knowledge injection in Phase 0's diverse task set. 31 Gemini-extracted
entries, zero injected. The bottleneck is not entry quality — it's entry
relevance. Curation matters most in same-domain task sequences where entries
accumulate over hours/days and the pool fills with redundant, slightly
different versions of the same knowledge. This is the production scenario.

---

## Track 1: ADR-048 — MemoryEntryRefined Event

**Type**: Event extension (requires operator approval per hard constraint #5)
**Result**: 65th event type added, replay-safe, Qdrant sync wired

### Why a new event

The knowledge store had two mutation events: `MemoryEntryCreated` (new entry)
and `MemoryEntryMerged` (two entries combined). Neither supports in-place
content improvement of a single entry. `MemoryEntryStatusChanged` doesn't
carry content fields. Direct projection mutation violates event-sourcing (hard
constraint #7). Self-merge via `MemoryEntryMerged` breaks the projection
handler (source gets marked rejected) and is semantically wrong.

### Event definition (`core/events.py:1306-1333`)

```python
class MemoryEntryRefined(EventEnvelope):
    type: Literal["MemoryEntryRefined"] = "MemoryEntryRefined"
    entry_id: str          # Entry being refined
    workspace_id: str
    old_content: str       # Audit trail
    new_content: str       # Improved content
    new_title: str = ""    # Empty = keep existing
    refinement_source: Literal["extraction", "maintenance", "operator"]
    source_colony_id: str = ""  # Empty for maintenance-triggered
```

`old_content` provides an audit trail — the previous content is preserved in
the event stream. `refinement_source` distinguishes extraction-triggered
refinements (a colony just completed), maintenance-triggered (periodic curation
handler), and operator-triggered (future manual refinement).

### Projection handler (`surface/projections.py`)

Updates `content`, optionally `title`, increments `refinement_count`, and
stamps `last_refined_at`. The handler reads from `store.memory_entries`
(populated by `MemoryEntryCreated`) and modifies in place.

### Qdrant sync (`surface/runtime.py`)

`MemoryEntryRefined` is added to the sync block in `emit_and_broadcast()`.
The existing `memory_store.sync_entry()` does full re-embed on upsert —
content change triggers re-embedding automatically.

### merge_source widening

`MemoryEntryMerged.merge_source` widened from `Literal["dedup", "federation"]`
to `Literal["dedup", "federation", "extraction"]`. This is a type widening
(additive). Existing events parse correctly. The archivist can now trigger
merges during extraction alongside the existing dedup and federation paths.

---

## Track 2: Curating Extraction Prompt

**Type**: Code (surface/memory_extractor.py, surface/colony_manager.py)
**Result**: Extraction enriched with existing-entry context and action dispatch

### Architecture

The extraction pipeline already ran as fire-and-forget `asyncio.create_task()`
in `colony_manager._hook_memory_extraction()`. The curating prompt enriches
this existing call — it does not add a second LLM call.

```
extract_institutional_memory()
  |
  +-- fetch top-10 existing entries via knowledge_catalog.search(query=task)
  +-- enrich each with access_count from knowledge_entry_usage
  |
  +-- build_extraction_prompt(..., existing_entries)
  |   Now includes: EXISTING ENTRIES section with id, title, confidence,
  |   access_count, content[:200]
  |
  +-- llm_router.complete(archivist model)  [unchanged]
  |
  +-- parse_extraction_response()
  |   New format: {"actions": [{"type": "CREATE|REFINE|MERGE|NOOP", ...}]}
  |   Fallback: if old format detected, wrap each entry as CREATE action
  |
  +-- Per action:
      +-- CREATE -> existing pipeline (quality check -> dedup -> scan -> emit)
      +-- REFINE -> emit MemoryEntryRefined(entry_id, new_content)
      +-- MERGE  -> emit MemoryEntryMerged(target_id, source_id, merged_content)
      +-- NOOP   -> log and skip
```

### Curating prompt design

When `existing_entries` are provided and `colony_status == "completed"`, the
extraction prompt includes an EXISTING ENTRIES section showing the top-10
most relevant entries with their IDs, titles, confidence scores, access
counts, and truncated content (first 200 chars).

The LLM is instructed to decide CREATE, REFINE, MERGE, or NOOP for each
piece of knowledge. The prompt emphasizes conservatism:

> Be conservative. REFINE only when the colony produced genuinely new
> information that makes an existing entry more precise, more actionable,
> or corrects an error. NOOP is the right choice when existing coverage
> is adequate.

When no existing entries are available (first colony in a workspace, catalog
not initialized), the prompt falls back to the legacy format
(`{"skills": [...], "experiences": [...]}`). The parser detects format by
checking for the `"actions"` key and normalizes accordingly.

### REFINE quality gate

Before emitting `MemoryEntryRefined`, three deterministic checks:

1. **Entry exists**: `entry_id` resolves in `projections.memory_entries`
2. **Content changed**: `new_content != old_content`
3. **Content non-empty**: `len(new_content.strip()) >= 20`

These prevent no-op refinements and blank rewrites without requiring an
embedding computation at refinement time.

### Non-deterministic curation context

`knowledge_catalog.search()` uses Thompson Sampling. In production, the
archivist sees a partially stochastic set of existing entries — different
runs may surface different entries. This is acceptable (diversity in curation
context is desirable) but means curation results are non-reproducible.
For eval measurement, `FORMICOS_DETERMINISTIC_SCORING=1` makes the curation
context reproducible.

### Timing subtlety

Extraction fires AFTER `_post_colony_hooks()` emits trajectory and transcript
entries synchronously. The curating archivist sees entries from previous
colonies but NOT the current colony's own trajectory or transcript entries.
This is correct — the archivist should not refine entries it just created in
the same colony.

---

## Track 3: Curation Maintenance Handler

**Type**: Code (surface/maintenance.py, surface/app.py)
**Result**: Periodic archivist review of popular-but-unexamined entries

### Architecture

New `make_curation_handler(runtime)` factory in `maintenance.py`, registered
as `service:consolidation:curation` in `app.py`. Follows the same factory
pattern as `make_dedup_handler()`.

### Candidate selection

The handler selects entries for refinement during the periodic maintenance
cycle (default 24h). Selection criteria:

```
access_count >= 5 AND confidence < 0.65 AND status == "verified"
```

This signal comes from Wave 58.5's popular-but-unexamined proactive rule.
Max 10 candidates per cycle.

### Archivist prompt

All candidates are batched into a single prompt asking the archivist to
decide REFINE or NOOP for each entry. The prompt instructs conservatism:

> Be conservative. Only refine when you can make the entry genuinely better.
> Do not add speculative information. Do not generalize away specific details.

The handler only dispatches REFINE actions (emitting `MemoryEntryRefined`
with `refinement_source="maintenance"`). MERGE is intentionally excluded
from the initial implementation. CREATE is not available — the maintenance
handler does not produce new entries. Unexpected action types are logged
and silently skipped.

### Model routing

The handler uses `runtime.resolve_model("archivist", workspace_id)` for
proper fallback chain support. This differs from the dedup handler's
hardcoded `"gemini/gemini-2.5-flash"` — the curation handler respects
workspace-level model configuration.

### Rate limiting

- Max 10 entries per maintenance cycle
- Max 1 archivist LLM call per cycle (all candidates batched)
- Respects `daily_maintenance_budget` from autonomy policy

---

## Track 4: Phase 1 Eval Design

**Type**: Eval design (operator + architect)
**Status**: Phase 1 v1 Arm 1 complete, Arm 2 pending

### Why Phase 0 cannot validate curation

Phase 0 uses 8 diverse tasks (email-validator, rate-limiter, haiku-writer,
etc.). v12 proved that entries have < 0.50 cosine similarity between tasks.
The 0.50 threshold correctly blocks all cross-domain injection. Running
Phase 0 with the curating archivist would produce delta near zero — curation
infrastructure would run at extraction time but its output would never be
tested by retrieval. Phase 0 is retired as a compounding measurement tool.

### Phase 1: same-domain task sequences

Phase 1 tests what Phase 0 cannot: does accumulated same-domain knowledge
improve downstream task quality?

**Task suite**: 8 tasks in a data-pipeline domain, executed sequentially:
csv-reader, data-validator, data-transformer, pipeline-orchestrator,
error-reporter, performance-profiler, schema-evolution, pipeline-cli.

Later tasks reference earlier tasks' artifacts and use project-specific
language to fire the specificity gate. Entries from task T1 have > 0.50
similarity to T2's goal (intra-domain).

### Phase 1 v1 Arm 1 results

| Task | Position | Quality | Wall | Extracted | Accessed | Pool |
|------|----------|---------|------|-----------|----------|------|
| csv-reader | 1 | 0.612 | 135s | 3 | 0 | 0 |
| data-validator | 2 | 0.580 | 226s | 2 | 3 | 3 |
| data-transformer | 3 | 0.592 | 408s | 3 | 2 | 5 |
| pipeline-orchestrator | 4 | 0.574 | 312s | 3 | 2 | 8 |
| error-reporter | 5 | 0.571 | 276s | 4 | 4 | 11 |
| performance-profiler | 6 | 0.499 | 757s | 12 | 3 | 15 |
| schema-evolution | 7 | 0.524 | 961s | 4 | 3 | 27 |
| pipeline-cli | 8 | 0.587 | 966s | 7 | 2 | 31 |

**Mean quality**: 0.567. **Total entries**: 38. **Total accessed**: 19.
**Tasks with entries accessed**: 7/8 (all except T1 cold start).

### The defining signal

Phase 0 (12 runs): 0 entries crossed 0.50 threshold between tasks.
Phase 1 v1 Arm 1: 19 entries crossed 0.50, accessed across 7 tasks.

Same-domain entries DO cross the similarity threshold. The knowledge pipeline
is active for the first time in any eval run. This validates the pipeline
architecture — the bottleneck was always task diversity, not pipeline defects.

### Pending measurement

Arm 2 (empty baseline) required to compute the accumulate vs empty delta.
v2 (curating archivist) required to compare curation vs append-only.
Both pending due to API token exhaustion during v1 Arm 1.

### Success criteria

- Positive accumulate delta: accumulate mean > empty mean by >= 0.03
- Knowledge injection: >= 3 tasks receive injected entries
- REFINE actions in v2: >= 3 across the sequence
- Entry count v2 < v1: curation reduces total entries vs append-only
- No quality regression: v2 accumulate >= v1 accumulate

---

## Implementation Summary

**Total code delta**: ~160 lines across 6 files.

| File | Lines | Purpose |
|------|-------|---------|
| `core/events.py` | ~20 | MemoryEntryRefined class, merge_source widening |
| `surface/projections.py` | ~15 | Refinement projection handler |
| `surface/runtime.py` | ~3 | Qdrant sync case |
| `surface/memory_extractor.py` | ~50 | Curating prompt + action parser |
| `surface/colony_manager.py` | ~30 | Fetch existing entries, dispatch actions |
| `surface/maintenance.py` | ~40 | Curation maintenance handler |

Plus: `docs/decisions/048-memory-entry-refined.md` (ADR),
`frontend/src/types.ts` (event name registration).

---

## What This Wave Did NOT Do

- **Run Phase 0 v13** — Phase 0 cannot measure curation value. Phase 1 is
  the correct measurement instrument.
- **Tune the 0.50 similarity threshold** — correctly calibrated for
  cross-domain protection. Within-domain calibration is a Phase 1 question.
- **Add semantic preservation gate on REFINE** — cosine > 0.75 between old
  and new embeddings would guard against drift, but requires embedding
  computation at refinement time. Defer to Wave 60 after Phase 1 data.
- **Add SPLIT operation** — decomposing compound entries into atomic facts.
  No production system implements this.
- **Add LINK operation** — typed relationships between entries. Requires
  graph data model beyond current vector store.
- **Change retrieval scoring weights** — ADR-044 composite unchanged.
- **Add Git-like versioning for entries** — `old_content` in
  MemoryEntryRefined provides audit trail. Full version history is
  over-engineering at current scale.

---

## Research Context

Three production patterns informed this wave's design:

1. **Mem0's LLM-as-classifier**: Retrieve top-10 similar existing entries,
   present to LLM, classify as ADD/UPDATE/DELETE/NOOP. Updates are full
   content rewrites with old content preserved for audit.

2. **Letta's sleep-time separation**: Curation runs asynchronously, separate
   from agent conversation. The archivist can use a stronger model without
   affecting agent execution latency.

3. **AGM belief revision**: The REFINE operation maps to AGM revision (add
   new belief while maintaining consistency). The minimal change principle
   guards against over-revision.

The experience-following finding (Xiong et al.) is the strongest empirical
motivation: add-all performs worse than no memory. The curating archivist
transforms add-all into selective-add-with-refinement, which is the only
strategy shown to enable long-term agent improvement.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/events.py:1306-1333` | MemoryEntryRefined event definition |
| `surface/projections.py` | Refinement handler + HANDLER_MAP registration |
| `surface/runtime.py` | Qdrant sync for refinements |
| `surface/memory_extractor.py:88-148` | Curating extraction prompt |
| `surface/colony_manager.py:1936-2099` | Extraction orchestration + action dispatch |
| `surface/maintenance.py:579-731` | Curation maintenance handler |
| `surface/app.py:609` | Handler registration |
| `docs/decisions/048-memory-entry-refined.md` | ADR for 65th event type |

---

## Related Documents

- [dispatch_prompts.md](dispatch_prompts.md) — original coder dispatch prompts
  (preserved as implementation reference)
- [docs/specs/knowledge_system.md](../../specs/knowledge_system.md) —
  knowledge system spec covering refinement lifecycle
- [docs/specs/extraction_pipeline.md](../../specs/extraction_pipeline.md) —
  extraction spec covering curating prompt and action dispatch
- [docs/specs/proactive_intelligence.md](../../specs/proactive_intelligence.md) —
  proactive intelligence spec covering popular-unexamined rule (Wave 58.5
  Track 4, consumed by Wave 59 Track 3)
