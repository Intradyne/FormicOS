# ADR-045: Event Union Expansion 53 to 55 -- Parallel Planning and Knowledge Distillation

**Status:** Accepted (shipped in Wave 35; event union now at 64 after subsequent waves)
**Date:** 2026-03-18
**Wave:** 35
**Depends on:** ADR-042 (event union governance), ADR-044 (co-occurrence scoring)

---

## Context

Wave 35 introduces two capabilities that produce first-class state changes requiring event-sourced audit trails:

1. **Multi-colony orchestration:** The Queen generates a DelegationPlan (a DAG of ColonyTasks organized into parallel groups) and dispatches them concurrently. The plan itself is a decision that must be auditable, replayable, and visible to the operator.

2. **Knowledge distillation:** When a co-occurrence cluster is dense enough (>= 5 entries, average weight > 3.0), an archivist colony synthesizes the entries into a single higher-order entry. The synthesis event must record provenance (which entries were distilled, cluster statistics) and be idempotent on replay.

Both capabilities produce state that cannot be derived from existing events. The delegation plan is a Queen decision (not a colony completion or workspace config change). The distillation is a knowledge transformation (not a merge, creation, or status change).

Current event count: 53 concrete types (excluding EventEnvelope base). After this ADR: 55.

---

## D1. ParallelPlanCreated event

**Decision:** Add `ParallelPlanCreated` as the 54th concrete event type. Emitted when the Queen generates and validates a DelegationPlan before dispatching colonies.

```python
class ParallelPlanCreated(EventEnvelope):
    type: Literal["ParallelPlanCreated"] = "ParallelPlanCreated"
    thread_id: str
    workspace_id: str
    plan: dict[str, Any]              # serialized DelegationPlan
    parallel_groups: list[list[str]]   # task_ids per execution group
    reasoning: str                     # Queen's planning rationale
    knowledge_gaps: list[str]          # domains where briefing flagged issues
    estimated_cost: float              # sum of per-task cost estimates
```

**Projection handler:**
- Stores the plan on the thread projection (`thread.active_plan`)
- Indexes by thread_id for the AG-UI stream to render the DAG
- On replay: reconstructs the plan structure without re-dispatching colonies (the ColonySpawned events that follow handle actual execution state)

**Rationale:** Without this event, the Queen's planning decisions are invisible to replay. An operator reviewing a thread's history would see colonies spawned but not why they were grouped or what the Queen's reasoning was. The event also enables the AG-UI PARALLEL_PLAN custom event for live DAG visualization.

**Not a WorkspaceConfigChanged:** WorkspaceConfigChanged is for operator-set configuration. The delegation plan is a Queen-generated runtime decision scoped to a specific thread.

---

## D2. KnowledgeDistilled event

**Decision:** Add `KnowledgeDistilled` as the 55th concrete event type. Emitted when an archivist colony synthesizes a knowledge cluster into a higher-order entry.

```python
class KnowledgeDistilled(EventEnvelope):
    type: Literal["KnowledgeDistilled"] = "KnowledgeDistilled"
    distilled_entry_id: str
    source_entry_ids: list[str]
    workspace_id: str
    cluster_avg_weight: float          # co-occurrence weight of the source cluster
    distillation_strategy: str         # "archivist_synthesis" (extensible)
```

**Projection handler:**

The archivist colony's extraction pipeline fires first (`MemoryEntryCreated`), creating the entry with actual synthesis content, domains, and sub_type. The `KnowledgeDistilled` handler then **upgrades the existing entry** — it does not create a new one.

1. Upgrades the existing distilled entry (already created by archivist's `MemoryEntryCreated`):
   - `decay_class = "stable"` (distilled knowledge is long-lived)
   - `conf_alpha = min(sum(source_alphas) / 2, 30.0)` (elevated but capped)
   - `merged_from = source_entry_ids` (provenance chain)
   - `distillation_strategy` from the event
   - Preserves archivist's content, domains, sub_type
2. Marks each source entry with `distilled_into: distilled_entry_id`
3. Does NOT reject or archive source entries -- they remain searchable. The distilled entry ranks higher due to elevated confidence.

**Idempotency:** Double-applying KnowledgeDistilled is safe:
- First apply: creates distilled entry, marks sources
- Second apply: distilled entry already exists (skip creation), sources already marked (no-op)

**Not a MemoryEntryMerged:** MemoryEntryMerged handles dedup merges (two near-identical entries combined). Distillation is synthesis (N diverse entries producing a new higher-order entry). Different semantics, different projection handling, different provenance chain.

---

## D3. No additional events for autonomy or directives

**Decision:** Operator directives and maintenance colony dispatch do NOT require new events.

- **Operator directives** are delivered via the existing `ColonyChatMessage` event with a `directive_type` field in the payload. The chat message event already captures operator-to-colony communication; directives are a typed variant.
- **Maintenance colony dispatch** is recorded by the existing `ColonySpawned` event. The spawn includes a `tags: ["maintenance"]` field and `maintenance_source` metadata that identifies which insight triggered it.
- **Autonomy level changes** are recorded by the existing `WorkspaceConfigChanged` event with the maintenance policy in the config payload.

**Rationale:** Reusing existing events for these capabilities avoids union expansion for what are semantic variants of existing communication patterns. The key information (directive type, maintenance source, autonomy level) is captured in the payload of established events.

---

## Rejected Alternatives

**Single event for both planning and distillation:** Combining them into a generic "SystemAction" event would lose type safety and make projection handlers more complex. Two specific events are clearer.

**OperatorDirectiveReceived as a new event:** The directive content is already a chat message. Adding a new event creates parallel paths for the same communication channel. The `directive_type` field in ColonyChatMessage payload is sufficient.

**MaintenanceColonySpawned as a new event:** This would duplicate ColonySpawned with extra fields. Using tags and metadata on the existing event is cleaner.
