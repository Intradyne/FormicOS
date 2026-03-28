# ADR-051: Dynamic Queen Context Caps

**Status:** Accepted
**Date:** 2026-03-25
**Wave:** 68 (updated Wave 70.0 — project_plan; Wave 71.0 — 9-slot expansion)

## Context

The Queen still uses several hardcoded caps in `queen_runtime.py`:

| Constant | Current value |
|----------|---------------|
| `_THREAD_TOKEN_BUDGET` | 6000 tokens |
| `_RECENT_WINDOW` | 10 messages |
| `_QUEEN_TOOL_OUTPUT_CAP` | 2000 chars |
| `_QUEEN_MAX_TOOL_HISTORY_CHARS` | 16000 chars |
| project context slice | 2000 chars |
| tool memory join cap | 6000 chars |
| cloud routing threshold | 2000 tokens |

These defaults were tuned for relatively small context windows. They waste
capacity on large-context models and make it harder to budget newer context
sources such as tags, plans, session summaries, and deliberation frames.

## Decision

Replace hardcoded caps with proportional slot budgeting derived from the
model's `context_window`, while preserving current behavior as the floor.

### No-regression rule

Every slot uses:

```python
slot_value = max(fallback_default, proportional_value)
```

Proportional scaling may grow budgets. It must never shrink them below today's
effective defaults.

### Budget slots

Budget is computed from:

```python
available = max(0, context_window - output_reserve)
```

Where `output_reserve` comes from the existing `_queen_max_tokens()` logic.

| Slot | Fraction | Purpose |
|------|----------|---------|
| `system_prompt` | 15% | Caste recipe + Queen notes + system guidance |
| `memory_retrieval` | 13% | Institutional memory retrieval block |
| `project_context` | 8% | `project_context.md` |
| `project_plan` | 5% | Cross-thread project plan milestones (Wave 70.0) |
| `operating_procedures` | 5% | Workspace operating procedures (Wave 71.0) |
| `queen_journal` | 4% | Recent Queen working-memory journal (Wave 71.0) |
| `thread_context` | 13% | Thread state, tags, session context, plan, deliberation frame |
| `tool_memory` | 9% | Prior-turn tool results |
| `conversation_history` | 28% | Compacted Queen thread history |

Fractions sum to 1.0. Wave 71.0 expanded from 7 to 9 slots by adding
`operating_procedures` and `queen_journal`, trading 9% across four
existing slots (memory_retrieval -2%, project_context -2%,
thread_context -2%, tool_memory -1%, conversation_history -2%).
No single slot lost more than 2 absolute points.

### Fallback floors

These floors preserve current behavior:

| Slot | Fallback |
|------|----------|
| `system_prompt` | 2000 |
| `memory_retrieval` | 1500 |
| `project_context` | 500 |
| `project_plan` | 400 |
| `operating_procedures` | 400 |
| `queen_journal` | 300 |
| `thread_context` | 1500 |
| `tool_memory` | 4000 |
| `conversation_history` | 6000 |

### Source of truth

- `context_window` comes from `ModelRecord.context_window`
- output reserve comes from `_queen_max_tokens()`
- when `context_window` is missing, invalid, or too small, return the fallback
  budget unchanged

## Implementation

Add `src/formicos/surface/queen_budget.py` with:

- `QueenContextBudget`
- `compute_queen_budget(context_window, output_reserve)`

Thread the resulting budget through `queen_runtime.py` so these seams use
budget-backed values:

- compacted conversation history
- recent-window derivation
- tool-memory cap
- project-context slice
- cloud routing threshold

## Examples

Assume `output_reserve = 4096`:

| Model | context_window | Available | History slot | Thread slot | Tool memory |
|-------|----------------|-----------|--------------|-------------|-------------|
| 8K model | 8192 | 4096 | 6000 floor | 1500 floor | 4000 floor |
| 32K model | 32768 | 28672 | 8601 | 5734 | 4000 floor |
| 200K model | 200000 | 195904 | 58771 | 39180 | 19590 |
| 4K model | 4096 | 0 | 6000 floor | 1500 floor | 4000 floor |

This keeps small-model behavior stable while letting larger models breathe.

## Consequences

### Positive

- large-context models get proportionally richer Queen context
- small or unknown models behave like today
- budgets become explicit and inspectable
- new context sources fit into named slots instead of one-off constants

### Negative

- one more data structure threads through `queen_runtime.py`
- slot fractions may need tuning later

### Neutral

- `_CHARS_PER_TOKEN = 4` remains an approximation
- no new events or schema changes are required
- this is runtime-only behavior, not replayed state

## Alternatives Considered

**1. Flat output reserve percentage.**
Rejected because `_queen_max_tokens()` already computes the real output ceiling.

**2. Per-model manual caps.**
Rejected because it adds too much operator surface for a problem that should
be deterministic.

**3. Adaptive runtime reallocation.**
Rejected because it makes prompt assembly harder to reason about and verify.

**4. Single context multiplier.**
Rejected because different context sources should grow at different rates.
