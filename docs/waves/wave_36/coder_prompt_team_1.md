# Wave 36 Team 1 - Command Center + Colony Intelligence

## Role

You own Track A of Wave 36: absorb the remaining 35.5 debt, turn the Queen
landing surface into a real command center, surface colony outcome
intelligence, and extend the briefing / maintenance loop with outcome-aware
insights and scheduled refresh triggers.

This is the "tell the truth in one glance" track.

## Coordination rules

- `CLAUDE.md` defines evergreen repo rules. This prompt and
  `docs/waves/wave_36/wave_36_plan.md` override stale assumptions elsewhere.
- Read `docs/decisions/047-outcome-metrics-retention.md` before coding.
- Wave 36 must not add a new event family. The event union stays at 55.
- Track B also touches `queen-overview.ts` and `routes/api.py`.
- Track C runs after A and B. Do not delegate documentation or integration
  tests to yourself; Track C owns those.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `frontend/src/components/formicos-app.ts` | MODIFY | A0: wire `runningColonies` and `@send-colony-message` into `fc-queen-chat` / `fc-queen-overview` path |
| `frontend/src/components/queen-overview.ts` | OWN | A0 debt fixes, three-row layout, knowledge pulse, maintenance spend, outcome badges |
| `frontend/src/components/colony-detail.ts` | MODIFY | Outcome section for completed colonies |
| `src/formicos/engine/runner.py` | MODIFY | A0c: governance convergence detection -- reclassify stall to converged when code_execute succeeds |
| `src/formicos/surface/routes/api.py` | MODIFY | Workspace outcomes endpoint |
| `src/formicos/surface/proactive_intelligence.py` | OWN | 4 performance rules + 3 scheduled refresh rules |
| `src/formicos/surface/self_maintenance.py` | MODIFY | Scheduled trigger evaluation in `MaintenanceDispatcher` |
| `src/formicos/surface/queen_runtime.py` | MODIFY | Include performance insights in Queen briefing injection |

## DO NOT TOUCH

- `frontend/src/components/workflow-view.ts` - Team 2 owns
- `frontend/src/components/demo-guide.ts` - Team 2 creates
- `config/templates/demo-workspace.yaml` - Team 2 owns
- `README.md` - Team 2 owns
- `CHANGELOG.md` - Team 2 owns
- `docs/screenshots/*` - Team 2 owns
- `tests/*` - Team 3 owns
- `docs/OPERATORS_GUIDE.md` - Team 3 owns
- `docs/KNOWLEDGE_LIFECYCLE.md` - Team 3 owns
- `AGENTS.md` - Team 3 owns
- `CLAUDE.md` - Team 3 owns
- `src/formicos/core/*`
- `src/formicos/engine/*` (EXCEPTION: `engine/runner.py` is owned by this team for A0c only)

## Overlap rules

- `frontend/src/components/queen-overview.ts`
  - You own the layout structure, data sections, posture cards, knowledge pulse,
    and outcome surfacing.
  - Team 2 adds the "Try the Demo" button and mini-DAG inside Active Plans.
  - Your work should land first.
- `src/formicos/surface/routes/api.py`
  - You own the outcomes endpoint only.
  - Team 2 adds the demo-workspace creation endpoint.

---

## A0. Absorb Wave 35.5 debt first

These are prerequisites, not optional polish.

### A0a. Queen-chat `runningColonies` wiring

At both `fc-queen-chat` mount points, pass running colony metadata so the
directive toggle actually appears:
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`

Also wire `@send-colony-message` through the `fc-queen-overview` mount in
`formicos-app.ts` so the surfaced quick-directive path actually dispatches to
`store.send('chat_colony', ...)`.

### A0b. Maintenance spend

The posture card currently shows policy only. Replace this with real daily
spent-vs-limit consumption derived from maintenance-tagged `ColonyOutcome`
data in the current day window.

### A0c. Governance convergence detection (CRITICAL prerequisite)

The governance engine in `engine/runner.py` currently treats
`stability >= threshold AND progress < threshold` as a stall, leading to
force-halt with `succeeded=false`. This is correct for stuck colonies but
wrong for colonies that solved their task and have nothing left to do. A
colony that writes correct, tested code in round 1 then gets labeled
`failed` with `quality_score=0.0` because rounds 2-6 are the model
repeating its finished answer.

This poisons ColonyOutcome, outcome badges, performance insights, and the
demo. It must be fixed before any other Track A work proceeds.

**Fix:** When evaluating the stall condition, also check whether the most
recent round included a successful `code_execute`. Use the smallest
deterministic signal available from the current round:

1. At least one `code_execute` with `exit_code == 0` in the current or
   recent round
2. Outputs are stable / repeated (the existing stability check)
3. No subsequent failing execution contradicts that success

If all three hold, reclassify from `stall` to `converged`. Converged
colonies get `ColonyCompleted` with `succeeded=true`, not
`ColonyFailed`.

**This is NOT 'any exit=0 equals completion.'** A single passing test in an
otherwise broken round does not trigger convergence. The conditions require
stable + successful + no contradicting failure.

**Scope:** Signal 1 only (governance-side detection from existing round
data). Do NOT implement Signal 2 (explicit agent completion tool) -- that
is stretch / 36.5.

---

## A1. Command center layout

Rework `queen-overview.ts` into the three-row command-center hierarchy from
the plan:

1. Proactive briefing at the top
2. Active work + system health in the middle
3. Recent completions at the bottom

Keep the current components, but improve hierarchy and grouping:
- briefing remains first and full-width
- active plans / approvals / running work read as "what is happening now"
- knowledge pulse / maintenance posture / federation summary read as
  "system health"
- recent completions and outcome-rich colony cards read as "what just happened"

Do not turn this into a brand new app shell. This is a layout restructure
inside the current Queen landing page.

---

## A2. Knowledge pulse + outcome surfacing

### Landing page

Add a "Knowledge Pulse" summary to `queen-overview.ts` using replay-derived
data and the new outcomes endpoint. Show concise, operator-friendly signals:
- total entries
- average confidence
- created / merged / distilled / decayed in the selected recent window
- recent completion quality / extraction totals where useful

### Colony cards

Completed colony cards on the landing page should show compact outcome badges:
- quality
- total cost
- entries extracted

### Colony detail

Add an Outcome section for completed colonies in `colony-detail.ts` showing:
- quality score
- total cost
- extraction count
- token efficiency or similar cost-per-result context
- knowledge impact summary if derivable from existing state
- maintenance provenance for maintenance-tagged colonies when available

Keep this readable. Do not drown the detail view in analytics tables.

### API

Add a workspace outcomes endpoint to `src/formicos/surface/routes/api.py`, for
example:
- `GET /api/v1/workspaces/{workspace_id}/outcomes?period=24h|7d|30d`

Source of truth is `projections.colony_outcomes`. No new persistence layer.

---

## A3. Outcome-aware Queen performance briefing

Extend `proactive_intelligence.py` with deterministic performance rules using
replay-derived `ColonyOutcome` data.

Target rules from the plan:
- strategy efficiency
- diminishing rounds
- cost outlier
- knowledge ROI

These should produce recommendation-style insights only.

Then extend `queen_runtime.py` so the Queen's briefing injection can include
these alongside knowledge-health insights.

Constraints:
- recommendations only, no auto-tuning
- deterministic, no LLM
- no new event types

---

## A4. Scheduled knowledge refresh

Extend `MaintenanceDispatcher` in `src/formicos/surface/self_maintenance.py`
with scheduled trigger evaluation for:
- approaching staleness
- domain health check
- distillation refresh

Reuse the existing insight / suggested-colony / maintenance-dispatch path.
Do not add a second maintenance loop.

These scheduled triggers should produce the same style of insight objects the
system already understands.

---

## Acceptance targets for Track A

1. The three prerequisite debt items are actually fixed:
   - Queen-chat directive toggle appears
   - sending from the Queen landing chat path works
   - maintenance posture shows spent-vs-limit
   - a colony that solves a coding task via successful code_execute
     ends as completed (not failed), with non-zero quality_score
2. Queen landing page has a clear command-center hierarchy.
3. Completed colonies visibly surface quality, cost, and extraction outcome.
4. Outcome data is exposed additively through a workspace read endpoint.
5. Queen briefing can reference deterministic performance insights.
6. Scheduled refresh extends the real `MaintenanceDispatcher`, not a side path.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
cd frontend && npm run build
```

## Required report

- exact files changed
- how A0a/A0b were fixed, including the event-forwarding seam
- how A0c was fixed: which conditions trigger convergence, where in runner.py
- final outcomes endpoint path and response shape
- which performance rules landed
- which scheduled refresh triggers landed
- confirmation that no new event types were added