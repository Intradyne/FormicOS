# Wave 82 Team A Prompt

## Mission

Turn the planning brief into a structured, replay-friendly signal
surface instead of a one-off string builder.

This is the track that makes learning visible and comparable.

## Owned Files

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

## Do Not Touch

- `src/formicos/adapters/code_analysis.py`
- `src/formicos/adapters/knowledge_graph.py`
- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/capability_profiles.py`
- frontend components

Track B owns structural hints.
Track C owns capability calibration.
Track D owns the UI and preview-dispatch interaction.

## Repo Truth To Read First

1. `src/formicos/surface/planning_brief.py`
   The Wave 80 brief already exists. Your job is to make it consume a
   richer structured signal object, not replace it with another prompt.

2. `src/formicos/surface/workflow_learning.py`
   Today it only writes action-queue proposals. It needs a read path for
   planning-time outcomes.

3. `src/formicos/surface/projections.py`
   This is where replay-derived plan and outcome truth already lives.

4. `src/formicos/surface/queen_runtime.py`
   This is where preview/result metadata already flows onto `QueenMessage`
   events.

5. `src/formicos/surface/routes/api.py`
   There is already a thread-plan read path. Add compare/history truth
   here instead of inventing an unrelated service.

6. `src/formicos/surface/parallel_plans.py`
   Wave 81 already introduced honest plan/group lifecycle truth. Your
   provenance fields should reinforce that shared plan story, not create
   a second representation.

## What To Build

### 1. Structured planning signals

Create `src/formicos/surface/planning_signals.py` with one small public
entry point:

```python
async def build_planning_signals(runtime, workspace_id, thread_id, operator_message) -> dict[str, Any]:
    ...
```

The helper should return structured objects for:

- learned patterns
- playbook hint
- capability signal
- structural hint
- previous successful plans

### 2. Workflow-learning read path

Add a planning-side helper to `workflow_learning.py` that returns
relevant prior decompositions instead of only writing action proposals.

Minimum outputs:

- task/category hint
- colony count
- group count
- strategy
- average quality
- rounds
- success rate
- planner model
- worker model
- evidence string

### 3. Replay-safe plan provenance

Add additive fields on `ParallelPlanCreated` for:

- `planner_model`
- `planning_signals`

Mirror them through projections and contract docs.

Do not replace the existing `plan` / `parallel_groups` / `reasoning`
payload. Extend it.
Do not accidentally drop the existing `estimated_cost` event field while
extending the event and projection contract.

The UI must be able to ask later:

- what signals existed?
- what model planned this?
- what prior plans were compared?

Track D owns `frontend/src/types.ts`, but your contract/docs changes
must leave room for richer preview-task truth. Coordinate so previewed
plan tasks can carry the fields the UI needs to render:

- `strategy`
- `depends_on`
- `expected_outputs`
- `target_files`

### 4. Planning history compare route

Add a compact compare route:

- `GET /api/v1/workspaces/{id}/planning-history?query=...&top_k=3`

Return small compare objects, not raw transcripts.

## Important Constraints

- No new LLM calls
- No giant context block
- No second planner service
- Degrade cleanly when learned data is sparse
- Keep the existing brief tiny even if the structured signal object is richer

## Validation

Run:

- `python -m pytest tests/unit/surface/test_workflow_learning.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_plan_read_endpoint.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`

## Overlap Note

You are not alone in the codebase.

- Track B will expose structural hints; consume its public helper
  instead of recomputing structure here.
- Track C will expose richer capability summaries; keep your signal
  format ready for that provider.
- Track D will render your `planning_signals` payload. Keep the payload
  compact, typed, and stable.
