# Wave 70.0 - Team C: Autonomy Trust Substrate

**Theme:** Give the Queen honest daily-budget, blast-radius, and earned-trust
contracts so `70.5` can render autonomy as something the operator can inspect.

## Context

Read `docs/waves/wave_70_0/wave_70_0_plan.md` first. This packet is backend.
Do not build the settings card or proposal UI here; land the trust contracts.

Read `CLAUDE.md` for hard constraints.

### Key seams to read before coding

- `self_maintenance.py` — `MaintenanceDispatcher.__init__()` (line 52),
  `evaluate_and_dispatch()` (line 57), `_daily_spend` dict (line 54,
  workspace_id→USD), `_reset_daily_budget_if_needed()` (line 243, UTC
  midnight reset), `_get_policy()` (line 213, reads from
  `ws.config["maintenance_policy"]`), `_count_active_maintenance_colonies()`
  (line 229), `_spawn_maintenance_colony()` (line 250). Per-caste cost
  estimates at line 38: researcher=$0.08, archivist=$0.05, coder=$0.12.
- `core/types.py` — `AutonomyLevel` (line 851: suggest/auto_notify/autonomous),
  `MaintenancePolicy` (line 857: `autonomy_level`, `auto_actions: list[str]`,
  `max_maintenance_colonies: int = 2`, `daily_maintenance_budget: float = 1.0`)
- `projections.py` — `ColonyOutcome` (line 89: `succeeded`, `total_rounds`,
  `total_cost`, `quality_score`, `strategy`, `caste_composition`, 18 fields
  total), `outcome_stats()` (line 736: returns `[{strategy, caste_mix, total,
  success_rate, avg_rounds, avg_cost}]`), `OperatorBehaviorProjection` (line
  170: `suggestion_categories_acted_on`, `kill_records`, `feedback_by_domain`,
  `kills_by_strategy`)
- `proactive_intelligence/rules.py` — `_rule_earned_autonomy()` (line 1237):
  read-only, promotion ≥5 follow-throughs, demotion ≥3 kills or >50% negative
  feedback, 7-day cooldown. Stays untouched.
- `queen_tools.py` — no existing autonomy/budget Queen tool. Proposal metadata
  is built at line 3241 (the `action` dict in `_propose_plan()`). Blast-radius
  truth should be attached here, not in `queen_runtime.py`.
- `routes/api.py` — existing budget endpoint:
  `GET /api/v1/workspaces/{id}/budget` (line 959). No autonomy-status endpoint
  exists yet.

## Your Files (exclusive ownership)

- `src/formicos/surface/self_maintenance.py` — blast radius estimator,
  autonomy scoring, dispatch gate integration
- `src/formicos/surface/queen_tools.py` — `check_autonomy_budget` handler,
  blast-radius metadata on `_propose_plan()` action dict
- `src/formicos/surface/routes/api.py` —
  `GET /api/v1/workspaces/{id}/autonomy-status` only
- `config/caste_recipes.yaml` — tool list only
- `tests/unit/surface/test_autonomy_guardrails.py` — **new**

## Do Not Touch

- `src/formicos/surface/queen_runtime.py` — Team A owns addon coverage,
  Team B owns project-plan injection. You have no changes here.
- frontend files
- `src/formicos/surface/addon_loader.py` — Team A owns
- `src/formicos/surface/project_plan.py` and `queen_budget.py` — Team B owns
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/addons/proactive_intelligence/rules.py` — the earned
  autonomy rule stays untouched

## Overlap Coordination

- Team A and Team B also add tools to `queen_tools.py`. Keep your additions
  additive and scoped to autonomy.
- Team A and Team B also touch `routes/api.py`. You only own the
  `autonomy-status` endpoint section.

---

## Track 7: Daily Autonomy Budget Truth

### Goal

Let the Queen and future UI see a stable daily autonomy budget contract.

### Requirements

- add `check_autonomy_budget` as an additive Queen tool
- expose daily spend, cap, remaining budget, and active autonomous work
- reuse existing maintenance/budget infrastructure rather than replacing it

The tool is for Queen introspection; `70.5` will use the endpoint below for UI.

---

## Track 8: Blast Radius + Proposal Metadata

### Goal

Make autonomous risk machine-readable before the UI exists.

### Requirements

Add a deterministic blast-radius estimator in `self_maintenance.py` with:

- numeric score
- level (`low` / `medium` / `high`)
- factors list
- recommendation (`proceed` / `notify` / `escalate`)

Then attach blast-radius truth to proposal metadata. The attachment point
is the `action` dict in `_propose_plan()` (queen_tools.py line 3241):

```python
action: dict[str, Any] = {
    "tool": "propose_plan",
    "render": "proposal_card",
    "proposal": proposal,
    # Wave 70: add blast-radius truth for 70.5 rendering
    "blast_radius": { ... },
}
```

Also integrate blast radius into `evaluate_and_dispatch()` as a dispatch
gate: skip colonies where the estimator recommends `"escalate"`. For
`auto_notify` level, also skip on `"notify"`. For `autonomous` level,
proceed on `"notify"` but skip on `"escalate"`.

`70.5` should not need to recompute anything in the browser.

Use additive metadata fields only. No new events.

---

## Track 9: Autonomy Score + Status Endpoint

### Goal

Turn earned autonomy from an internal recommendation into a stable read
contract.

### Requirements

**1. Scoring**

Compute an autonomy score from replay-derived/workspace-derived history using:

- success rate
- follow-through count
- operator interrupts / kills
- recent budget behavior
- maybe recent quality trend if already easy to access

Keep it deterministic and inspectable. Return components, not just one number.

**2. Endpoint**

Add:

```text
GET /api/v1/workspaces/{id}/autonomy-status
```

Suggested shape:

```json
{
  "level": "auto_notify",
  "score": 74,
  "grade": "B",
  "daily_budget": 5.0,
  "daily_spend": 1.6,
  "remaining": 3.4,
  "components": {
    "follow_through": 0.8,
    "success_rate": 0.72,
    "budget_discipline": 0.9,
    "operator_interrupt_rate": 0.15
  },
  "recent_actions": [
    {
      "task": "...",
      "blast_radius": 0.28,
      "recommendation": "proceed",
      "outcome": "completed"
    }
  ]
}
```

This endpoint is the `70.5` autonomy card contract.

## Tests

Create `tests/unit/surface/test_autonomy_guardrails.py` with at least:

1. `check_autonomy_budget` returns stable budget truth
2. blast-radius estimator produces expected levels/factors on representative tasks
3. autonomy score is deterministic from mocked outcome history
4. `GET /api/v1/workspaces/{id}/autonomy-status` returns the expected shape
5. proposal metadata carries blast-radius truth additively

## Acceptance Gates

- [ ] `check_autonomy_budget` lands as an additive Queen tool
- [ ] blast radius is deterministic and structured
- [ ] proposal metadata carries blast-radius/autonomy truth for `70.5`
- [ ] autonomy scoring is structured, not opaque
- [ ] `GET /api/v1/workspaces/{id}/autonomy-status` exists and returns stable JSON
- [ ] no frontend changes
- [ ] no new event types

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
pytest tests/unit/surface/test_autonomy_guardrails.py -v
```
