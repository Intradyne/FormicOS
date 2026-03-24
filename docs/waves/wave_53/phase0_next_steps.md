# Phase 0 Rerun: Conclusions and Next Steps

## What Phase 0 established

### Settled

1. **Fast-path calibration is a clear product win.** Simple tasks: 0.9036
   quality in 1 round, both arms. Compare to 0.197/10 rounds pre-calibration.
   The product's minimal-colony-first philosophy is empirically validated.

2. **The learning pipeline works end-to-end.** Knowledge is produced
   (44-56 entries per arm), retrieved (38 access events in accumulate,
   0 in empty), and correctly isolated between workspaces.

3. **The eval harness is now valid.** Four bugs fixed. Catalog wired.
   Metrics correct. Timing race resolved. The harness measures what it
   claims to measure.

4. **The local model has a hard moderate-task ceiling.** ~85% parse failure
   rate on Qwen3-30B-A3B. Quality clusters at 0.17-0.27 regardless of
   knowledge availability. The ceiling is set by tool-call formatting
   reliability, not knowledge.

5. **The accumulate arm is measurably more efficient.** 406s vs 1224s
   wall time (3x). 8/8 tasks completed vs 7/8. Whether from memory
   or workspace state, carrying state forward helps the product.

### Not settled

1. **Memory-only compounding is not isolated.** The accumulate arm carries
   forward both workspace files AND knowledge entries. The strongest
   task-level signal (data-pipeline completing vs timeout) is the one
   most plausibly explained by workspace artifact carry-over, not memory
   retrieval.

2. **The +0.04 mean quality lift is within noise.** Excluding
   data-pipeline, the lift drops to +0.003. The local model's parse
   failure rate creates too much variance for a small quality delta
   to be meaningful.

## The confound the orchestrator identified

Current eval semantics:
- `accumulate`: one shared workspace + knowledge retrieval active
- `empty`: fresh workspace per task + no knowledge retrieval

This conflates two effects:
- institutional memory compounding (retrieved knowledge improving later tasks)
- workspace state compounding (prior files/artifacts giving later tasks a head start)

A clean memory-only test would require a third arm:
- shared workspace + knowledge retrieval disabled

This would isolate memory's contribution. However, this experiment
does not change the next action regardless of outcome -- the model
floor is the bottleneck either way.

## Recommended next steps (priority order)

### 1. Raise the model floor (highest leverage, do now)

The ~85% parse failure rate on moderate tasks is the gating bottleneck.
Knowledge retrieval cannot help when the model fails to produce valid
tool calls. Two parallel paths:

**Path A: Prompt scaffold (cheapest, do first)**

Add the three-instruction scaffold to all caste system prompts in
`config/caste_recipes.yaml`:

1. Persistence: "Keep working until the task is fully resolved."
2. Tool discipline: "Do not guess. Use tools to verify state before
   and after changes."
3. Planning: "Before each tool call, state what you expect. After
   each result, assess whether it advanced the goal."

~60 tokens per caste. Zero code changes. Empirically validated at
~20% SWE-bench improvement. Directly targets the parse failure
pattern by encouraging more structured model output.

**Path B: Qwen3-Coder evaluation (higher ceiling, do second)**

Qwen3-Coder-30B-A3B-Instruct: same VRAM envelope, RL-trained for
agentic coding. The non-thinking -2507 variant eliminates think-tag
conflicts with tool-call stopwords. Community reports confirm
significantly better tool-calling stability. Requires downloading
the GGUF, registering in formicos.yaml, and using the Unsloth-fixed
Jinja template.

### 2. Re-run Phase 0 after model floor improves

If parse failures drop from 85% to 50%, knowledge retrieval has 3x
more opportunities to influence outcomes. The compounding signal should
become visible if it exists. Use the same calibrated suite.

### 3. Isolate memory vs workspace state (optional, after model improves)

Run a third arm: shared workspace + knowledge_mode=empty. This isolates
workspace-state compounding from memory compounding. Defer until the
model floor is high enough to produce a clear signal -- on the current
model, the noise floor is too high for this experiment to be informative.

### 4. Cloud-assisted measurement (if local floor stays too low)

If prompt scaffold + Qwen3-Coder still can't break through ~50% parse
success on moderate tasks, run one Phase 0 arm with a cloud model
(Anthropic or MiniMax M2.7) that has near-zero parse failures. This
isolates the compounding question from the model quality question
entirely.

## What NOT to do

- No more harness fixes (the harness is valid)
- No new infrastructure waves
- No broad caste/tool redesign
- No protocol expansion
- No "fix compounding" architecture work
- No cloud provider additions before local model floor is tested

## The honest one-line summary

Phase 0 proved the infrastructure works and the product benefits
from carrying state forward, but the local model's tool-call
reliability is too low to produce a clean compounding signal --
raise the model floor first, then re-measure.
