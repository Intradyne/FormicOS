# Reduced Tool Surface Experiment — Wave 53

## Experiment design

Test whether reducing the coder's tool set from 16 to 6 productive tools
shifts the Qwen3-30B-A3B model's behavior from "knowledge spam" to "productive
file/code actions" when combined with `tool_choice=required`.

### Conditions

| Setting | Full palette (prior) | Reduced surface (this) |
|---------|---------------------|----------------------|
| Coder tools | 16 (incl. memory, knowledge, git, transcript) | 6: list/read/write_workspace_file, patch_file, workspace_execute, code_execute |
| Reviewer tools | 9 (incl. memory, knowledge, transcript) | 4: list/read_workspace_file, git_status, git_diff |
| tool_choice | required | required |
| Model | Qwen3-30B-A3B Q4_K_M | same |
| Suite | smoke-scaffold (csv-analyzer, markdown-parser) | same |

### Hypothesis

The model spammed knowledge tools (109 KnowledgeAccessRecorded) in the prior
`tool_choice=required` test because those tools were "safe" escape hatches.
Removing them forces the model to use productive implementation tools.

---

## Results

| Metric | Full palette + required | Reduced surface + required |
|--------|------------------------:|---------------------------:|
| Parse failures | 0 | **0** |
| CodeExecuted | 5 | **0** |
| KnowledgeAccessRecorded | 109 | **0** (tools removed) |
| write_workspace_file | ? | **0** |
| patch_file | ? | **0** |
| code_execute | ? | **0** |
| workspace_execute | ? | **~189** (ls, mkdir loops) |
| csv-analyzer quality | 0.1550 | **0.1541** |
| markdown-parser quality | 0.1543 | **0.1542** |
| Stall rounds (both) | 3 | **3** |
| Wall time | 237.98s | **125.04s** |

### What the model actually did

With only productive tools available, the model called:

| Command | Count | Productive? |
|---------|------:|:-----------:|
| `ls -R` | 36 | No (repeated) |
| `ls -R markdown_parser/` | 32 | No (repeated) |
| `ls -la` | 29 | No (repeated) |
| `mkdir -p ... && touch ...` | ~44 | No (creates empty files) |
| `ls -la csv_analyzer` | 3 | No |
| `ls -R csv_analyzer/` | 2 | No |

**Zero calls to `write_workspace_file`, `patch_file`, or `code_execute`.**

The model creates project directory structures (`mkdir -p csv_analyzer &&
touch csv_analyzer/__init__.py`) and lists them repeatedly, but never writes
actual code to any file.

---

## Analysis

### The model finds new escape hatches

Removing knowledge tools eliminated knowledge spam (109 → 0). But the model
immediately found new escape hatches: `workspace_execute` with `ls` and `mkdir`
commands. The behavior pattern is identical:

1. Call a "safe" tool that produces output but doesn't advance the task
2. Read the output
3. Call the same type of tool again
4. Loop until rounds expire

With 16 tools: hides in `memory_search` / `scratch_memory`
With 6 tools: hides in `workspace_execute ls` / `mkdir`

### Tool selection is not choice overload — it's reasoning depth

The hypothesis was: "too many tools → model can't choose." The data refutes
this. With only 6 tools, the model still can't choose `write_workspace_file`
over `workspace_execute ls -R`. The problem is not the number of options —
it's that the model cannot reason about what constitutes productive work.

The model understands:
- It must call a tool (tool_choice=required enforces this)
- Files exist in the workspace (it lists them)
- Project structure should exist (it creates directories)

The model does NOT understand:
- It should write Python code to files
- It should execute code to test it
- Listing files 36 times does not advance the task

### Quality floor is ~0.154 regardless of condition

| Condition | csv quality | md quality |
|-----------|----------:|----------:|
| Baseline (no tool_choice) | 0.2268–0.2806 | 0.1721–0.2085 |
| tool_choice=auto | 0.1597 | 0.2597 |
| tool_choice=required, full palette | 0.1550 | 0.1543 |
| tool_choice=required, reduced tools | 0.1541 | 0.1542 |

All `tool_choice=required` conditions cluster at ~0.154 — the governance
score for "colony ran, tools were called, but no meaningful code produced."
The baseline without tool_choice scores higher (~0.22) because the model
writes code in its prose responses, which governance partially credits.

---

## Verdict

**Tool surface reduction does not fix the bottleneck.**

The Qwen3-30B-A3B model (3.3B active parameters) cannot:
1. **Select productive tools** — it loops on ls/mkdir regardless of palette size
2. **Generate code as tool arguments** — it never calls write_workspace_file
3. **Reason about task progress** — it repeats the same actions each round

This is a model capability ceiling, not a surface or adapter problem.

### What this experiment series proved (full chain)

| Experiment | What it tested | Finding |
|------------|---------------|---------|
| Phase 0 rerun | Knowledge pipeline wiring | Pipeline works, compounding signal weak |
| Prompt scaffold | Can prompts fix parse failures? | No — model-level |
| Qwen2.5-Coder-7B | Can code model fix parse failures? | Yes (85% → 14%) but task-dependent |
| tool_choice=auto | Does explicit auto help? | No effect (or negative) |
| tool_choice=required | Does forced structure help? | Fixes parsing, breaks tool selection |
| **Reduced tools + required** | **Is it choice overload?** | **No — model hides in any safe tool** |

### Recommended next move

**Stop optimizing around Qwen3-30B-A3B.** The model's 3.3B active parameters
are insufficient for agentic tool use on moderate tasks. Every adapter and
surface change tested has been absorbed by the model's inability to reason
about productive tool use.

**Next step: larger model evaluation.** The only condition that produced
productive tool use was Qwen2.5-Coder-7B (14 CodeExecuted on csv-analyzer).
A larger code-specialized model (Qwen2.5-Coder-32B, Qwen3-8B+) is the
minimum viable experiment.

### Changes reverted

Both `caste_recipes.yaml` (tool sets + system prompts) and
`llm_openai_compatible.py` (tool_choice) have been reverted to their
pre-experiment state. The scaffold (execution discipline) from the prior
smoke remains in place as it was neutral.

---

## Raw data

- Reduced-tools smoke log: `docs/waves/wave_53/qwen25coder_data/reduced_tools_smoke.log`
- tool_choice=auto log: `docs/waves/wave_53/qwen25coder_data/toolchoice_auto_smoke.log`
- tool_choice=required log: `docs/waves/wave_53/qwen25coder_data/toolchoice_required_smoke.log`
- Qwen2.5-Coder-7B log: `docs/waves/wave_53/qwen25coder_data/qwen25coder_smoke.log`
