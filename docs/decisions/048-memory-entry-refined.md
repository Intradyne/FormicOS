# ADR-048: MemoryEntryRefined Event — In-Place Knowledge Curation

**Status**: Proposed
**Date**: 2026-03-23
**Wave**: 59

## Context

The knowledge pipeline is append-only. Every extraction call produces new entries.
Over N colonies, the store grows linearly with no refinement, no consolidation,
and no quality improvement. v11 demonstrated that richer extraction (Gemini
archivist) amplifies this — more entries means more noise. v12 confirmed the
safety stack (specificity gate + domain boundaries + progressive disclosure)
prevents harm, but knowledge quality stagnates because entries are never improved
after creation.

The codebase has 64 event types (closed union). Knowledge entries can be created
(`MemoryEntryCreated`), merged (`MemoryEntryMerged`, two entries combined), or
have their status changed (`MemoryEntryStatusChanged`). There is no mechanism for
in-place content improvement of a single entry.

The curating archivist (Wave 59) needs to improve existing entries when a colony
produces genuinely new information that makes an existing entry more precise, more
actionable, or corrects an error.

## Decision

Add `MemoryEntryRefined` as the 65th event type. This event represents an
auditable, replay-safe, in-place content improvement of a single knowledge entry.

```python
class MemoryEntryRefined(EventEnvelope):
    type: Literal["MemoryEntryRefined"] = "MemoryEntryRefined"
    entry_id: str           # Entry being refined
    workspace_id: str       # Workspace scope
    old_content: str        # Content before refinement (audit trail)
    new_content: str        # Improved content
    new_title: str          # Updated title (empty = keep existing)
    refinement_source: Literal["extraction", "maintenance", "operator"]
    source_colony_id: str   # Colony that informed the refinement (empty for maintenance)
```

### Projection handler

```python
def _on_memory_entry_refined(store, event):
    entry = store.memory_entries.get(event.entry_id)
    if entry is None:
        return
    entry["content"] = event.new_content
    if event.new_title:
        entry["title"] = event.new_title
    entry["refinement_count"] = entry.get("refinement_count", 0) + 1
    entry["last_refined_at"] = event.timestamp
```

### Qdrant sync

`MemoryEntryRefined` is added to the sync block in `runtime.py:emit_and_broadcast()`.
The existing `memory_store.sync_entry()` does full re-embed on upsert — content
change triggers re-embedding automatically. No memory_store changes needed.

## Alternatives rejected

1. **Self-merge via MemoryEntryMerged** — the projection handler rejects the source
   entry (sets `status="rejected"`). Self-merge would reject the entry being refined.
   Semantically wrong: refinement preserves the entry, merge absorbs one into another.

2. **Reuse MemoryEntryStatusChanged** — doesn't carry content fields. Would require
   adding optional content/title fields to an event that was designed for status
   transitions only. Violates single-responsibility.

3. **Direct projection mutation** — violates event-sourcing (hard constraint #7:
   "Every state change is an event. No shadow databases."). Content changes must be
   replay-safe.

4. **Delete + recreate** — loses entry ID, access history, confidence posteriors,
   co-occurrence weights, and federation provenance. Destructive.

## Consequences

- Event count: 64 → 65. CLAUDE.md updated.
- Replay-safe: old_content field provides audit trail. Replaying the event
  stream reproduces the refined content deterministically.
- Qdrant sync automatic: existing upsert path re-embeds on content change.
- Three refinement sources: `extraction` (curating archivist during colony
  completion), `maintenance` (periodic curation handler), `operator` (future
  manual refinement UI).
- No confidence change on refinement. Confidence evolves through
  Thompson Sampling on subsequent access, not through content improvement.
  This is deliberate — refinement improves content quality, not certainty.
