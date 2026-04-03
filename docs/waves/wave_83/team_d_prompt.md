# Wave 83 Team D Prompt

## Mission

Build the workbench shell that connects preview, editor, compare, save,
and dispatch into one coherent operator surface.

The current repo already has most of the pieces, but they are split
across preview cards, thread DAGs, and direct-dispatch seams. Your job
is to make that feel like one truthful workflow.

## Owned Files

- `frontend/src/components/plan-workbench.ts` (new)
- `frontend/src/components/fc-plan-comparison.ts` (new)
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/parallel-result.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/types.ts`

## Do Not Touch

- editor internals inside `fc-plan-editor.ts`
- backend validation or plan-pattern storage modules
- `frontend/src/components/fc-parallel-preview.ts` except for event-shape
  coordination already called out by the packet

Track C owns the editor component.
Track A owns validation and reviewed-plan dispatch safety.
Track B owns compare/reuse backend routes.

## Repo Truth To Read First

1. `frontend/src/components/thread-view.ts`
   Today the "Edit before launch" seam jumps straight into
   `confirm_reviewed_plan`. This is the most important misleading flow
   to replace.

2. `frontend/src/components/queen-chat.ts`
   This already renders parallel preview cards and is a natural place to
   open a fuller workbench.

3. `frontend/src/components/formicos-app.ts`
   This already handles preview confirmation. It is where reviewed-plan
   workbench actions will eventually route.

4. `frontend/src/components/parallel-result.ts` and
   `frontend/src/components/queen-overview.ts`
   These already surface plan-group truth after launch. Keep the
   workbench aligned with them.

## What To Build

### 1. Workbench shell

Create:

- `frontend/src/components/plan-workbench.ts`
- `frontend/src/components/fc-plan-comparison.ts`

The shell should compose:

- the editor from Track C
- validation state from Track A
- planning-history summary compare
- saved-pattern compare and apply from Track B
- explicit save-pattern and dispatch actions

### 2. Replace the direct-dispatch edit path

When the operator chooses "Edit before launch", the UI should open the
workbench first instead of immediately dispatching.

Keep the simple "Dispatch Plan" path available for users who do not need
the workbench.

### 3. Compare and reuse UI

The operator should be able to:

- inspect summary planning-history evidence
- inspect a saved pattern with full structure
- apply a saved pattern as the starting shape for the editor
- save the current reviewed plan as a new pattern

### 4. Keep post-launch truth aligned

After dispatch:

- active-plan surfaces should reflect the reviewed plan
- result and overview surfaces should agree on group-state truth
- the workbench should not become a disconnected pre-launch island

## Important Constraints

- do not hide dispatch behind ambiguous buttons
- do not auto-apply saved patterns silently
- do not create yet another disconnected planner UI
- keep shared frontend types centralized in `frontend/src/types.ts`

## Validation

Run:

- `cd frontend; npm run build`

Manual smoke:

1. open workbench from a Queen parallel preview
2. open workbench from pre-launch thread DAG view
3. compare against summary history and saved patterns
4. save a reviewed plan as a pattern
5. dispatch the reviewed plan and confirm active-plan/result surfaces
   stay aligned

## Overlap Note

You are not alone in the codebase.

- Track C owns the editor internals. Compose their component; do not
  re-implement editing inside the shell.
- Track A owns validation shape and dispatch safety. Consume that seam
  as-is.
- Track B owns plan-pattern routes. Keep compare payload handling
  explicit about the difference between summary history and full saved
  patterns.
