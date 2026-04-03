# Wave 83 Team C Prompt

## Mission

Build the actual DAG editor for the planning workbench.

The current preview already shows the right plan truth. It just does not
let the operator reshape it deeply enough. Your job is to turn that
preview into a real editor without inventing a frontend-only plan model.

## Owned Files

- `frontend/src/components/fc-plan-editor.ts` (new)
- `frontend/src/components/fc-parallel-preview.ts`
- `frontend/src/components/workflow-view.ts`
- `frontend/src/components/colony-creator.ts`

## Do Not Touch

- `frontend/src/components/plan-workbench.ts`
- `frontend/src/components/fc-plan-comparison.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/queen-chat.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/types.ts`
- backend command or route files

Track D owns the shell and shared frontend types.
Track A owns backend validation.
Track B owns compare/reuse backend.

## Repo Truth To Read First

1. `frontend/src/components/fc-parallel-preview.ts`
   This already renders the reviewed plan and already supports task-text
   edits. It is your starting seam.

2. `frontend/src/components/workflow-view.ts`
   This already knows how to render the live DAG. Reuse its truth where
   that helps instead of creating a disconnected second graph widget.

3. `frontend/src/components/colony-creator.ts`
   This already has target-file plumbing. Reuse ideas and helpers from
   here where possible.

4. `src/formicos/surface/commands.py`
   Read the reviewed-plan command shape so the editor edits the data the
   backend can actually validate and dispatch.

## What To Build

### 1. Editor component

Create `frontend/src/components/fc-plan-editor.ts`.

Use the existing preview object as the editable state:

- `taskPreviews`
- `groups`
- existing task fields like `depends_on`, `target_files`,
  `expected_outputs`

### 2. High-value edit operations

Support:

- task-text editing
- moving files between tasks
- splitting a task into two tasks in the same group
- merging two tasks in the same group
- moving tasks between groups
- reordering groups
- adding or removing dependencies

If drag/drop is solid, use it.
If explicit controls are more reliable, use them instead.

### 3. Validation UX

Track A owns validation truth.

Your component should:

- call backend validation as edits change
- show errors clearly
- show warnings without hiding them
- make it obvious when the current edited plan is dispatchable

### 4. Original versus edited clarity

The operator should be able to tell:

- what the Queen proposed
- what they changed

Do not let the editor become a freeform graph toy with no provenance.

## Important Constraints

- do not invent fields the backend does not understand
- do not build a separate plan format just for the UI
- do not own the workbench shell; build a reusable editor component
- prefer explicit controls over clever gestures when reliability wins

## Validation

Run:

- `cd frontend; npm run build`

Manual smoke:

1. open a reviewed parallel plan and edit task text
2. move a file from one task to another
3. split and merge tasks
4. trigger validation and see errors or warnings update

## Overlap Note

You are not alone in the codebase.

- Track A provides validation responses. Consume them; do not duplicate
  their rules in the editor.
- Track D wraps your component inside the workbench shell. Keep your
  public events and inputs simple.
- `frontend/src/types.ts` is Track D's single-owner seam. If you need a
  new shared type, coordinate through that file instead of forking local
  conventions in multiple components.
- **Sequencing note:** Define your editor's event interface types (edited
  plan payload, split/merge actions, file-move actions) in `types.ts`
  early so Track D can code the shell against stable types. If you
  defer type definitions, both tracks block waiting on each other.
