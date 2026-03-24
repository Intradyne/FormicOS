# Phase 0 Benchmark Contract — Wave 53

## Verdict

**GO — clean-room strongly recommended**

Phase 0 is now ready to run on a truthful benchmark mode (`WORKSPACE_ISOLATION=false`),
with retrieval isolation verified, partial-save verified, and task calibration aligned
to the product's minimal-colony-first philosophy.

---

## Hard benchmark conditions

These are non-negotiable for official Phase 0 runs:

1. **All runs use `WORKSPACE_ISOLATION=false`.**
   Isolated Docker workspace execution is denied by the current proxy/runtime config.
   The benchmark intentionally uses the truthful subprocess workspace path.
   Isolated Docker workspace execution remains open runtime/deployment debt.

2. **Clean-room state is strongly recommended.**
   Legacy thread-scoped entries exist in catalog inventory but do not contaminate
   fresh eval workspace retrieval (verified). Clean volumes remove theoretical
   edge cases and give the cleanest baseline.

3. **Task calibration is frozen as `phase0.yaml`.**
   Simple tasks: sequential fast-path, single coder, max 3 rounds.
   Moderate sequential: coder+reviewer, max 5 rounds.
   Moderate stigmergic: full castes, max 8 rounds.

---

## Arm-to-arm contamination

Running `accumulate` then `empty` in the same clean-room is acceptable.

- Auto-learned templates only emit when `spawn_source == "queen"`
  (`colony_manager.py:1531`).
- The sequential eval runner spawns colonies directly via `runtime.py`
  with the default empty `spawn_source`.
- Global knowledge promotion is not automatic.

The first arm does not auto-seed learned-template or global-knowledge
contamination into the second arm. If gold-standard hygiene is needed,
wipe between arms — but from current code truth it is not required.

---

## Preflight evidence

### Simple preflight: email-validator

| Field | Value |
|-------|-------|
| Status | completed |
| Rounds | 1 of 3 |
| Quality | 0.9036 |
| Wall time | 135s |
| Entries extracted | 0 |
| Entries accessed | 0 |
| Parse failures | 1 of ~2 turns |

### Moderate preflight: csv-analyzer (exact benchmark mode)

| Field | Value |
|-------|-------|
| Status | completed |
| Rounds | 5 of 5 |
| Quality | 0.2542 |
| Wall time | 60s |
| Entries extracted | 0 |
| Entries accessed | 0 |
| Workspace files | 5 files persisted (subprocess mode, truthful) |
| Parse failures | ~9 of 10 turns |

### Retrieval isolation (3 independent probes)

| Workspace | Query | Results |
|-----------|-------|---------|
| seq-smoke1-5263ac383f4b | "workspace not configured" | **0** |
| seq-phase0-0fdb15e97829 | "git unavailable" | **0** |
| seq-smoke-moderate-09d0c804d5bf | "workspace not configured" | **0** |

Code-level: `memory_store.py:219` skips non-global entries in merge;
`memory_store.py:259-262` filters by workspace_id server-side in Qdrant.

### Workspace truth (explicit probe, benchmark mode)

```
WORKSPACE_ISOLATION=False
Command: mkdir -p probe_dir && printf 'hello' > probe_dir/test.txt
exit_code=0
files_created=['probe_dir/', 'probe_dir/test.txt']
File exists: True
Content matches 'hello': True
```

### Partial-save

`results.jsonl` written incrementally, one valid JSON line per completed task.
Manifest and full run JSON also present.

---

## Budget enforcement note

Local llama-cpp reports $0.00 cost per completion. `budget_remaining` stays at
the initial value throughout all local runs. Budget enforcement does not
constrain local colonies — they run until `max_rounds` or completion, whichever
comes first. This is acceptable for Phase 0 measurement (budget is not the
variable being tested), but means budget-limit behavior is untested on local
model runs.

---

## Calibration comparison: old vs new

| Task | Old (stigmergic, 10 rounds) | New (calibrated) | New rounds |
|------|----------------------------|-------------------|------------|
| email-validator | 0.1971 | **0.9036** | 1 of 3 |
| csv-analyzer | 0.2095 | 0.2542 | 5 of 5 |

---

## Analysis structure for real benchmark

Report results by task class, not only overall:

### Simple tasks (email-validator, json-transformer, haiku-writer)
- completion rate
- median quality
- median rounds
- entries extracted / accessed
- parse failure count

### Moderate tasks (csv-analyzer, markdown-parser, rate-limiter, api-design, data-pipeline)
- completion rate
- median quality
- median rounds
- entries extracted / accessed
- parse failure count

Per-class breakdown prevents model/tool-call weakness on harder tasks
from blurring the compounding signal on simpler tasks.

---

## Run commands

### Step 1: Clean-room setup

```bash
cd /c/Users/User/FormicOSa
docker compose down -v
docker compose up -d
# Wait ~2 min for LLM model load
docker compose ps   # confirm all 5 services healthy
docker compose cp config/eval/suites/phase0.yaml formicos:/app/config/eval/suites/phase0.yaml
```

### Step 2: Arm 1 — accumulate

```bash
docker compose exec -e WORKSPACE_ISOLATION=false formicos bash -c '
  echo "=== BENCHMARK PREAMBLE ==="
  echo "WORKSPACE_ISOLATION=$WORKSPACE_ISOLATION"
  echo "SUITE=phase0"
  echo "KNOWLEDGE_MODE=accumulate"
  echo "TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "==========================="
  uv run python -m formicos.eval.sequential_runner \
    --suite phase0 --knowledge-mode accumulate
' 2>&1 | tee phase0_arm1_accumulate.log
```

### Step 3: Arm 2 — empty

```bash
docker compose exec -e WORKSPACE_ISOLATION=false formicos bash -c '
  echo "=== BENCHMARK PREAMBLE ==="
  echo "WORKSPACE_ISOLATION=$WORKSPACE_ISOLATION"
  echo "SUITE=phase0"
  echo "KNOWLEDGE_MODE=empty"
  echo "TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "==========================="
  uv run python -m formicos.eval.sequential_runner \
    --suite phase0 --knowledge-mode empty
' 2>&1 | tee phase0_arm2_empty.log
```

### Step 4: Collect results

```bash
docker compose cp formicos:/data/eval/sequential/phase0/ ./phase0_results/
```

---

## Abort conditions

Stop the run and investigate if any of these appear:

1. **Fresh retrieval contamination**: entries from outside the `seq-phase0-<run_id>`
   workspace appear in colony retrieval during the run.

2. **Workspace execution truth failure**: `workspace_execute` returns non-zero exit
   codes or empty `files_created` for legitimate file operations under
   `WORKSPACE_ISOLATION=false`.

3. **Catastrophic parse loop**: 3+ consecutive tasks where every agent turn hits
   `parse_defensive.all_stages_failed` and zero `CodeExecuted` events fire.

4. **Event store corruption**: `sqlite_store` errors or missing `results.jsonl`
   entries for completed tasks.
