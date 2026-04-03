# Wave 87 Team C Prompt

## Mission

Harden the runtime enough that panel zero can be used daily without
repeating the two most visible failures from the last session:

- ballooning operator snapshots
- fresh-thread prose instead of delegation

This track also re-verifies the already-landed learning-loop wiring
fixes without reopening them unnecessarily.

## Owned Files

- `src/formicos/surface/view_state.py`
- `src/formicos/surface/planning_policy.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_policy.py`
- `tests/unit/surface/test_routing_agreement.py`
- `tests/unit/surface/test_snapshot_fields.py`
- `tests/unit/surface/test_snapshot_routing.py`
- `tests/unit/surface/test_queen_runtime.py`
- `tests/unit/surface/test_toolset_classifier.py`
- `tests/eval/queen_planning_eval.py` if the deterministic prompt surface
  needs to reflect capability mode
- any small new targeted tests for cold-start delegation

## Do Not Touch

- addon package files owned by Team A
- frontend files owned by Team B
- full lifecycle/workstream architecture
- playbook provenance

## Repo Truth To Read First

1. `view_state.py`
   Snapshot construction is global and unbounded today. It includes:
   - all workspaces
   - all threads
   - all colonies
   - full colony chat messages
   - full round history
   - full Queen thread messages

2. `projections.py`
   Thread status already supports `archived`, so archived threads can be
   skipped cheaply.

3. `queen_runtime.py`
   Cold-start narrowing already exists, but:
   - `_is_colony_turn` is blocked by any `?`
   - the Queen path does not yet require tool use on the first narrowed turn

4. `planning_policy.py`
   The current decision object only models colony execution modes:
   - `fast_path`
   - `single_colony`
   - `parallel_dag`

   This is too narrow for the current tool surface.

5. `runtime.py` and adapters
   The `tool_choice` seam already exists. This should be a Queen wiring
   change, not an adapter project.

6. `plan_patterns.py` and `colony_manager.py`
   The learning-loop wiring fixes are already in source. This track should
   verify and preserve them, not re-scope them as new work unless drift is
   discovered.

## What To Build

### 1. Extend `PlanningDecision` to the durability ladder

Add a higher-level capability mode to planning policy:

- `reply`
- `inspect`
- `edit`
- `execute`
- `host`
- `operate`

Keep `route` as the execution-mode choice inside `execute`.

This is the policy doctrine that keeps the Queen from overusing the
strongest available primitive, whether that is colonies now or addons
later.

### 2. Add deterministic policy tests for the ladder

Add or extend golden tests so prompts land on the expected capability
mode, for example:

- status / explanation -> `reply` or `inspect`
- bounded file fix -> `edit`
- repo audit / multi-step implementation -> `execute`
- dashboard request -> `host`
- hosted + persistent + integration-heavy request -> `operate`

The goal is stable instrument selection, not fuzzy aspiration.

### 3. Use capability mode to scope Queen behavior

Wire the new policy output into `_respond_inner()` so the Queen's tool
surface is scoped to the right level before route-specific logic kicks in.

Important:

- do not create a new tool orchestration subsystem
- do not require fully autonomous addon generation in this wave
- use the policy to prevent overreach

### 4. Ship the quick bounded-snapshot cap

In `view_state.py`:

- skip archived threads by default
- cap per-thread colonies to the most recent 20

Use existing projection timestamps/recency fields. Favor a stable,
truthful recency order.

This is intentionally the quick operational cap, not the full lifecycle
refactor.

### 5. Expose the new addon panel refresh field through the snapshot

Team A will preserve `refresh_interval_s` in addon registration.

Your job is to expose it through the snapshot shape so Team B can consume
it in the frontend.

Keep the field additive and backward-compatible.

### 6. Replace the raw `?` gate with a truthful helper

The colony path should not be suppressed merely because the operator used
polite punctuation.

Implement a helper that suppresses colony pressure only for genuine
informational questions, not for requests like:

- `can you fix ...?`
- `could you audit ...?`
- `would you add ...?`

### 7. Require tool use on the first narrowed fresh-thread turn

When:

- the thread is truly fresh for the Queen path
- `_colony_narrowed` is true

pass `tool_choice="required"` into the Queen completion call so the
model cannot answer with prose alone.

Keep the enforcement narrowly scoped to this cold-start delegation case.

### 8. Re-verify the learning-loop wiring fixes

Confirm that current source still preserves:

- `task_previews` / `tasks` fallback
- `groups` / `parallel_groups` fallback
- relaxed single-colony `spawn_source` gate
- verification gate logging

Only patch these if repo truth has drifted.

## Constraints

- Do not turn the snapshot cap into a bigger lifecycle redesign.
- Do not force tool use globally for all Queen turns.
- Do not remove existing recon/intention fallbacks.
- Keep all changes additive and replay-safe.
- Do not turn `host` or `operate` into a demand for fully autonomous
  addon/service creation in this wave. The ladder is policy first.

## Validation

- `python -m pytest tests/unit/surface/test_planning_policy.py -q`
- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`
- `python -m pytest tests/unit/surface/test_snapshot_fields.py -q`
- `python -m pytest tests/unit/surface/test_snapshot_routing.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/surface/test_toolset_classifier.py -q`

Add targeted tests for:

- capability-mode golden prompts across the durability ladder
- archived threads excluded from default snapshot
- per-thread colony cap behavior
- polite-question implementation prompts still entering the colony path
- `tool_choice="required"` on the first narrowed fresh-thread turn

## Overlap Note

- Team A owns addon registration of the new refresh field.
- Team B owns frontend consumption of the field.
- You own the snapshot contract exposure and runtime hardening.
