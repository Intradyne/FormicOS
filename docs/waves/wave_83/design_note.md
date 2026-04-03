# Wave 83 Design Note: Planning Workbench

## Status

Dispatch-ready framing note after the Wave 82 landing audit.

The older Wave 83 draft was useful as a north-star document, but it was
written before the current seams existed. This note records the product
stance that matches the repo now.

## Theme

Wave 83 is the operator-control wave.

Wave 81 made planning and execution truthful.
Wave 82 made planning visible and reviewable.
Wave 83 should make planning steerable.

The question is no longer "can the Queen propose a parallel plan?"
The question is "can the operator deliberately reshape that plan before
FormicOS spends time and money executing it?"

## What Already Exists

The repo already has the hard part of the execution contract:

- the Queen emits a real parallel preview
- the preview already carries task, file, and signal detail
- `confirm_reviewed_plan` already dispatches the reviewed plan
- the thread surface already has an active-plan DAG view
- planning-history already provides compact prior-outcome evidence

That means Wave 83 does not need to start by inventing a new planner or
a new event family.

## What The Older Draft Got Wrong

The earlier draft over-indexed on new durable draft substrate:

- `PlanDraft` types
- `PlanDraft*` events
- a separate plan-editing model

That shape made sense before the current reviewed-plan seam existed.
It is too heavy for the codebase we have now.

The current gap is not "there is no editable plan object."
The current gap is:

- the preview can only be lightly edited
- the backend does not validate reviewed plans yet
- comparison is summary-only
- there is no explicit saved-pattern library
- the "Edit before launch" path still jumps straight to dispatch

## The Right Wave 83 Shape

Wave 83 should stay grounded in the existing plan contract and add four
things:

1. Backend validation over the reviewed plan.
2. A real DAG editor over the existing preview shape.
3. A saved-pattern library for operator-approved decompositions.
4. One coherent workbench shell that connects preview, edit, compare,
   save, and dispatch.

## Product Standard

The workbench should meet four standards.

1. Truthful
   It operates on the same task and file contract that
   `spawn_parallel` actually runs.

2. Bounded
   Editing is validated and constrained. This is not a freeform graph
   toy.

3. Explicit
   Saved decompositions and plan reuse are visible operator actions, not
   hidden automation.

4. Coherent
   Preview, workbench, active-plan DAG, and result surfaces all tell the
   same story.

## Success Standard

Wave 83 is the right shape if the operator can:

1. open a workbench from a Queen plan preview or pre-launch DAG
2. move files, split/merge tasks, and adjust dependencies
3. see backend validation before dispatch
4. compare against prior outcome summaries and saved patterns
5. dispatch the exact reviewed plan
6. save a good decomposition and reuse it later on purpose

That is the point where FormicOS stops being "a system that proposes
plans" and becomes "a system where the operator can deliberately steer
parallel work".
