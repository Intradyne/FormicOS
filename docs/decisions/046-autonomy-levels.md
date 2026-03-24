# ADR-046: Autonomy Levels for Self-Maintenance Colonies

**Status:** Accepted (shipped in Wave 35; three autonomy levels operational)
**Date:** 2026-03-18
**Wave:** 35
**Depends on:** ADR-044 (co-occurrence scoring), Wave 34.5 (SuggestedColony, distillation_candidates)

---

## Context

After Wave 34.5, the proactive intelligence system knows what's wrong with the knowledge base and can recommend specific colonies to fix problems. Three of seven insight rules carry `SuggestedColony` data (contradiction, coverage_gap, stale_cluster). Distillation candidates are identified by the maintenance loop. But the system cannot act on any of this -- all action requires manual operator intervention.

Wave 35 connects insight to action: the system spawns colonies to operate on itself. This requires explicit operator control over how much autonomy the system has. The control surface must be:
- **Per-workspace:** Different workspaces may have different risk profiles
- **Graduated:** Operators should be able to start conservative and increase autonomy as trust builds
- **Budget-constrained:** Automatic colonies must have cost limits to prevent runaway spend
- **Auditable:** Every automatic action must be traceable to the insight that triggered it

---

## D1. Three autonomy levels

**Decision:** Three levels, per-workspace, stored via `WorkspaceConfigChanged`:

| Level | Behavior | Default |
|-------|----------|---------|
| `suggest` | Briefing shows SuggestedColony data. No automatic action. | YES (safe default) |
| `auto_notify` | System auto-dispatches colonies for categories listed in `auto_actions`. Operator notified of each dispatch. Operator can kill any maintenance colony. | No |
| `autonomous` | All SuggestedColony-eligible insights can auto-dispatch without explicit category opt-in. Operator sees results. | No |

**Rationale for three levels (not two, not five):**
- Two levels (off/on) provides no middle ground. Operators who want auto-contradiction-resolution but not auto-distillation have no recourse.
- Five levels (off/suggest/notify/auto/full) adds granularity that doesn't map to real operator decisions. The three levels map cleanly to: "show me" / "do it but tell me" / "handle it."

---

## D2. MaintenancePolicy model

**Decision:** Per-workspace maintenance policy with safe defaults:

```python
class AutonomyLevel(StrEnum):
    suggest = "suggest"
    auto_notify = "auto_notify"
    autonomous = "autonomous"

class MaintenancePolicy(BaseModel):
    autonomy_level: AutonomyLevel = AutonomyLevel.suggest
    auto_actions: list[str] = []          # insight categories that auto-dispatch
    max_maintenance_colonies: int = 2     # concurrent cap
    daily_maintenance_budget: float = 1.0 # USD limit for auto-spawned colonies
```

**`auto_actions`** is a list of insight category strings (e.g., `["contradiction", "coverage_gap"]`). Only relevant at `auto_notify` level -- at `suggest` nothing dispatches, at `autonomous` all eligible categories dispatch.

**`max_maintenance_colonies`** caps concurrent maintenance colonies per workspace. When the cap is reached, new maintenance insights queue until a slot opens. Default 2 prevents maintenance from crowding out task work.

**`daily_maintenance_budget`** caps total estimated cost of auto-spawned colonies per calendar day per workspace. When exhausted, remaining insights are shown in the briefing but not dispatched. Resets at midnight UTC. Default $1.00 is conservative -- a typical research colony costs ~$0.10-0.30.

**Cost estimation:** Add `estimated_cost: float = 0.0` to the `SuggestedColony` model. The insight generation rules estimate cost based on `max_rounds * per_round_estimate` where `per_round_estimate` varies by caste (researcher: $0.08, archivist: $0.05, coder: $0.12). These are rough estimates; actual costs come from TokensConsumed events after completion.

**Storage:** MaintenancePolicy is stored in the workspace projection via `WorkspaceConfigChanged`. No new event type needed (see ADR-045 D3).

---

## D3. Only SuggestedColony-eligible insights auto-dispatch

**Decision:** Only 3 of 7 insight types can trigger automatic colonies:

| Insight Category | Auto-dispatch eligible | Rationale |
|-----------------|----------------------|-----------|
| `contradiction` | YES | Research colony to investigate and resolve |
| `coverage_gap` | YES | Research colony to fill knowledge gap |
| `stale_cluster` | YES | Research colony to re-validate |
| `confidence_decline` | NO | Observational -- confidence may recover naturally |
| `federation_trust_drop` | NO | Operator judgment required (peer relationship) |
| `merge_opportunity` | NO | Deterministic merge, no colony needed |
| `federation_inbound` | NO | Operator review of foreign knowledge required |

**Distillation** is also auto-dispatch-eligible but requires explicit `"distillation"` in `auto_actions`. It is NOT included in the 3 insight-based categories -- it runs from the maintenance loop's `distillation_candidates` check, not from a proactive insight.

**Rationale:** The eligible categories share three properties:
1. The problem is well-defined (contradiction between X and Y, gap in domain Z, cluster with high prediction errors)
2. The resolution colony is low-risk (research/re-validation, not code changes)
3. The outcome is self-verifying (contradiction resolves → insight clears, gap fills → new entries appear, cluster validates → confidence updates)

The ineligible categories either require operator judgment (federation trust, inbound knowledge), have no colony-based resolution (merge opportunity is deterministic), or may resolve without intervention (confidence decline).

---

## D4. Feedback loop: maintenance outcomes update briefing

**Decision:** Maintenance colony outcomes feed back into the proactive intelligence system:

- **Contradiction resolved:** Winning entry gets confidence boost, losing entry gets prediction_error increment. Contradiction insight clears from next briefing.
- **Coverage gap filled:** New entries appear in the domain. Coverage_gap insight clears if the new entries are HIGH or MODERATE confidence after initial Thompson exploration.
- **Stale cluster re-validated:** Entries get confidence boosts (still relevant) or prediction_error increments (confirmed stale). Stale_cluster insight clears or escalates.
- **Distillation completed:** KnowledgeDistilled event emitted. Source entries marked. Distilled entry appears in searches. distillation_candidates list shrinks.

This feedback is emergent -- it requires no special machinery. The existing confidence pipeline, prediction error counters, and proactive intelligence rules handle it. The only new piece is tagging maintenance colonies with their source insight so operators can trace outcomes.

**Tagging:** Maintenance colonies are spawned with `tags=["maintenance", insight.category]` and metadata `maintenance_source=insight.category, maintenance_insight_title=insight.title`. These appear in the ColonySpawned event and the AG-UI stream.

---

## Rejected Alternatives

**Earned autonomy (system proves itself over time):** The autonomy level would increase automatically as the system demonstrates correct maintenance outcomes. Deferred to Wave 36+ -- requires a trust-building metric that doesn't exist yet. For now, the operator explicitly sets the level.

**Per-insight-instance approval:** Each individual auto-dispatch requires operator approval before spawning. This defeats the purpose of automation -- the operator might as well spawn manually. The category-level opt-in provides sufficient control without per-instance friction.

**Global autonomy (not per-workspace):** All workspaces share one policy. Rejected because workspaces have different risk profiles -- a production workspace should be more conservative than a sandbox.
