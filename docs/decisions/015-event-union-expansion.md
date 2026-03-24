# ADR-015: Event Union Expansion -- Wave 11 Contract Opening

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-001 (Event Sourcing), ADR-010 (Skill Crystallization), ADR-013 (Qdrant Migration)

## Context

The 22-event `FormicOSEvent` union has been frozen since Phase 2 (pre-Wave 1). Ten waves of development have respected this boundary. The union is the most stable artifact in the codebase, with 672+ tests validating every consumer.

Wave 11 introduces three features that require event-sourced state changes visible to projections, the frontend, and the replay pipeline:

1. **Colony templates** -- reusable colony configurations. The projection store needs to track available templates and their usage counts. Templates are created and used at runtime -- not just config files -- so their lifecycle must be event-sourced for replay consistency.

2. **Colony naming** -- the Queen assigns human-readable names to colonies post-creation. The frontend must update reactively via WebSocket, which means the name change must be an event that flows through the existing `emit_and_broadcast()` pipeline.

3. **Skill confidence tracking** -- Wave 9 introduced confidence updates as mutable Qdrant metadata (fire-and-forget, best-effort). Wave 11 upgrades to Bayesian confidence. A single event per colony completion provides an audit trail of confidence changes without drowning the event store in per-skill updates.

## Decision

### Open the union from 22 -> 27 events across two phases

**Phase A adds 4 events (22 -> 26):**

```python
class ColonyTemplateCreated(EventEnvelope):
    """A reusable colony configuration was saved."""
    type: Literal["ColonyTemplateCreated"] = "ColonyTemplateCreated"
    template_id: str
    name: str
    description: str
    caste_names: list[str]
    strategy: CoordinationStrategyName
    source_colony_id: str | None = None

class ColonyTemplateUsed(EventEnvelope):
    """A colony was spawned from a saved template."""
    type: Literal["ColonyTemplateUsed"] = "ColonyTemplateUsed"
    template_id: str
    colony_id: str

class ColonyNamed(EventEnvelope):
    """A colony received a human-readable display name."""
    type: Literal["ColonyNamed"] = "ColonyNamed"
    colony_id: str
    display_name: str
    named_by: str  # "queen" or "operator"

class SkillConfidenceUpdated(EventEnvelope):
    """Batch skill confidence update after colony completion."""
    type: Literal["SkillConfidenceUpdated"] = "SkillConfidenceUpdated"
    colony_id: str
    skills_updated: int
    colony_succeeded: bool
```

**Phase B adds 1 event (26 -> 27):**

```python
class SkillMerged(EventEnvelope):
    """Two skills were merged during LLM-gated deduplication."""
    type: Literal["SkillMerged"] = "SkillMerged"
    surviving_skill_id: str
    merged_skill_id: str
    merge_reason: str  # "llm_dedup"
```

### Events explicitly NOT added

| Rejected | Reason |
|----------|--------|
| `SkillAdded` | `ColonyCompleted.skills_extracted` + Qdrant upsert is sufficient. No projection consumer. |
| `SkillDecayed` | No decay job exists. Add when the feature ships. |
| `SkillSynthesized` | No synthesis mechanism exists. Add when HDBSCAN/clustering ships. |
| `ColonyTemplateDeprecated` | No deprecation workflow exists. Speculative. |
| `SkillUpdated` | Covered by `SkillMerged` for the dedup case. General updates are Qdrant metadata. |

### Discipline rule

**Every new event must have an emitter and a projection handler at the time it enters the union.** Do not add events that nothing fires. This prevents the union from accumulating dead types that clutter consumer match statements.

## Implementation requirements

1. Add event classes to `core/events.py` following existing `FrozenConfig` pattern.
2. Extend the `FormicOSEvent` union type alias.
3. Update `EventTypeName` literal in `core/ports.py`.
4. Add projection handlers in `surface/projections.py` for each event.
5. Update `frontend/src/types.ts` TypeScript mirrors.
6. Update contract parity tests.
7. All 672+ existing tests must pass -- new events extend the union, they do not change existing event handling.

## Consequences

- Union grows from 22 -> 27 types (23% expansion over two phases).
- Every `match` or `if event.type ==` consumer must handle unknown types gracefully (they already do -- the `deserialize()` function raises on unknown types, and projections skip unhandled types).
- Frontend TypeScript mirror must stay in sync. The contract parity test catches drift.
- Future waves can add events incrementally -- the contract is now "open for extension" rather than "frozen." The discipline rule prevents bloat.
