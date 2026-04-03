# Wave 83 Team A Prompt

## Mission

Turn reviewed-plan dispatch into a validated backend seam.

Wave 82 already proved that the operator can review a parallel plan and
dispatch it deterministically. Your job is to make that path safe enough
for a real workbench by adding backend normalization and validation over
the plan that the UI edits.

## Owned Files

- `src/formicos/surface/reviewed_plan.py` (new)
- `src/formicos/surface/commands.py`
- `tests/unit/surface/test_reviewed_plan.py` (new)
- `tests/unit/surface/test_ws_handler.py`
- `tests/unit/surface/test_parallel_planning.py`

## Do Not Touch

- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/plan_patterns.py`
- frontend components
- planning signals and planning-history shaping

Track B owns compare/reuse backend.
Track C owns editor internals.
Track D owns workbench shell and integration.

## Repo Truth To Read First

1. `src/formicos/surface/commands.py`
   `confirm_reviewed_plan` already exists and already dispatches
   deterministically. Today it trusts the preview payload too much.

2. `src/formicos/surface/queen_tools.py`
   Read `_spawn_parallel()` and the existing file-handoff logic.
   Validation must match the real execution contract.

3. `frontend/src/components/fc-parallel-preview.ts`
   This is the current reviewed-plan payload shape coming from the UI.

4. `frontend/src/components/thread-view.ts`
   The current "edit before launch" path lands here. This is why your
   validation contract matters even before the full workbench shell is
   in place.

## What To Build

### 1. Reviewed-plan helper

Create `src/formicos/surface/reviewed_plan.py` with pure helpers that:

- normalize preview payloads into `spawn_parallel` input shape
- validate task ids, group structure, dependencies, and file ownership
- return blocking errors plus non-blocking warnings

### 2. Dry-run validation command

Add a thin WS command:

- `validate_reviewed_plan`

The workbench should be able to ask the backend whether the edited plan
is valid before it dispatches anything.

### 3. Make dispatch reuse the same validator

`confirm_reviewed_plan` should call the same helper before dispatch.

Important rule:

- there should not be one validation path for preview and a different
  one for dispatch

### 4. Validate the real plan contract

Cover at least:

- empty or duplicate task ids
- tasks that disappear from groups
- invalid or cyclic dependencies
- dependency edges that violate group ordering
- duplicate file ownership unless intentionally allowed
- `expected_outputs` / `target_files` coherence
- empty groups or orphaned later groups
- `input_from` vs `depends_on` divergence: the current dispatch handler
  at `commands.py:317` hardcodes `input_from = depends_on`, which is
  wrong — they are semantically different fields. `depends_on` is
  execution ordering; `input_from` is data provenance. Normalization
  should preserve both when present in the preview, and warn when
  `input_from` is absent but `depends_on` is set.
- hardcoded `max_rounds: 8` and `budget_limit: 2.0` in the dispatch
  handler: normalization should preserve these from the original preview
  when present, falling back to sensible defaults only when absent.

Respect the current execution truth:

- `_spawn_parallel()` already auto-wires downstream `target_files` from
  upstream `expected_outputs` in some cases

Do not reject operator plans just because they rely on that existing
contract.

## Important Constraints

- do not add a `PlanDraft*` event family
- do not invent a second plan model
- do not put validation rules only in the frontend
- do not silently rewrite the operator plan beyond deterministic
  normalization and safe defaults

## Validation

Run:

- `python -m pytest tests/unit/surface/test_reviewed_plan.py -q`
- `python -m pytest tests/unit/surface/test_ws_handler.py -q`
- `python -m pytest tests/unit/surface/test_parallel_planning.py -q`

## Overlap Note

You are not alone in the codebase.

- Track B will add saved-pattern and compare routes. Keep your contract
  command-based and do not claim route ownership.
- Track C will call your validation command repeatedly from the editor.
  Keep the response compact and stable.
- Track D will route dispatch through your validated path. Do not bury
  errors in opaque strings if a structured detail payload will do.
