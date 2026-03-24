# ADR-008: Tiered Context Window Management

**Status:** Proposed
**Date:** 2026-03-13

## Context

Current `engine/context.py` assembles agent context as a flat priority list
with a single `budget_tokens` parameter and a crude 4-char-per-token estimator.
Trimming removes messages from the tail (lowest priority). This has three
problems:

1. **No per-source caps.** One agent's 8000-token raw output can consume the
   entire budget, starving skill injection and round goals of context space.
2. **Lost-in-the-middle effect.** Research (Liu et al., 2024) shows LLM accuracy
   retrieving information at position 10 of 20 drops to ~55% vs ~80% at
   position 1. High-priority content buried in the middle gets deprioritized
   by the model regardless of our priority ordering.
3. **No compaction.** Previous round summaries are injected raw. A 25-round
   colony accumulates enormous prev_round_summary strings that dilute the
   current round's context.

## Decision

Context assembly uses **tiered budgets with per-source caps and positional
awareness**. The priority order remains the same (algorithms.md §4), but each
tier has an independent token cap and the assembly strategy respects the
"recency at edges" principle.

### Tier Budgets (configurable in `formicos.yaml`)

| Tier | Content | Default Cap | Priority |
|------|---------|-------------|----------|
| 1 | System prompt | Uncapped (always included) | Highest |
| 2 | Round goal | 500 tokens | High |
| 3 | Routed agent outputs | 1500 tokens total, 500 per source | High |
| 4 | Merge summaries | 500 tokens total | Medium |
| 5 | Previous round summary | 500 tokens (compacted) | Medium |
| 6 | Skill bank results | 800 tokens | Low |

Total budget: system_prompt + 3800 tokens of assembled context. The `max_tokens`
from `CasteRecipe` remains the output budget (separate concern).

### Per-Source Output Caps

When injecting routed agent outputs (tier 3), each source agent's output is
truncated to `max_output_per_source` (default 500 tokens). This prevents one
verbose agent from consuming the entire routed-context budget. Truncation
preserves the first and last 200 tokens with `[... truncated ...]` in the
middle — the "edges" carry the most information (opening summary + final
conclusion).

### Compaction of Previous Round Summary

When `prev_round_summary` exceeds 500 tokens, the runner compresses it before
injecting. Compression uses a simple extractive approach (no LLM call — too
expensive per round):

1. Split into sentences.
2. Score each sentence by keyword overlap with the current round goal.
3. Keep top-K sentences (by score) that fit within the 500-token budget.
4. Reassemble in original order.

This is cheap (~1ms), deterministic, and preserves goal-relevant content. LLM-
based summarization is deferred to post-alpha when the Compute Router can route
it to a cheap local model.

### Positional Awareness

The assembly order places the most important content at positions the model
attends to best (first and last):

```
Position 1: System prompt (always first — highest attention)
Position 2: Round goal (the task — must be salient)
Position 3+: Routed context, merge summaries (middle — acceptable)
Position N-1: Previous round summary (near end — good recall)
Position N: Skill bank results (last — high recall, lowest priority for trimming)
```

This contradicts the naive "highest priority first" ordering but matches the
empirical finding that models attend best to the beginning and end of context.

## Consequences

- **Good:** Prevents context window starvation. Every tier gets a guaranteed
  budget allocation regardless of what other tiers produce.
- **Good:** Output caps prevent verbose agents from dominating routed context.
- **Good:** Compaction keeps prev_round_summary from growing unboundedly.
- **Bad:** More configuration parameters. Tuning tier budgets requires
  experimentation (future Experimentation Engine work).
- **Acceptable:** The default budgets are conservative. They will work for
  Qwen3-30B's 8192 context window. Larger-context models can use larger budgets.

## FormicOS Impact

Affects: `engine/context.py`, `config/formicos.yaml` (new `context` section).
Reads: `core/types.py` (AgentConfig, ColonyContext).
