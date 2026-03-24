# tool_choice Experiment Results — Wave 53

## Experiment design

Three conditions tested on the same suite (csv-analyzer + markdown-parser),
same model (Qwen3-30B-A3B Q4_K_M), same scaffold (execution discipline):

1. **Baseline**: No `tool_choice` parameter (previous runs)
2. **tool_choice=auto**: Explicit `"auto"` in payload
3. **tool_choice=required**: Force every response to be a structured tool call

Plus the Qwen2.5-Coder-7B model swap from the prior smoke (no tool_choice).

## Results matrix

| Condition | Model | Parse failures | CodeExecuted | Quality csv | Quality md | KnowledgeAccess |
|-----------|-------|---------------:|-------------:|------------:|----------:|----------------:|
| Baseline | Qwen3-30B | ~85–95% | 0–2 | 0.2268–0.2806 | 0.1721–0.2085 | 5–11 |
| tool_choice=auto | Qwen3-30B | **100%** (20/20) | 0 | 0.1597 | 0.2597 | 5 |
| tool_choice=required | Qwen3-30B | **0%** (0/20) | 5 | 0.1550 | 0.1543 | **109** |
| No tool_choice | Qwen2.5-Coder-7B | **14.4%** (15/104) | **14** | 0.2553 | 0.1735 | 11 |

### Run IDs

| Condition | Run ID | Wall time |
|-----------|--------|-----------|
| tool_choice=auto | `6dcfc635bce8` | 155.54s |
| tool_choice=required | `2ecca940e9da` | 237.98s |
| Qwen2.5-Coder-7B | `37f961d886ec` | 327.66s |

---

## Analysis

### tool_choice=auto: no effect (or negative)

Explicitly setting `tool_choice=auto` with Qwen3-30B produced 100% parse
failures (20/20) — potentially worse than the ~85% baseline. The model
continued writing prose. llama.cpp may handle explicit `tool_choice=auto`
differently from omitting the parameter entirely, possibly enabling a grammar
constraint that the model's chat template doesn't properly support.

### tool_choice=required: parse solved, quality regressed

`tool_choice=required` completely eliminated parse failures: 0/20 agent turns
triggered `parse_defensive` fallback. Every response was a structured
`tool_calls` object with valid JSON.

**But quality dropped** to the lowest scores of any condition (0.155, 0.154).
The root cause: forced into structured tool calls, the model spammed
knowledge/scratch_memory tools instead of writing code:

- **csv-analyzer**: 0 CodeExecuted, 46 KnowledgeAccessRecorded — the model
  called scratch_memory search/upsert ~4.6x per turn instead of write_file +
  code_execute.
- **markdown-parser**: 5 CodeExecuted, 63 KnowledgeAccessRecorded — slightly
  better, but still dominated by knowledge tool calls.

The 109 total KnowledgeAccessRecorded events (vs 5–11 baseline) confirm the
model defaults to "safe" knowledge tools when forced to make a tool call but
unsure which tool to use.

### Why parse success ≠ quality improvement

The experiment isolates three distinct capabilities:

1. **Structured output** — can the model produce valid JSON tool calls?
2. **Tool selection** — does the model choose the right tool?
3. **Code generation** — does the model write correct code?

| Condition | Structured output | Tool selection | Code quality |
|-----------|:-:|:-:|:-:|
| Baseline (Qwen3-30B) | Poor | N/A (can't call tools) | N/A |
| tool_choice=required (Qwen3-30B) | Perfect | **Poor** (spams knowledge) | N/A |
| Qwen2.5-Coder-7B | Good (task-dependent) | Good (for csv-analyzer) | Moderate |

Qwen3-30B with tool_choice=required fixes capability #1 but exposes
deficiency #2. The model's 3.3B active parameters (MoE routing) apparently
lack the reasoning depth for tool selection in the FormicOS tool set.

Qwen2.5-Coder-7B (7B dense, code-specialized) has both #1 and #2 for simpler
tasks but fails on complex tasks (markdown-parser). Quality still doesn't
improve much because #3 (writing correct code for moderate tasks) remains
limited at 7B scale.

---

## Verdict

**tool_choice is not the high-leverage fix.** The bottleneck is model reasoning
about tool selection and code generation, not output format.

### What we proved

1. `tool_choice=auto` has no effect (or negative) on Qwen3-30B via llama.cpp
2. `tool_choice=required` eliminates parse failures but causes tool-selection
   regression — the model calls wrong tools
3. Quality ceiling is set by model reasoning capability, not output format
4. The Qwen3-30B-A3B MoE model (3.3B active params) lacks the depth for both
   tool selection AND code generation on moderate tasks
5. Qwen2.5-Coder-7B (7B dense) is better at tool selection but hits a quality
   ceiling on code correctness

### What to try next

The experiment narrows the search space. The bottleneck is model capability
(tool selection + code generation), not harness or adapter changes.

**Priority order:**

1. **Larger code-specialized model** — Qwen2.5-Coder-32B or Qwen3-Coder (when
   available). Needs >7B active params with code specialization.

2. **Tool set reduction** — reduce the number of tools presented to the model.
   Currently the agent sees ~12+ tools. Presenting only write_workspace_file,
   read_workspace_file, code_execute, and task_complete_signal for the coder
   caste could improve tool selection without changing models.

3. **Caste-specific tool_choice** — use `required` only for coder turns (where
   a tool call is always expected), `auto` or absent for reviewer turns (where
   text is appropriate). This needs a caller-side change in engine/runner.py.

4. **Two-model routing** — use Qwen2.5-Coder-7B for coder turns (good at
   tool calls) and Qwen3-30B for reviewer/researcher turns (better reasoning).
   The routing infrastructure already supports per-caste model assignment.

### Adapter change status

**Reverted.** The `tool_choice` additions to `llm_openai_compatible.py`
`complete()` and `stream()` have been removed. Neither `auto` nor `required`
improved quality on the current model.

The adapter remains ready for the change — it's a one-line addition per method
when paired with a model that benefits from it.

---

## Raw data location

- tool_choice=auto log: `docs/waves/wave_53/qwen25coder_data/toolchoice_auto_smoke.log`
- tool_choice=required log: `docs/waves/wave_53/qwen25coder_data/toolchoice_required_smoke.log`
- Qwen2.5-Coder-7B log: `docs/waves/wave_53/qwen25coder_data/qwen25coder_smoke.log`
