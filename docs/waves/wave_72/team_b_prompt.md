# Wave 72 - Team B: Autonomous Continuation

Theme: make the Queen continue work coherently across sessions and idle time,
using the existing action queue and approval machinery.

## Read First

- `docs/waves/wave_72/wave_72_plan.md`
- `docs/waves/wave_72/design_note.md`
- `CLAUDE.md`

## Repo Truth You Must Start From

- `app.py` currently has two relevant loops:
  - `_maintenance_loop()` for consolidation services and proactive dispatch
  - `_operational_sweep_loop()` for fast-cadence action processing
- Wave 72 should not leave continuation logic split across parallel schedulers.
- `build_operations_summary()` in `operations_coordinator.py` already computes:
  - continuation candidates
  - operator activity
  - idle time
- `approve_action()` already knows how to execute queued work when the action
  payload includes `suggested_colony`.
- `maintenance_policy` lives in `ws.config`, not in a separate projection map.

## Key Seams To Read Before Coding

- `src/formicos/surface/app.py`
  You own scheduler integration and call order.
- `src/formicos/surface/operations_coordinator.py`
  Read `build_operations_summary()`.
- `src/formicos/surface/self_maintenance.py`
  Read:
  - `run_proactive_dispatch()`
  - `estimate_blast_radius()`
  - `compute_autonomy_score()`
  - maintenance policy loading from `ws.config`
- `src/formicos/surface/action_queue.py`
  Read `create_action()`, `append_action()`, `read_actions()`,
  `update_action()`, and status constants.
- `src/formicos/surface/routes/api.py`
  Read `approve_action()` and `reject_action()`.
- `src/formicos/surface/queen_runtime.py`
  Read `respond()` and the existing continuity/session-summary injection order.
- `src/formicos/surface/operational_state.py`
  Read `append_journal_entry()`.

## Your Files

- `src/formicos/surface/continuation.py` - new
- `src/formicos/surface/app.py` - scheduler integration
- `src/formicos/surface/queen_runtime.py` - warm-start cue
- `tests/unit/surface/test_autonomous_continuation.py` - new

Read but do not own:

- `src/formicos/surface/operations_coordinator.py`
- `src/formicos/surface/self_maintenance.py`
- `src/formicos/surface/action_queue.py`

## Do Not Touch

- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/projections.py`
- `frontend/src/components/operations-inbox.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`

## Overlap Rules

- Team A provides `scan_knowledge_for_review(...)`.
- Team C provides `extract_workflow_patterns(...)` and
  `detect_operator_patterns(...)`.
- You own the scheduler in `app.py` and wire the background call order.

## Track 5: Continuation Proposals

Create `src/formicos/surface/continuation.py` with:

```python
async def queue_continuation_proposals(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    dispatcher: MaintenanceDispatcher,
) -> int:
    """Queue continuation actions for work that is ready to resume."""
```

Rules:

1. Read candidates from `build_operations_summary(...)`.
2. Respect operator activity:
   - if the operator has interacted recently, do not queue or execute
     continuation work
3. Read maintenance/autonomy policy from `ws.config["maintenance_policy"]`.
4. Estimate blast radius with the existing helper.
5. Respect daily budget before auto-executing anything.
6. Dedupe pending continuation actions by `thread_id`.

Important implementation rule:

- continuation actions should reuse the existing `approve_action()` seam by
  including a `payload.suggested_colony`
- do not invent a second approval/execution mechanism if the existing one can
  dispatch the colony for you

Suggested payload shape:

```python
payload = {
    "thread_id": candidate["thread_id"],
    "description": candidate["description"],
    "priority": candidate.get("priority", "medium"),
    "blast_radius_score": blast.score,
    "blast_radius_level": blast.level,
    "suggested_colony": {
        "task": candidate["description"],
        "caste": "coder",
        "strategy": "sequential",
        "max_rounds": 3,
    },
}
```

That keeps queue review, manual approval, and automatic execution on one
shared contract.

## Track 6: Consolidate The Background Scheduler

You own the background cadence in `app.py`.

Wave 72 should have one clear operational sweep:

1. `run_proactive_dispatch()` — capture returned briefing insights
2. Team A `scan_knowledge_for_review(...)` — pass briefing insights via
   `briefing_insights` kwarg so contradiction detection reuses the briefing
   instead of re-generating it
3. `queue_continuation_proposals(...)`
4. `execute_idle_continuations(...)`
5. Team C `extract_workflow_patterns(...)`
6. Team C `detect_operator_patterns(...)`
7. existing approved-action processing / compaction

If you move `run_proactive_dispatch()` into `_operational_sweep_loop()`, then
the old daily `_maintenance_loop()` should stay responsible only for the
consolidation services. Do not run proactive dispatch in both places.

This is the main structural cleanup in the wave.

## Track 7: Cross-Session Warm Start And Idle Execution

In `queen_runtime.py`, enrich the first Queen response of a returning session
with a continuation cue.

Requirements:

- use the same continuation candidate source as the sweep
- keep it as a proposal, not an automatic dispatch
- cap the hint block to the top few candidates
- place it after the existing continuity/session-summary context, not before

The output should nudge the Queen toward:

- "here is what was in progress"
- "here is the most promising next step"
- "confirm or redirect me"

Even at `autonomous`, the first turn after the operator returns should stay
proposal-first.

Idle-time execution also lives in this track. Add to `continuation.py`:

```python
async def execute_idle_continuations(
    data_dir: str,
    workspace_id: str,
    projections: ProjectionStore,
    dispatcher: MaintenanceDispatcher,
    *,
    max_per_sweep: int = 1,
) -> int:
    """Execute low-risk continuation actions during operator idle time."""
```

Guard rails:

1. workspace autonomy level is `autonomous`
2. operator idle time exceeds the configured threshold
3. no pending-review actions of any kind exist
4. blast radius remains low at execution time
5. daily budget still has capacity

Execution rules:

- limit to 1 continuation per sweep cycle
- journal every autonomous continuation
- update action status cleanly
- increment daily spend

## Config Guidance

If you need an idle threshold setting, keep it in workspace config / maintenance
policy, not in a new sidecar file or a second settings system.

Do not invent a new persistence mechanism for this.

## Acceptance Gates

- continuation actions are queued through the action queue
- queued continuation actions reuse `approve_action()` via `suggested_colony`
- recent operator activity blocks continuation dispatch
- blast radius and budget gate auto-execution
- the background scheduler has one clear ownership/call order in `app.py`
- proactive dispatch is not duplicated across two loops
- warm start surfaces continuation opportunities on the first returning turn
- idle-time continuation work journals what it did

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
