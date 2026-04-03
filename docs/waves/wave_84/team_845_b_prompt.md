# Wave 84.5 Team B Prompt

## Mission

Build the Queen-only eval harness, routing drift tests, and ablation
framework. This is the testing infrastructure that makes Queen
improvements measurable.

This track should land AFTER Team A so you can test the consolidated
routing policy and saved-pattern signal path.

## Owned Files

- `tests/eval/queen_planning_eval.py` (new)
- `tests/eval/test_planning_ablation.py` (new)
- `tests/eval/conftest.py` (new, if needed for fixtures)
- `tests/unit/surface/test_routing_agreement.py` (new)

## Do Not Touch

- `src/formicos/surface/planning_signals.py` (Team A)
- `src/formicos/surface/planning_brief.py` (Team A)
- `src/formicos/surface/planning_policy.py` (Team A)
- `src/formicos/surface/queen_runtime.py` (Team A)
- `src/formicos/engine/runner.py`
- frontend components

## Repo Truth To Read First

1. `src/formicos/surface/queen_runtime.py`
   After Team A lands, routing decisions flow through
   `decide_planning_route()` from `planning_policy.py`. Read the
   `PlanningDecision` dataclass to understand the output shape.

2. `src/formicos/surface/planning_signals.py`
   After Team A lands, `build_planning_signals()` returns a dict
   with keys: `patterns`, `playbook`, `capability`, `coupling`,
   `previous_plans`, and `saved_patterns`.

3. `src/formicos/surface/task_classifier.py:72`
   `classify_task()` returns `(category_name, defaults_dict)`.

4. `src/formicos/surface/queen_runtime.py:74-118`
   `classify_complexity()`, `_looks_like_colony_work()`,
   `_prefer_single_colony_route()` -- the individual classifiers
   that Team A wraps into `planning_policy.py`.

5. `src/formicos/engine/playbook_loader.py`
   `get_decomposition_hints()` -- the playbook hint classifier.

6. `src/formicos/core/types.py`
   `ColonyTask` and `DelegationPlan` -- the plan output types.

7. `docs/waves/wave_81/real_repo_task_pack.md`
   The existing real-repo task prompts. Reuse these as part of the
   golden prompt set.

## What To Build

### 1. Queen-only eval pack

Create `tests/eval/queen_planning_eval.py`.

This track has two layers:

- a deterministic scoring harness that evaluates captured Queen tool
  calls or fixture plans without running colonies or requiring a live LLM
- an optional live Queen capture mode behind `FORMICOS_LIVE_EVAL=1`,
  used only when you want to measure dispatch latency or preview escapes

The default test path should be deterministic and fast. The live layer
is optional and should reuse the same scoring logic once it has a
captured tool call / plan to inspect.

Define 10-15 golden prompts spanning:

```python
GOLDEN_PROMPTS = [
    # Simple single-file tasks (should route to fast_path)
    {
        "prompt": "Write tests for checkpoint.py",
        "expected_route": "fast_path",
        "expected_files": ["checkpoint.py", "test_checkpoint.py"],
    },
    {
        "prompt": "Fix the SSRF validator to block RFC 1918 ranges",
        "expected_route": "fast_path",
        "expected_files": ["ssrf_validate.py"],
    },

    # Multi-file tasks (should route to parallel_dag)
    {
        "prompt": "Build a multi-file addon with scanner, coverage, quality, handlers, and tests",
        "expected_route": "parallel_dag",
        "min_colonies": 3,
        "expected_files": ["scanner.py", "coverage.py", "quality.py", "handlers.py"],
    },

    # Refactoring tasks (should group coupled files)
    {
        "prompt": "Consolidate workspace root resolution in runner.py to use workspace_roots.py",
        "expected_route": "fast_path",
        "expected_files": ["runner.py", "workspace_roots.py"],
    },

    # Ambiguous tasks (classification should be deterministic)
    {
        "prompt": "Improve the auth module",
        "expected_route": "single_colony",
    },

    # Q&A tasks (should NOT spawn)
    {
        "prompt": "What is the status of colony X?",
        "expected_route": "none",
    },
    # ... add 5-10 more
]
```

Metrics to capture per prompt in the deterministic path:

- **Planning validity**: correct dependencies, no cycles, no
  orphaned tasks, non-overlapping file ownership
- **Route correctness**: did the routing decision match expected?
- **Deliverable coverage**: does the plan cover all expected files?
- **Colony count**: appropriate for the task complexity?
- **Route consistency**: do task class, complexity, single-colony
  preference, and playbook expectations cohere?

For live-LLM evaluation (optional, gated behind an env flag):

- **Time to first dispatch**: seconds to first spawn tool call
- **Preview escape rate**: propose_plan or preview:True instead of
  dispatching
- **Saved pattern recall**: when a saved pattern exists, does the
  resulting plan structurally resemble it?

### 2. Routing drift tests

Create `tests/unit/surface/test_routing_agreement.py`.

Golden-test the routing helpers on a canonical prompt set:

```python
import pytest
from formicos.surface.task_classifier import classify_task
from formicos.surface.queen_runtime import (
    classify_complexity,
    _looks_like_colony_work,
    _prefer_single_colony_route,
)

GOLDEN_ROUTES = [
    # (prompt, task_class, complexity, is_colony_work, prefers_single)
    ("Write tests for checkpoint.py",
     "code_implementation", "simple", True, True),
    ("Build a multi-file addon with handlers and tests",
     "code_implementation", "complex", True, False),
    ("What is the status of colony X?",
     "generic", "simple", False, False),
    ("Refactor the auth module across 5 files",
     "code_implementation", "complex", True, False),
    ("Fix the typo in README.md",
     "code_implementation", "simple", True, True),
    # ... 10-15 total
]

@pytest.mark.parametrize(
    "prompt,task_class,complexity,colony_work,single",
    GOLDEN_ROUTES,
)
def test_routing_agreement(prompt, task_class, complexity, colony_work, single):
    assert classify_task(prompt)[0] == task_class
    assert classify_complexity(prompt) == complexity
    assert _looks_like_colony_work(prompt) == colony_work
    assert _prefer_single_colony_route(prompt) == single
```

If Team A has landed `planning_policy.py`, also test:

```python
from formicos.surface.planning_policy import decide_planning_route

def test_policy_matches_golden(prompt, ...):
    decision = decide_planning_route(prompt)
    assert decision.route == expected_route
    assert decision.task_class == task_class
```

Treat playbook hints as an expectation-coherence signal, not a strict
equality assertion. `get_decomposition_hints()` returns hint text, not a
typed route enum.

### 3. Ablation harness

Create `tests/eval/test_planning_ablation.py`.

Run the same prompt set under four planning-signal configurations:

| Config | Knowledge patterns | Playbook | Capability | Coupling | Saved patterns |
|--------|-------------------|----------|------------|----------|----------------|
| A: none | off | off | off | off | off |
| B: base | on | on | on | off | off |
| C: +structural | on | on | on | on | off |
| D: +saved | on | on | on | on | on |

Use env vars or parameter flags to suppress signal sources in
`build_planning_signals()`:

```python
ABLATION_CONFIGS = {
    "none": {"skip_all": True},
    "base": {"skip_coupling": True, "skip_saved": True},
    "structural": {"skip_saved": True},
    "full": {},
}
```

For each config, capture the plan structure (colony count, file
groups, route decision) and compare across configs. The output
should be a comparison table:

```
Prompt: "Build multi-file addon..."
  none:       3 colonies, no file grouping
  base:       4 colonies, playbook-guided grouping
  structural: 4 colonies, coupling-guided grouping
  full:       5 colonies, pattern-guided grouping (saved pattern applied)
```

This is a structural comparison, not a worker-quality measurement. It
tells you which signals actually change plan decisions.

The ablation should work with mocked or fixture-backed signal responses
for the default structural comparison path. Live LLM ablation is
optional and gated behind an env flag.

## Important Constraints

- Do not modify production code (Team A owns that)
- Keep eval tests fast (fixture/capture-driven for default runs)
- Gate live-LLM evaluation behind `FORMICOS_LIVE_EVAL=1` env flag
- Make routing golden tests deterministic (no LLM, pure classifier)
- Output ablation results as structured JSON or markdown table

## Validation

- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`
- `python -m pytest tests/eval/queen_planning_eval.py -q`
  (unit tests only, no live LLM)
- `FORMICOS_LIVE_EVAL=1 python -m pytest tests/eval/ -q`
  (live eval, optional)

## Overlap Note

Team A owns all production code changes. Your eval harness tests
their output. Wait for Team A to land before finalizing tests that
depend on `planning_policy.py` or the `saved_patterns` signal field.
You CAN start building the golden prompt set, routing drift tests,
and ablation framework structure immediately -- just stub the
Team A imports until they land.
