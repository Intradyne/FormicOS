# Wave 68 - Team B: Queen Intelligence & Context Scaling

**Theme:** The Queen reasons with structured, source-labeled evidence and
scales cleanly from small to large context models.

## Context

Read `docs/waves/wave_68/design_note.md` first. You are bound by all three
invariants.

Read `CLAUDE.md` for hard constraints (event closed union, layer rules, etc.).
Read `AGENTS.md` for repo norms. This prompt overrides stale root `AGENTS.md`
for file ownership within this wave.

## Your Files (exclusive ownership)

- `src/formicos/surface/queen_budget.py` - **new**, `QueenContextBudget` +
  `compute_queen_budget()`
- `src/formicos/surface/queen_runtime.py` - budget threading in
  `_build_messages()`, constant replacement in `respond()`,
  `_build_deliberation_frame()` new helper, deliberation detection/injection
- `tests/unit/surface/test_queen_budget.py` - **new**
- `tests/unit/surface/test_deliberation_frame.py` - **new**

## Do Not Touch

- `src/formicos/surface/queen_tools.py` - Team A owns plan tools; Team C owns
  `_list_addons()` and workspace tags tooling
- `src/formicos/surface/projections.py`
- `src/formicos/core/types.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/colony_manager.py`
- `_build_thread_context()` in `queen_runtime.py` - Team A owns bottom
  insertion; Team C owns top insertion
- `config/caste_recipes.yaml` - Team C owns
- any frontend files

## Overlap Coordination

- Team A touches `respond()` for session-summary injection after the
  project-context area. You own early budget computation and the
  deliberation-frame injection path before the LLM call.
- Team C makes addon capability metadata visible. Your deliberation frame
  should prefer that metadata once it exists, but must still work before
  Team C lands.
- You own `_build_messages()` exclusively.

---

## Track 3: Dynamic Context Budget (ADR-051)

### Problem

`queen_runtime.py` still relies on seven hardcoded caps:

| Constant | Current value |
|----------|---------------|
| `_THREAD_TOKEN_BUDGET` | 6000 tokens |
| `_RECENT_WINDOW` | 10 messages |
| `_QUEEN_TOOL_OUTPUT_CAP` | 2000 chars |
| `_QUEEN_MAX_TOOL_HISTORY_CHARS` | 16000 chars |
| project context cap | 2000 chars |
| tool memory join cap | 6000 chars |
| cloud routing threshold | 2000 tokens |

These values are too small on large-context models and too rigid to express
how the Queen should use new context sources such as plans, session summaries,
tags, and deliberation frames.

### Non-negotiable rule

Every computed slot must use:

```python
slot_value = max(current_default, proportional_value)
```

This is the no-regression guarantee. Proportional scaling may grow budgets.
It must never shrink behavior below current defaults.

### Implementation

**1. New module `src/formicos/surface/queen_budget.py`.**

Add a small surface-only module:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class QueenContextBudget:
    system_prompt: int
    memory_retrieval: int
    project_context: int
    thread_context: int
    tool_memory: int
    conversation_history: int
```

Budget fractions:

- `system_prompt`: 15%
- `memory_retrieval`: 15%
- `project_context`: 10%
- `thread_context`: 20%
- `tool_memory`: 10%
- `conversation_history`: 30%

Fallback floors must match current behavior exactly:

- `system_prompt=2000`
- `memory_retrieval=1500`
- `project_context=500`
- `thread_context=1500`
- `tool_memory=4000`
- `conversation_history=6000`

`compute_queen_budget(context_window, output_reserve)` should:

- read `context_window` as the model's total context window
- subtract `output_reserve`
- compute each proportional slot
- return `max(fallback, proportional)` for every slot
- return the fallback object unchanged when `context_window` is missing,
  invalid, or too small

**2. Compute the budget in `respond()`.**

Use the same model-registry lookup pattern already used by
`_queen_max_tokens()`. Read:

- `rec.context_window` from `ModelRecord`
- output reserve from `_queen_max_tokens(workspace_id)`

Then:

```python
budget = compute_queen_budget(_ctx_window, _output_reserve)
```

Pass `budget` into `_build_messages()`.

**3. Thread the budget through `_build_messages()`.**

Change the signature to accept an optional budget object. If none is supplied,
use the fallback budget from `queen_budget.py`.

Replace hardcoded caps in `_build_messages()`:

- tool-memory join cap -> `budget.tool_memory * 4`
- any other local hardcoded limit there -> budget-backed equivalent

**4. Replace the remaining hardcoded caps in `respond()`.**

Replace:

- project-context file slice -> `budget.project_context * 4`
- cloud routing threshold -> `budget.system_prompt`

**5. Replace `_compact_thread_history()` inputs.**

Preferred approach:

```python
def _compact_thread_history(
    queen_messages: list[Any],
    token_budget: int = 6000,
    recent_window: int = 10,
) -> list[dict[str, str]]:
```

Call it with:

```python
_compact_thread_history(
    thread.queen_messages,
    token_budget=budget.conversation_history,
    recent_window=max(5, budget.conversation_history // 600),
)
```

If you discover a lower-risk seam that preserves the same behavior, note it in
the summary, but do not fall back to the old constants for normal operation.

**6. Add a lightweight debug log.**

Emit one debug log showing model, context window, output reserve, and the final
slot allocation. Keep it small and deterministic.

---

## Track 4: Deliberation Frame Assembly

### Problem

The Queen's `CLASSIFY -> DIRECT -> COLONY` flow is guided mostly by the system
prompt. On exploratory or open-ended operator messages
(`_DELIBERATION_RE` in `queen_intent_parser.py`), the Queen still lacks a
structured pre-LLM snapshot of:

- institutional memory coverage
- recent colony outcomes
- addon-owned corpus coverage
- thread momentum
- active intelligence alerts

The remaining routing weakness is that addon coverage can degrade into a tool
inventory. A strong router needs source-labeled evidence: what is institutional
memory, what is docs/code corpus coverage, and how each source is meant to be
used.

### Implementation

**1. Add `_build_deliberation_frame()`.**

Create a helper on `QueenRuntime` that assembles a deterministic frame from
projections only. No LLM calls. No network.

Use sections like:

- `## Institutional Memory Coverage`
- `## Recent Colony Outcomes`
- `## Addon Corpus Coverage`
- `## Thread Progress`
- `## Active Alerts`

For institutional memory, summarize top domains by entry count and average
confidence.

For recent outcomes, summarize the latest few outcomes with success marker,
strategy, rounds, and cost.

For addon coverage, prefer manifest-backed capability metadata once Team C
lands. The goal is routing signal, not just tool names. The frame should
ideally read like:

```text
- docs-index: content documentation; files **/*.md, **/*.rst; search via search_docs
- codebase-index: content source_code; files **/*.py, **/*.ts; search via semantic_search_code
```

If the manifest or runtime seam for capability metadata is not yet present,
fall back gracefully to addon tool descriptions. Final truth pass should happen
after Team C lands so the corpus-coverage section reflects real capability
metadata.

If an addon already exposes an obvious refresh/index trigger or handler, you
may surface it here too, but do not invent a new core contract from Team B.

For alerts, reuse the existing proactive-intelligence path if available, but
guard it tightly.

**2. Inject the frame before the LLM call.**

In `respond()`, after building messages and before entering the tool loop,
check the latest operator message for `_DELIBERATION_RE`.

If it matches:

- build the deliberation frame
- cap it at `budget.thread_context * 4` chars (fallback 1500 chars if needed)
- insert it as a system message before the first non-system message

This is pre-context for reasoning, routing, and planning. It is not a
post-response annotation.

### Tests

Create `tests/unit/surface/test_deliberation_frame.py` with at least:

1. `test_frame_includes_domains_and_outcomes`
2. `test_frame_caps_at_budget`
3. `test_deliberation_triggers_on_exploratory_message`
4. `test_frame_empty_for_bare_workspace`
5. `test_frame_prefers_capability_metadata_when_available`

The last test should mock addon manifests with `content_kinds`, `path_globs`,
and `search_tool`, then assert the frame labels addon corpus coverage by source
type rather than only by tool name.

---

## Acceptance Gates

- [ ] `queen_budget.py` exists with `QueenContextBudget` and `compute_queen_budget()`
- [ ] Every slot uses `max(fallback, proportional)`
- [ ] Fallback values match the current hardcoded defaults
- [ ] `context_window` is read from `ModelRecord.context_window`
- [ ] Output reserve comes from `_queen_max_tokens()`
- [ ] `_build_messages()` and `respond()` consume budget values instead of the old hardcoded caps
- [ ] Deliberation frame is assembled from projections only
- [ ] Deliberation frame is injected before the LLM call
- [ ] Addon coverage is source-labeled and prefers capability metadata when available
- [ ] Budget logging is present at debug level
- [ ] No new event types are added

## Validation

```bash
pytest tests/unit/surface/test_queen_budget.py -v
pytest tests/unit/surface/test_deliberation_frame.py -v

ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
