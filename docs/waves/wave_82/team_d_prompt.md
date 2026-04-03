# Wave 82 Team D Prompt

## Mission

Make learned planning visible and lightly steerable before dispatch.

This is not a polish track.
This is where the operator gets the steering wheel that should land
before the full Wave 83 workbench.

## Owned Files

- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/fc-preview-card.ts`
- `frontend/src/components/fc-parallel-preview.ts` (new)
- `frontend/src/components/workflow-view.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/thread-timeline.ts`
- `frontend/src/components/parallel-result.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/colony-creator.ts`
- `frontend/src/types.ts`
- `frontend/src/state/store.ts`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/runtime.py`
- `tests/unit/surface/test_ws_handler.py`

## Do Not Touch

- `src/formicos/surface/workflow_learning.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/adapters/code_analysis.py`
- `src/formicos/surface/capability_profiles.py`

Track A owns the planning-signal payload.
Track B owns structural hints.
Track C owns capability evidence.

## Repo Truth To Read First

1. `frontend/src/components/queen-chat.ts`
   This already renders multiple card types and already shows consulted
   sources. It is the right place to add a true parallel-plan preview
   render path.

2. `frontend/src/components/fc-preview-card.ts`
   This is still single-colony shaped. It needs either a branch for
   parallel preview or a dedicated sibling component.

3. `frontend/src/components/workflow-view.ts`
   This already renders the active DAG and already exposes an
   `edit-plan` action. It should become part of the Wave 82 steering
   surface, not remain an isolated post-dispatch view.

4. `frontend/src/components/thread-view.ts`
   This already wires `active_plan`, `parallel_groups`, and `edit-plan`
   through the thread surface. Today it only does a best-effort
   `config-overrides` write; that placeholder seam is one of your most
   important upgrade points.

5. `frontend/src/components/formicos-app.ts`
   The current confirm-preview path only dispatches single-colony
   previews. Parallel preview confirm is the missing steering seam.

6. `frontend/src/components/colony-creator.ts`
   This already has target-file state and is the right place to support
   minimal file reassignment before dispatch.

7. `frontend/src/components/queen-overview.ts`
   Active plan truth is already partially visible here. It should stay
   aligned with the richer preview/result truth.

8. `frontend/src/types.ts`
   `DelegationTaskPreview` is currently too thin for Wave 82. You will
   need to extend it so the preview DAG can render file handoff and task
   truth instead of a task-name-only approximation.

## What To Build

### 1. Real parallel preview

Add a preview surface that can show:

- groups
- tasks
- expected outputs
- target files
- dependencies
- why-this-plan signals
- previous successful plan comparison

This should feel like the operator is reviewing a DAG, not a blob of
text.

Prefer reusing `fc-workflow-view` for canonical DAG truth where
possible, even if you still add a dedicated preview wrapper.

Extend the preview task type so it can render at least:

- `strategy`
- `depends_on`
- `expected_outputs`
- `target_files`

### 2. Why-this-plan rendering

Render the planning-signal payload from Track A:

- patterns used
- playbook hint
- capability signal
- structural grouping/coupling
- prior-plan comparison

Do not invent frontend-only explanations.

### 3. Minimal correction slice

Before dispatch, the operator should be able to:

- edit a colony task text
- move a target file between colonies
- accept/reject the plan
- compare to a previous successful plan

This is the minimum Wave 82 steering surface.

### 4. Deterministic preview dispatch

Do not route parallel preview confirmation back through vague Queen
prose if a deterministic path is possible.

Add a thin command/dispatch seam so reviewed parallel previews can be
confirmed as plans.

Replace the current `config-overrides` placeholder path rather than
"upgrading" it. `config-overrides` is a workspace settings surface, not
the right substrate for reviewed-plan dispatch. Route `edit-plan` /
confirm flows to a dedicated reviewed-plan command path instead.

### 5. Keep execution truth aligned

Preview, active-plan, and result surfaces should agree about:

- pending groups
- running groups
- blocked groups
- completed groups
- failed groups

## Important Constraints

- Do not build the full drag-and-drop workbench yet
- Do not add hidden frontend heuristics that reinterpret backend truth
- Prefer explicit labels over clever ones
- Reuse existing target-file state and open-editor seams where possible

## Validation

Run:

- `cd frontend; npm run build`
- `python -m pytest tests/unit/surface/test_ws_handler.py -q`

Manual smoke:

1. a parallel preview shows why-this-plan signals before dispatch
2. the operator can make a small correction before dispatch
3. confirming a reviewed parallel preview dispatches that plan
4. active-plan and result views agree about blocked/pending/completed
   groups

## Overlap Note

You are not alone in the codebase.

- Track A will finalize the signal payload and history/compare route
- Track B will finalize structural group hints
- Track C will finalize capability evidence

You can scaffold the card structure early, but finalize labels and
rendering only after those payloads are stable. Reuse the existing
workflow/thread DAG surfaces instead of creating a disconnected second
planner UI.
