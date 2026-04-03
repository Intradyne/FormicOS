# Wave 84.5 Plan: Queen Planning Intelligence

## Status

Dispatch-ready. Grounded in live repo truth as of 2026-04-01.

## Summary

Wave 84 fixed the runtime stability gate. The system now runs 5/5
tasks at 0.503 average quality with zero hangs.

Wave 84.5 is not a feature wave. It is a Queen measurement and
feedback wave. The goal is to close the operator-feedback loop,
make planning decisions visible, build a Queen-specific eval harness,
and use ablation data to decide the next real lever.

Three tracks:

- Track A: saved pattern feedback + planning observability
- Track B: Queen-only eval pack + ablation harness
- Track C: routing policy consolidation

## Dispatch Shape

This packet should dispatch to two teams, not three.

- Team A owns Track A and Track C together. They both change the same
  Queen planning path and shared signal/routing files.
- Team B owns Track B. Their harness should finalize after Team A lands,
  but they can scaffold prompt fixtures and scoring helpers in parallel.

## Verified Repo Truth

### The saved-pattern feedback gap

Wave 83 built `plan_patterns.py` (107 lines) with `list_patterns()`,
`get_pattern()`, and `save_pattern()`. The operator can save and
retrieve plan patterns via the workbench and REST routes.

But `planning_signals.py` does not query saved patterns. The signal
sources it currently consults:

- `_fetch_patterns()` at line 63: searches the knowledge catalog
  for decomposition-relevant entries. Does NOT query plan_patterns.
- `_fetch_playbook()` at line 104: gets decomposition hints from
  the playbook loader
- `_fetch_capability()` at line 118: gets capability evidence from
  replay-derived profiles
- `_fetch_coupling()` at line 178: gets structural hints from
  code_analysis
- `_fetch_previous_plans()` at line 202: gets prior outcomes from
  workflow_learning. Does NOT query plan_patterns.

The operator saves a plan pattern via the workbench. The Queen
never sees it. The feedback loop is open.

### Planning observability is absent

`planning_brief.py` (100 lines) builds the brief silently. There is
no log line showing what signals the Queen received. There is no
structured summary in the Queen's message metadata. When debugging
Queen behavior, the only option is guessing what the brief contained.

### Routing policy is scattered

Four separate functions contribute to Queen routing decisions:

- `classify_task()` in `task_classifier.py:72` -- keyword-based
  task category
- `classify_complexity()` in `queen_runtime.py:74` -- simple/complex
  for cheap-queen routing
- `_prefer_single_colony_route()` in `queen_runtime.py:108` --
  decides spawn_colony vs spawn_parallel
- `get_decomposition_hints()` in `playbook_loader.py` -- structural
  template from curated playbooks

These can disagree on the same input. `classify_task` may return
`code_implementation`, `classify_complexity` may return `simple`,
`_prefer_single_colony_route` may return True, and the playbook
hint may suggest 3-5 colonies. The Queen sees contradictory signals.

## Track A: Saved Pattern Feedback + Planning Observability

Goal:

Close the Wave 83 feedback loop and make planning decisions visible.

### 1. Add saved-pattern retrieval to planning_signals.py

Add a `_fetch_saved_patterns()` helper that queries `plan_patterns.py`
for the current workspace.

Important: do NOT use text-similarity matching. Key retrieval by a
deterministic bundle:

- `task_class` from `classify_task()`
- `complexity_bucket` from `classify_complexity()`
- explicit file references extracted from the operator message
- `workspace_id`

Derive these keys at read time from the existing stored pattern fields
(`source_query`, `task_previews`, `groups`). Do not expand the on-disk
`plan_patterns.py` schema in this wave.

Match saved patterns where at least 2 of these keys overlap. Return
the top-1 match with its quality/outcome evidence.

Add the result to the `build_planning_signals()` return dict as a
`saved_patterns` field.

Update `planning_brief.py` to render the saved pattern as a brief
line when present:

```
Saved: auth-refactor (q=0.87, 3 colonies, operator-approved)
```

### 2. Add structured planning observability

In `planning_brief.py`, after building the brief:

- Extend the capability signal shape so it carries structured provenance
  such as `source` / `evidence_tier` alongside the existing summary text.
  The observability layer should log real signal provenance, not infer it
  later from the formatted summary string.

- Always log a compact structured summary at info level:

```python
log.info(
    "planning_brief.assembled",
    pattern_count=len(signals.get("patterns", [])),
    playbook_source=signals.get("playbook", {}).get("source", "none"),
    capability_source=signals.get("capability", {}).get("source", "none"),
    coupling_confidence=signals.get("coupling", {}).get("confidence", 0),
    saved_pattern=bool(signals.get("saved_patterns")),
    previous_plan_count=len(signals.get("previous_plans", [])),
    brief_tokens=len(brief) // 4,
)
```

- Optionally log the full brief text at debug level
- Include a compact `planning_signals` summary in the Queen's
  `QueenMessage.meta` so the UI can render "why this plan" without log
  scraping. Do not attach heavyweight saved-pattern payloads such as full
  `task_previews` / `groups` arrays to every Queen message.

### 3. Surface signals in Queen message metadata

In `queen_runtime.py`, when the planning brief is injected, attach
the compact signal summary to the response metadata:

```python
if msg_meta is None:
    msg_meta = {}
msg_meta["planning_signals"] = signals  # from build_planning_signals
```

Only attach this metadata on turns where a planning brief was actually
built/injected. Do not add it to unrelated Queen messages.

Owned files:

- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`

Validation:

- `python -m pytest tests/unit/surface/test_planning_signals.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`

## Track B: Queen-Only Eval Pack + Ablation Harness

Goal:

Build a test harness that measures Queen planning quality separately
from worker execution quality. Then use it to ablate planning signals.

### 1. Queen-only eval pack

Create `tests/eval/queen_planning_eval.py` (or similar).

This track has two layers:

- a deterministic scoring harness that evaluates captured Queen tool-call
  outputs or fixture plans without running colonies or requiring a live LLM
- an optional live Queen capture mode behind an env flag, used only when
  you explicitly want to measure planning latency or escape behavior

The deterministic harness scores the resulting plan structure; the live
layer is for measuring Queen behavior, not required for every test run.

Deterministic metrics to capture per prompt:

- **Planning validity**: correct dependencies, no cycles, no orphaned
  tasks, non-overlapping file ownership
- **Unnecessary DAG rate**: did the Queen use spawn_parallel for a
  task that _prefer_single_colony_route would handle?
- **Deliverable coverage**: does the plan cover all files/outputs
  the operator message referenced?
- **Route consistency**: do classify_task, classify_complexity,
  `_prefer_single_colony_route`, and playbook expectations cohere?
- **Saved pattern recall**: when a saved pattern exists for this
  task bundle, does the Queen's plan structurally resemble it?

Live-only metrics (optional, behind env flag):

- **Time to first dispatch**: seconds from message to first spawn
  tool call
- **Preview escape rate**: did the Queen call `propose_plan` or use
  `preview: True` instead of dispatching?

The eval pack should include 10-15 golden prompts spanning:

- Simple single-file tasks (should route to fast_path)
- Multi-file implementation tasks (should route to spawn_parallel)
- Refactoring tasks (should group coupled files)
- Test-writing tasks (should identify test + source pairs)
- Ambiguous tasks (classification should be deterministic)

### 2. Ablation harness

Run the same prompt set under four planning-signal configurations:

| Config | Patterns | Playbook | Capability | Coupling | Saved |
|--------|----------|----------|------------|----------|-------|
| A: none | off | off | off | off | off |
| B: base | on | on | on | off | off |
| C: +structural | on | on | on | on | off |
| D: +saved | on | on | on | on | on |

For each config, suppress the disabled signals in
`build_planning_signals()` (env-var gated or parameter flags).

The ablation measures which signals actually change plan structure
(colony count, file grouping, route choice) -- not colony output
quality. This isolates Queen improvement from worker variability.

### 3. Routing drift tests

Add golden tests that verify the four routing classifiers agree on
a canonical prompt set:

```python
GOLDEN_ROUTES = [
    ("Write tests for checkpoint.py", "code_implementation", "simple", True, None),
    ("Build a multi-file addon with handlers and tests", "code_implementation", "complex", False, "code_implementation"),
    ("What is the status of colony X?", "generic", "simple", False, None),
    # ... 10-15 more
]

@pytest.mark.parametrize("prompt,task_class,complexity,single,playbook", GOLDEN_ROUTES)
def test_routing_agreement(prompt, task_class, complexity, single, playbook):
    assert classify_task(prompt)[0] == task_class
    assert classify_complexity(prompt) == complexity
    assert _prefer_single_colony_route(prompt) == single
    # playbook hint agreement where applicable
```

Owned files:

- `tests/eval/queen_planning_eval.py` (new)
- `tests/eval/test_planning_ablation.py` (new)
- `tests/unit/surface/test_routing_agreement.py` (new)

Validation:

- `python -m pytest tests/eval/queen_planning_eval.py -q`
- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`

## Track C: Routing Policy Consolidation

Goal:

Unify the four scattered routing classifiers into one planning-policy
object that outputs a consistent routing decision.

### 1. Create a planning policy helper

Create `src/formicos/surface/planning_policy.py`:

```python
@dataclass
class PlanningDecision:
    task_class: str        # from classify_task
    complexity: str        # "simple" | "complex"
    route: str             # "fast_path" | "single_colony" | "parallel_dag"
    playbook_hint: str | None
    behavior_flags: dict[str, bool]  # needs_tool_narrowing, etc.
    confidence: float      # agreement score across classifiers

def decide_planning_route(
    message: str,
    *,
    model_addr: str = "",
    active_colonies: int = 0,
) -> PlanningDecision:
    ...
```

The function calls all four classifiers internally and resolves
disagreements with explicit precedence rules:

- If classify_task says `code_implementation` and complexity says
  `simple` and single-colony says True: route = `fast_path`
- If classify_task says `code_implementation` and complexity says
  `complex`: route = `parallel_dag`
- If classifiers disagree: use the most conservative route and
  set confidence lower

### 2. Replace scattered classifier calls

In `queen_runtime.py`, replace the direct calls to
`classify_complexity()`, `_prefer_single_colony_route()`, and
`classify_task()` with a single call to `decide_planning_route()`.

Keep the individual classifiers as internal helpers called by the
policy object -- do not delete them, just stop calling them directly
from the Queen respond path.

### 3. Add behavior flags from capability profiles

If `capability_profiles.py` stores behavioral evidence for the
current model (e.g., the model needed tool narrowing in prior runs),
include it in the PlanningDecision as behavior_flags:

```python
behavior_flags={
    "needs_tool_narrowing": True,   # Qwen3.5 does
    "respects_tool_choice": False,  # Qwen3.5 doesn't
    "benefits_from_fast_path": True,
}
```

These flags start as static entries in capability_profiles.json
and can later be derived from replay observations.

Owned files:

- `src/formicos/surface/planning_policy.py` (new)
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/capability_profiles.py`
- `config/capability_profiles.json`
- `tests/unit/surface/test_planning_policy.py` (new)

Validation:

- `python -m pytest tests/unit/surface/test_planning_policy.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`
- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`

## Merge Order

1. Team A Track A (saved patterns + observability)
2. Team A Track C (routing consolidation)
3. Team B Track B (eval pack + ablation) -- finalizes after Team A
   so it can test the consolidated routing and saved-pattern path

Track A and Track C may be implemented in parallel by the same owner,
but this packet should not split them across teams. Track B should
finalize after both land so the eval harness tests the consolidated
routing policy and the saved-pattern signal path.

## What This Wave Does Not Do

- No new frontend components
- No graph bridging or MODULE node population
- No changes to colony execution or runner.py
- No new event types
- No verification agent
- No two-pass decomposition
- No model changes

## Success Criteria

Wave 84.5 is successful if:

1. Saved plan patterns appear in the planning brief when a matching
   pattern exists for the current task type
2. Planning observability logs show signal sources and token counts
   on every planning turn
3. The Queen-only eval pack runs deterministically on 10-15 golden
   prompts and produces per-prompt routing metrics
4. The ablation harness can compare plan structure across 4 signal
   configurations
5. Routing classifiers agree on the golden prompt set (no silent
   drift)
6. The planning policy object produces a single PlanningDecision
   that replaces scattered classifier calls in queen_runtime.py

## Post-Wave Decision

After Wave 84.5 lands and the ablation runs:

- If saved patterns produce the biggest plan-quality uplift: invest
  in richer pattern matching and auto-save after successful plans
- If structural hints are the limiting factor: prioritize graph
  bridging (MODULE nodes connected to memory entries) as Wave 85
- If capability flags change routing quality: invest in replay-derived
  behavior flags
- If none of the signals materially change plan structure: the Queen's
  current planning is already near-optimal for this model, and the
  next lever is a better base model
