# ADR-042: Event Union Expansion 48 → 53 — CRDT Operations and Merge Audit

**Status:** Proposed
**Date:** 2026-03-18
**Wave:** 33
**Depends on:** ADR-041 (knowledge tuning), ADR-039 (knowledge metabolism)

---

## Context

FormicOS's event vocabulary is a closed discriminated union (ADR-001, ADR-036). The union has grown in controlled increments: Wave 26 (37→40), Wave 28 (40→41), Wave 29 (41→45), Wave 30 (45→48). Each expansion required operator approval.

Wave 33 introduces two capabilities that require new event types:

1. **Federation via Computational CRDTs.** Two FormicOS instances sharing knowledge bidirectionally. CRDT operations must be first-class events for replay determinism and selective replication. Without event-level CRDT operations, federation state cannot be reconstructed from replay, violating the "every state change is an event" hard constraint.

2. **Merge provenance.** The current dedup handler emits `MemoryEntryStatusChanged(new_status="rejected")` when auto-merging duplicates. This loses the merge relationship: which entry absorbed which, what content survived, what tags were unioned, and what provenance chain accumulated. Federation's conflict resolution needs the same merge semantics. A single `MemoryEntryMerged` event serves both paths.

---

## D1. Four CRDT operation event types (union 48 → 52)

**Decision:** Add four event types that represent primitive CRDT state mutations. Each maps to exactly one CRDT primitive operation.

```python
class CRDTCounterIncremented(EventEnvelope):
    """G-Counter increment for observation tracking."""
    model_config = FrozenConfig
    type: Literal["CRDTCounterIncremented"] = "CRDTCounterIncremented"
    entry_id: str = Field(..., description="Knowledge entry being observed.")
    instance_id: str = Field(..., description="FormicOS instance that recorded the observation.")
    field: Literal["successes", "failures"] = Field(
        ..., description="Which counter: positive or negative observations.",
    )
    delta: int = Field(..., ge=1, description="Increment amount (always positive, G-Counter invariant).")
    workspace_id: str = Field(...)

class CRDTTimestampUpdated(EventEnvelope):
    """LWW Register update for per-instance last-observation time."""
    model_config = FrozenConfig
    type: Literal["CRDTTimestampUpdated"] = "CRDTTimestampUpdated"
    entry_id: str = Field(...)
    instance_id: str = Field(...)
    timestamp: float = Field(..., description="Epoch seconds of the observation. From event timestamp, not wall clock.")
    workspace_id: str = Field(...)

class CRDTSetElementAdded(EventEnvelope):
    """G-Set element addition for domains and archival markers."""
    model_config = FrozenConfig
    type: Literal["CRDTSetElementAdded"] = "CRDTSetElementAdded"
    entry_id: str = Field(...)
    field: Literal["domains", "archived_by"] = Field(
        ..., description="Which G-Set: domain tags or archival markers.",
    )
    element: str = Field(..., description="Element being added (domain name or instance_id).")
    workspace_id: str = Field(...)

class CRDTRegisterAssigned(EventEnvelope):
    """LWW Register assignment for content, entry_type, and decay_class."""
    model_config = FrozenConfig
    type: Literal["CRDTRegisterAssigned"] = "CRDTRegisterAssigned"
    entry_id: str = Field(...)
    field: Literal["content", "entry_type", "decay_class"] = Field(
        ..., description="Which register is being updated.",
    )
    value: str = Field(..., description="New register value.")
    timestamp: float = Field(..., description="LWW timestamp. Higher timestamp wins on merge.")
    instance_id: str = Field(..., description="Instance that assigned the value.")
    workspace_id: str = Field(...)
```

**Design rationale — four types vs. one generic:**

A single `CRDTOperationApplied` event with a `kind` discriminator would reduce the union size by 3. But it would also:
- Require nested validation logic (field constraints depend on kind)
- Make projection handler dispatch ambiguous (one handler for four operations)
- Defeat Pydantic's discriminated union optimization (the `type` field is the fast path)

Four types with `Literal` field constraints give compile-time type safety and O(1) dispatch.

**Replay determinism:** All timestamps come from event-envelope timestamps or explicitly carried epoch values. No wall-clock reads during projection rebuild. CRDT merge is commutative, associative, and idempotent — event ordering affects intermediate states but not final state after convergence.

**Projection handler:** Each event type gets a dedicated handler in `projections.py` that rebuilds the in-memory `ObservationCRDT` state. The CRDT is the projection — events are the source of truth.

---

## D2. MemoryEntryMerged event (union 52 → 53)

**Decision:** Add a single event type that captures the full merge operation with provenance.

```python
class MemoryEntryMerged(EventEnvelope):
    """Two knowledge entries merged, with full provenance trail.

    Dual-purpose: emitted by the dedup maintenance handler (merge_source="dedup")
    and by the federation conflict resolver (merge_source="federation").
    """
    model_config = FrozenConfig
    type: Literal["MemoryEntryMerged"] = "MemoryEntryMerged"
    target_id: str = Field(..., description="Surviving entry that absorbs the source.")
    source_id: str = Field(..., description="Entry being absorbed. Will be marked rejected.")
    merged_content: str = Field(
        ..., description="Content that survived selection. May be target's or source's.",
    )
    merged_domains: list[str] = Field(
        ..., description="Union of both entries' domain tags.",
    )
    merged_from: list[str] = Field(
        ..., description="Accumulated provenance: all entry IDs that were merged into the target.",
    )
    content_strategy: Literal["keep_longer", "keep_target", "llm_selected"] = Field(
        ..., description="How merged_content was selected.",
    )
    similarity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Cosine similarity that triggered the merge.",
    )
    merge_source: Literal["dedup", "federation"] = Field(
        ..., description="Which code path emitted this event.",
    )
    workspace_id: str = Field(...)
```

**Projection handler behavior:**
1. Update target entry: content ← merged_content, domains ← merged_domains, append source_id to merged_from list, increment merge_count
2. Set source entry status to `"rejected"` with reason `"merged_into:{target_id}"`
3. Queue Qdrant re-sync for target (new embedding if content changed) and source (delete from active index)

**Dedup handler migration:** The current `_handle_dedup()` in `maintenance.py` emits `MemoryEntryStatusChanged(new_status="rejected")` at two points:
- Auto-merge (cosine ≥ 0.98): line 58 → replace with `MemoryEntryMerged`
- LLM-confirmed merge (cosine 0.82–0.98): line 143 → replace with `MemoryEntryMerged`

Content strategy for both: `keep_longer` (source wins if content length > 1.2× target length, otherwise target wins). This follows NeuroStack's merge heuristic which empirically preserves more information than always keeping the higher-confidence entry.

**Federation usage:** The conflict resolver emits `MemoryEntryMerged(merge_source="federation")` when merging a foreign entry with a local near-duplicate. The receiving instance applies the merge independently — `merged_from` is a hint to the originating instance, not a mandate to other peers.

**Why not extend MemoryEntryStatusChanged:** Adding merge fields to StatusChanged would overload a simple status-transition event with complex merge semantics. The two events have different consumers (StatusChanged is consumed by simple status displays; Merged is consumed by provenance tracking, federation sync, and the knowledge dashboard). Separate types keep handler logic clean.

---

## D3. Governance — from numeric cap to ADR-gated expansion

**Decision:** The "48 events" numeric cap in CLAUDE.md is replaced with: "Event types require ADR approval. The union is ADR-gated, not numerically capped."

**Rationale:** The numeric cap was a useful constraint during early development (Waves 1–31) when the event vocabulary was stabilizing. At Wave 33, the system is mature enough that the governance mechanism should be the ADR process, not an arbitrary number. Each expansion still requires:
1. Operator approval before implementation
2. An ADR documenting the new types, their projection handlers, and their replay behavior
3. Updates to `docs/contracts/events.py` (the contract file with import-time self-check)
4. Updates to `EVENT_TYPE_NAMES` manifest and `FormicOSEvent` union
5. Updates to `__all__` exports

The self-check at the bottom of `events.py` (lines 948–977) catches any drift between the manifest and the union at import time. This is the enforcement mechanism — the ADR is the governance mechanism.

**CLAUDE.md update:** Change hard constraint #5 from:
> Event types are a CLOSED union of 48 — adding one requires operator approval.

To:
> Event types are a CLOSED union — adding types requires an ADR with operator approval. See ADR-042 for governance.

---

## Migration

No data migration required. New event types are additive:
- Old event stores contain no CRDT or Merged events → projections initialize those fields to empty/default
- New projections rebuild from full replay including new events
- The `deserialize()` function in `events.py` uses Pydantic's discriminated union which handles new types automatically once added to the union

---

## Rejected Alternatives

**Single generic CRDTOperation event:** Discussed above (D1). Loses type safety, complicates dispatch, defeats Pydantic optimization.

**Embed merge data in MemoryEntryStatusChanged:** Discussed above (D2). Overloads a simple event with complex semantics.

**Keep numeric cap at 53:** Would need another ADR at the next expansion. The ADR-gated governance is strictly better — it requires the same approval process without the arbitrary number.
