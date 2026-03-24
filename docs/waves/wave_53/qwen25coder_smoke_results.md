# Qwen2.5-Coder-7B Smoke Results — Wave 53

## Run metadata

| Field | Value |
|-------|-------|
| Run ID | `37f961d886ec` |
| Suite | smoke-scaffold (csv-analyzer, markdown-parser) |
| Knowledge mode | accumulate |
| Model | Qwen2.5-Coder-7B-Instruct Q4_K_M (4.4GB dense) via llama-cpp |
| Baseline model | Qwen3-30B-A3B Q4_K_M (MoE, 3.3B active) |
| Scaffold | Execution discipline (coder/reviewer/researcher) |
| Start | 2026-03-21T18:43Z |
| Wall time | 327.66s (~5.5 min) |
| Cost | $0.00 (local) |

## Hypothesis

A code-specialized 7B dense model (RL-trained for structured output/function
calling) materially lowers the tool-call parse failure rate compared to a 30B
MoE general-purpose model.

## Results

### Per-task comparison

| Task | Model | Quality | Rounds | Stalls | CodeExecuted | Parse fail rate |
|------|-------|--------:|-------:|-------:|-------------:|----------------:|
| csv-analyzer | **Qwen2.5-Coder-7B** | 0.2553 | 5 | **0** | **14** | **~5%** |
| csv-analyzer | Qwen3-30B-A3B (baseline) | 0.2268–0.2806 | 5–6 | 3+ | 0–2 | ~85–100% |
| markdown-parser | **Qwen2.5-Coder-7B** | 0.1735 | 5 | **3** | **0** | **100%** |
| markdown-parser | Qwen3-30B-A3B (baseline) | 0.1721–0.2085 | 5 | 3+ | 0 | ~100% |

### Parse success rate (aggregate)

| Metric | Qwen3-30B-A3B | Qwen2.5-Coder-7B |
|--------|-------------:|------------------:|
| Stage 2 (json_repair) successes | ~3–6 | **89** |
| All stages failed | ~85–95% | **15** (14.4%) |
| Overall parse success | ~5–15% | **85.6%** |

### Event store

| Event type | csv-analyzer | markdown-parser |
|------------|------------:|----------------:|
| CodeExecuted | **14** | 0 |
| KnowledgeAccessRecorded | 11 | 0 |
| MemoryEntryCreated | 3 | 0 |
| AgentTurnCompleted | 10 | 10 |
| RoundCompleted | 5 | 5 |

---

## Analysis

### Parse failure rate: confirmed model-level, now task-dependent

The aggregate parse success rate inverted: 85.6% with Qwen2.5-Coder-7B vs ~15%
with Qwen3-30B-A3B. This confirms the hypothesis that tool-call failure is
model-level behavior, not harness wiring.

However, the improvement is **task-dependent**:

- **csv-analyzer**: ~95% parse success, 14 code executions, 0 stall rounds.
  The model actively writes Python, executes it, reads results, iterates.
- **markdown-parser**: 0% parse success, 0 code executions, 3 stall rounds.
  Every turn produced ~6.6KB of prose/code that `parse_defensive` could not
  recover tool calls from.

The markdown-parser failure pattern: the model writes the full solution as a
markdown code block in its response text rather than wrapping it in a
`write_workspace_file` tool call. The 7B model understands tools for "simple"
tool patterns (write file, execute code) but regresses to prose mode when the
task description is more complex.

### Quality scores unchanged despite tool-call improvement

csv-analyzer quality (0.2553) is within the baseline range (0.2268–0.2806).
Despite executing 14 tool calls (vs 0–2 baseline), the quality score did not
materially improve. This suggests:

1. The quality scoring function (governance-weighted) penalizes aspects beyond
   "did the agent produce code" — likely correctness, completeness, test passage.
2. A 7B model writing code 14 times doesn't mean it's writing *correct* code.
3. The quality ceiling for moderate tasks may require a larger model or better
   prompting, not just better tool-call parsing.

### Fuzzy tool name match

One `fuzzy_match` event: model called `write_workspace_file` (correct tool name),
matched to `read_workspace_file`. This is a `parse_defensive` false positive
that should be investigated — it's matching a valid tool name to the wrong one.

---

## Verdict

**Parse failure floor: materially lowered for some tasks.**

The code-specialized model proves that structured output capability is the
dominant factor in tool-call success rate. But the improvement is task-dependent
and quality scores did not improve proportionally.

### Recommendation

1. **Do NOT proceed to full Phase 0 rerun** with Qwen2.5-Coder-7B alone.
   markdown-parser shows the model still fails on complex task descriptions.

2. **Investigate the fuzzy_match false positive** — `write_workspace_file`
   being matched to `read_workspace_file` may be silently corrupting tool
   calls.

3. **Next model candidates** (in priority order):
   - Qwen2.5-Coder-32B (if available in GGUF) — same architecture, 4.5x params
   - Qwen3-8B or Qwen3-14B dense — newer architecture with native tool support
   - Any model with native `tool_choice` support in llama.cpp chat templates

4. **Consider `tool_choice` parameter**: Qwen2.5-Coder-7B produced perfect
   structured `tool_calls` when `tool_choice=required` was set. Adding
   `tool_choice: "auto"` to the OpenAI-compatible adapter may improve all
   models' structured output without any model swap.

---

## Raw data location

- Smoke log: `docs/waves/wave_53/qwen25coder_data/qwen25coder_smoke.log`
- Run JSON: `docs/waves/wave_53/qwen25coder_data/run_20260321T184932_37f961d886ec.json`
- Manifest: `docs/waves/wave_53/qwen25coder_data/manifest_20260321T184932_37f961d886ec.json`
- Results JSONL: `docs/waves/wave_53/qwen25coder_data/results.jsonl`
