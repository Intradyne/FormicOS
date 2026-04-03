# Wave 82 Team C Prompt

## Mission

Turn capability profiles into replay-derived overlays over shipped
priors.

This is the track that makes the planner adapt automatically as models
change without making mutable JSON files the source of truth.

## Owned Files

- `src/formicos/surface/capability_profiles.py`
- `config/capability_profiles.json`
- `tests/unit/surface/test_capability_profiles.py`
- `tests/unit/surface/test_projections_w11.py`

## Do Not Touch

- `src/formicos/surface/workflow_learning.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/adapters/code_analysis.py`
- frontend components

Track A owns the planning-signal contract.
Track B owns structural hints.
Track D owns explainability and correction UI.

## Repo Truth To Read First

1. `src/formicos/surface/capability_profiles.py`
   It currently loads shipped JSON plus an optional runtime override.
   That is a good bootstrap, but not enough for a compounding planner.

2. `src/formicos/surface/projections.py`
   Replay already derives colony outcomes, model assignments, rounds,
   costs, and quality. Consume replay truth instead of inventing a side
   database.

3. `src/formicos/surface/planning_brief.py`
   The brief only needs a short summary line, but your provider should
   return richer evidence for Track A and Track D.

4. `src/formicos/core/events.py` and Track A's plan provenance work
   Planner-model truth should come from replayable plan/event data once
   Track A lands it, not from a UI guess or mutable runtime cache.

## What To Build

### 1. Merge priors with replay-derived overlays

Keep `config/capability_profiles.json` as the bootstrap source, but make
the provider merge it with replay-derived observations.

Replay is the truth.
The shipped file is the prior.

### 2. Key capability by planner + worker + granularity

Do not summarize only by worker model.

At minimum, capability should be keyed by:

- planner model
- worker model
- task class
- granularity bucket

Recommended buckets:

- `focused_single`
- `fine_split`
- `grouped_small`
- `grouped_medium`

Important live seam:

- planner-model truth should come from Track A's additive
  `ParallelPlanCreated.planner_model`
- worker-model truth is not currently a first-class field on the colony
  projection; derive it from replayed model-usage maps
- in practice, use the dominant non-planner model from colony budget
  usage (`budget_truth.model_usage` / emitted `model_usage`) by highest
  token volume rather than searching for a nonexistent `worker_model`
  field

### 3. Surface evidence

Return structured evidence, not just a one-line sentence:

- sample count
- average quality
- average rounds
- confidence or evidence tier
- notable warnings

Track A can format the short brief line.
Track D can render the fuller evidence.

### 4. Avoid side-file truth drift

Do not make an override file the source of truth.
If you add caching, it must be optional and fully replay-regenerable.

## Important Constraints

- No new external database
- No runtime-only truth that disappears on replay
- No giant matrix UI work in this track
- Keep the provider deterministic

## Validation

Run:

- `python -m pytest tests/unit/surface/test_capability_profiles.py -q`
- `python -m pytest tests/unit/surface/test_projections_w11.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`

## Overlap Note

You are not alone in the codebase.

- Track A will consume your structured capability summary
- Track D will render your evidence

Keep the public API tight so the rest of the wave can depend on it
without re-reading your internals.
