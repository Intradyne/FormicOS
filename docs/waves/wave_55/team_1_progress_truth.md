# Team 1: Progress Truth

You own the backend progress and governance seams.

Your job is to make stall detection truthful for:
- file-writing coding colonies
- planning-heavy colonies
- research/review/design colonies

This is **Progress Truth**, not just coder-centric convergence.

## Mission

Fix false stall detection so productive colonies are not mislabeled and prematurely halted.

Phase 0 v2 proved the problem:
- `api-design` failed with a governance halt at round 6
- wall time was only about 10 seconds
- the task likely needed planning/research time before code artifacts appeared

The current convergence path is too text-similarity-driven and too narrow about what counts as progress.

## Read first

1. `src/formicos/engine/runner.py` lines covering:
   - round summary construction
   - convergence computation
   - governance evaluation
2. `src/formicos/engine/runner.py` tool category constants for productive vs observation tools
3. `src/formicos/engine/runner_types.py`
4. `src/formicos/surface/colony_manager.py` only around stall/governance interaction

## Required change

Introduce a broader **round_had_progress** signal and thread it into convergence/governance.

At minimum, a round should count as having progress when **any** of these are true:
- productive tool calls occurred
- substantive routed-output change occurred from the previous round
- knowledge was accessed and changed the colony’s evidence base

The point is not to blindly bless all activity.
The point is to distinguish:
- real work
- from spin

## Required implementation shape

### 1. Broaden convergence inputs

Add a `round_had_progress` boolean parameter to the convergence helpers in `runner.py`.

When `round_had_progress` is true:
- apply a small progress floor
- prevent identical-looking summaries from automatically collapsing into `progress < 0.01`

Keep genuine stall detection intact for observation spam.

### 2. Broaden the positive governance escape hatch

The current completion escape hatch is too dependent on `code_execute`.

Broaden it so a stalled colony can still complete when there was recent **successful productive action**, not only successful `code_execute`.

That should include truthful workspace/code progress, not just text.

### 3. Make the signal task-type aware in spirit, but keep implementation small

Do not build a new subsystem.

Use a compact boolean based on existing information already available in the runner:
- productive tool counts
- routed output changes
- knowledge access

This should be an additive refinement, not a redesign.

## Acceptance bar

1. A colony that writes files productively across rounds is not falsely marked stalled.
2. A planning-heavy colony like `api-design` no longer false-halts purely because early rounds are text-heavy.
3. A colony that only observation-spams is still classified as stalled.
4. The widened governance path does not create easy false-positive completion.
5. Simple fast-path tasks do not regress.

## Owned files

- `src/formicos/engine/runner.py`
- `src/formicos/engine/runner_types.py` if needed
- `src/formicos/surface/colony_manager.py` only if strictly required for stall/governance plumbing
- targeted tests under `tests/unit/engine/` and nearby backend seams

## Do not touch

- frontend files
- quality formula weights
- playbook loader or playbook YAML files
- event types
- `projections.py`
- `view_state.py`
- `routes/api.py`

## Validation

Run focused backend validation only.

At minimum:
- productive coding colony no longer stalls
- planning-heavy colony no longer false-halts
- observation loop still stalls

If you use pytest, keep it targeted to touched seams.

## Summary must include

- exact definition of `round_had_progress`
- exact rule for “recent successful productive action”
- what still counts as a true stall
- whether `api-design`-style false halts are addressed
- any tests added or updated
