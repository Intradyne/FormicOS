# Wave 82 Plan: Visible Learning Planner

## Summary

Wave 82 should make FormicOS learn from real planning outcomes, ground
those plans in real project structure, and expose the resulting
reasoning to the operator before dispatch.

This wave has four tracks:

- Track A: learned planning signals
- Track B: structural planner
- Track C: replay-derived capability calibration
- Track D: visible learning planner

The goal is not a new planner subsystem. The goal is to connect the
existing planner, knowledge graph, replay state, and UI into one visible
planning loop.

Wave 81 leaves Wave 82 with three important live seams:

- real project binding and project-file truth
- `parallel_plans.py` for honest deferred-group execution state
- `thread-view.ts` + `workflow-view.ts` for already-visible DAG truth

Two more runtime truths now matter for dispatch:

- natural operator verbs like `improve`, `strengthen`, `write`, and
  `cover` now hit the colony path, so the real-repo task pack no longer
  depends on operator-side rephrasing
- the project-binding endpoint and code-index status are live and
  populated, so Wave 82 can treat indexed real-repo truth as a real seam

Wave 82 should extend those seams, not route around them.

## Shared Evaluation Substrate

Wave 82 should reuse the real-repo task pack from Wave 81:

- `docs/waves/wave_81/real_repo_task_pack.md`

That keeps evaluation honest:

- Wave 81: can FormicOS act on real code truthfully?
- Wave 82: does learned + structural planning improve the same real
  tasks?

Current status:

- `rtp-01` already validated end-to-end real-code stack behavior
- `rtp-02` through `rtp-05` are the active task-pack run set

## Track A: Learned Planning Signals

Goal:

Turn planning inputs into a structured signal surface that can be reused
by the Queen, persisted for replay, and rendered by the UI.

Implementation shape:

### 1. Add a structured planning-signals helper

Create:

- `src/formicos/surface/planning_signals.py`

Recommended public API:

```python
async def build_planning_signals(
    runtime,
    workspace_id: str,
    thread_id: str,
    operator_message: str,
) -> dict[str, Any]: ...
```

Recommended returned shape:

```python
{
    "patterns": [...],
    "playbook": {...} | None,
    "capability": {...} | None,
    "coupling": {...} | None,
    "previous_plans": [...],
}
```

This helper is the structured source of truth.
`planning_brief.py` should become a formatting layer over it, not a
one-off signal assembler forever.

### 2. Extend workflow learning with a read path

Keep the existing proposal-writing behavior in
`workflow_learning.py`, but add a planning-side read helper such as:

```python
def get_relevant_outcomes(
    projections,
    *,
    workspace_id: str,
    operator_message: str,
    planner_model: str,
    worker_model: str,
    top_k: int = 3,
) -> list[dict[str, Any]]: ...
```

Minimum fields the helper should surface:

- task/category hint
- colony count
- group count
- strategy
- average quality
- rounds
- success rate
- planner model
- worker model
- short reason/evidence string

Important rule:

- if learned data is sparse, degrade cleanly to Wave 80 behavior

### 3. Persist planning provenance on plan creation

Recent waves already proved that the UI needs plan truth, not just
result truth. `ParallelPlanCreated` already carries the plan, groups,
reasoning, and estimated cost; this track should add the missing
planning-context fields instead of creating a second event.

Add additive fields on `ParallelPlanCreated` so the plan can be replayed
with its planning context intact.

Recommended new optional fields:

- `planner_model: str = ""`
- `planning_signals: dict[str, Any] = Field(default_factory=dict)`

Mirror these through:

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/projections.py`

The goal is not to persist every token. The goal is to persist the
signals the operator should later be able to inspect.

### 4. Expose compare-ready planning history

Add a thin backend route that returns similar successful prior plans for
the current task.

Recommended route:

- `GET /api/v1/workspaces/{id}/planning-history?query=...&top_k=3`

Return compact compare objects, not full transcripts.

Important constraints:

- no new LLM calls
- no new external memory system
- no prompt-dump planning context
- the brief remains tiny even if the structured signal object is richer

Owned files:

- `src/formicos/surface/planning_signals.py` (new)
- `src/formicos/surface/workflow_learning.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/api.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `tests/unit/surface/test_workflow_learning.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_plan_read_endpoint.py`
- `tests/unit/surface/test_queen_runtime.py`

Validation:

- `python -m pytest tests/unit/surface/test_workflow_learning.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_plan_read_endpoint.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`

## Track B: Structural Planner

Goal:

Make project structure a first-class planning signal by using the real
project root, the existing code-analysis seam, and the existing
knowledge graph.

Implementation shape:

### 1. Add a structural-planner helper

Create:

- `src/formicos/surface/structural_planner.py`

Recommended public API:

```python
def get_structural_hints(
    runtime,
    workspace_id: str,
    operator_message: str,
    *,
    max_groups: int = 3,
) -> dict[str, Any]: ...
```

Recommended output shape:

```python
{
    "matched_files": [...],
    "coupling_pairs": [...],
    "suggested_groups": [
        {"label": "...", "files": [...], "confidence": 0.0, "reason": "..."},
    ],
}
```

### 2. Reflect project structure into the knowledge graph

Use the bound project root from Wave 81 and the existing
`code_analysis.py` output to create or update:

- `MODULE` entities
- `DEPENDS_ON` edges

Do not build a parallel graph.
Do not wait for perfect tree-sitter coverage.
The goal is better planning signals from the repo FormicOS already has.

### 3. Feed proved structure into planning

`planning_signals.py` from Track A should consume your helper.

The structural signal should be useful enough to replace most
reconnaissance-only `ls`/`find` behavior on common coding tasks.

The codebase index is now live and populated, but the core structural
planner should still derive its truth from deterministic project-root
analysis plus the knowledge graph. Search readiness is a supporting
seam, not the source of truth.

### 4. Prefer omission over speculation

If a relationship cannot be proved from the current project root, omit
it. Do not fill the coupling line with weak guesses just to populate the
UI.

Important constraints:

- use the Wave 81 project root helpers
- do not invent a second repo-index format
- do not rewrite the existing codebase-index addon
- do not build a full automatic grouping engine yet

Owned files:

- `src/formicos/adapters/code_analysis.py`
- `src/formicos/adapters/knowledge_graph.py`
- `src/formicos/surface/structural_planner.py` (new)
- `tests/unit/adapters/test_code_analysis.py`
- `tests/unit/surface/test_structural_planner.py` (new)
- `tests/unit/surface/test_knowledge_catalog.py`

Validation:

- `python -m pytest tests/unit/adapters/test_code_analysis.py -q`
- `python -m pytest tests/unit/surface/test_structural_planner.py -q`
- `python -m pytest tests/unit/surface/test_knowledge_catalog.py -q`

## Track C: Replay-Derived Capability Calibration

Goal:

Turn capability profiles from shipped priors into learned overlays
derived from replay truth.

Implementation shape:

### 1. Keep shipped priors, but stop treating them as the final truth

`config/capability_profiles.json` remains the bootstrap.

`src/formicos/surface/capability_profiles.py` should merge:

- shipped priors
- replay-derived overlays from recent real colony outcomes

Replay truth should be the authority when enough evidence exists.

### 2. Key capability by planner + worker + granularity

Do not summarize only by worker model.

The minimum useful key is:

- planner model
- worker model
- task class
- granularity bucket

Recommended granularity buckets:

- `focused_single`
- `fine_split`
- `grouped_small`
- `grouped_medium`

### 3. Surface evidence, not just advice

Capability summaries should include:

- sample count
- quality mean
- rounds mean
- confidence label or evidence tier

The summary line in the planning brief can stay short, but the provider
should return structured evidence for the UI.

### 4. Avoid side-file truth drift

Do not make a mutable runtime JSON file the source of truth.

Replay-derived state should be the truth.
A cache file is acceptable only as an optimization and only if it can be
fully regenerated.

Owned files:

- `src/formicos/surface/capability_profiles.py`
- `config/capability_profiles.json`
- `tests/unit/surface/test_capability_profiles.py`
- `tests/unit/surface/test_projections_w11.py`

Validation:

- `python -m pytest tests/unit/surface/test_capability_profiles.py -q`
- `python -m pytest tests/unit/surface/test_projections_w11.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`

## Track D: Visible Learning Planner

Goal:

Make learned and structural planning visible to the operator and land
the minimal pre-dispatch correction slice that should not wait for Wave
83.

Implementation shape:

### 1. Add a real parallel-plan preview surface

The repo no longer starts from "no plan UI." `thread-view.ts` and
`workflow-view.ts` already render active DAGs, and `queen-chat.ts`
already renders structured preview/result cards. The gap is that these
surfaces are not yet one coherent, explainable, lightly editable
planning experience.

Add a true pre-dispatch parallel preview path by extending the existing
surfaces, not by creating an isolated plan-only island.

Recommended additions:

- `parallel_preview` render type, or
- an explicit `spawn_parallel` branch inside preview-card rendering, or
- reusing `fc-workflow-view` as the canonical DAG renderer inside the
  preview path

The preview must show:

- groups and tasks
- expected outputs
- target files
- dependencies
- why-this-plan signals
- previous-plan comparison summary

That means the current frontend `DelegationTaskPreview` shape is too
thin for this wave. Track D should extend the preview task type to carry
the minimum plan fields the UI must render truthfully:

- `strategy`
- `depends_on`
- `expected_outputs`
- `target_files`
- existing `task_id` / `task` / `caste` / `colony_id`

### 2. Show "Why this plan"

Render the structured planning signals from Track A:

- matched pattern(s)
- playbook hint
- capability signal
- structural groups/coupling
- previous successful plan comparison

The operator should be able to tell whether a plan is grounded,
speculative, or thinly supported.

### 3. Land the minimal correction slice

Before dispatch, the operator should be able to:

- edit a colony task text
- move a target file between colonies
- accept/reject the plan
- compare to a previous successful plan

This is not the full Wave 83 workbench.
It is the smallest useful steering surface.

Important live seam:

- `workflow-view.ts` already emits `edit-plan`
- `thread-view.ts` already forwards that event
- today that path only does a best-effort `config-overrides` write

Wave 82 should replace that placeholder with a deterministic
reviewed-plan path. `config-overrides` is a settings surface, not a plan
editing substrate, and should not become the long-term dispatch path.

### 4. Confirm the actual parallel preview deterministically

The current preview confirm path in `formicos-app.ts` only dispatches
single-colony previews. Parallel plans already have better truth on the
active-plan side than they do on the preview-confirm side.

Add a thin dispatch path for previewed parallel plans so the frontend
does not have to ask the Queen again in prose.

Preferred shape:

- a small WS action / command handler that dispatches a reviewed
  `DelegationPlan`
- reuse Wave 81 parallel-plan truth/sequencing helpers rather than
  reimplementing dispatch logic in the UI

### 5. Keep plan and result truth aligned

Use the Wave 81 group-state truth so the operator can see:

- pending groups
- running groups
- blocked groups
- completed groups
- failed groups

Do not let the planning UI look richer than the execution UI.

Important constraints:

- do not build the full drag-and-drop workbench yet
- do not invent frontend-only plan heuristics
- do not round-trip acceptance through vague Queen prose if a deterministic
  preview-dispatch path is available

Owned files:

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

Validation:

- `cd frontend; npm run build`
- `python -m pytest tests/unit/surface/test_ws_handler.py -q`

Manual smoke:

1. a parallel preview shows groups, files, and signals before dispatch
2. the operator can make a small correction before dispatch
3. confirming a reviewed parallel preview dispatches that plan, not a
   new Queen improvisation
4. active-plan and result UI agree about pending/blocked/completed group
   truth

## Merge Order

Recommended order:

1. Track B
2. Track A
3. Track C
4. Track D

Parallel start:

- Track B can start immediately
- Track A can start once Track B's structural helper name is frozen
- Track C should wait for Track A's planning/projection contract to
  freeze
- Track D can begin immediately on workflow-view / thread-view /
  queen-chat convergence and reviewed-plan interaction seams, but should
  finalize labels and payload rendering only after Track A's signal
  payload and compare route are stable

## What This Wave Explicitly Does Not Do

- no new planner microservice
- no second graph subsystem
- no full Wave 83 workbench
- no delegator-only runtime charter
- no giant planning prompt
- no host/project-binding redesign beyond Wave 81
- no new benchmark pack

## Post-Wave Validation

After Wave 82 lands, rerun the Wave 81 real-repo task pack on the same
workspace and compare against the Wave 81 baseline.

Success target:

- planning explanations are visible in-product
- plan corrections can happen before dispatch
- preview, active-plan, and result surfaces agree about group truth
- structural hints reduce reconnaissance-only turns
- learned patterns and replay-derived capability summaries improve plan
  quality or reduce avoidable mis-grouping on the same real tasks
