# Wave 86 Team A Prompt

## Mission

Teach FormicOS to learn decomposition patterns from validated success,
while using the same validation seam to improve completion truth.

This is not a new subsystem. It extends existing outcome learning,
validator truth, contract truth, and plan-pattern persistence.

## Owned Files

- `src/formicos/surface/plan_patterns.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/colony_manager.py`
- `tests/unit/surface/test_plan_patterns.py`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_queen_runtime.py`
- `tests/unit/surface/test_colony_manager.py`

## Do Not Touch

- graph bridge files owned by Team B
- worker loop / `runner.py`
- frontend files
- playbook loader / playbook ranking logic

## Repo Truth To Read First

1. `plan_patterns.py`
   The store exists and is backward-compatible YAML. It currently has no
   trust/status semantics.

2. `projections.py`
   `thread.active_plan`, `parallel_groups`, and `colony_outcomes` are the
   durable seams that survive restart/replay.

3. `queen_runtime.py`
   Parallel-plan completion already funnels through `_emit_parallel_summary()`.
   Do not rely on `_pending_parallel` alone; use persisted plan/projection
   state for learning decisions.

4. `colony_manager.py`
   There are already nearby learning hooks:
   - auto-template creation
   - trajectory extraction
   - playbook proposal

5. `queen_runtime.py` and `colony_manager.py`
   Validator, contract, and productivity truth already flow through result
   metadata and projections.

## What To Build

### 1. Add additive trust fields to plan patterns

Extend the persisted pattern shape in a backward-compatible way.

Good additive fields:

- `status`: `approved` | `candidate`
- `learning_source`: `operator` | `auto`
- `evidence`: compact counters / summary

Existing operator-saved patterns should continue to behave as approved if
no new status is present.

### 2. Build one eligibility/verification helper

Create one helper that evaluates a result or plan outcome using existing
truth only:

- quality
- validator verdict
- contract satisfaction
- productive vs total calls
- failure presence for parallel plans

The helper should return something like:

- verification state (`validated`, `needs_review`, `failed_delivery`)
- learnable / not learnable
- compact reasons

Do not build a second verification subsystem.

### 3. Auto-save candidate patterns from validated success

Parallel plans:

- use durable plan data plus colony outcomes
- save only when the plan passes conservative learning gates

Single-colony / fast_path:

- only learn from clearly strong validated runs

### 4. Deduplicate by deterministic bundle

Do not create a new pattern file for every near-duplicate run.

Derive a deterministic bundle from persisted structure, for example:

- task class
- route kind
- normalized target files
- group count / colony count

Use that to update/promote existing candidate patterns instead of spraying
duplicates.

### 5. Promote cautiously

Do not make first-sighting auto-learned patterns fully trusted.

Safe target behavior:

- first learnable success -> candidate
- repeated learnable success for same bundle -> approved / learned

### 6. Keep planning retrieval safe

Update planning-signal retrieval so approved/operator patterns remain the
default trusted path.

If you surface candidate patterns at all, they must be visibly marked as
candidate and must not silently outrank approved patterns.

### 7. Improve completion truth

Use the same helper to enrich completion truth:

- single-colony result metadata
- parallel summary aggregation
- operator-facing `needs review` semantics

Do not add new event types.

## Constraints

- Do not depend on `_pending_parallel` alone.
- Do not learn from mediocre or validator-failed runs.
- Do not treat `expected_outputs` as guaranteed file paths.
- Do not implement playbook-quality tracking here.
- Keep new pattern fields additive and replay-safe.

## Validation

- `python -m pytest tests/unit/surface/test_plan_patterns.py -q`
- `python -m pytest tests/unit/surface/test_planning_signals.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/surface/test_colony_manager.py -q`

## Overlap Note

Team B may reread any new pattern trust fields if they become relevant to
retrieval diagnostics, but Team B does not own plan-pattern persistence.
