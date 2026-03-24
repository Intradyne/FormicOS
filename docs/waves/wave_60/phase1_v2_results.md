# Phase 1 v2 Results

Run date: 2026-03-23/24
Stack: Wave 59.5 (graph bridge, curating archivist, progressive disclosure fix)
Suite: Phase 1 -- 8 same-domain data-processing tasks, sequential execution
Scoring: FORMICOS_DETERMINISTIC_SCORING=1
Protocol: accumulate-vs-empty (identical tasks, identical models)

## Configuration

| Role | Model | Provider |
|------|-------|----------|
| Coder | Qwen3-30B-A3B | llama-cpp (local GPU) |
| Reviewer | gpt-4o | OpenAI (cloud) |
| Researcher | gpt-4o-mini | OpenAI (cloud) |
| Archivist | qwen3-coder:480b | Ollama Cloud (free) |

First multi-provider run: genuine parallel hardware utilization across
local GPU, OpenAI cloud, and Ollama cloud.

## Arm 1: Accumulate (multi-provider)

Knowledge pipeline active. Entries persist across tasks. Archivist curates
(CREATE/REFINE/MERGE/NOOP). Graph bridge connects entries with typed edges.

| # | Task | Quality | Rounds | Accessed | Extracted |
|---|------|---------|--------|----------|-----------|
| 1 | csv-reader | 0.629 | 3 | 0 | 6 |
| 2 | data-validator | 0.463 | 3 | 3 | 4 |
| 3 | data-transformer | 0.593 | 5 | 2 | 3 |
| 4 | pipeline-orchestrator | 0.573 | 5 | 2 | 2 |
| 5 | error-reporter | 0.582 | 5 | 2 | 2 |
| 6 | performance-profiler | 0.597 | 8 | 3 | 3 |
| 7 | schema-evolution | 0.602 | 8 | 2 | 7 |
| 8 | pipeline-cli | 0.601 | 8 | 2 | 10 |

- **Mean quality: 0.580**
- Total entries accessed: 16
- Total entries extracted: 37
- Wall time: ~75 min (4,525s)
- API cost: < $0.50 (researcher/reviewer only)

## Arm 2: Empty (multi-provider)

Knowledge pipeline disabled. Each task starts with empty knowledge bank.
Same models, same routing.

| # | Task | Quality | Rounds | Accessed | Extracted |
|---|------|---------|--------|----------|-----------|
| 1 | csv-reader | 0.490 | 3 | 0 | 0 |
| 2 | data-validator | 0.499 | 3 | 0 | 0 |
| 3 | data-transformer | 0.508 | 5 | 0 | 0 |
| 4 | pipeline-orchestrator | 0.572 | 5 | 0 | 0 |
| 5 | error-reporter | 0.690 | 3 | 0 | 0 |
| 6 | performance-profiler | 0.670 | 5 | 0 | 0 |
| 7 | schema-evolution | 0.531 | 8 | 0 | 0 |
| 8 | pipeline-cli | 0.595 | 8 | 0 | 0 |

- **Mean quality: 0.569**
- Total entries accessed: 0
- Total entries extracted: 0
- Wall time: ~51 min
- API cost: < $0.30 (researcher/reviewer only)

## Delta

**+0.011** (accumulate - empty)

Within the +/- 0.10 per-task noise band. Per-task variance (0.463-0.629
in Arm 1, 0.490-0.690 in Arm 2) exceeds the between-arm delta by an
order of magnitude.

## v1 vs v2 Comparison

Phase 1 v1 ran local-only (coder + archivist on llama-cpp, no cloud).
v2 added multi-provider routing: reviewer on gpt-4o, researcher on
gpt-4o-mini.

| Task | v1 Quality | v2 Quality | Delta |
|------|-----------|-----------|-------|
| csv-reader | 0.629 | 0.629 | 0.000 |
| data-validator | 0.463 | 0.463 | 0.000 |
| data-transformer | 0.593 | 0.593 | 0.000 |
| pipeline-orchestrator | 0.573 | 0.573 | 0.000 |
| error-reporter | 0.582 | 0.582 | 0.000 |
| performance-profiler | 0.499 | 0.597 | +0.098 |
| schema-evolution | 0.524 | 0.602 | +0.078 |
| pipeline-cli | 0.601 | 0.601 | 0.000 |

Tasks 1-5 produced identical results (same seed, coder on llama-cpp drove
quality). Tasks 6-7 recovered from v1's OpenAI 429 exhaustion -- v1 fell
back to local-only after API quota ran out mid-run. v2 ran with $10 prepaid
quota, zero 429 errors.

v1 mean: 0.558. v2 mean: 0.580. Improvement: +0.022 (API recovery effect).

## Observations

1. **Multi-provider routing works.** Three providers (local GPU, OpenAI,
   Ollama Cloud) served different castes concurrently without fallback
   chain failures.

2. **Curating archivist active.** 37 entries extracted with
   CREATE/REFINE/MERGE/NOOP curation (vs append-only in prior runs).
   Graph bridge connected entries with SUPERSEDES and DERIVED_FROM edges.

3. **Knowledge accessed but not impactful.** 16 entries accessed across
   8 tasks in the accumulate arm. Pipeline activates correctly on
   same-domain tasks. Quality impact: negligible.

4. **Empty arm faster.** 51 min vs 75 min -- no extraction, no curation,
   no archival overhead.

5. **Per-task variance dominates.** Error-reporter scored 0.582
   (accumulate) vs 0.690 (empty). Performance-profiler scored 0.597
   (accumulate) vs 0.670 (empty). Individual task variance is 10x the
   between-arm delta.
