# Proactive Intelligence Implementation Reference

Current-state reference for FormicOS proactive intelligence: deterministic
briefing rules, MaintenanceDispatcher, distillation, colony outcome analysis,
forage signals, and earned autonomy. Code-anchored to Wave 59.

---

## Overview

All rules are deterministic (no LLM calls). Target execution < 100ms.
Implemented in `surface/proactive_intelligence.py`. Rules return
`list[KnowledgeInsight]` sorted by severity.

---

## Output Types

### KnowledgeInsight

```python
class KnowledgeInsight(BaseModel):
    severity: str            # "info" | "attention" | "action_required"
    category: str            # rule category name
    title: str               # one-line summary
    detail: str              # 2-3 sentence explanation
    affected_entries: list[str] = []
    suggested_action: str = ""
    suggested_colony: SuggestedColony | None = None
    forage_signal: dict[str, Any] | None = None
```

### SuggestedColony

```python
class SuggestedColony(BaseModel):
    task: str
    caste: str               # researcher|archivist|coder
    strategy: str             # sequential|stigmergic
    max_rounds: int = 5
    rationale: str = ""
    estimated_cost: float = 0.0  # USD
```

### ProactiveBriefing

```python
class ProactiveBriefing(BaseModel):
    workspace_id: str
    generated_at: str
    insights: list[KnowledgeInsight]  # sorted by severity
    total_entries: int
    entries_by_status: dict[str, int]
    avg_confidence: float
    prediction_error_rate: float
    active_clusters: int
    distillation_candidates: int = 0
    federation_summary: dict[str, Any] = {}
```

---

## Knowledge-Health Rules (7)

### Rule 1: Confidence Decline

- **Detects**: Entry alpha dropped > 20% from peak in 7 days.
- **Category**: "confidence"
- **Severity**: "attention"
- **Suggested colony**: YES (researcher, 5 rounds, $0.40)
- **Forage signal**: YES (`trigger="proactive:confidence_decline"`, max_results=3)

### Rule 2: Contradiction

- **Detects**: Two high-confidence entries with opposite conclusions on
  overlapping domains. Also detects temporal updates and complementary pairs.
- **Thresholds**: `min_alpha=5.0`, status in {verified, stable, promoted}.
- **Category**: "contradiction"
- **Severity**: "action_required" for contradictions, "attention" for temporal.
- **Suggested colony**: YES for contradictions (researcher, 5 rounds, $0.40).

### Rule 3: Federation Trust Drop

- **Detects**: Any peer's trust score dropped below 0.5.
- **Category**: "federation"
- **Severity**: "attention"
- **Suggested colony**: NO

### Rule 4: Coverage Gap

- **Detects**: Entries with high prediction error counts (>= 3 per entry).
- **Category**: "coverage"
- **Severity**: "attention" if >= 3 entries affected, else "info".
- **Suggested colony**: YES (researcher, 5 rounds, $0.40)
- **Forage signal**: YES (`trigger="proactive:coverage_gap"`, max_results=5)

### Rule 5: Stale Cluster

- **Detects**: Co-occurrence clusters where ALL entries have
  `prediction_error_count > 3`.
- **Thresholds**: edge weight > 0.5, cluster size >= 2.
- **Category**: "staleness"
- **Severity**: "attention"
- **Suggested colony**: YES (researcher, 5 rounds, $0.40)
- **Forage signal**: YES (`trigger="proactive:stale_cluster"`, max_results=5)

### Rule 6: Merge Opportunity

- **Detects**: 2+ entries with similar titles/domains (Jaccard >= 0.5,
  title similarity >= 0.5). Capped at 10 suggestions.
- **Category**: "merge"
- **Severity**: "info"
- **Suggested colony**: NO

### Rule 7: Federation Inbound

- **Detects**: New entries from peer in domain with no local coverage.
- **Category**: "inbound"
- **Severity**: "info"
- **Suggested colony**: NO

---

## Performance Rules (4)

Based on `ColonyOutcome` projection (ADR-047).

### Rule 8: Strategy Efficiency

- **Detects**: Strategies with consistently lower quality than alternatives.
- **Thresholds**: >= 3 outcomes per strategy, gap > 0.15 vs best.
- **Category**: "performance"
- **Severity**: "info"

### Rule 9: Diminishing Rounds

- **Detects**: Colonies hitting max rounds without quality improvement.
- **Thresholds**: total_rounds >= 10, quality_score < 0.4, >= 2 low-ROI colonies.
- **Category**: "performance"
- **Severity**: "attention"

### Rule 10: Cost Outlier

- **Detects**: Colonies > 2.5x workspace median cost.
- **Thresholds**: >= 5 outcomes in dataset.
- **Category**: "performance"
- **Severity**: "info"

### Rule 11: Knowledge ROI

- **Detects**: Successful colonies extracting zero knowledge entries.
- **Thresholds**: >= 3 no-extraction colonies, > 30% of total cost.
- **Category**: "performance"
- **Severity**: "attention"

---

## Evaporation Rule

### Rule 12: Adaptive Evaporation Recommendation

- **Detects**: Domain-specific decay adjustment signals.
- **Faster decay**: avg_errors >= 3.0 OR demotion_rate >= 0.4 OR
  (avg_conf < 0.4 AND count >= 5).
- **Slower decay**: avg_errors < 1.0 AND avg_conf >= 0.7 AND
  demotion_rate < 0.1 AND count >= 5.
- **Category**: "evaporation"
- **Severity**: "info"

---

## Branching Rule

### Rule 13: Branching Stagnation

- **Detects**: Narrowing search breadth across three dimensions.
- **Thresholds**: Must have stagnation_signals >= 2 AND failure_rate >= 0.3.
  - Topology branching: `bf < 2.0`
  - Knowledge branching: `bf < 3.0` AND count >= 5
  - Config branching: `bf < 1.5` AND outcomes >= 5
- **Category**: "stagnation"
- **Severity**: "attention"

---

## Earned Autonomy Rule

### Rule 14: Earned Autonomy

- **Detects**: Autonomy level changes based on operator behavior.
- **Promotion** (asymmetric, harder): >= 5 follow-throughs.
- **Demotion** (easier): >= 3 kills OR > 50% negative feedback.
- **Cooldown**: 7 days before re-recommendation.
- **Category**: "earned_autonomy"
- **Severity**: "info" or "attention"

---

## Learning Loop Rules (2)

### Rule 15: Learned Template Health

- **Detects**: Template performance.
- **Thresholds**: `total_failure > total_success` AND >= 3 uses -> "attention".
- **Category**: "learning_loop"

### Rule 16: Recent Outcome Digest

- **Detects**: Compact digest of last 20 colony outcomes.
- **Thresholds**: `failed > succeeded` AND >= 3 outcomes -> "attention".
- **Category**: "outcome_digest"

---

## Popular Unexamined Rule (Wave 58.5)

### Rule 17: Popular Unexamined

- **Detects**: Entries accessed >= 5 times but confidence < 0.65.
- **Status filter**: "verified" only.
- **Category**: "popular_unexamined"
- **Severity**: "info"
- **Capped at**: 10 suggestions.

---

## Briefing Generation

`generate_briefing(workspace_id)` orchestrates all rules in order:

1. Filter entries by workspace_id.
2. Apply 7 knowledge rules.
3. Apply 4 performance rules (if outcomes exist).
4. Apply evaporation rule.
5. Apply branching stagnation rule.
6. Apply earned autonomy rule.
7. Apply learned-template health rule.
8. Apply recent outcome digest rule.
9. Apply popular unexamined rule.
10. Sort by severity (action_required > attention > info).
11. Compute stats (status counts, avg confidence, error rate, clusters).
12. Return `ProactiveBriefing`.

---

## MaintenanceDispatcher (`surface/self_maintenance.py`)

Connects proactive insights to automatic colony dispatch.

### Autonomy Levels

| Level | Behavior |
|-------|----------|
| `suggest` | Show data only (default) |
| `auto_notify` | Dispatch opted-in categories, notify operator |
| `autonomous` | Dispatch all eligible categories |

### Policy Controls

```python
class MaintenancePolicy(BaseModel):
    autonomy_level: AutonomyLevel = AutonomyLevel.suggest
    auto_actions: list[str] = []          # insight categories to auto-dispatch
    max_maintenance_colonies: int = 2     # active colony limit
    daily_maintenance_budget: float = 1.0 # USD cap, resets at UTC midnight
```

### Cost Estimates

| Caste | Cost/round |
|-------|------------|
| researcher | $0.08 |
| archivist | $0.05 |
| coder | $0.12 |

### evaluate_and_dispatch()

For each insight in briefing:
1. If `forage_signal` present, hand to ForagerService.
2. If `autonomy_level == suggest`, skip auto-dispatch.
3. If no `suggested_colony`, skip.
4. If active colonies >= `max_maintenance_colonies`, stop.
5. If budget_remaining < cost, skip.
6. If `auto_notify` AND category not in `auto_actions`, skip.
7. Otherwise spawn via `_spawn_maintenance_colony()`.

---

## Distillation

### Identification (`surface/maintenance.py`)

Dense co-occurrence clusters: edges with `weight > 2.0`, connected components
via BFS, components with `len >= 5` AND `avg_weight > 3.0`.

### Dispatch

`evaluate_distillation()` in MaintenanceDispatcher. Requires "distillation"
in `auto_actions` (if `auto_notify`). Spawns archivist colony
(max_rounds=3, sequential). Cost: $0.15 per distillation.

### Event

`KnowledgeDistilled`: `distilled_entry_id`, `source_entry_ids`,
`workspace_id`, `cluster_avg_weight`, `distillation_strategy`.
Distilled entries get `decay_class="stable"` and elevated alpha (capped at 30).

---

## Colony Outcome Intelligence (ADR-047)

### ColonyOutcome Projection

Replay-derived from existing events (no new event types). Fields:
`colony_id`, `workspace_id`, `thread_id`, `succeeded`, `total_rounds`,
`total_cost`, `duration_ms`, `entries_extracted`, `entries_accessed`,
`quality_score`, `caste_composition`, `strategy`, `maintenance_source`,
`escalated`, `validator_verdict`, `validator_task_type`.

### REST Endpoint

`GET /api/v1/workspaces/{id}/outcomes?period=7d`

---

## Forage Signals

Three rules emit forage signals (dict attached to `KnowledgeInsight.forage_signal`):

| Rule | Trigger | max_results |
|------|---------|-------------|
| Confidence Decline | `proactive:confidence_decline` | 3 |
| Coverage Gap | `proactive:coverage_gap` | 5 |
| Stale Cluster | `proactive:stale_cluster` | 5 |

Signal shape:
```python
{
    "trigger": str,
    "gap_description": str,
    "topic": str,
    "domains": list[str],
    "context": str,
    "max_results": int,
}
```

Dispatched by MaintenanceDispatcher to ForagerService (background, non-blocking).

---

## Key Source Files

| File | Purpose |
|------|---------|
| `surface/proactive_intelligence.py` | All 17 deterministic rules, generate_briefing() |
| `surface/self_maintenance.py` | MaintenanceDispatcher, autonomy policy, distillation |
| `surface/maintenance.py` | Distillation candidate identification |
| `surface/projections.py` | ColonyOutcome projection |
| `surface/forager.py` | ForagerService.handle_forage_signal() |
| `core/types.py` | MaintenancePolicy, AutonomyLevel |
| `core/events.py` | KnowledgeDistilled |
| `surface/routes/api.py` | Outcomes REST endpoint |
