# Knowledge Curation Audit: Entry Lifecycle Seams

**Date**: 2026-03-22
**Context**: Wave 58 landed specificity gate, trajectory storage, progressive
disclosure, and asymmetric extraction. This audit maps every seam where an
existing knowledge entry can be modified, and identifies what's missing for a
curating archivist that can refine entries, not just create new ones.

> **STATUS (2026-03-23):** All 5 recommendations from this audit have been
> implemented in Wave 59. See `docs/specs/extraction_pipeline.md` for the
> current-state reference.
>
> - **R1 (MemoryEntryMerged Qdrant sync):** ✅ IMPLEMENTED
> - **R2 (MemoryEntryRefined event):** ✅ IMPLEMENTED — event #65
> - **R3 (Curating extraction prompt):** ✅ IMPLEMENTED — `build_extraction_prompt()`
>   now accepts `existing_entries` and returns CREATE/REFINE/MERGE/NOOP actions
> - **R4 (Popular unexamined proactive rule):** ✅ IMPLEMENTED — Rule 17 in
>   `proactive_intelligence.py` (Wave 58.5)
> - **R5 (make_curation_handler):** ✅ IMPLEMENTED — registered as
>   `service:consolidation:curation` in `maintenance.py`

---

## Section 1: Entry Creation Path

### Annotated pipeline

```
colony_manager._hook_memory_extraction()                    # line 1184
  │
  ├─ colony_proj = self._runtime.projections.get_colony()   # ← CURATION POINT A
  │   Available: colony_proj.task, .summary, .artifacts,
  │   .thread_id, .workspace_id
  │   Could also access: self._runtime.memory_store,
  │   self._runtime.knowledge_catalog
  │
  └─ asyncio.create_task(extract_institutional_memory(...))
      │
      ├─ build_extraction_prompt()                          # memory_extractor.py:88
      │   Inputs: task, final_output[:2000], artifacts[:5],
      │   colony_status, failure_reason, contract_result
      │   Output: ~2K token prompt requesting JSON
      │   ← CURATION POINT B: existing entries could be
      │     injected here as additional context
      │
      ├─ llm_router.complete(archivist model)               # line ~1970
      │   Uses resolve_model("archivist", workspace_id)
      │   Currently: ollama-cloud/qwen3-coder:480b (262K context)
      │
      ├─ parse_extraction_response()                        # memory_extractor.py:218
      │   Returns: {"skills": [...], "experiences": [...]}
      │   ← CURATION POINT C: response format could include
      │     REFINE and MERGE actions alongside CREATE
      │
      ├─ build_memory_entries()                             # memory_extractor.py:147
      │   Constructs MemoryEntry dicts from LLM output
      │   Currently only handles CREATE
      │
      └─ Per entry:
          ├─ _check_extraction_quality()                    # line 226 (conjunctive gate)
          ├─ _check_inline_dedup()                          # line 1850 (cosine > 0.92)
          │   ← CURATION POINT D: instead of just reinforcing
          │     confidence on near-duplicates, could trigger
          │     content refinement
          ├─ scan_entry()                                   # security scan
          ├─ evaluate_entry()                               # admission policy
          ├─ compute_playbook_generation()                  # playbook stamp
          ├─ emit MemoryEntryCreated                        # line ~2030
          └─ emit MemoryEntryStatusChanged → "verified"     # if colony succeeded
```

### Best insertion point for curation context

**Curation Point B** (before `build_extraction_prompt()`) is the cleanest seam.
At this point `extract_institutional_memory()` has access to:
- `self._runtime.knowledge_catalog` — can call `catalog.search(query=task)`
- `self._runtime.projections.memory_entries` — full projection cache
- `self._runtime.memory_store` — can do vector search

A curating prompt would fetch Top-K existing entries relevant to the colony's
task domain, then inject them into the extraction prompt as context. The
archivist would see what already exists before deciding what to create.

### Token budget for existing entries

- Current extraction prompt: ~2K tokens
- Archivist model context: 262K (Ollama Cloud qwen3-coder:480b)
- Each existing entry in summary format: ~80 tokens (title + summary + confidence + domains)
- Each existing entry in full format: ~300 tokens (title + content + metadata)
- **Conservative budget**: 20 entries × 80 tokens = 1,600 tokens (~3.6K total prompt)
- **Rich budget**: 10 entries × 300 tokens = 3,000 tokens (~5K total prompt)
- **Headroom**: 257K tokens remaining — context is not a constraint

---

## Section 2: Entry Update Capabilities

### What exists

| Capability | Mechanism | Modifies content? | Event |
|---|---|---|---|
| Confidence reinforcement | `_check_inline_dedup()` at cosine > 0.92 | No — metadata only | MemoryConfidenceUpdated |
| Quality-aware confidence | Colony outcome in `_post_colony_hooks()` | No — metadata only | MemoryConfidenceUpdated |
| Archival decay | Thread archival in `queen_thread.py` | No — metadata only | MemoryConfidenceUpdated |
| Mastery restoration | 20% gap recovery for stable/permanent | No — metadata only | MemoryConfidenceUpdated |
| Status changes | Stale sweep, credential sweep, admission | No — status only | MemoryEntryStatusChanged |
| Entry merge | Dedup handler at cosine ∈ [0.82, 0.98) | **Yes** — replaces content | MemoryEntryMerged |
| Auto-merge | Dedup handler at cosine ≥ 0.98 | **Yes** — replaces content | MemoryEntryMerged |

### What was missing (all now addressed in Wave 59)

1. ~~**No in-place content refinement.**~~ → ✅ `MemoryEntryRefined` event added.
   Carries `entry_id`, `old_content`, `new_content`, `new_title`,
   `refinement_source`, `source_colony_id`.

2. ~~**No MemoryEntryUpdated event.**~~ → ✅ `MemoryEntryRefined` serves this role.
   7 memory events total (create, status, extraction, scope, confidence, merge, refined).

3. ~~**Qdrant sync gap.**~~ → ✅ `emit_and_broadcast()` now syncs on
   `MemoryEntryMerged` and `MemoryEntryRefined` in addition to created/status.

4. **memory_store.py has no partial update.** `upsert_entry()` does a full
   re-embed + re-upsert. `sync_entry()` calls `upsert_entry()` for
   non-rejected entries or deletes for rejected. There is no incremental
   content patch — any content change requires full re-embedding. (This is
   still true but not a practical problem since content changes are infrequent.)

### Could confidence signal refinement candidates?

Yes. The data exists to identify "popular but vague" entries:

```python
# Projection store has both:
usage = store.knowledge_entry_usage.get(entry_id)  # {count, last_accessed}
entry = store.memory_entries.get(entry_id)          # {conf_alpha, conf_beta, ...}

# "Popular but vague" signal:
# High access count (>= 5) but confidence hasn't risen above prior
# (alpha hasn't grown much despite repeated use)
access_count = usage["count"]
alpha_growth = entry["conf_alpha"] - PRIOR_ALPHA  # 5.0 default
if access_count >= 5 and alpha_growth < 2.0:
    # Entry is retrieved often but colonies using it don't improve
    # → candidate for refinement
```

This signal could drive a proactive intelligence rule (14th → 15th rule) that
flags entries for archivist refinement during the maintenance cycle.

---

## Section 3: Maintenance Handler Analysis

### Current dedup handler architecture

The dedup handler (`maintenance.py:22-233`) is the closest existing code to a
curator. Its architecture:

1. **Selection**: O(n²) pairwise comparison of all verified entries
2. **Two-tier action**:
   - Cosine ≥ 0.98 → auto-merge (no LLM)
   - Cosine ∈ [0.82, 0.98) → LLM confirmation ("YES/NO: same thing?")
3. **Merge mechanics**: survivor = higher confidence, absorbed = lower
4. **Content strategy**: `keep_longer` or `keep_target` (auto) or `llm_selected`
5. **Provenance**: `merged_from` list accumulates absorbed entry IDs
6. **Dismissal**: durable marker via MemoryEntryStatusChanged with
   `reason="dedup:dismissed"` prevents re-evaluation

### Could it become the curator?

**Partially.** The dedup handler's architecture has two properties a curator needs:

- **LLM-in-the-loop classification** (the YES/NO prompt at line 124)
- **Structured action dispatch** (merge vs dismiss)

But it lacks:

- **Single-entry refinement** — it only operates on pairs
- **Content generation** — the LLM prompt is binary classification, not rewriting
- **Domain-aware entry selection** — it compares all pairs, not domain-scoped
- **Access/quality signal input** — it doesn't consider usage patterns

**Recommendation**: Don't extend the dedup handler. Build a separate
`make_curation_handler(runtime)` in the same file, following the same factory
pattern, but with different selection logic and a richer LLM prompt. The dedup
handler handles deduplication (structural similarity). The curation handler
handles refinement (semantic quality improvement).

---

## Section 4: Curating Extraction Prompt Design

### What the archivist currently receives

```
build_extraction_prompt() inputs:
  task:            "Fix the rate limiter"
  final_output:    "Implemented token bucket..." (2000 chars)
  artifacts:       [{name, type, content[:200]}] (max 5)
  colony_status:   "completed"
  failure_reason:  None
  contract_result: None
```

### What a curating archivist would also receive

```python
# Fetch existing entries relevant to this colony's domain
existing = await self._runtime.knowledge_catalog.search(
    query=colony_proj.task,
    workspace_id=workspace_id,
    top_k=10,
)

# Enrich each with access count from projection
for item in existing:
    usage = self._runtime.projections.knowledge_entry_usage.get(item["id"], {})
    item["access_count"] = usage.get("count", 0)
    item["last_accessed"] = usage.get("last_accessed", "")
```

### Structured output format

```json
{
  "actions": [
    {
      "type": "CREATE",
      "entry": {
        "title": "...", "content": "...", "domains": [...],
        "tool_refs": [...], "sub_type": "technique",
        "decay_class": "stable"
      }
    },
    {
      "type": "REFINE",
      "entry_id": "mem-col-42-s-0",
      "new_content": "...",
      "new_title": "...",
      "reason": "Original was vague about error handling edge case"
    },
    {
      "type": "MERGE",
      "target_id": "mem-col-10-s-1",
      "source_id": "mem-col-30-s-0",
      "merged_content": "...",
      "reason": "Both describe the same CSV parsing pattern"
    },
    {
      "type": "NOOP",
      "entry_id": "mem-col-5-s-2",
      "reason": "Entry is already comprehensive"
    }
  ]
}
```

### Prompt template sketch

```
You are extracting institutional memory from a completed colony run.
You also have access to EXISTING entries in this workspace's knowledge base.

TASK: {task}
STATUS: {colony_status}
FINAL OUTPUT: {final_output[:2000]}
ARTIFACTS: {artifacts[:5]}

EXISTING ENTRIES (most relevant to this task):
{for entry in existing[:10]:}
  - [{entry.id}] "{entry.title}" (conf: {entry.confidence:.2f},
    accessed: {entry.access_count}x, age: {entry.age_days}d)
    Content: {entry.content[:200]}
{endfor}

For each piece of knowledge from this colony, decide:
- CREATE: New knowledge not covered by existing entries
- REFINE: An existing entry should be updated with new information
  from this colony (provide entry_id + improved content)
- MERGE: Two entries (one existing + one new, or two existing)
  should be combined (provide both IDs + merged content)
- NOOP: Existing entry already covers this knowledge adequately

Return JSON: {"actions": [...]}
Be conservative. REFINE only when the colony produced genuinely
new information that makes an existing entry more actionable.
```

---

## Section 5: REFINE Operation Design

### How to update an entry's content

The cleanest path reuses the existing merge infrastructure with a new event:

**Option A: New MemoryEntryRefined event** (clean, explicit)

```
MemoryEntryRefined(EventEnvelope):
    entry_id: str           # Entry being refined
    old_content: str        # For audit trail
    new_content: str        # Replacement content
    new_title: str          # Optional title update (empty = keep)
    refinement_source: str  # "extraction" | "maintenance" | "operator"
    source_colony_id: str   # Colony that triggered the refinement
    workspace_id: str
```

Projection handler would:
1. Update `entry["content"]` and optionally `entry["title"]`
2. Bump `entry["refinement_count"]` (new field, default 0)
3. Set `entry["last_refined_at"]` timestamp

Runtime sync would:
1. Add `"MemoryEntryRefined"` to the Qdrant sync block in `emit_and_broadcast()`
2. `memory_store.sync_entry()` already does full re-embed on upsert — content
   change triggers re-embedding automatically

**Option B: Reuse MemoryEntryMerged with self-merge** (no new event)

Emit `MemoryEntryMerged` where `target_id == source_id` with
`content_strategy="llm_selected"` and `merge_source="refinement"`.

Problems:
- `merge_source` is `Literal["dedup", "federation"]` — adding "refinement"
  changes the type
- Projection handler marks `source` as rejected — self-merge would reject the
  entry being refined
- Semantically wrong: refinement is not a merge

**Recommendation: Option A.** One new event type (65 → 66). The event is
genuinely distinct from merge — it has one entry, not two. The projection
handler is simpler. The audit trail is explicit. Cost: ~30 lines of event +
handler + sync addition.

### Qdrant sync fix (prerequisite)

Before adding REFINE, fix the existing sync gap. In `runtime.py:emit_and_broadcast()`,
the Qdrant sync block (lines 491-502) should also handle `MemoryEntryMerged`:

```python
if etype == "MemoryEntryCreated":
    sync_id = str(getattr(event_with_seq, "entry", {}).get("id", ""))
elif etype == "MemoryEntryStatusChanged":
    sync_id = str(getattr(event_with_seq, "entry_id", ""))
elif etype == "MemoryEntryMerged":                    # NEW
    sync_id = str(getattr(event_with_seq, "target_id", ""))
    # Also sync source (now rejected → will be deleted from Qdrant)
    source_id = str(getattr(event_with_seq, "source_id", ""))
    if source_id:
        await self.memory_store.sync_entry(
            source_id, self.projections.memory_entries,
        )
```

This fixes the existing bug where merged entries have stale vectors in Qdrant.

---

## Section 6: Event Model Gaps

### Current memory events (6)

| Event | Purpose | Modifies content? | Triggers Qdrant sync? |
|---|---|---|---|
| MemoryEntryCreated | New entry | N/A (new) | Yes |
| MemoryEntryStatusChanged | Status transitions | No | Yes |
| MemoryExtractionCompleted | Extraction receipt | No | No |
| MemoryEntryScopeChanged | Thread scope | No | No |
| MemoryConfidenceUpdated | Beta posterior update | No | **No (gap)** |
| MemoryEntryMerged | Two entries → one | Yes | **No (gap)** |

### Proposed additions

| Event | Purpose | Modifies content? | Triggers Qdrant sync? |
|---|---|---|---|
| MemoryEntryRefined | In-place content improvement | Yes | Yes |

### Qdrant sync gaps to fix regardless of curation

1. **MemoryEntryMerged** — target gets new content but old vector persists.
   Retrieval uses stale embedding. Fix: add to sync block.
2. **MemoryConfidenceUpdated** — metadata stale in Qdrant, but retrieval
   re-reads from projection at query time so impact is lower. Could defer.

---

## Section 7: Recommendations

### Recommendation 1: Fix MemoryEntryMerged Qdrant sync gap

**File**: `src/formicos/surface/runtime.py:491-502`
**Data flow**: MemoryEntryMerged event → sync target_id (re-embed with new
content) + sync source_id (delete from Qdrant as rejected)
**Requires**: No new events, no new fields, no new types
**Home**: Existing `emit_and_broadcast()` method — 6-line addition
**Interaction with asymmetric extraction**: None — this is a pre-existing bug
independent of the archivist model choice

### Recommendation 2: Add MemoryEntryRefined event

**File**: `src/formicos/core/events.py` (definition, ~20 lines)
**File**: `src/formicos/surface/projections.py` (handler, ~15 lines)
**File**: `src/formicos/surface/runtime.py:491-502` (Qdrant sync, 2 lines)
**Data flow**: Curation action → MemoryEntryRefined(entry_id, new_content) →
projection updates content + refinement_count → Qdrant re-embeds
**Requires**: 1 new event type (65 → 66), 1 new optional field on projection
entries (`refinement_count: int`)
**Home**: New event + projection handler
**Interaction with asymmetric extraction**: The curating archivist produces
REFINE actions that emit this event. Same model, richer output format.

### Recommendation 3: Extend build_extraction_prompt() to accept existing entries

**File**: `src/formicos/surface/memory_extractor.py:88-144`
**Data flow**: `extract_institutional_memory()` fetches Top-10 existing entries
via `self._runtime.knowledge_catalog.search(query=task)`, enriches with
`knowledge_entry_usage` access counts, passes to `build_extraction_prompt()`
as new `existing_entries` parameter
**Requires**: No new events. New parameter on `build_extraction_prompt()`.
New response parser logic to handle CREATE/REFINE/MERGE/NOOP actions.
**Home**: `memory_extractor.py` (prompt + parser) and
`colony_manager.extract_institutional_memory()` (fetch + dispatch)
**Interaction with asymmetric extraction**: This IS the curating archivist.
The same 480B model that currently does one-shot extraction would now do
context-aware curation. No additional LLM call — the existing extraction
call gets a richer prompt and produces richer output.

### Recommendation 4: Add "popular but vague" proactive rule

**File**: `src/formicos/surface/proactive_intelligence.py` (new rule, ~30 lines)
**Data flow**: During maintenance briefing, scan `knowledge_entry_usage` for
entries with `count >= 5` and `alpha_growth < 2.0` (accessed often, colonies
don't improve). Flag as refinement candidates in the briefing.
**Requires**: No new events. Uses existing projection data.
**Home**: `proactive_intelligence.py` — 15th deterministic rule, follows
the pattern of the existing 14 rules
**Interaction with asymmetric extraction**: The rule identifies refinement
candidates. The curating archivist (Recommendation 3) acts on them. The
maintenance dispatcher could auto-dispatch a curation colony targeting
flagged entries, similar to how distillation dispatches archivist colonies.

### Recommendation 5: Build make_curation_handler() in maintenance.py

**File**: `src/formicos/surface/maintenance.py` (new handler factory, ~100 lines)
**File**: `src/formicos/surface/app.py` (registration, 1 line)
**Data flow**: Periodic maintenance cycle → select entries flagged by
Recommendation 4 → fetch their content + related entries → call archivist
LLM with curation prompt → parse REFINE/MERGE actions → emit
MemoryEntryRefined or MemoryEntryMerged events
**Requires**: MemoryEntryRefined event (Recommendation 2). Registered as
`service:consolidation:curation`.
**Home**: New handler in `maintenance.py`, same factory pattern as
`make_dedup_handler()`. NOT an extension of the dedup handler — different
selection logic, different prompt, different actions.
**Interaction with asymmetric extraction**: Uses the archivist model
(`resolve_model("archivist")`). Runs in the slow loop (maintenance cycle,
default 24h). Fire-and-forget async, same as extraction. The 480B cloud
model has the capacity for this — curation prompts are ~5K tokens,
well within the 262K context window.

### Implementation order

```
1. Fix MemoryEntryMerged sync gap        (standalone, no dependencies)
2. Add MemoryEntryRefined event          (requires ADR for new event type)
3. Extend build_extraction_prompt()      (requires #2 for REFINE dispatch)
4. Add "popular but vague" proactive rule (standalone, no dependencies)
5. Build make_curation_handler()         (requires #2, #3, #4)
```

Steps 1 and 4 can ship independently. Steps 2-3-5 form a single wave.
The curating archivist extends the existing one-shot extraction — it does
not replace it. When no existing entries are relevant (empty knowledge base,
new domain), the prompt naturally produces only CREATE actions, which is
identical to today's behavior.
