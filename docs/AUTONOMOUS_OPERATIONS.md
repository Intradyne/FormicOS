# Autonomous Operations

FormicOS supports graduated autonomy for self-maintenance, workflow learning,
and operational procedure evolution. All autonomous behavior flows through the
**action queue** and respects operator-configured policy.

## Action Queue

Every proposed autonomous action is a generic record in the action queue
(`surface/action_queue.py`). Actions carry:

- **kind** — `maintenance`, `continuation`, `workflow_template`,
  `procedure_suggestion`, `knowledge_review`
- **status** — `pending_review`, `approved`, `executed`, `rejected`,
  `self_rejected`, `failed`
- **blast_radius** — 0.0..1.0 score from 6 heuristic factors
- **confidence** — proposer's confidence in the action's value
- **payload** — kind-specific structured data

The Operations Inbox in the UI renders all action kinds with color-coded chips
and supports approve/reject flows.

## Autonomy Levels

Workspace maintenance policy controls how far the system can act without
operator confirmation:

| Level | Behavior |
|-------|----------|
| `suggest` | Show proposals in the inbox, take no action |
| `auto_notify` | Execute opted-in categories automatically, notify the operator |
| `autonomous` | Execute all eligible actions, notify only on escalation |

Policy is set via the Settings view (Budgeting & Autonomy card) or the
`set_maintenance_policy` MCP tool. Persisted through `WorkspaceConfigChanged`
events.

### Policy Controls

- **auto_actions** — list of action categories opted in for automatic execution
- **max_maintenance_colonies** — concurrent maintenance colony cap
- **daily_maintenance_budget** — USD spending cap, resets at UTC midnight

### Blast Radius Gating

Dispatch is gated by blast radius score:

- **>= 0.6** — escalate to operator regardless of autonomy level
- **>= 0.3** — notify operator (`auto_notify` skips this)
- **< 0.3** — proceed silently

## Autonomy Scoring (ADR-046)

Four weighted components produce a grade (A-F) and level:

1. **success_rate** — colony success ratio
2. **volume** — total colonies executed
3. **cost_efficiency** — cost per successful colony
4. **operator_trust** — approval/rejection ratio

Levels: `full`, `standard`, `limited`, `restricted`. The Queen can check
budget and autonomy status via `check_autonomy_budget`.

## Workflow Learning (Wave 72)

### Pattern Recognition (Track 8)

`workflow_learning.extract_workflow_patterns()` scans colony outcomes for
repeating successful patterns. When a `(strategy, caste_set)` fingerprint
appears >= 3 times across >= 2 distinct threads, a `workflow_template`
action is proposed.

On approval, the template is saved as a `ColonyTemplate(learned=True)` —
reusable from the colony creator and Queen dispatch.

### Procedure Suggestions (Track 9)

`workflow_learning.detect_operator_patterns()` scans the action queue for
recurring operator behaviors:

- **Rejection patterns** — repeated rejection of a specific source category
  suggests a standing "require approval" rule
- **Review patterns** — repeated manual approval of maintenance actions
  suggests a standing "always review" rule

On approval, the suggested rule is appended to the workspace operating
procedures via `append_procedure_rule()`.

### Integration

Both extractors are called by the operational sweep in `app.py`. They
produce actions through the existing action queue — no new event types,
no LLM calls. All proposals are deterministic.

## Proactive Intelligence

17 deterministic rules surface briefing insights without LLM calls:

- 7 knowledge-health rules (confidence decline, contradiction, federation
  trust drop, coverage gap, stale cluster, merge opportunity, federation
  inbound)
- 4 performance rules (strategy efficiency, diminishing rounds, cost
  outlier, knowledge ROI)
- Evaporation, branching stagnation, earned autonomy, learned template
  health, recent outcome digest, popular unexamined

Three rules (contradiction, coverage gap, stale cluster) include
`suggested_colony` configurations for auto-dispatch through
`MaintenanceDispatcher`.

## Operator Controls Summary

| Control | Location | Persistence |
|---------|----------|-------------|
| Autonomy level | Settings > Budgeting & Autonomy | `WorkspaceConfigChanged` event |
| Daily budget | Settings > Budgeting & Autonomy | `WorkspaceConfigChanged` event |
| Max colonies | Settings > Budgeting & Autonomy | `WorkspaceConfigChanged` event |
| Model visibility | Models > Policy card > Hide/Unhide | `SystemSettings` registry |
| Action review | Operations > Inbox | Action queue ledger |
| Procedure rules | Playbook > Operating Procedures | `.formicos/procedures.md` |
| Learned templates | Colony Creator > Templates | `ColonyTemplate` projection |
