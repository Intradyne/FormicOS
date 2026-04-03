# Wave 83 Team B Prompt

## Mission

Build the compare-and-reuse backend for the planning workbench.

Wave 82 already provides summary planning history. Wave 83 needs two new
truthful things on top of that:

- explicit saved plan patterns with full DAG structure
- compare routes that stay honest about the difference between summary
  history and reusable saved patterns

## Owned Files

- `src/formicos/surface/plan_patterns.py` (new)
- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/workflow_learning.py`
- `tests/unit/surface/test_plan_patterns.py` (new)
- `tests/unit/surface/test_plan_read_endpoint.py`

## Do Not Touch

- `src/formicos/surface/commands.py`
- `src/formicos/surface/reviewed_plan.py`
- frontend workbench components
- template editor/browser unless you discover a hard blocker and re-read
  the packet first

Track A owns validation and dispatch safety.
Track C owns editor internals.
Track D owns compare/reuse UI.

## Repo Truth To Read First

1. `src/formicos/surface/routes/api.py`
   `planning-history` already exists. Today it returns compact outcome
   summaries only.

2. `src/formicos/surface/workflow_learning.py`
   `get_relevant_outcomes()` is the current planning-history read path.
   It is intentionally summary-shaped.

3. `src/formicos/surface/template_manager.py`
   Read it for storage patterns only. It is not the right semantic model
   for multi-task DAG reuse.

4. `frontend/src/components/fc-parallel-preview.ts`
   The reviewed preview already carries the task and group structure you
   need to persist as a saved pattern.

## What To Build

### 1. Saved plan-pattern store

Create `src/formicos/surface/plan_patterns.py`.

Use a thin YAML-backed operator asset store. Keep it small and explicit.

Minimum fields:

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
- `created_from`
- optional execution/outcome summary

### 2. REST routes

Add:

- `GET /api/v1/workspaces/{id}/plan-patterns`
- `POST /api/v1/workspaces/{id}/plan-patterns`
- `GET /api/v1/workspaces/{id}/plan-patterns/{pattern_id}`

The POST route should accept a reviewed plan payload from the operator
surface and persist it as a named pattern.

### 3. Honest compare behavior

Improve planning-history only where the data really exists.

Good:

- richer evidence strings
- source references
- explicit labels like "summary only"

Not good:

- fabricating task graphs for legacy outcomes that only have aggregate
  stats

### 4. Keep reuse explicit

Wave 83 supports manual save and manual apply.

Wave 83 does not silently route Queen planning through saved patterns.

## Important Constraints

- do not add new event types for v1
- do not overload `ColonyTemplate` with multi-task DAG semantics
- do not claim full historical structural compare if the old data does
  not support it
- keep the persistence shape small and inspectable

## Validation

Run:

- `python -m pytest tests/unit/surface/test_plan_patterns.py -q`
- `python -m pytest tests/unit/surface/test_plan_read_endpoint.py -q`

## Overlap Note

You are not alone in the codebase.

- Track A owns validation. Do not invent a second backend notion of what
  a valid plan is.
- Track C will edit plans locally. Your job is to store and return
  compare/reuse assets, not to own editor mutation flows.
- Track D will consume your routes directly in the workbench shell. Keep
  response payloads compact, typed, and explicit about whether they are
  summary history or full saved patterns.
