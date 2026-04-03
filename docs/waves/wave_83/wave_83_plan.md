# Wave 83 Plan: Planning Workbench

## Status

Dispatch-ready after a 2026-03-31 local audit.

This packet replaces the older provisional Wave 83 draft that still
assumed Wave 82 was in flight. Wave 82 has landed. The packet below is
grounded in the repo as it exists now.

## Summary

Wave 82 gave FormicOS the first visible planning loop:

- structured planning signals
- real parallel preview cards
- a live DAG view
- deterministic reviewed-plan dispatch through `confirm_reviewed_plan`

Wave 83 should turn that seam into a bounded operator workbench.

The goal is not a new planner subsystem.
The goal is to let the operator reshape, compare, save, and dispatch the
exact parallel plan that will run.

Wave 83 has four tracks:

- Track A: reviewed-plan validation and normalization
- Track B: plan patterns and compare backend
- Track C: DAG editor UI
- Track D: workbench shell and launch truth

## Verified Repo Truth

The packet should dispatch against these facts, not against the older
forecast.

- `frontend/src/components/fc-parallel-preview.ts` already renders
  groups, task text, target files, expected outputs, and planning
  signals. It only supports task-text edits today.
- `frontend/src/components/workflow-view.ts` already renders active DAG
  truth and exposes an `edit-plan` action before launch.
- `frontend/src/components/thread-view.ts` currently routes that action
  straight into `confirm_reviewed_plan`, so "edit" effectively means
  "dispatch now", not "open a real editing workflow".
- `src/formicos/surface/commands.py::_handle_confirm_reviewed_plan()`
  already performs deterministic dispatch, but it blindly trusts the
  preview payload. There is no backend validation pass yet.
- `GET /api/v1/workspaces/{id}/planning-history` already exists, but it
  only returns compact prior-outcome summaries. It does not reconstruct
  historical DAG structure.
- `src/formicos/surface/template_manager.py` is currently single-colony
  shaped. It is not a truthful multi-task plan library as-is.
- `ParallelPlanCreated`, thread `active_plan`, and result aggregation
  already provide runtime plan truth after dispatch. Wave 83 should
  extend that story, not create a second plan representation.

## Shared Product Stance

Wave 83 should be ambitious, but it should not rebuild substrate we
already have.

- The editable plan object for this wave is the existing preview/plan
  contract: `taskPreviews` plus `groups`, grounded in the same task and
  file fields that `spawn_parallel` already consumes.
- The runtime truth after launch remains `ParallelPlanCreated`,
  `active_plan`, and the existing plan/result surfaces.
- The old `PlanDraft*` event-family idea is not the default shape for
  this wave. Do not add it unless coding reveals a concrete gap that the
  current preview/event trail cannot cover.
- Saved operator decompositions should be explicit assets, not hidden
  planner behavior.
- Preferred scope adds no new event types. Keep the event union at 70
  unless a later audit proves one additive event is clearly better than
  hiding operator state.

## Track A: Reviewed-Plan Validation and Normalization

Goal:

Turn `confirm_reviewed_plan` from a blind preview relay into a
deterministic validation and normalization seam.

Implementation shape:

### 1. Add a reviewed-plan helper

Create:

- `src/formicos/surface/reviewed_plan.py`

Recommended responsibilities:

- normalize preview payloads into `spawn_parallel` inputs
- validate task/group/dependency structure
- validate target-file ownership and handoff coherence
- return errors plus non-blocking warnings

### 2. Add dry-run validation

The workbench needs to ask the backend:

- is this edited plan valid?
- what warnings will dispatch raise?

without dispatching the plan.

Recommended WS command:

- `validate_reviewed_plan`

### 3. Make dispatch reuse the same validator

`confirm_reviewed_plan` should call the same reviewed-plan helper before
dispatch.

Important rule:

- no separate "validation rules in UI, different rules in backend"

### 4. Validate the real execution contract

Validation should cover at least:

- empty or duplicate task ids
- group structure that leaves tasks orphaned
- dependency cycles
- dependency edges that point forward across invalid group order
- duplicate file ownership unless clearly intentional
- `expected_outputs` / `target_files` coherence
- silent task disappearance during split/merge/regroup

Important constraint:

`queen_tools._spawn_parallel()` already auto-wires downstream
`target_files` from upstream `expected_outputs` when needed. Validation
must respect that real contract instead of fighting it.

Owned files:

- `src/formicos/surface/reviewed_plan.py` (new)
- `src/formicos/surface/commands.py`
- `tests/unit/surface/test_reviewed_plan.py` (new)
- `tests/unit/surface/test_ws_handler.py`
- `tests/unit/surface/test_parallel_planning.py`

## Track B: Plan Patterns and Compare Backend

Goal:

Give the operator a truthful compare-and-reuse substrate without
pretending we can recover every historical DAG from old data.

Implementation shape:

### 1. Keep planning history honest

`planning-history` should remain summary-first for legacy runs.

It may return richer metadata where available, but it must not fabricate
task graphs for old outcomes that only have aggregate evidence.

### 2. Add explicit saved plan patterns

Create a small operator-authored asset store for reviewed parallel plans.

Create:

- `src/formicos/surface/plan_patterns.py`

Recommended persistence shape:

- YAML-backed, similar in spirit to `template_manager.py`
- separate from single-colony templates
- explicit provenance and source fields

Minimum stored fields:

- `pattern_id`
- `name`
- `description`
- `workspace_id`
- `thread_id`
- `source_query`
- `planner_model`
- `task_previews`
- `groups`
- `created_at`
- `created_from` (`queen_preview` or `reviewed_plan`)
- optional outcome summary if saved after execution

### 3. Add read/write APIs

Recommended routes:

- `GET /api/v1/workspaces/{id}/plan-patterns`
- `POST /api/v1/workspaces/{id}/plan-patterns`
- `GET /api/v1/workspaces/{id}/plan-patterns/{pattern_id}`

### 4. Keep reuse manual and explicit

Wave 83 should support:

- save current reviewed plan as a pattern
- inspect a saved pattern
- apply a saved pattern as the starting shape for the editor

Wave 83 should not:

- silently auto-apply saved patterns in the Queen
- overload `ColonyTemplate` with multi-task DAG semantics
- claim full structural compare for historical runs that only have
  summary outcome data

Owned files:

- `src/formicos/surface/plan_patterns.py` (new)
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/workflow_learning.py`
- `tests/unit/surface/test_plan_patterns.py` (new)
- `tests/unit/surface/test_plan_read_endpoint.py`

## Track C: DAG Editor UI

Goal:

Turn the current preview into a real plan editor without inventing a new
frontend-only plan model.

Implementation shape:

### 1. Build an editor component around the existing preview contract

Create:

- `frontend/src/components/fc-plan-editor.ts`

Use the existing preview/task/group object as the editable state.
Do not create a shadow DAG format the backend cannot validate.

### 2. Add the high-value edit operations

The operator should be able to:

- move a file between tasks
- split a task into two tasks in the same group
- merge two tasks in the same group
- move a task between groups
- reorder groups
- add or remove dependencies
- edit task text

If drag/drop proves brittle, explicit transfer controls are acceptable.
The important thing is the capability, not the gesture.

### 3. Surface backend validation continuously

Track A owns validation truth.

This track should:

- call validation as the edited plan changes
- show blocking errors clearly
- show warnings without hiding the dispatch path

### 4. Keep original versus edited state visible

The workbench should make it obvious what the Queen proposed and what the
operator changed.

Owned files:

- `frontend/src/components/fc-plan-editor.ts` (new)
- `frontend/src/components/fc-parallel-preview.ts`
- `frontend/src/components/workflow-view.ts`
- `frontend/src/components/colony-creator.ts`

## Track D: Workbench Shell and Launch Truth

Goal:

Turn preview, editor, compare, save, and dispatch into one coherent
operator surface.

Implementation shape:

### 1. Add a dedicated workbench shell

Create:

- `frontend/src/components/plan-workbench.ts`
- `frontend/src/components/fc-plan-comparison.ts`

The workbench should compose:

- the editor from Track C
- validation state from Track A
- planning-history summary compare
- saved-pattern compare and apply
- explicit dispatch and save-pattern actions

### 2. Replace misleading direct-dispatch edit flows

Current repo truth:

- `workflow-view` offers "Edit before launch"
- `thread-view` immediately dispatches when that action fires

Wave 83 should change that seam so "Edit before launch" opens the
workbench first.

### 3. Keep launch truth aligned after dispatch

After the operator dispatches the reviewed plan:

- active plan view should reflect the reviewed shape
- group-state truth should still match parallel-result and overview
- the workbench should not become a disconnected pre-launch toy

### 4. Keep the simple path for easy work

Wave 83 should improve the parallel-plan workflow without forcing every
simple task through a heavy editor.

Owned files:

- `frontend/src/components/plan-workbench.ts` (new)
- `frontend/src/components/fc-plan-comparison.ts` (new)
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/parallel-result.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/types.ts`

## Merge Order

Recommended:

1. Track A (validation helper + commands)
2. Track B (plan patterns + routes)
3. Track C (DAG editor)
4. Track D (workbench shell + integration)

Why:

- Track A establishes the validation contract that C and D consume.
- Track B establishes the compare/pattern routes that D renders.
- Track C builds the editor that D composes into the shell.
- Track D should land last so it can compose accepted Track A/B/C seams.

## Parallel Start Note

The wave can start in parallel with clear ownership.

1. Track A and Track B can start immediately.
2. Track C can scaffold immediately, but should finalize validation UX
   after Track A's payload shape stabilizes.
3. Track D can scaffold immediately, but should finalize compare/reuse
   after Track B's route shapes stabilize.
4. `frontend/src/types.ts` is a single-owner seam for Track D.
5. Plan validation is a single-owner seam for Track A.
6. Plan-pattern persistence is a single-owner seam for Track B.
7. Editor internals are a single-owner seam for Track C.

## What Is Already Landed

These seams are live and should be extended, not replaced:

- `confirm_reviewed_plan` in `commands.py`: deterministic dispatch that
  calls `_spawn_parallel` directly (Wave 82 polish). Track A should add
  validation before this call, not replace the dispatch path.
- `fc-parallel-preview.ts`: editable task text, target files, expected
  outputs, planning signals, confirm/reject. Track C should extend edit
  capabilities, not rebuild the preview component.
- `workflow-view.ts`: active DAG rendering with group/task truth and
  `edit-plan` action. Track C can reuse its rendering patterns.
- `thread-view.ts`: routes `edit-plan` through `confirm_reviewed_plan`.
  Track D should intercept this to open the workbench instead.
- `planning-history` route: returns compact prior-outcome summaries.
  Track B should enrich, not replace.
- First-turn tool narrowing in `queen_runtime.py`: keeps delegation
  tools only until spawn happens. Not in scope for Wave 83.
- Colony start stagger (200ms) and `tool_choice` dict→"required"
  normalization. Not in scope for Wave 83.

## What This Wave Explicitly Does Not Do

- it does not replace the Queen
- it does not add a new planner LLM loop
- it does not introduce a `PlanDraft*` event family by default
- it does not turn FormicOS into a freeform BPMN canvas
- it does not silently auto-apply saved decompositions
- it does not maintain a second plan model separate from the existing
  preview/DelegationPlan contract

## Acceptance Standard

Wave 83 is successful if the operator can:

1. open a workbench from a Queen parallel preview or pre-launch DAG view
2. edit task text, file ownership, grouping, and dependencies
3. see backend validation before dispatch
4. compare the current plan against summary history and saved patterns
5. dispatch the reviewed plan deterministically
6. see the reviewed shape remain truthful in active-plan and result
   surfaces after launch
7. save a reviewed decomposition as a reusable pattern for later manual
   reuse
