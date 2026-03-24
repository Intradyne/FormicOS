# Wave 35 Team 2 — Self-Maintaining Knowledge + Knowledge Distillation

## Role

You are building the self-maintenance engine: autonomy levels, the maintenance dispatcher that bridges proactive insights to automatic colony dispatch, and knowledge distillation via archivist colonies. All three build on Wave 34.5 foundations (SuggestedColony, distillation_candidates). None depend on Team 1's parallel planner — you spawn colonies via the existing `spawn_colony` infrastructure.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/046-autonomy-levels.md` (ADR-046) for the autonomy model. Follow the exact levels, safe defaults, and auto-dispatch eligibility rules.
- Read `docs/decisions/045-event-union-parallel-distillation.md` (ADR-045 D2) for the KnowledgeDistilled event schema.
- Read `surface/proactive_intelligence.py` for the existing SuggestedColony model and 7 insight rules — you extend both.
- Read `surface/maintenance.py` for `make_cooccurrence_decay_handler` and the `distillation_candidates` computation from Wave 34.5.
- The event union goes from 54 to 55 with KnowledgeDistilled. Team 1 adds ParallelPlanCreated (54th) — you add KnowledgeDistilled (55th). Add yours after Team 1's entry in EVENT_TYPE_NAMES.
- You run in parallel with Teams 1 and 3. No dependencies between teams.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `core/types.py` | MODIFY | AutonomyLevel StrEnum, MaintenancePolicy model (add after DelegationPlan area, before `__all__`) |
| `core/events.py` | MODIFY | KnowledgeDistilled event (55th type), update EVENT_TYPE_NAMES + self-check |
| `surface/self_maintenance.py` | CREATE | ~250 LOC: MaintenanceDispatcher |
| `surface/proactive_intelligence.py` | MODIFY | Add estimated_cost to SuggestedColony, wire dispatcher into briefing pipeline |
| `surface/maintenance.py` | MODIFY | Trigger distillation dispatch, integration with self_maintenance |
| `surface/projections.py` | MODIFY | KnowledgeDistilled handler, distilled_into field, per-workspace maintenance policy storage |
| `surface/mcp_server.py` | MODIFY | set_maintenance_policy + get_maintenance_policy MCP tools |
| `surface/event_translator.py` | MODIFY | MAINTENANCE_COLONY_SPAWNED + KNOWLEDGE_DISTILLED AG-UI events |
| `tests/unit/surface/test_self_maintenance.py` | CREATE | Dispatcher tests |
| `tests/unit/surface/test_distillation.py` | CREATE | Distillation pipeline tests |

## DO NOT TOUCH

- `surface/queen_runtime.py` — Team 1 owns (parallel planning)
- `config/caste_recipes.yaml` — Team 1 owns (Queen prompt)
- `surface/knowledge_catalog.py` — Team 3 owns (score rendering, per-workspace weights)
- `surface/knowledge_constants.py` — Team 3 owns (per-workspace weight lookup)
- `engine/runner.py` — Team 3 owns (directive injection)
- `surface/colony_manager.py` — Team 3 owns (mastery restoration)
- `frontend/*` — Teams 1 and 3 own
- All integration test files — Validation track owns
- All documentation — Validation track owns

## Overlap rules

- `core/types.py`: Teams 1 and 3 also add models. You add AutonomyLevel StrEnum and MaintenancePolicy. Team 1 adds DelegationPlan/ColonyTask. Team 3 adds DirectiveType/OperatorDirective. All are independent classes — add yours after Team 1's models, before `__all__`.
- `core/events.py`: Team 1 adds ParallelPlanCreated (54th). You add KnowledgeDistilled (55th). Append after Team 1's entry in EVENT_TYPE_NAMES.
- `surface/mcp_server.py`: Team 3 also modifies this file (configure_scoring tool, directive param on chat_colony). You add maintenance policy tools (set_maintenance_policy, get_maintenance_policy). Different tool registrations, no overlap. Do not modify chat_colony or add scoring tools.

---

## B1. Autonomy levels + MaintenancePolicy

### Models (in core/types.py)

```python
class AutonomyLevel(StrEnum):
    suggest = "suggest"             # briefing shows data, no auto-action (DEFAULT)
    auto_notify = "auto_notify"     # auto-dispatch for opted-in categories, operator notified
    autonomous = "autonomous"       # all eligible categories auto-dispatch

class MaintenancePolicy(BaseModel):
    autonomy_level: AutonomyLevel = AutonomyLevel.suggest
    auto_actions: list[str] = []          # insight categories that auto-dispatch
    max_maintenance_colonies: int = 2     # concurrent cap
    daily_maintenance_budget: float = 1.0 # USD limit for auto-spawned colonies per day
```

### SuggestedColony extension (in proactive_intelligence.py)

Add `estimated_cost` to SuggestedColony:
```python
class SuggestedColony(BaseModel):
    task: str
    caste: str
    strategy: str
    max_rounds: int = 5
    rationale: str = ""
    estimated_cost: float = 0.0  # NEW: estimated USD cost for budget tracking
```

Per-caste cost estimates:
- researcher: `max_rounds * 0.08`
- archivist: `max_rounds * 0.05`
- coder: `max_rounds * 0.12`

Update the 3 rules that populate SuggestedColony (contradiction, coverage_gap, stale_cluster) to include estimated_cost.

### Storage (in projections.py)

Store MaintenancePolicy on workspace projection via WorkspaceConfigChanged. Add handler:
```python
def _on_workspace_config_changed(self, event):
    # existing handling...
    if "maintenance_policy" in event.config:
        ws = self.workspaces.get(event.workspace_id)
        if ws:
            ws["maintenance_policy"] = event.config["maintenance_policy"]
```

### MCP tools (in mcp_server.py)

```python
@mcp.tool()
async def set_maintenance_policy(
    workspace_id: str,
    autonomy_level: str = "suggest",
    auto_actions: list[str] | None = None,
    max_maintenance_colonies: int = 2,
    daily_maintenance_budget: float = 1.0,
) -> dict:
    """Set the self-maintenance autonomy policy for a workspace."""

@mcp.tool()
async def get_maintenance_policy(workspace_id: str) -> dict:
    """Get the current maintenance policy for a workspace."""
```

Validate: `autonomy_level` must be one of the 3 StrEnum values. `auto_actions` entries must be from `["contradiction", "coverage_gap", "stale_cluster", "distillation"]`. `daily_maintenance_budget` must be > 0.

### Tests

- Default policy: suggest level, empty auto_actions, 2 max, $1.00 budget
- Set policy via MCP tool, retrieve, verify round-trip
- Invalid autonomy_level → StructuredError
- Invalid auto_actions category → StructuredError

---

## B2. Self-maintenance dispatch engine

### What

Create `surface/self_maintenance.py` (~250 LOC). The MaintenanceDispatcher bridges proactive insights to colony dispatch.

### Implementation

```python
class MaintenanceDispatcher:
    """Connects proactive insights to automatic colony dispatch.

    Runs after generate_briefing() in the maintenance loop. Checks insights
    against workspace autonomy policy. Dispatches eligible colonies.
    """

    def __init__(self, runtime):
        self._runtime = runtime
        self._daily_spend: dict[str, float] = {}  # workspace_id -> USD spent today
        self._last_reset: date | None = None

    async def evaluate_and_dispatch(
        self, workspace_id: str, briefing: ProactiveBriefing
    ) -> list[str]:
        """Check insights against autonomy policy. Dispatch eligible colonies.

        Returns list of spawned colony IDs.
        """
        self._reset_daily_budget_if_needed()
        policy = self._get_policy(workspace_id)

        if policy.autonomy_level == AutonomyLevel.suggest:
            return []

        dispatched = []
        active = self._count_active_maintenance_colonies(workspace_id)
        budget_remaining = policy.daily_maintenance_budget - self._daily_spend.get(workspace_id, 0.0)

        for insight in briefing.insights:
            if not insight.suggested_colony:
                continue
            if active >= policy.max_maintenance_colonies:
                break
            if budget_remaining <= 0:
                break
            if (policy.autonomy_level == AutonomyLevel.auto_notify
                    and insight.category not in policy.auto_actions):
                continue

            colony_id = await self._spawn_maintenance_colony(
                workspace_id, insight
            )
            dispatched.append(colony_id)
            active += 1
            self._daily_spend[workspace_id] = (
                self._daily_spend.get(workspace_id, 0.0)
                + insight.suggested_colony.estimated_cost
            )
            budget_remaining -= insight.suggested_colony.estimated_cost

        return dispatched

    async def _spawn_maintenance_colony(
        self, workspace_id: str, insight: KnowledgeInsight
    ) -> str:
        """Spawn a colony from insight's suggested_colony."""
        sc = insight.suggested_colony
        return await self._runtime.spawn_colony(
            workspace_id=workspace_id,
            task=sc.task,
            caste=sc.caste,
            strategy=sc.strategy,
            max_rounds=sc.max_rounds,
            tags=["maintenance", insight.category],
            metadata={
                "maintenance_source": insight.category,
                "maintenance_insight_title": insight.title,
            },
        )
```

### Integration

Wire the dispatcher into the maintenance loop. After `generate_briefing()` runs:
```python
dispatcher = MaintenanceDispatcher(runtime)
dispatched = await dispatcher.evaluate_and_dispatch(workspace_id, briefing)
```

The exact integration point depends on how the maintenance loop currently calls generate_briefing. Check `surface/maintenance.py` and `surface/app.py` for the current flow.

### AG-UI event (in event_translator.py)

When a maintenance colony is spawned, emit a MAINTENANCE_COLONY_SPAWNED custom event:
```python
{
    "type": "MAINTENANCE_COLONY_SPAWNED",
    "colony_id": colony_id,
    "insight_category": insight.category,
    "insight_title": insight.title,
    "estimated_cost": insight.suggested_colony.estimated_cost,
}
```

### Tests

- suggest level: no colonies dispatched regardless of insights
- auto_notify with auto_actions=["contradiction"]: contradiction insight dispatches, coverage_gap does not
- auto_notify with empty auto_actions: nothing dispatches
- autonomous: all 3 eligible categories dispatch
- Budget cap: 3rd colony blocked when daily budget exhausted
- Concurrent cap: 3rd colony blocked when max_maintenance_colonies=2 reached
- Daily budget resets at midnight UTC

---

## B3. Knowledge distillation via archivist colonies

### What

When a co-occurrence cluster reaches density thresholds (>= 5 entries, avg weight > 3.0), and the maintenance policy allows, an archivist colony synthesizes the entries.

### KnowledgeDistilled event (in core/events.py)

```python
class KnowledgeDistilled(EventEnvelope):
    type: Literal["KnowledgeDistilled"] = "KnowledgeDistilled"
    distilled_entry_id: str
    source_entry_ids: list[str]
    workspace_id: str
    cluster_avg_weight: float
    distillation_strategy: str  # "archivist_synthesis"
```

Add to EVENT_TYPE_NAMES and self-check. This is the 55th event type.

### Distillation dispatch (in self_maintenance.py or maintenance.py)

```python
async def _spawn_distillation_colony(
    self, workspace_id: str, cluster: list[str]
) -> str:
    """Spawn archivist colony to synthesize a knowledge cluster."""
    entries = [self._runtime.projections.memory_entries[eid] for eid in cluster
               if eid in self._runtime.projections.memory_entries]
    entry_summaries = "\n".join(
        f"- [{e.get('id', '')}] ({e.get('sub_type', 'unknown')}): {e.get('title', '')}\n"
        f"  Content: {str(e.get('content', ''))[:300]}\n"
        for e in entries
    )

    task = (
        f"Synthesize these {len(cluster)} related knowledge entries into a single "
        f"comprehensive entry. Preserve all key insights. Resolve any contradictions "
        f"by noting the strongest evidence. The synthesis should be more useful than "
        f"any individual entry.\n\n{entry_summaries}"
    )

    return await self._runtime.spawn_colony(
        workspace_id=workspace_id,
        task=task,
        caste="archivist",
        strategy="sequential",
        max_rounds=3,
        tags=["maintenance", "distillation"],
        metadata={"distillation_cluster": cluster},
    )
```

### Trigger

After the maintenance loop identifies distillation_candidates (Wave 34.5 code), check if `"distillation"` is in the workspace's `auto_actions`. If yes and budget allows, spawn distillation colonies (one per candidate cluster, respecting concurrent cap).

### Colony-to-event handoff

The gap between "spawn archivist colony" and "emit KnowledgeDistilled" needs explicit wiring. The flow is:

1. `_spawn_distillation_colony()` spawns the archivist colony with `metadata={"distillation_cluster": cluster}`
2. When the colony completes, the normal extraction pipeline fires (`_hook_memory_extraction` at position 4) → `MemoryEntryCreated` emitted → entry exists in projections with the archivist's synthesis content
3. The MaintenanceDispatcher needs a **completion callback** that fires after the colony completes and extraction runs. Register it on the runtime using the same pattern as `_hook_memory_extraction` in `colony_manager.py` (line 649+). The callback:
   - Reads the colony's extracted entry IDs from the colony completion metadata
   - Identifies the newly created entry (the synthesis)
   - Emits `KnowledgeDistilled` referencing that entry + the source cluster from the colony's metadata

The most natural approach: register a post-colony hook (position 5, after extraction at 4.5) that checks for the `["maintenance", "distillation"]` tags. If present, reads `distillation_cluster` from colony metadata, finds the new entry, emits `KnowledgeDistilled`. This keeps the handoff in the existing hook pipeline rather than adding a polling mechanism.

```python
async def _hook_distillation_complete(self, colony_id: str, result: ColonyResult):
    """Post-colony hook for distillation. Fires after extraction (position 5)."""
    colony = self._colonies.get(colony_id)
    if not colony or "distillation" not in colony.get("tags", []):
        return
    cluster = colony.get("metadata", {}).get("distillation_cluster", [])
    if not cluster:
        return
    # Find the newly extracted entry (created by _hook_memory_extraction)
    new_entries = [eid for eid in result.extracted_entry_ids
                   if eid not in cluster]
    if not new_entries:
        return
    distilled_id = new_entries[0]
    await self._emit(KnowledgeDistilled(
        distilled_entry_id=distilled_id,
        source_entry_ids=cluster,
        workspace_id=colony["workspace_id"],
        cluster_avg_weight=colony.get("metadata", {}).get("cluster_avg_weight", 0.0),
        distillation_strategy="archivist_synthesis",
    ))
```

### Projection handler (in projections.py)

**IMPORTANT:** The archivist colony's normal extraction pipeline fires first. When the
colony completes, `_hook_memory_extraction()` emits `MemoryEntryCreated` — the distilled
entry already exists in `memory_entries` with content, domains, sub_type from the
archivist's synthesis. The `KnowledgeDistilled` handler must MODIFY the existing entry
(upgrade it), not create a new one — otherwise it overwrites the archivist's actual
synthesis text with placeholder fields.

```python
def _on_knowledge_distilled(self, event):
    # Upgrade existing entry (created by archivist's MemoryEntryCreated)
    entry = self.memory_entries.get(event.distilled_entry_id)
    if not entry:
        return  # Entry should exist from extraction; skip if replay order differs

    source_alphas = [
        self.memory_entries.get(sid, {}).get("conf_alpha", 5.0)
        for sid in event.source_entry_ids
    ]
    entry["decay_class"] = "stable"
    entry["conf_alpha"] = min(sum(source_alphas) / 2, 30.0)
    entry["merged_from"] = event.source_entry_ids
    entry["distillation_strategy"] = event.distillation_strategy

    # Mark source entries
    for sid in event.source_entry_ids:
        source = self.memory_entries.get(sid)
        if source:
            source["distilled_into"] = event.distilled_entry_id
```

### AG-UI event (in event_translator.py)

KNOWLEDGE_DISTILLED custom event with distilled_entry_id, source count, cluster_avg_weight.

### Tests

- Distillation candidate flagged → archivist colony spawns (when policy allows)
- Distillation candidate flagged → no colony (when policy is suggest)
- KnowledgeDistilled event → existing entry upgraded to stable decay + elevated alpha (NOT created fresh)
- KnowledgeDistilled event → archivist's synthesis content/domains/sub_type preserved after upgrade
- KnowledgeDistilled event → source entries marked with distilled_into
- Double-apply KnowledgeDistilled → idempotent (re-sets same fields)
- Distilled entry has alpha = min(sum(source_alphas)/2, 30.0)

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
