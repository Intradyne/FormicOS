# Wave 81 Team B Prompt

## Mission

Make recent runtime behavior truthful.

The main bug is no longer "the Queen planned badly." The main bug is
"the runtime lied about what plan actually ran."

Your job is to fix that operational truth.

## Owned Files

- `src/formicos/core/types.py`
- `src/formicos/surface/parallel_plans.py` (new)
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/adapters/llm_openai_compatible.py`
- `tests/unit/surface/test_parallel_planning.py`
- `tests/unit/surface/test_queen_runtime.py`
- `tests/unit/surface/test_runtime.py`
- `tests/unit/surface/test_queen_budget.py`

## Do Not Touch

- `docker-compose.yml`
- `.env.example`
- `src/formicos/surface/workspace_roots.py`
- `src/formicos/surface/routes/colony_io.py`
- frontend components
- codebase-index addon files

Track A owns project binding. Track D owns UI truth.

## What Is Already Landed

These fixes are already in the working tree. Preserve them; do not
reimplement or revert:

- shared-KV budget fix: `_num_slots = 1` in `queen_runtime.py` and
  `routes/api.py` (the `os` import was already removed)
- colony start stagger: 200ms delay between `start_colony()` calls in
  `spawn_parallel()` Phase 2
- scope validation: `_validate_operator_scoped_coverage()` in
  `queen_tools.py` (lines 2517-2568) with helpers
  `_extract_explicit_deliverables()`, `_required_group_count()`, and
  `_task_text_covers_deliverable()`
- recon follow-up: bounded single retry in `queen_runtime.py` when the
  Queen does tool-based reconnaissance on a concrete build task and
  tries to stop with prose

## Repo Truth To Read First

1. `src/formicos/surface/queen_tools.py`
   `spawn_parallel()` already validates the full plan, emits
   `ParallelPlanCreated`, and then loops `parallel_groups` immediately.
   The scope-validation preflight (`_validate_operator_scoped_coverage`)
   already rejects plans that omit explicitly named deliverables or
   groups. Your deferred-group dispatch work should sit after this
   validation, not replace it.

2. `src/formicos/surface/runtime.py`
   `_resolve_input_sources()` rejects source colonies that are not
   completed:

   `Chain only from completed colonies.`

3. `src/formicos/surface/queen_runtime.py`
   Parallel aggregation currently tracks only the colony IDs that were
   actually spawned, so a 5-task plan can collapse into "3/3 succeeded."

4. Recent runtime truth from live runs:
   the plan really did contain 5 tasks and 2 groups; Group 2 failed to
   spawn because its `input_from` sources were still running.

5. Track A will add `workspace_roots.py`.
   Reuse it in `queen_tools.py` path resolution if you need to touch
   workspace-root logic there.

## What To Build

### 1. Plan-level task identity

Give each planned task a durable colony identity before any dispatch
happens.

Recommended approach:

- add `colony_id: str = ""` to `ColonyTask`
- pre-allocate a colony ID for every task before emitting
  `ParallelPlanCreated`
- store those IDs on the serialized plan

This lets the plan describe all tasks, not only the ones that happened
to spawn in Group 1.

### 2. Deferred group dispatch

Do not wait inside `spawn_parallel()`.

Instead:

- dispatch only the first runnable group immediately
- keep later groups pending
- when a group reaches terminal state, dispatch the next runnable group

Recommended helper:

- `src/formicos/surface/parallel_plans.py`

It should handle:

- plan registration
- next-group eligibility
- planned task count vs spawned task count
- partial / blocked plan status
- restart-time reconstruction from `thread.active_plan`,
  `thread.parallel_groups`, and colony projections

### 3. Honest aggregation

Fix `queen_runtime.py` so aggregated plan summaries are based on the
full planned task set, not only on the colony IDs that spawned in the
first dispatch pass.

The operator-facing truth should distinguish:

- pending
- running
- blocked
- completed
- failed

### 4. Diagnostics truth

Bundle the smaller runtime-truth fixes while you are here:

- use `repr(exc)` where provider exceptions can collapse to an empty
  string
- normalize `tool_choice` for llama.cpp / OpenAI-compatible paths
- the shared-KV budget fix is already landed; keep only the regression
  coverage and any helper cleanup

## Important Constraints

- Do not block the Queen tool call waiting for Group 1 to finish
- Do not report a partial plan as a fully successful plan
- Do not add a brand-new workflow engine
- Do not reimplement Track A's workspace-root logic

## Validation

Add focused tests that prove:

1. a 2-group plan with `input_from` dependencies defers Group 2 instead
   of failing it immediately
2. plan aggregation counts total planned tasks, not only spawned tasks
3. restart-time reconstruction can recover pending groups from plan +
   colony projection truth
4. provider-error logging retains real exception text
5. shared-KV budget truth stays covered

Run:

- `python -m pytest tests/unit/surface/test_parallel_planning.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/surface/test_runtime.py -q`
- `python -m pytest tests/unit/surface/test_queen_budget.py -q`

## Overlap Note

You are not alone in the codebase. Track A owns the root helper. Reread
it before touching `queen_tools.py`. Track D will render the states you
expose, so keep state names crisp and additive rather than hiding them
behind prose.
