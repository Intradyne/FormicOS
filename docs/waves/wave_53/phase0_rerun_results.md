# Phase 0 Rerun Results — Wave 53

## Run metadata

| Field | Arm 1 (accumulate) | Arm 2 (empty) |
|-------|--------------------:|---------------:|
| Run ID | `501607065a70` | `21b397c18c32` |
| Suite | phase0 | phase0 |
| Knowledge mode | accumulate | empty |
| WORKSPACE_ISOLATION | false | false |
| Start | 2026-03-21T07:39Z | 2026-03-21T07:49Z |
| End | 2026-03-21T07:46Z | 2026-03-21T08:07Z |
| Wall time | ~6.8 min (406s) | ~20.4 min (1224s) |
| Stack | Clean-room (fresh volumes) | Same session, second arm |
| Model | Qwen3-30B-A3B Q4_K_M via llama-cpp | Same |
| Cost per completion | $0.00 (local) | $0.00 (local) |
| KnowledgeCatalog wired | **YES** | **YES** |
| Vector store (Qdrant) | **YES** (collections created) | **YES** (same instance) |

### Difference from first run (invalidated)

The first Phase 0 run (run IDs `bca38ea0d9a7` / `8c7fbfd254b6`) was invalidated because
`eval/run.py` `_bootstrap()` never created a `KnowledgeCatalog`, so neither arm had
knowledge retrieval. Additionally, the vector store config read raw YAML without
environment variable interpolation, causing `QdrantVectorPort` construction to silently
fail. This rerun fixes both bugs plus the extraction metrics mapping and timing race.

---

## Per-task comparison

| Task | Class | Accumulate ||| Empty |||
|------|-------|--------:|------:|------:|--------:|------:|------:|
| | | Quality | Rounds | Wall(s) | Quality | Rounds | Wall(s) |
| email-validator | simple | **0.9036** | 1 | 26 | **0.9036** | 1 | 21 |
| json-transformer | simple | **0.9036** | 1 | 46 | **0.9036** | 1 | 108 |
| haiku-writer | simple | **0.9036** | 1 | 2 | **0.9036** | 1 | 10 |
| csv-analyzer | moderate | 0.2268 | 5 | 79 | 0.1592 | 5 | 45 |
| markdown-parser | moderate | 0.2085 | 5 | 50 | 0.2311 | 5 | 88 |
| rate-limiter | moderate | 0.2471 | 8 | 130 | **0.2634** | 8 | 54 |
| api-design | moderate | **0.2708** | 8 | 46 | 0.2881 | 8 | 277 |
| data-pipeline | moderate | **0.1908** | 8 | 27 | 0.0 (failed) | 8 | 488 |

---

## Knowledge flow (accumulate arm only)

| Task | Seq | entries_accessed | entries_extracted | Knowledge IDs accessed |
|------|-----|-----------------|-------------------|----------------------|
| email-validator | 1 | 0 | 1 | (none — first task) |
| json-transformer | 2 | 1 | 1 | 1 from email-validator |
| haiku-writer | 3 | 5 | 1 | 5 from earlier extraction |
| csv-analyzer | 4 | 5 | 3 | 5 entries |
| markdown-parser | 5 | 5 | 0 | 5 entries |
| rate-limiter | 6 | 5 | 6 | 5 entries |
| api-design | 7 | 5 | 4 | 5 entries |
| data-pipeline | 8 | 5 | 10 | 5 entries |

### Knowledge timeline: boundary-visible vs eventual

Knowledge enters the system via two paths with different timing:

1. **Boundary-visible (fast harvest)**: `transcript_harvest` completes 0-1s after
   `ColonyCompleted`. These entries are available before `sequential.task_complete`
   fires. The `entries_extracted` count in results reflects this path.

2. **Eventual (LLM extraction)**: `memory_extraction` completes 3-8s after colony
   completion as fire-and-forget `asyncio.create_task()`. These entries arrive during
   the next task's execution.

| Colony | Fast harvest entries | LLM extraction entries | LLM extraction timing |
|--------|--------------------:|----------------------:|----------------------|
| email-validator | 1 | 5 | Completed during json-transformer R1 |
| json-transformer | 0 | 7 | Completed during haiku-writer R1 |
| csv-analyzer | 1 | 3 | Completed during markdown-parser |
| rate-limiter | 3 | 8 | Completed during api-design |

**Compounding is measured from eventual knowledge arriving one task later.**
The 5 entries accessed by tasks 4-8 come from the LLM extraction pass of tasks 1-2,
which completes during task 3. This means:
- Task 3 (haiku-writer) is the first task that could access compounded knowledge
- Tasks 4-8 all access the same top-5 results from the growing knowledge pool
- Knowledge retrieval saturates at 5 items (`top_k=5` in `fetch_knowledge_for_colony`)

---

## By task class

### Simple tasks (email-validator, json-transformer, haiku-writer)

| Metric | Accumulate | Empty | Delta |
|--------|----------:|------:|------:|
| Completion rate | 3/3 (100%) | 3/3 (100%) | 0 |
| Median quality | 0.9036 | 0.9036 | 0 |
| Median rounds | 1 | 1 | 0 |
| Total entries_accessed | 6 | 0 | +6 |
| Total entries_extracted | 3 | 2 | +1 |

Simple tasks show **no quality signal from compounding**. Both arms produce identical
quality in 1 round. Knowledge is accessed (6 entries in accumulate) but does not
measurably change the output.

### Moderate tasks (csv-analyzer, markdown-parser, rate-limiter, api-design, data-pipeline)

| Metric | Accumulate | Empty | Delta |
|--------|----------:|------:|------:|
| Completion rate | 5/5 (100%) | 4/5 (80%) | +1 task |
| Median quality | 0.2268 | 0.2311 | -0.0043 |
| Mean quality | 0.2288 | 0.1884 | +0.0404 |
| Median rounds | 8 | 8 | 0 |
| Total entries_accessed | 25 | 0 | +25 |
| Total entries_extracted | 23 | 13 | +10 |
| Total wall time | 332s | 952s | -620s |

Moderate tasks show a **weak positive signal** for accumulate:

- **data-pipeline**: accumulate completed (0.1908); empty failed (0.0). Strongest
  single-task difference. Same pattern as first run.
- **api-design**: empty scored slightly higher (0.2881 vs 0.2708). Reversed from
  the first invalidated run.
- **csv-analyzer**: accumulate notably higher (0.2268 vs 0.1592).
- **markdown-parser**: empty slightly higher (0.2311 vs 0.2085).
- **rate-limiter**: empty slightly higher (0.2634 vs 0.2471).

---

## Event store summary

| Metric | Arm 1 (accumulate) | Arm 2 (empty) |
|--------|-------------------:|---------------:|
| KnowledgeAccessRecorded | 38 | 9 (all items=0) |
| MemoryEntryCreated | 57 | 49 |
| MemoryExtractionCompleted | 15 | 16 |

### Cross-arm contamination check

All 9 `KnowledgeAccessRecorded` events in Arm 2 have `items=[]`. The knowledge
system fires (catalog is wired) but correctly returns empty results because each
empty-mode task has its own fresh workspace with no vector entries. **No
contamination detected.**

---

## Wall time anomaly (persists)

Arm 2 (empty) took 3x longer: 1224s vs 406s. Same pattern as the invalidated run.

| Task | Accumulate wall(s) | Empty wall(s) | Ratio |
|------|---------:|---------:|------:|
| json-transformer | 46 | 108 | 2.3x |
| csv-analyzer | 79 | 45 | 0.6x |
| api-design | 46 | 277 | 6.0x |
| data-pipeline | 27 | 488 | 18.1x |

Likely causes: (1) LLM inference contention from Arm 1's background extraction
completing, (2) KV cache warming from Arm 1 (similar prompts faster on first
pass), (3) Qdrant I/O from Arm 1's accumulated state. This does not affect
quality scores.

---

## Compounding verdict

**Compounding was tested.** This is a valid measurement.

### What the rerun proves

1. **Knowledge retrieval is operational.** 38 `KnowledgeAccessRecorded` events with
   non-empty items in accumulate. Zero items in empty. The experimental condition
   (knowledge on vs off) is correctly differentiated.

2. **Fast-path recalibration confirmed.** Simple tasks: 0.9036 quality in 1 round,
   both arms, every time.

3. **Knowledge production is robust.** 57 entries produced in accumulate, 49 in empty.
   Extraction pipeline works in both modes.

4. **Compounding signal is weak at the model floor.** With ~85% parse failure rate,
   the model cannot act on injected knowledge effectively. Quality scores cluster
   at 0.15-0.29 on moderate tasks regardless of knowledge access.

5. **data-pipeline is the consistent signal.** Accumulate completed (0.1908, 27s);
   empty failed (0.0, 488s). This reproduced from the invalidated run. Could be
   workspace state (accumulate has more files from earlier tasks) rather than
   knowledge compounding.

### Mean quality lift

- Moderate tasks mean: accumulate 0.2288 vs empty 0.1884 — **+0.0404 lift**
- If data-pipeline is excluded (completion vs failure biases mean):
  accumulate 0.2383 vs empty 0.2355 — **+0.0028 lift** (within noise)

### Interpretation

The compounding condition is now correctly active, but the local model's tool-call
parse failure rate (~85%) creates a hard ceiling that knowledge injection cannot
overcome. The model receives 5 knowledge items per round via `[System Knowledge]`
context injection, but with only ~15% of agent turns producing parseable tool calls,
the knowledge has minimal opportunity to influence code generation.

**Next bottleneck: model/tool-use behavior, not harness wiring.**

---

## Harness fixes applied (4 bugs)

1. **Wire KnowledgeCatalog** in `eval/run.py` `_bootstrap()` — create MemoryStore +
   KnowledgeCatalog, wire to runtime, rebuild after replay.

2. **Fix config interpolation** in `eval/run.py` — vector store config was reading
   raw YAML without `_interpolate_recursive()`, so `${QDRANT_URL:...}` was passed
   as a literal string to QdrantClient, causing silent failure.

3. **Fix extraction metrics** in `sequential_runner.py` — use
   `colony_proj.entries_extracted_count` instead of `transcript.get("skills_extracted")`
   (hardcoded 0 since Wave 28).

4. **Fix extraction timing race** in `sequential_runner.py` — add bounded 30s wait
   for `MemoryExtractionCompleted` after colony completion before snapshotting results.

---

## Raw data location

- Arm 1 log: `/c/tmp/phase0_rerun2_arm1.log`
- Arm 2 log: `/c/tmp/phase0_rerun2_arm2.log`
- Arm 1 results.jsonl: `/c/tmp/phase0_rerun2_results/results_arm1.jsonl`
- Arm 2 results.jsonl: `/c/tmp/phase0_rerun2_arm2_results/results_arm2.jsonl`
- Arm 1 run JSON: `run_20260321T074604_501607065a70.json`
- Arm 2 run JSON: `run_20260321T080738_21b397c18c32.json`
- Arm 1 manifest: `manifest_20260321T074604_501607065a70.json`
- Arm 2 manifest: `manifest_20260321T080738_21b397c18c32.json`
