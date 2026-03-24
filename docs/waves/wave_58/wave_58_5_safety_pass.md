# Wave 58.5: Mandatory Safety Pass Before Asymmetric Extraction

**Date**: 2026-03-23
**Status**: SUPERSEDED by `wave_58_5_plan.md` — this document is the v11 analysis;
the plan document has the actionable dispatch tracks
**Blocking**: Team 0 (asymmetric extraction) MUST NOT deploy until 58.5 lands

---

## What happened in v11

Phase 0 v11 ran with Gemini Flash as the archivist (one config line change).
The smarter model extracted 2.25x more entries per task. Then those entries
destroyed the heavy tasks:

| Task | v10 Acc (local archivist) | v11 Acc (Gemini archivist) | Delta |
|------|-------------------------|---------------------------|-------|
| email-validator | 0.899 | 0.880 | -0.019 |
| json-transformer | 0.864 | 0.878 | +0.014 |
| haiku-writer | 0.882 | 0.912 | +0.030 |
| csv-analyzer | 0.574 | 0.533 | -0.041 |
| markdown-parser | 0.000 | 0.000 | 0.000 |
| rate-limiter | 0.503 | 0.000 | **-0.503** |
| api-design | 0.523 | 0.000 | **-0.523** |
| data-pipeline | 0.470 | pending | — |

rate-limiter and api-design both completed fine in v10 with local extraction.
Both died in v11 with Gemini extraction. Both accessed 3 Gemini-extracted
entries before timing out.

## Root cause

Gemini Flash produces richer, longer, more detailed entries than Qwen3-Coder-30B.
By task 6 (rate-limiter), the pool has ~9 entries at ~160 tokens each = ~1,440
tokens of Gemini-quality knowledge injected into every round of the colony.

The simple 1-round tasks (email, json, haiku) survive because they complete
before the model loops with contaminated context. The heavy 8-round tasks
loop for 8 rounds with 1,440 tokens of sophisticated Gemini knowledge in
context every round. The 30B model's behavior degrades:

- "Context rot" (Du et al., EMNLP 2025): performance degrades 13.9-85% as
  input length increases, even when added content is relevant
- "Related but not relevant" (Cuconasu, SIGIR 2024): retrieved similar content
  performs worse than random noise
- Style mismatch: Gemini's vocabulary and reasoning patterns may produce code
  the 30B model cannot reliably execute

## What this means for Wave 58 deployment order

The original plan was: Teams 0+1+2 in parallel, then Team 3.

**THE NEW ORDER IS NON-NEGOTIABLE:**

```
Phase A:  Team 1 (specificity gate) -- MUST ship first
          Team 2 (trajectory storage) -- parallel with Team 1, safe
          
Phase A.5: VALIDATE that the gate correctly skips general tasks
           Run a quick smoke: does _should_inject_knowledge() return False
           for "implement a token bucket rate limiter"?

Phase B:  Team 3 (progressive disclosure) -- reduces tokens 800 -> 250
          VALIDATE: index-only injection confirmed, full content only via tool

Phase C:  Team 0 (asymmetric extraction) -- NOW SAFE because:
          - Gate skips injection for general tasks (rate-limiter, api-design)
          - When gate fires, injection is index-only (~50 tokens, not ~160)
          - Agent pulls full content on demand via knowledge_detail
          - Gemini entries never force-fed into context
```

**Team 0 MUST NOT merge before Teams 1 + 3.**

## What Wave 58.5 adds

A validation pass between Phase B and Phase C:

### 58.5 Step 1: Gate validation

Run Phase 0 v12 with Teams 1+2+3 merged but NO asymmetric extraction
(archivist still local). Confirm:
- Specificity gate skips injection for 6-7 of 8 general coding tasks
- Progressive disclosure injects ~250 tokens when gate fires (not ~800)
- Quality on completing tasks is >= v10 levels (no regression from gating)
- knowledge_detail tool works when agents pull on demand

### 58.5 Step 2: Gated asymmetric extraction

ONLY after Step 1 passes: change archivist to Gemini Flash and rerun.
Now Gemini's richer entries exist in the pool but:
- The gate skips injection for general tasks (rate-limiter completes)
- When injected (project-specific tasks), it's index-only (50 tokens)
- The model pulls full Gemini content ONLY when it decides to

### 58.5 Step 3: Comparison

| Config | Expected |
|--------|----------|
| v10: local extraction, full injection | baseline (delta -0.011) |
| v12: local extraction, gated + disclosure | should match or beat v10 |
| v13: Gemini extraction, gated + disclosure | the real test |

If v13 shows positive delta vs v12, asymmetric extraction works WHEN GATED.
If v13 shows negative delta, the entries themselves are harmful regardless
of injection method.

## The lesson

The v11 data is the most valuable negative result in the project.
It proves three things:

1. **Smarter extraction without gating is actively dangerous.**
   More knowledge != better outcomes. The context window has a carrying
   capacity, and exceeding it degrades the model.

2. **The specificity gate is not optional polish -- it's a safety mechanism.**
   Without it, any improvement to extraction quality becomes a regression
   risk for general tasks.

3. **Progressive disclosure is not optional polish -- it's a damage limiter.**
   Index-only injection (50 tokens vs 160) reduces the blast radius of any
   entry that shouldn't have been injected.

## Files

This document lives at: `docs/waves/wave_58/wave_58_5_safety_pass.md`

No code changes. This is a deployment ordering document that constrains
when Team 0's config changes can be applied.
