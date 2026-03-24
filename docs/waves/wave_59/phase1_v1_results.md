# Phase 1 v1 Results -- Same-Domain Knowledge Compounding

**Date**: 2026-03-23
**Stack**: Wave 59 (full curating pipeline active)
**Archivist**: gemini/gemini-2.5-flash (asymmetric extraction)
**Coder model**: Qwen3-Coder-30B-A3B (local GPU, llama-cpp)
**Suite**: phase1 (8 same-domain data-processing tasks)
**Knowledge mode**: accumulate (shared workspace, knowledge carries forward)

## Historic finding

First eval run where knowledge entries cross the 0.50 similarity
threshold between tasks. 19 entries accessed across 7/8 tasks.

- Phase 0 (12 runs, diverse tasks): zero cross-task access.
- Phase 1 (1 run, same-domain tasks): 19 cross-task accesses.

The knowledge pipeline activates on same-domain task sequences.

---

## Arm 1: Accumulate

| Task | Pos | Quality | Wall (s) | Rounds | Extracted | Accessed | Pool size |
|------|-----|---------|----------|--------|-----------|----------|-----------|
| csv-reader | 1 | 0.612 | 135 | 3 | 3 | 0 | 0 |
| data-validator | 2 | 0.580 | 226 | 3 | 2 | 3 | 3 |
| data-transformer | 3 | 0.592 | 408 | 5 | 3 | 2 | 5 |
| pipeline-orchestrator | 4 | 0.574 | 312 | 5 | 3 | 2 | 8 |
| error-reporter | 5 | 0.571 | 276 | 5 | 4 | 4 | 11 |
| performance-profiler | 6 | 0.499 | 757 | ? | 12 | 3 | 15 |
| schema-evolution | 7 | 0.524 | 961 | 8 | 4 | 3 | 27 |
| pipeline-cli | 8 | 0.587 | 966 | 8 | 7 | 2 | 31 |

**Mean quality**: 0.567
**Total extracted**: 38 entries
**Total accessed**: 19 entries
**Tasks with access**: 7/8 (all except T1, which is cold start)
**Total wall time**: 4,041s (~67 min)

---

## Arm 2: PENDING

Gemini (429 rate limit) and Anthropic (400 Bad Request / cooldown) API
tokens exhausted during Arm 1. Empty arm will run when tokens reset.

Without Arm 2, the accumulate-vs-empty delta cannot be computed. The
access counts above prove the pipeline activates, but quality impact
requires the control arm.

---

## Signal Analysis

### Signal 1: Entries crossed the 0.50 similarity threshold

**YES.** 19 entries accessed across 7 tasks. This is the defining
difference from Phase 0. Same-domain vocabulary (CSV, validation,
pipeline, transform) produces embedding similarity above 0.50 where
cross-domain vocabulary (email-validator vs rate-limiter) does not.

### Signal 2: Specificity gate

No explicit gate fire/skip messages in logs. The gate checks for
project-specific signals ("our," "existing," "module") in task
descriptions. Tasks 2-8 all contain these signals. The gate may have
allowed injection without logging, or the similarity threshold alone
was sufficient to admit same-domain entries.

### Signal 3: knowledge_detail tool usage

**0 calls.** Agents received index-only summaries via progressive
disclosure but never pulled full content. This suggests either:
- The index summaries were sufficient for the tasks, or
- Agents did not recognize the knowledge_detail tool as available, or
- The tool was not offered to these castes.

This is a notable gap. Progressive disclosure's pull-on-demand model
was not exercised.

### Signal 4: Curation actions (Wave 59)

**1 REFINE action observed.**

```
MemoryEntryRefined: entry_id=mem-colony-60bb6531-e-4
  old_len=111, new_len=244, colony_id=colony-77c82532
```

The curating extraction prompt produced at least one REFINE action
during T2 (data-validator), improving an entry from T1. Content grew
from 111 to 244 characters -- the archivist added detail from the
validator's perspective.

This is the first observed REFINE in production. Wave 59's curating
pipeline is functional.

### Signal 5: Extraction volume

38 entries from 8 tasks (mean 4.75/task). T6 (performance-profiler)
produced 12 entries -- the researcher caste generates more observations.
Gemini archivist extraction is active (consistent with v12 finding of
3.4x vs local).

### Signal 6: API fallback impact

889 provider cooldown/error/retry events in the log. The run was
heavily impacted by API exhaustion:

- Anthropic: 400 Bad Request throughout (token/billing limit)
- Gemini: 429 rate limit on later tasks
- Fallback chain: anthropic -> gemini -> llama-cpp (local)

Most work was done by the local Qwen3-30B model. The researcher caste
(T6) was supposed to use a cloud provider but fell back to local,
which explains the 757s wall time and lower quality (0.499).

The heavy tasks (T7-T8) ran entirely on local GPU with 3 agents
competing for inference, explaining the ~960s wall times.

---

## Task Completion Log

```
18:42:02 task_complete  task=p1-csv-reader           q=0.612 rounds=3 ext=3 acc=0
18:46:03 task_complete  task=p1-data-validator        q=0.580 rounds=3 ext=2 acc=3
18:53:15 task_complete  task=p1-data-transformer      q=0.592 rounds=5 ext=3 acc=2
18:58:48 task_complete  task=p1-pipeline-orchestrator q=0.574 rounds=5 ext=3 acc=2
19:03:40 task_complete  task=p1-error-reporter        q=0.571 rounds=5 ext=4 acc=4
19:17:02 task_complete  task=p1-performance-profiler  q=0.499 rounds=? ext=12 acc=3
19:34:00 task_complete  task=p1-schema-evolution      q=0.524 rounds=8 ext=4 acc=3
19:51:03 task_complete  task=p1-pipeline-cli          q=0.587 rounds=8 ext=7 acc=2
19:51:03 sequential.complete  manifest=/data/eval/sequential/phase1/manifest_20260323T195103_cba77663...
```

---

## Interpretation (preliminary, Arm 1 only)

### What Phase 1 Arm 1 proves

1. **Same-domain entries cross the 0.50 threshold.** The embedding model
   (Qwen3-Embedding-0.6B) produces high enough similarity for tasks that
   share vocabulary and domain. The threshold is not the bottleneck for
   same-domain sequences.

2. **The knowledge pipeline activates.** 19 entries accessed across 7
   tasks. The retrieval + injection path works end-to-end for same-domain
   task sequences.

3. **Wave 59 curation is functional.** At least 1 REFINE action observed
   in production. The curating extraction prompt correctly identifies
   refinement opportunities.

### What Phase 1 Arm 1 cannot answer (needs Arm 2)

1. **Does access translate to quality improvement?** Without the empty
   arm, we cannot compute delta. The quality scores (mean 0.567) are
   plausible but not interpretable without a control.

2. **Is the quality curve shaped by knowledge or by task difficulty?**
   T6 (0.499) and T7 (0.524) are lower quality, but they are also the
   hardest tasks with the most API fallback pressure. Separating
   knowledge effect from difficulty effect requires the control arm.

### Quality observations

- Quality does NOT monotonically increase with pool size (would indicate
  compounding). Pattern: 0.612, 0.580, 0.592, 0.574, 0.571, 0.499,
  0.524, 0.587.
- T6 dip (0.499) likely caused by researcher caste falling back to local
  model (757s, 889 API errors).
- T8 recovery (0.587) despite largest pool and heaviest agent load
  suggests the local model handled the CLI task well.
- Mean quality (0.567) is below Phase 0 v7 mean (0.688), but Phase 0
  v7 ran with functioning cloud providers. API exhaustion is a
  confounding factor.

---

## Run artifacts

| Artifact | Location |
|----------|----------|
| Full log | `phase1_v1_arm1.log` (repo root) |
| Task results | `/data/eval/sequential/phase1/results.jsonl` (container) |
| Run manifest | `/data/eval/sequential/phase1/manifest_20260323T195103_cba77663*.json` (container) |
| Suite config | `config/eval/suites/phase1.yaml` |
| Task configs | `config/eval/tasks/p1-*.yaml` (8 files) |

---

## Next steps

1. **Arm 2 (empty)**: Run when API tokens reset. Same suite, same stack,
   `--knowledge-mode empty`. This produces the delta.

2. **Signal deep-dive**: Analyze which specific entries were accessed by
   which tasks. Are T1's CSV entries actually used by T4's orchestrator?

3. **knowledge_detail investigation**: Why zero calls? Check if the tool
   is offered to coder/reviewer castes in caste_recipes.yaml.

4. **API-clean rerun**: Consider a rerun with fresh API budget to remove
   the fallback confound. The current run's quality is depressed by
   ~889 fallback events.
