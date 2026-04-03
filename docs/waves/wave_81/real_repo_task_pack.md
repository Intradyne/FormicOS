# Wave 81 Real-Repo Task Pack

## Purpose

This task pack is the evaluation substrate for Wave 81 and Wave 82.

Use it after project binding is active so FormicOS is working on a real
codebase instead of the synthetic test-sentinel addon.

The pack is intentionally small, concrete, and rerunnable.

## Naming Convention

Create one thread per task with a stable `rtp-xx` prefix.

Examples:

- `rtp-01 checkpoint-tests`
- `rtp-02 codebase-index-status`
- `rtp-03 workspace-roots`

This lets the product surface task-pack outcomes using existing thread
and colony outcome truth.

## Task 1: `rtp-01 checkpoint-tests`

Goal:

Strengthen checkpoint coverage on real FormicOS code.

Scope:

- `src/formicos/surface/checkpoint.py`
- `tests/unit/surface/test_checkpoint.py`

Verification:

- `python -m pytest tests/unit/surface/test_checkpoint.py -q`

What this measures:

- ability to navigate an existing module
- targeted test writing
- safe repo-local changes

## Task 2: `rtp-02 codebase-index-status`

Goal:

Improve codebase-index status truth for a bound real repo.

Scope:

- `src/formicos/addons/codebase_index/status.py`
- `src/formicos/addons/codebase_index/indexer.py`

Verification:

- status surface shows bound root
- status surface shows last indexed time
- code index reports non-zero chunks after reindex on the bound repo

What this measures:

- real-project indexing
- addon/runtime integration
- operator-visible status truth

## Task 3: `rtp-03 workspace-roots`

Goal:

Consolidate runtime root resolution around one shared helper and expose
project-file truth through the API.

Scope:

- `src/formicos/surface/workspace_roots.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/colony_io.py`

Verification:

- bound project root is returned when present
- workspace library remains intact
- project-file route lists real repo files

What this measures:

- multi-file refactor on a live seam
- correctness of project vs library separation

## Task 4: `rtp-04 parallel-group-truth`

Goal:

Fix later-group execution truth for parallel plans (backend).

Scope:

- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/parallel_plans.py`

Verification:

- later groups defer instead of failing immediately
- aggregated summary reflects total planned tasks, not only spawned
- `python -m pytest tests/unit/surface/test_parallel_planning.py -q`

What this measures:

- runtime-state reasoning
- deferred execution correctness

Note: the UI counterpart (blocked/pending groups in `queen-overview.ts`)
is part of Track D and should be verified after both Track B and Track D
land.

## Task 4b: `rtp-04b parallel-group-ui`

Goal:

Surface blocked/pending group truth in the operator UI.

Scope:

- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/fc-result-card.ts`

Verification:

- active plan surface shows blocked / pending / completed groups
- result cards do not collapse partial plans into simple success

What this measures:

- backend/frontend truth alignment
- operator-visible plan state

Prerequisite: Track B (rtp-04) must land first.

## Task 5: `rtp-05 ssrf-guard-adoption`

Goal:

Route one more external-fetch path through the shared SSRF guard and
cover it with tests.

Scope:

- `src/formicos/surface/ssrf_validate.py`
- one live caller, e.g. `src/formicos/adapters/egress_gateway.py` or
  `src/formicos/adapters/fetch_pipeline.py` (forager fetch paths)
- `tests/unit/surface/test_ssrf_validate.py`

Verification:

- relevant unit tests pass
- allowed local paths still work
- blocked private/unsafe targets fail explicitly

What this measures:

- security-sensitive refactoring
- targeted reasoning about existing runtime paths

## Evaluation Fields

For each task-pack run, capture:

- thread ID / task ID
- plan size
- whether scope coverage was correct
- final status
- average quality
- rounds
- total time
- verification pass/fail

The product UI should surface these results without requiring log
inspection.

## Why This Pack Exists

The synthetic addon benchmark taught us a lot about infrastructure, but
it stopped teaching us about real planning quality.

This pack forces evaluation on:

- real files
- real imports
- real tests
- real UI truth

That is the point of Wave 81.
