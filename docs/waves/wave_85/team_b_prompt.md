# Wave 85 Team B Prompt

## Mission

Make `planning_policy.py` the live Queen routing seam and upgrade the eval
layer so it measures actual route changes instead of assuming routing stays
stable across signal configs.

This is the production-routing plus measurement track. Team A owns signal
quality in the planning brief.

## Owned Files

- `src/formicos/surface/planning_policy.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_policy.py`
- `tests/unit/surface/test_routing_agreement.py`
- `tests/eval/queen_planning_eval.py`
- `tests/eval/test_planning_ablation.py`
- `pyproject.toml` if needed for marker registration

## Do Not Touch

- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- frontend files
- worker-loop or runner files
- graph reflection / knowledge graph code

## Repo Truth To Read First

1. `src/formicos/surface/planning_policy.py`
   `decide_planning_route()` exists and already wraps:
   - `classify_task()`
   - `classify_complexity()`
   - `_looks_like_colony_work()`
   - `_prefer_single_colony_route()`
   - playbook hints

2. `src/formicos/surface/queen_runtime.py`
   The live respond path still uses the older scattered helpers directly.
   This is the key seam to fix.

3. `tests/eval/queen_planning_eval.py`
   The deterministic layer exists. The live layer is still a placeholder
   skip and is not exercising the live Queen path.

4. `tests/eval/test_planning_ablation.py`
   It currently asserts route stability across all configs. That assumption
   must be removed once the policy object is live.

5. `tests/unit/surface/test_routing_agreement.py`
   This is the right place to protect the classifier/policy seam from drift.

## What To Build

### 1. Wire planning_policy into the live Queen path

Call `decide_planning_route()` ONCE, early in the respond path inside
`queen_runtime.py` (around line 1290, where `_relevant_toolsets` is
computed). Use the `PlanningDecision` object to drive:

- `_prefer_direct_spawn` (from `decision.route == "single_colony"`)
- `_colony_narrowed` (from `decision.route != "fast_path"` and colony
  markers)
- the planning directive insertion (from `decision.complexity`)

Keep the existing scattered helper calls as INTERNAL ingredients of
`decide_planning_route()` — they already are. The respond path should
stop calling `classify_complexity()`, `_looks_like_colony_work()`, and
`_prefer_single_colony_route()` directly for routing decisions.

Important:

- keep the existing helper functions intact as policy ingredients
- keep route semantics close to the validated Wave 84 Qwen path unless a
  test explicitly proves a better route
- do not turn capability behavior flags into aggressive live route flips
  in this wave
- do not refactor every call site in one pass — focus on the routing
  decision block (lines ~1326-1395) and leave defensive guards elsewhere

The main win is not "new magic routing." It is making one tested policy
object the live authority instead of leaving production behavior scattered.

### 2. Make policy output observable in tests

Strengthen `tests/unit/surface/test_planning_policy.py` and
`tests/unit/surface/test_routing_agreement.py` so they protect:

- task class
- complexity
- route
- playbook override behavior
- any bounded behavior-flag handling you keep live

### 3. Upgrade queen_planning_eval.py

The deterministic eval should score the actual policy seam.

Do not keep reconstructing route solely from the old helper trio if the
live path now goes through `PlanningDecision`.

### 4. Replace the live placeholder with a real bounded smoke

Keep it optional behind `FORMICOS_LIVE_EVAL=1`, but do not leave it as:

- placeholder skip
- fake smoke

The live test can stay narrow. It only needs to prove that a real Queen
planning call can be captured and scored through the same harness.

### 5. Fix the ablation contract

Update `tests/eval/test_planning_ablation.py` so it no longer asserts
that all configs must produce the same route.

Instead:

- assert signal availability truthfully
- capture route and structure differences
- report when added signals do or do not change route
- keep the deterministic path fast and fixture-backed by default

### 6. Register the live_eval marker

Remove the `PytestUnknownMarkWarning` by registering `live_eval`.

## Constraints

- Do not rewrite the whole Queen respond loop.
- Do not make graph work part of this track.
- Do not introduce large behavior-flag-driven policy changes without tests.
- Do not depend on Team A changing the shape of saved-pattern retrieval;
  only reread their final compact signal fields before you finalize eval
  assertions.

## Validation

- `python -m pytest tests/unit/surface/test_planning_policy.py -q`
- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`
- `python -m pytest tests/eval/queen_planning_eval.py -q`
- `python -m pytest tests/eval/test_planning_ablation.py -q`

If you implement the live smoke:

- run the smallest bounded live command path that proves the live eval is
  no longer a placeholder

## Overlap Note

Team A owns the planning-signal payload. Reread their final compact
structural and saved-pattern fields before you freeze any eval expectations.
