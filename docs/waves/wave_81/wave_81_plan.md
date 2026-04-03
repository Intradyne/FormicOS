# Wave 81 Plan: Real Workspace Truth

## Summary

Wave 81 should make FormicOS operate on real code and tell the truth
about what it is doing.

This wave has four tracks:

- Track A: project binding
- Track B: operational truth bundle
- Track C: codebase-index activation + real-repo task pack
- Track D: operator-visible workspace truth

The goal is not another intelligence subsystem. The goal is to make the
existing planner, colony runtime, codebase indexing, and UI work against
the same real project and expose the same truth to the operator.

## Core Design Correction

Wave 81 should not collapse all file surfaces into one tree.

The live repo already has a real `workspace library` concept under
`/api/v1/workspaces/{id}/files`. That surface supports upload/ingest and
shared reference files. It is not the same thing as a bound project
root.

Wave 81 therefore introduces four distinct surfaces:

- `Project Root`
  The bound real project, used by colonies, Queen file tools, planning
  brief coupling, and codebase indexing when present.
- `Workspace Library`
  Existing uploaded/shared files under the workspace data dir.
- `Working Memory`
  Runtime AI filesystem state.
- `Artifacts`
  Durable outputs promoted from working memory or colony completion.

This keeps upload/ingest truth intact while letting the system act on a
real repo.

## Track A: Project Binding

Goal:

Bind FormicOS to a real project root with `PROJECT_DIR`, while keeping
the existing workspace library intact.

Implementation shape:

1. Add the bootstrap mount in `docker-compose.yml`:

```yaml
volumes:
  - formicos-data:/data
  - ${PROJECT_DIR:-.}:/project
```

2. Add a shared helper such as:

`src/formicos/surface/workspace_roots.py`

Recommended public helpers:

- `workspace_library_root(settings, workspace_id) -> Path`
- `workspace_project_root(settings, workspace_id) -> Path | None`
- `workspace_runtime_root(settings, workspace_id) -> Path`
- `workspace_binding_status(settings, workspace_id) -> dict[str, Any]`

3. Replace hard-coded runtime-root fallbacks with the shared helper in:

- `src/formicos/surface/app.py`
  Use `workspace_runtime_root(...)` for addon `workspace_root_fn`
- `src/formicos/engine/runner.py`
  Colony file tools and workspace reads/writes
- `src/formicos/surface/colony_manager.py`
  Colony working directory resolution
- `src/formicos/surface/planning_brief.py`
  Coupling analysis root

4. Keep existing workspace-library routes for uploads/shared files, but
   add separate project-file read routes for the UI, for example:

- `GET /api/v1/workspaces/{id}/project-files`
- `GET /api/v1/workspaces/{id}/project-files/{path}`
- `GET /api/v1/workspaces/{id}/project-binding`

5. Make the binding status visible through backend truth so the UI does
   not guess:

- whether a project is bound
- what root path is in use
- whether the runtime root is the bound project or the library fallback

Important constraints:

- `PROJECT_DIR` is the v1 bootstrap for this wave
- do not add a per-workspace persisted binding model yet
- do not repurpose `/files` away from workspace-library semantics
- do not require the UI to scrape config files to discover the binding

Owned files:

- `docker-compose.yml`
- `.env.example`
- `src/formicos/surface/workspace_roots.py` (new)
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/colony_io.py`
- `src/formicos/surface/routes/api.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/planning_brief.py`
- `tests/unit/surface/test_workspace_roots.py` (new)
- `tests/unit/surface/test_runtime.py`
- `tests/unit/engine/test_runner.py`
- `tests/unit/surface/test_planning_brief.py`

Validation:

- `python -m pytest tests/unit/surface/test_workspace_roots.py -q`
- `python -m pytest tests/unit/surface/test_runtime.py -q`
- `python -m pytest tests/unit/engine/test_runner.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`

## Track B: Operational Truth Bundle

Goal:

Make runtime behavior and reported behavior match.

This track includes the fixes that recent experiments exposed:

- budget truth
- provider error visibility
- parallel-group execution truth
- honest result aggregation

Implementation shape:

### 1. Budget truth

Use one shared helper for Queen budget computation and the REST budget
endpoint.

The shared-KV budget fix (`_num_slots = 1` in `queen_runtime.py` and
`routes/api.py`) is already in the working tree. Keep only the helper
cleanup and regression coverage.

The important rule is:

- do not derive per-request context by dividing by slot count when the
  local provider exposes a shared-KV topology

### 2. Provider error truth

Improve provider diagnostics so "empty string" failures stop hiding the
underlying cause.

Minimum fixes:

- use `repr(exc)` where provider exceptions can collapse to empty text
- normalize provider-facing `tool_choice` typing for llama.cpp / OpenAI-
  compatible paths instead of relying on implicit coercion

### 3. Parallel-group execution semantics

Recent runs proved the Queen can produce the correct multi-group plan.
The bug is that `spawn_parallel()` dispatches all groups immediately,
while `Runtime._resolve_input_sources()` only allows completed source
colonies.

The fix should be:

- pre-allocate colony IDs for every task in the plan before emitting
  `ParallelPlanCreated`
- store those IDs on the planned tasks
- dispatch only the first runnable group immediately
- defer later groups until upstream groups reach terminal state
- never block inside the Queen tool call waiting for completion

Recommended shape:

- add `colony_id: str = ""` to `ColonyTask`
- introduce a small helper such as
  `src/formicos/surface/parallel_plans.py` to manage:
  - plan state
  - next-runnable-group calculation
  - total planned task count vs spawned task count
  - restart-time reconstruction from `thread.active_plan`,
    `thread.parallel_groups`, and colony projections

### 4. Honest result aggregation and completion

Current aggregated summaries only count colonies that actually spawned.
That is how a 5-task plan became "3/3 succeeded."

Fix the truth surface so:

- plan summaries know total planned tasks and groups
- later groups can be `pending` or `blocked`
- a plan is not "complete" until all planned groups are terminal
- partial dispatch is surfaced as partial, not as success

Important constraints:

- do not add blocking waits inside `spawn_parallel()`
- do not hide Group 2 by silently counting only spawned colonies
- do not build a full new workflow engine
- if Track A lands `workspace_roots.py`, use it in `queen_tools.py`
  rather than re-deriving workspace paths locally

Owned files:

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

Validation:

- `python -m pytest tests/unit/surface/test_parallel_planning.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/surface/test_runtime.py -q`
- `python -m pytest tests/unit/surface/test_queen_budget.py -q`

## Track C: Codebase-Index Activation + Real-Repo Task Pack

Goal:

Make the existing codebase-index addon truthful on real project roots and
define the benchmark pack that Wave 81 and Wave 82 will both use.

Implementation shape:

### 1. Codebase-index status truth

Once Track A makes `workspace_root_fn` truthful, codebase-index becomes
useful. This track should make its status truthful too.

Upgrade `src/formicos/addons/codebase_index/status.py` so it can show:

- bound root path
- chunks indexed
- collection name
- last indexed time
- last indexed file/chunk/error counts
- unavailable / unbound states explicitly

Recommended implementation:

- persist a tiny per-workspace status sidecar under the data dir when
  reindex completes
- have `status.py` read both vector-store collection info and the sidecar

### 2. Reindex truth

Keep `handle_reindex()` and scheduled reindex behavior simple, but make
the result durable enough that the operator can see when indexing last
ran and what it covered.

### 3. Real-repo task pack

Write the canonical task-pack note for FormicOS-on-FormicOS evaluation:

- 3-5 concrete tasks
- each with scope, verification, and naming convention
- thread names prefixed `rtp-xx`

This note becomes the evaluation substrate for both Wave 81 and Wave 82.

Important constraints:

- do not add import-graph population yet
- do not add learned planning here
- keep the task pack small, concrete, and rerunnable

Owned files:

- `src/formicos/addons/codebase_index/indexer.py`
- `src/formicos/addons/codebase_index/status.py`
- `docs/waves/wave_81/real_repo_task_pack.md`
- `tests/unit/addons/test_codebase_index_status.py` (new)
- `tests/unit/addons/test_codebase_index_indexer.py` (new)

Validation:

- `python -m pytest tests/unit/addons/test_codebase_index_status.py -q`
- `python -m pytest tests/unit/addons/test_codebase_index_indexer.py -q`

## Track D: Operator-Visible Workspace Truth

Goal:

Make project truth, plan truth, and benchmark truth visible in-product.

Implementation shape:

### 1. Workspace truth

Update the workspace surface so it shows separate sections for:

- `Project Files` when a binding is active
- `Workspace Library`
- `Working Memory`
- `Artifacts`

The operator should never have to infer which tree they are looking at.

### 2. Binding + index status in Settings and Workspace

Surface:

- bound path
- binding mode
- code index status
- last indexed time
- reindex action

Reuse backend truth from Track A and Track C. Do not duplicate logic in
the frontend.

### 3. Plan-group truth

Upgrade active-plan and result surfaces so they can show:

- pending groups
- running groups
- blocked groups
- completed groups
- failed groups

This is the UI counterpart to Track B's runtime truth work.

### 4. Real-repo benchmark dashboard

Use the existing workspace outcomes route plus the `rtp-xx` thread/task
pack naming convention to show task-pack results in-product.

Minimum dashboard fields:

- task ID
- latest run status
- quality
- rounds
- time / cost
- verification pass indicator when available

Important constraints:

- do not build the full Wave 83 planning workbench yet
- do not hide blocked groups behind a simplified "3/3 succeeded" summary
- keep all new UI truth additive and compatible with Wave 82's explain-
  ability work

Owned files:

- `frontend/src/components/workspace-browser.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/fc-preview-card.ts`
- `frontend/src/components/fc-result-card.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/types.ts`

Validation:

- `cd frontend; npm run build`

Manual smoke:

- bound project shows up as `Project Files`
- workspace library still supports upload/ingest
- blocked later groups are visible before the operator opens logs
- code index status is visible in Settings and Workspace
- task-pack results are visible without log scraping

## Merge Order

Recommended order:

1. Track A
2. Track C
3. Track B
4. Track D

Why:

- Track A establishes the root-truth helpers used by later tracks
- Track C becomes immediately useful once Track A lands
- Track B should build on Track A's root helper and Track C's real-root
  indexing truth
- Track D should land last so it can render accepted backend truth

Parallel start:

- Track A and Track C can start together if Track C treats the new root
  helper name as the only dependency
- Track B should reread `workspace_roots.py` before touching
  `queen_tools.py`
- Track D should start with layout/state work but reread Track A/B/C
  output before finalizing labels and status handling

## What Is Already Landed

These fixes are in the working tree from the v6-v8 experiment session.
Tracks should preserve them and build on them, not revert or reimplement:

- shared-KV budget fix: `_num_slots = 1` in `queen_runtime.py` and
  `routes/api.py`
- colony start stagger: 200ms delay in `spawn_parallel()` Phase 2
- scope validation: `_validate_operator_scoped_coverage()` in
  `queen_tools.py` with file and group coverage checks
- recon follow-up: bounded single retry in `queen_runtime.py` for
  build tasks that stall after reconnaissance
- unified model config: `formicos.yaml` registry uses env-var
  interpolation for `context_window` and `max_concurrent`
- coder recipe tuning: execution-first prompt, `max_tokens: 4096`,
  `max_iterations: 15` in `caste_recipes.yaml`
- worker output cap: `min(recipe.max_tokens, model_rec.max_output_tokens)`
  in `runtime.py`

## What This Wave Explicitly Does Not Do

- no full per-workspace persisted binding model
- no import-graph or knowledge-graph population
- no workflow-learning feedback into planning brief patterns
- no replay-derived capability profiles yet
- no full pre-dispatch DAG editing workbench
- no stage-gated execution engine

## Post-Wave Validation

After Wave 81 lands:

1. bind FormicOS to its own repo with `PROJECT_DIR`
2. reindex the bound project
3. run the real-repo task pack from
   `docs/waves/wave_81/real_repo_task_pack.md`
4. review results in the product UI, not only in logs

Wave 81 is successful when the operator can see:

- the real project root
- the real plan state
- the real benchmark state

without leaving the product to reconstruct truth by hand.
