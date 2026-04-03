# Wave 84.5 Team A Prompt

## Mission

Close the saved-pattern feedback loop, add planning observability,
and consolidate the scattered routing policy into one decision object.

This is the production-code track. Team B builds the eval harness
that tests your work.

## Owned Files

- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/planning_policy.py` (new)
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/capability_profiles.py`
- `config/capability_profiles.json`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_planning_policy.py` (new)
- `tests/unit/surface/test_queen_runtime.py`

## Do Not Touch

- `src/formicos/surface/plan_patterns.py` (read only -- query it,
  don't modify it)
- `src/formicos/surface/task_classifier.py` (keep as internal helper)
- `src/formicos/engine/runner.py`
- `src/formicos/surface/queen_tools.py`
- frontend components
- eval harness files (Team B owns those)

## Repo Truth To Read First

1. `src/formicos/surface/planning_signals.py:63-228`
   `_fetch_patterns()` searches the knowledge catalog only.
   `_fetch_previous_plans()` queries workflow_learning only.
   Neither queries saved plan patterns from `plan_patterns.py`.

2. `src/formicos/surface/plan_patterns.py`
   `list_patterns(data_dir, workspace_id)` returns all saved patterns.
   Each pattern has: `pattern_id`, `name`, `task_previews`, `groups`,
   `source_query`, `planner_model`, `created_from`, and optional
   `outcome_summary`. Read this to understand the stored shape.

3. `src/formicos/surface/planning_brief.py:24-86`
   Builds the brief from `build_planning_signals()` output. Renders
   patterns, playbook, capability, and coupling lines. Currently
   has no log output and no saved-pattern line.

4. `src/formicos/surface/queen_runtime.py:74-118`
   Three routing functions: `classify_complexity()` at line 74,
   `_looks_like_colony_work()` at line 92,
   `_prefer_single_colony_route()` at line 108.
   These are called at lines 1322-1325 in `_respond_inner()`.

5. `src/formicos/surface/task_classifier.py:72`
   `classify_task()` returns `(category_name, defaults_dict)`.

6. `src/formicos/engine/playbook_loader.py`
   `get_decomposition_hints()` returns a one-line playbook hint.

## What To Build

### 1. Saved-pattern retrieval in planning_signals.py

Add a `_fetch_saved_patterns()` helper. Key retrieval by a
deterministic bundle, NOT text similarity:

```python
def _fetch_saved_patterns(
    runtime: Runtime,
    workspace_id: str,
    operator_message: str,
) -> list[dict[str, Any]]:
    from formicos.surface.plan_patterns import list_patterns
    from formicos.surface.task_classifier import classify_task

    data_dir = runtime.settings.system.data_dir
    if not data_dir:
        return []

    patterns = list_patterns(data_dir, workspace_id)
    if not patterns:
        return []

    task_class, _ = classify_task(operator_message)
    complexity = classify_complexity(operator_message)
    file_refs = set(_FILE_HINT_RE.findall(operator_message))

    scored = []
    for p in patterns:
        # Derive the bundle from existing stored fields.
        # Do not change the plan_patterns schema in this wave.
        score = 0.0
        source_query = p.get("source_query", "")
        p_class, _ = classify_task(source_query) if source_query else ("", {})
        p_complexity = (
            classify_complexity(source_query) if source_query else ""
        )
        if p_class == task_class:
            score += 0.5
        if p_complexity == complexity:
            score += 0.2
        p_files = set()
        for tp in p.get("task_previews", []):
            p_files.update(tp.get("target_files", []))
        if file_refs & p_files:
            score += 0.3
        if p.get("outcome_summary", {}).get("quality", 0) > 0.5:
            score += 0.2
        if score >= 0.5:
            scored.append({**p, "_match_score": score})

    scored.sort(key=lambda x: -x["_match_score"])
    return scored[:1]  # top-1 only
```

Call it from `build_planning_signals()` and include the result as
`saved_patterns` in the returned dict.

Important: keep the saved-pattern signal compact. The planning signal
and Queen metadata should carry summary fields such as `pattern_id`,
`name`, `created_from`, `match_score`, derived colony/group counts, and
optional outcome quality. Do not attach full `task_previews` / `groups`
payloads to every Queen message.

### 2. Render saved patterns in planning_brief.py

When `signals["saved_patterns"]` is non-empty, add a brief line:

```
Saved: auth-refactor (q=0.87, 3 colonies, operator-approved)
```

### 3. Structured planning observability

After the brief is assembled, log a compact structured summary:

```python
log.info(
    "planning_brief.assembled",
    pattern_count=...,
    playbook_source=...,
    capability_source=...,
    coupling_confidence=...,
    saved_pattern=bool(...),
    previous_plan_count=...,
    brief_tokens=len(brief) // 4,
)
```

Full brief text under debug level only.

Make this truthful by extending the capability signal shape so it
includes structured provenance like `source` / `evidence_tier` in
addition to the existing summary text.

### 4. Attach signals to Queen message metadata

In `queen_runtime.py`, where the planning brief is injected (around
line 1290), store the compact signal summary so it reaches the UI:

```python
# Store for later attachment to QueenMessage meta
_planning_signals_for_meta = signals
```

Then at the response emission (around line 1950), attach:

```python
if _planning_signals_for_meta:
    if msg_meta is None:
        msg_meta = {}
    msg_meta["planning_signals"] = _planning_signals_for_meta
```

Attach this only when a planning brief was actually built/injected.
Use the compact signal summary described above, not the full saved
pattern payload.

### 5. Planning policy consolidation

Create `src/formicos/surface/planning_policy.py`:

```python
@dataclass
class PlanningDecision:
    task_class: str
    complexity: str
    route: str  # "fast_path" | "single_colony" | "parallel_dag"
    playbook_hint: str | None
    behavior_flags: dict[str, bool]
    confidence: float

def decide_planning_route(
    message: str,
    *,
    model_addr: str = "",
    active_colonies: int = 0,
) -> PlanningDecision:
```

The function calls `classify_task`, `classify_complexity`,
`_prefer_single_colony_route`, and `get_decomposition_hints`
internally and resolves disagreements with explicit precedence.

Replace the scattered calls in `queen_runtime.py._respond_inner()`
with a single `decide_planning_route()` call.

### 6. Behavior flags in capability profiles

Add static entries to `config/capability_profiles.json`:

```json
{
  "profiles": {
    "qwen3.5-35b": {
      "behavior": {
        "needs_tool_narrowing": true,
        "respects_tool_choice": false,
        "benefits_from_fast_path": true
      }
    },
    "devstral-small-2-24b": {
      "behavior": {
        "needs_tool_narrowing": false,
        "respects_tool_choice": true,
        "benefits_from_fast_path": false
      }
    }
  }
}
```

Use keys that match the existing resolver behavior (full address or last
path segment). Keep this additive to the current shipped profile schema;
do not redesign capability_profiles storage in this wave.

Surface these in `PlanningDecision.behavior_flags`.

## Important Constraints

- Do not use text-similarity for pattern matching
- Do not log the full brief at info level (debug only)
- Do not delete the existing classifiers -- wrap them
- Keep the planning brief under 500 tokens
- Degrade cleanly when no saved patterns exist

## Validation

- `python -m pytest tests/unit/surface/test_planning_signals.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- `python -m pytest tests/unit/surface/test_planning_policy.py -q`
- `python -m pytest tests/unit/surface/test_queen_runtime.py -q`

## Overlap Note

Team B builds the eval harness and ablation tests. They will test
your consolidated routing policy and saved-pattern signal path.
Keep public APIs stable so their tests don't break on landing.
