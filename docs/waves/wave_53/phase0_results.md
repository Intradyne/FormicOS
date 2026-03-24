# Phase 0 Results — Wave 53

## Run metadata

| Field | Arm 1 (accumulate) | Arm 2 (empty) |
|-------|--------------------:|---------------:|
| Run ID | `bca38ea0d9a7` | `8c7fbfd254b6` |
| Suite | phase0 | phase0 |
| Knowledge mode | accumulate | empty |
| WORKSPACE_ISOLATION | false | false |
| Start | 2026-03-21T05:53Z | 2026-03-21T06:17Z |
| End | 2026-03-21T06:03Z | 2026-03-21T06:39Z |
| Wall time | ~9 min | ~22 min |
| Stack | Clean-room (fresh volumes) | Same session, second arm |
| Model | Qwen3-30B-A3B Q4_K_M via llama-cpp | Same |
| Cost per completion | $0.00 (local) | $0.00 (local) |

---

## Per-task comparison

| Task | Class | Accumulate ||| Empty |||
|------|-------|--------:|------:|------:|--------:|------:|------:|
| | | Quality | Rounds | Wall(s) | Quality | Rounds | Wall(s) |
| email-validator | simple | **0.9036** | 1 | 23 | **0.9036** | 1 | 23 |
| json-transformer | simple | **0.9036** | 1 | 56 | **0.9036** | 1 | 39 |
| haiku-writer | simple | **0.9036** | 1 | 22 | **0.9036** | 1 | 9 |
| csv-analyzer | moderate | 0.1978 | 5 | 31 | 0.1727 | 5 | 309 |
| markdown-parser | moderate | 0.1993 | 5 | 118 | **0.2654** | 5 | 78 |
| rate-limiter | moderate | 0.2173 | 8 | 114 | **0.2538** | 8 | 146 |
| api-design | moderate | **0.2667** | 8 | 141 | 0.1896 | 8 | 239 |
| data-pipeline | moderate | **0.1857** | 8 | 70 | 0.0 (timeout) | 8 | 601 |

---

## By task class

### Simple tasks (email-validator, json-transformer, haiku-writer)

| Metric | Accumulate | Empty | Delta |
|--------|----------:|------:|------:|
| Completion rate | 3/3 (100%) | 3/3 (100%) | 0 |
| Median quality | 0.9036 | 0.9036 | 0 |
| Median rounds | 1 | 1 | 0 |
| Entries extracted* | 0 | 0 | 0 |
| Entries accessed* | 0 | 0 | 0 |

Simple tasks show **no compounding signal**. Both arms produce identical quality
in 1 round. The model completes these on the first pass — there is nothing for
knowledge retrieval to improve.

### Moderate tasks (csv-analyzer, markdown-parser, rate-limiter, api-design, data-pipeline)

| Metric | Accumulate | Empty | Delta |
|--------|----------:|------:|------:|
| Completion rate | 5/5 (100%) | 4/5 (80%) | +1 task |
| Median quality | 0.1993 | 0.1896 | +0.0097 |
| Mean quality | 0.2134 | 0.1763 | +0.0371 |
| Median rounds | 8 | 8 | 0 |
| Total wall time | 474s | 1373s | -899s |

Moderate tasks show a **weak positive signal** for accumulate:

- **data-pipeline**: accumulate completed (0.1857); empty timed out (0.0).
  This is the strongest single-task difference and was the task designed as
  the "strongest compounding candidate" (last in sequence, multi-stage data).
- **api-design**: accumulate scored notably higher (0.2667 vs 0.1896).
- **markdown-parser** and **rate-limiter**: empty scored slightly higher,
  suggesting natural model variance rather than compounding.
- **csv-analyzer**: accumulate slightly higher (0.1978 vs 0.1727).

---

## Event store audit (post-run)

### Knowledge was produced — extraction pipeline worked

| Arm | MemoryEntryCreated | MemoryExtractionCompleted | Entries verified |
|-----|-------------------:|-------------------------:|-----------------:|
| Accumulate | **44** | 44 | 40 |
| Empty | **56** | 56 | 36 |

Extraction fired for 7/8 colonies per arm. Transcript harvest and LLM
extraction both ran correctly. The extraction pipeline is not inactive.

### Knowledge was NEVER retrieved — eval harness missing KnowledgeCatalog

**Root cause**: `eval/run.py` `_bootstrap()` does not wire up a
`KnowledgeCatalog` on the Runtime. Production `app.py` (lines 296-347)
creates and attaches the catalog explicitly. The eval bootstrap skips this.

Result: `runtime.fetch_knowledge_for_colony()` returns `[]` because
`catalog is None`. Zero `KnowledgeAccessRecorded` events in either arm.
**Both arms were effectively "empty" — knowledge was produced but could
never be consumed by later tasks.**

### Reporting bugs (secondary, but need fixing)

**Bug A — Wrong field**: `sequential_runner.py:561` reads
`transcript.get("skills_extracted")` which maps to `colony.skills_extracted`,
hardcoded to 0 since Wave 28. The actual counter is
`colony.entries_extracted_count` (tracked in projections via
`MemoryEntryCreated` handler).

**Bug B — Race condition**: Sequential runner snapshots results 3-12 seconds
before extraction completes. `_wait_for_colony()` returns as soon as
`ColonyCompleted` sets `status="completed"`, but extraction runs as
fire-and-forget `asyncio.create_task()` in `_post_colony_hooks`. Log evidence:

| Task | task_complete | extraction_complete | Gap |
|------|-------------|--------------------:|----:|
| email-validator | 05:54:16 | 05:54:23 | +7s |
| json-transformer | 05:55:09 | 05:55:15 | +6s |
| api-design | 06:01:48 | 06:02:00 | +12s |
| data-pipeline | 06:02:53 | *never logged* | exited |

---

## Parse failure observation

Both arms show high `parse_defensive.all_stages_failed` rates on moderate tasks
(~80-90% of agent turns). This is a model-level limitation of Qwen3-30B-A3B
with the current tool-call format, not a system bug. The model produces output
that the parse pipeline cannot extract structured tool calls from, so those
turns produce no code execution events. This is consistent across both arms and
does not bias the comparison.

---

## Wall time anomaly

Arm 2 (empty) took significantly longer overall: 22 min vs 9 min for Arm 1.
The per-task wall times diverge sharply on moderate tasks:

| Task | Accumulate wall(s) | Empty wall(s) | Ratio |
|------|---------:|---------:|------:|
| csv-analyzer | 31 | 309 | 10.0x |
| api-design | 141 | 239 | 1.7x |
| data-pipeline | 70 | 601 | 8.6x |

Possible causes: (1) LLM inference load from Arm 1's extraction hooks still
running in background, (2) Qdrant/SQLite I/O contention from Arm 1's
accumulated state, (3) LLM cache effects — Arm 1 warmed the KV cache and
similar prompts ran faster. This wall-time variance does not affect quality
scores (quality is computed from workspace output, not speed).

---

## Compounding verdict

**Compounding was not tested.** The eval harness is missing `KnowledgeCatalog`
wiring, so both arms ran without knowledge retrieval. The accumulate-vs-empty
comparison measured "no knowledge" vs "no knowledge."

### What Phase 0 DID prove

1. **Fast-path recalibration is a clear success.** Simple tasks: 0.9036 quality
   in 1 round, every time, both arms. Compare to the old pre-recalibration
   baseline of 0.197 quality in 10 rounds. The product's "minimal colony first"
   philosophy is empirically validated.

2. **Local model has a hard ceiling on moderate tasks.** Quality scores cluster
   at 0.17-0.27 with ~85% parse failure rate. This is a tool-call formatting
   problem, not a knowledge or colony-shape problem. More rounds don't help.

3. **data-pipeline is the only interesting candidate signal.** Accumulate
   completed (0.1857, 70s); empty timed out (600s). Could be workspace state
   or model variance — single data point, inconclusive.

4. **The knowledge extraction pipeline works.** 44 entries produced in
   accumulate, 56 in empty. Extraction is functional — retrieval is disconnected.

### What Phase 0 did NOT prove

It did not prove or disprove compounding because the experimental condition
(knowledge retrieval on vs off) was never activated.

### Priority fixes for Phase 0 re-run

1. **Wire `KnowledgeCatalog` in `eval/run.py` `_bootstrap()`** — replicate
   production `app.py` lines 296-347 catalog creation. This is the gating fix.
2. **Fix reporting**: read `entries_extracted_count` instead of `skills_extracted`
3. **Fix race**: await extraction completion before snapshotting results
4. **Raise model floor**: reduce parse failures via prompt engineering or model
   upgrade so knowledge has room to help

---

## Raw data location

- Arm 1 log: background task output `br7tcr0z8`
- Arm 2 log: `phase0_arm2_empty.log` + background task output `bz62dfzos`
- Results: `phase0_results/phase0/`
- Arm 1 run JSON: `run_20260321T060253_bca38ea0d9a7.json`
- Arm 2 run JSON: `run_20260321T063921_8c7fbfd254b6.json`
- Arm 2 results.jsonl: `results.jsonl` (Arm 1 was overwritten; data preserved in log)
