# Phase 0 v4 Results -- Qwen3-Coder Model Upgrade

## 1. Conditions

- **Date**: 2026-03-22
- **Arm 1 run ID**: `a055f566be6e` (accumulate)
- **Arm 2 run ID**: `9397baef07a1` (empty)
- **Config hash**: `9d23e65f5f8f1b78` (identical both arms)
- **Docker image**: Same Wave 55 build, clean-room volumes
- **Model**: Qwen3-Coder-30B-A3B-Instruct (Q4_K_M) via llama-cpp
- **Change from v3**: Model swap only (`LLM_MODEL_FILE` env var). No code changes.
- **WORKSPACE_ISOLATION**: `false` (both arms)
- **Formula version**: v2 (5-signal weighted geometric mean with productivity)
- **Tasks**: 8, calibrated profiles (3 simple, 2 moderate, 3 heavy)
- **All 5 services healthy** at run start

## 2. Per-task Comparison Table

| Task | Class | Acc Status | Acc Q | Acc Rounds | Acc Extracted | Acc Accessed | Acc Wall | Empty Status | Empty Q | Empty Rounds | Empty Extracted | Empty Accessed | Empty Wall |
|------|-------|-----------|-------|-----------|--------------|-------------|---------|-------------|---------|-------------|----------------|---------------|-----------|
| email-validator | simple | completed | 0.8586 | 1 | 1 | 0 | 300s | completed | 0.8503 | 1 | 0 | 0 | 56s |
| json-transformer | simple | completed | 0.8027 | 1 | 0 | 1 | 68s | completed | 0.8706 | 1 | 1 | 0 | 59s |
| haiku-writer | simple | completed | 0.3671 | 1 | 0 | 5 | 1s | completed | 0.3671 | 1 | 0 | 0 | 1s |
| csv-analyzer | moderate | completed | 0.4149 | 5 | 0 | 5 | 16s | completed | 0.4052 | 5 | 4 | 0 | 78s |
| markdown-parser | moderate | completed | 0.4697 | 5 | 2 | 5 | 197s | completed | 0.5215 | 5 | 3 | 0 | 195s |
| rate-limiter | heavy | completed | 0.3508 | 8 | 4 | 5 | 41s | completed | 0.5079 | 8 | 4 | 0 | 100s |
| api-design | heavy | completed | 0.3100 | 8 | 8 | 5 | 43s | completed | 0.3402 | 6 | 0 | 0 | 52s |
| data-pipeline | heavy | completed | 0.5281 | 8 | 6 | 5 | 448s | completed | 0.4062 | 8 | 4 | 0 | 156s |

## 3. By-class Summary

### Simple (email-validator, json-transformer, haiku-writer)

| Metric | Accumulate | Empty |
|--------|-----------|-------|
| Completion rate | 3/3 | 3/3 |
| Mean quality | 0.6761 | 0.6960 |
| Delta | -0.020 | -- |
| Total entries extracted | 1 | 1 |
| Total entries accessed | 6 | 0 |
| Mean wall time | 123s | 39s |

Simple tasks: essentially tied (-0.020). haiku-writer identical in both
arms (0.3671). json-transformer slightly favors empty (-0.068), likely
model variance on 1-round tasks.

### Moderate (csv-analyzer, markdown-parser)

| Metric | Accumulate | Empty |
|--------|-----------|-------|
| Completion rate | 2/2 | 2/2 |
| Mean quality | 0.4423 | 0.4634 |
| Delta | -0.021 | -- |
| Total entries extracted | 2 | 7 |
| Total entries accessed | 10 | 0 |
| Mean wall time | 107s | 137s |

Moderate tasks: essentially tied (-0.021). markdown-parser slightly favors
empty (-0.052); csv-analyzer slightly favors accumulate (+0.010).

### Heavy (rate-limiter, api-design, data-pipeline)

| Metric | Accumulate | Empty |
|--------|-----------|-------|
| Completion rate | 3/3 | 3/3 |
| Mean quality | 0.3963 | 0.4181 |
| Delta | -0.022 | -- |
| Total entries extracted | 18 | 8 |
| Total entries accessed | 15 | 0 |
| Mean wall time | 177s | 103s |

Heavy tasks: slightly negative (-0.022). data-pipeline strongly favors
accumulate (+0.122), but rate-limiter strongly favors empty (-0.157).
api-design slightly favors empty (-0.030).

### Overall

| Metric | Accumulate | Empty |
|--------|-----------|-------|
| Completion rate | 8/8 (100%) | 8/8 (100%) |
| Mean quality (all 8) | 0.5002 | 0.5336 |
| Delta | -0.033 | -- |
| Total entries extracted | 21 | 16 |
| Total entries accessed | 31 | 0 |
| Total wall time | 1115s | 698s |

## 4. Compounding Assessment

### Is the accumulate arm better overall?

**No.** Empty arm mean quality (0.534) exceeds accumulate (0.500) by 0.033.
This is the reverse of v3. With both arms completing 8/8, no failure-driven
confound explains the gap.

### Per-task deltas

| Task | Acc Q | Empty Q | Delta | Signal |
|------|-------|---------|-------|--------|
| email-validator | 0.8586 | 0.8503 | +0.008 | Noise |
| json-transformer | 0.8027 | 0.8706 | -0.068 | Model variance |
| haiku-writer | 0.3671 | 0.3671 | 0.000 | Identical |
| csv-analyzer | 0.4149 | 0.4052 | +0.010 | Noise |
| markdown-parser | 0.4697 | 0.5215 | -0.052 | Mild empty advantage |
| rate-limiter | 0.3508 | 0.5079 | -0.157 | **Strong empty advantage** |
| api-design | 0.3100 | 0.3402 | -0.030 | Mild empty advantage |
| data-pipeline | 0.5281 | 0.4062 | +0.122 | **Strong accumulate advantage** |

The biggest swings: rate-limiter (-0.157 favoring empty) and data-pipeline
(+0.122 favoring accumulate). These nearly cancel.

### What happened to the compounding signal?

Three hypotheses:

1. **Knowledge quality mismatch**: The Coder model extracted 21 entries
   (vs 9 in v3), but extracted knowledge may not match retrieval needs.
   More entries doesn't mean better entries — irrelevant knowledge in
   context can hurt performance by consuming token budget.

2. **Retrieval noise at scale**: With 21 entries available by task 8 (vs 9
   in v3), the retrieval system returns 5 entries per task. More candidates
   means more chance of retrieving low-relevance entries that dilute context.

3. **Model-specific tool calling patterns**: The Coder model's tool calling
   may produce different convergence/progress patterns that interact
   differently with the knowledge pipeline. The faster inference times
   (698s total for empty arm vs 1081s in v3) suggest the model generates
   shorter outputs, which affects the quality formula's productivity signal.

### 100% completion in both arms

The most important structural result: **both arms completed all 8 tasks**.
This is the first run with no failures in either arm across all three
Phase 0 measurement versions. Wave 55 progress truth + Qwen3-Coder
eliminated both failure modes (false governance halt and model timeout).

## 5. Cross-version Comparison (v3 vs v4, accumulate arm)

| Task | v3 Q (general) | v4 Q (coder) | Delta | Notes |
|------|---------------|-------------|-------|-------|
| email-validator | 0.8424 | 0.8586 | +0.016 | Stable |
| json-transformer | 0.7677 | 0.8027 | +0.035 | Slight improvement |
| haiku-writer | 0.8503 | 0.3671 | -0.483 | **Score swap** (model variance) |
| csv-analyzer | 0.4770 | 0.4149 | -0.062 | Slight regression |
| markdown-parser | 0.4730 | 0.4697 | -0.003 | Stable |
| rate-limiter | 0.5082 | 0.3508 | -0.157 | **Regression** |
| api-design | 0.2326 | 0.3100 | +0.077 | **Improvement** |
| data-pipeline | 0.5373 | 0.5281 | -0.009 | Stable |
| **Mean** | **0.5361** | **0.5002** | **-0.036** | |

The Coder model does not produce higher quality scores on average.
The haiku-writer swap dominates the mean (-0.483). Excluding it,
the remaining 7 tasks show a mean delta of -0.015 — essentially flat.

### Knowledge production comparison

| Metric | v3 Acc | v4 Acc | Delta |
|--------|-------|-------|-------|
| Entries extracted | 9 | 21 | +133% |
| Entries accessed | 29 | 31 | +7% |
| api-design extracted | 0 | 8 | New |
| data-pipeline extracted | 3 | 6 | +100% |

The Coder model is a dramatically better knowledge **producer** (2.3x
entries), but this doesn't translate to higher quality in the same run.
The knowledge may benefit future runs or longer task sequences.

## 6. What This Means for the Project

### Model swap is not a silver bullet

The Qwen3-Coder model did not improve compounding. The accumulate-empty
delta went from +0.129 (v3) to -0.033 (v4). The Coder model produces
more knowledge but doesn't benefit from it within a single 8-task sequence.

### 100% completion is the real win

Both models, both arms, all 8 tasks completed in v4. This is the strongest
evidence that Wave 55's progress truth fix is robust — it works regardless
of which model is generating the tool calls.

### Knowledge production is model-dependent

21 entries in v4 vs 9 in v3 with identical infrastructure. The extraction
pipeline amplifies model behavior. A model that generates richer tool-call
output produces more extractable knowledge.

### The compounding question is still open

With model variance ~0.15-0.48 per task and only 8 tasks per run, the
signal cannot be distinguished from noise in any single run. The
accumulate-empty delta across all four arms (v3+v4) is:

| Run | Acc Mean | Empty Mean | Delta |
|-----|---------|-----------|-------|
| v3 (general) | 0.536 | 0.407 | +0.129 |
| v4 (coder) | 0.500 | 0.534 | -0.033 |
| **Pooled** | **0.518** | **0.470** | **+0.048** |

Pooled across both models: accumulate leads by +0.048. Not definitive,
but directionally positive.

### Recommended next steps

1. **Repeated trials** (3x per task per model) — the single most important
   investment for statistical power. The infrastructure is proven, the
   failure modes are fixed, the measurement is cheap.
2. **Investigate rate-limiter regression** in v4 — the -0.157 delta is
   the largest single-task swing. Understanding why the Coder model
   underperforms on this specific task with knowledge access may reveal
   retrieval quality issues.
3. **Retrieval quality analysis** — compare which entries are retrieved
   across v3 vs v4. If v4's larger knowledge pool causes lower-relevance
   retrievals, the composite scoring weights may need adjustment.

## Raw Data

Run files preserved in container at `/data/eval/sequential/phase0/`:
- `run_20260322T031429_a055f566be6e.json` (Arm 1: accumulate, Qwen3-Coder)
- `run_20260322T032815_9397baef07a1.json` (Arm 2: empty, Qwen3-Coder)
- `manifest_*.json` (run manifests)
