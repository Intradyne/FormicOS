# Team 1: Specificity Gate

## Context

Phase 0 v4-v10 measurements show that injecting retrieved knowledge into
agent context HURTS quality on general coding tasks where the model already
knows the patterns. The retrieval audit found that "related but not relevant"
entries -- email validation knowledge injected into a rate-limiter task --
consumed ~375 tokens per round of noise. The empty arm (no knowledge)
outperformed the accumulate arm by 0.157 quality points on rate-limiter.

The specificity gate is a fast, deterministic check that decides whether
the current task should receive ANY knowledge injection. When the task is
a general coding pattern the model already knows (implement a rate limiter,
parse CSV, write a haiku), the gate skips injection entirely -- saving ~250
tokens of noise from the context. When the task references project-specific
concepts or the knowledge pool contains a genuinely relevant entry, the gate
allows injection.

**Env var toggle**: `FORMICOS_SPECIFICITY_GATE` (default `"1"` = ON).
Set to `"0"` to disable the gate (always inject). This allows A/B testing
in eval runs.

---

## Implementation

### File: `src/formicos/engine/context.py`

All changes are in this single file. Three additions:

### Addition 1: Env var and constants (add after line 53)

After the existing `_MIN_KNOWLEDGE_SIMILARITY` declaration (line 51-52),
add the gate toggle and word sets:

```python
# Wave 58: Specificity gate -- skip knowledge injection for general tasks.
# When enabled, the gate checks for project-specific signals in the task
# description and strong semantic matches in the retrieved pool.
_SPECIFICITY_GATE_ENABLED: bool = (
    os.environ.get("FORMICOS_SPECIFICITY_GATE", "1") == "1"
)

_PROJECT_SIGNALS: frozenset[str] = frozenset({
    "our", "existing", "internal", "custom", "legacy", "current",
    "workspace", "codebase", "repo", "project", "module",
})
```

Note: the design doc included a `_GENERAL_TASK_SIGNALS` set but the gate
function does not use it. Do NOT add it. Only `_PROJECT_SIGNALS` is needed.

### Addition 2: Gate function (add before `assemble_context()`, around line 370)

```python
def _should_inject_knowledge(
    round_goal: str,
    knowledge_items: list[dict[str, Any]],
) -> bool:
    """Specificity gate: skip injection when knowledge won't help.

    Returns True (inject) when:
    1. Gate is disabled via env var, OR
    2. Any retrieved entry is a trajectory (always valuable), OR
    3. Task contains project-specific signals, OR
    4. Top retrieved entry has raw similarity >= 0.55 (strong match exists)

    Returns False (skip) when none of the above hold.
    """
    if not _SPECIFICITY_GATE_ENABLED:
        return True

    # Always inject when trajectory entries are available -- they are
    # action sequences, not redundant prose.
    for item in knowledge_items[:5]:
        if item.get("sub_type") == "trajectory":
            return True

    # Check for project-specific language in the task description.
    words = set(round_goal.lower().split())
    if words & _PROJECT_SIGNALS:
        return True

    # Check whether the pool contains a genuinely relevant entry.
    # 0.55 is above the per-entry threshold (0.50) to avoid redundancy.
    if knowledge_items:
        top_sim = max(
            float(item.get("similarity", item.get("score", 0.0)))
            for item in knowledge_items[:5]
        )
        if top_sim >= 0.55:
            return True

    log.debug(
        "context.specificity_gate_skip",
        round_goal=round_goal[:80],
        top_similarity=round(
            max(
                (float(i.get("similarity", i.get("score", 0.0))) for i in knowledge_items[:5]),
                default=0.0,
            ), 3,
        ),
    )
    return False
```

### Addition 3: Wrap the injection block (line 459)

Change line 459 from:

```python
    if knowledge_items:
```

to:

```python
    if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
```

Everything inside the block (lines 460-505) stays unchanged. Team 3 will
replace that inner block after you merge.

---

## Tests to write

File: `tests/unit/engine/test_context.py`

Add 5 new test functions. Each test calls `_should_inject_knowledge()`
directly (import from `formicos.engine.context`).

### test_should_inject_knowledge_skip_general

```
Given: round_goal = "implement a token bucket rate limiter"
       knowledge_items = [{"similarity": 0.41, "title": "Email Validation", "sub_type": "technique"}]
Expect: returns False (no project signals, similarity < 0.55, no trajectories)
```

### test_should_inject_knowledge_inject_project

```
Given: round_goal = "fix our auth middleware token refresh"
       knowledge_items = [{"similarity": 0.35, "title": "Auth Patterns", "sub_type": "technique"}]
Expect: returns True ("our" is a project signal)
```

### test_should_inject_knowledge_inject_high_similarity

```
Given: round_goal = "parse CSV and compute statistics"
       knowledge_items = [{"similarity": 0.67, "title": "CSV Parsing Patterns", "sub_type": "technique"}]
Expect: returns True (similarity >= 0.55)
```

### test_specificity_gate_env_disable

```
Given: monkeypatch FORMICOS_SPECIFICITY_GATE to "0"
       round_goal = "implement a rate limiter"
       knowledge_items = [{"similarity": 0.30, "sub_type": "technique"}]
Expect: returns True (gate disabled, always inject)
Note: You need to reload the module-level _SPECIFICITY_GATE_ENABLED, OR
      test the behavior via assemble_context() which respects the live value.
      Simplest approach: monkeypatch context._SPECIFICITY_GATE_ENABLED = False.
```

### test_should_inject_knowledge_inject_trajectory

```
Given: round_goal = "write a haiku about spring"
       knowledge_items = [{"similarity": 0.30, "title": "Trajectory: creative", "sub_type": "trajectory"}]
Expect: returns True (trajectory entry present, always inject)
```

---

## Files owned

- `src/formicos/engine/context.py`

## Do not touch

- `surface/knowledge_catalog.py` (pre-dispatch fix landed `sub_type` propagation)
- `surface/colony_manager.py`
- `surface/runtime.py`
- `core/types.py`
- `engine/tool_dispatch.py`
- `surface/memory_store.py`

## Validation commands

```bash
uv run ruff check src/formicos/engine/context.py
uv run pyright src/formicos/engine/context.py
uv run pytest tests/unit/engine/test_context.py -x -q
```

Run the full CI before declaring done:

```bash
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && uv run pytest
```

## Merge order

You merge in **parallel with Team 2** (no file overlap). Team 3 depends
on your merge -- they will re-read context.py after you land and replace
the inner injection block. Do not change the inner block format (lines
460-505) -- that is Team 3's territory.
