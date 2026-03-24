# Tool Dispatch and Agent Loop — Integration Reference

How tools flow from config to model to execution, how governance works, and
where the quality score comes from.

> **Last updated: 2026-03-23** — aligned with Waves 54–59. Quality score now 5 signals,
> governance broadened with `recent_productive_action`, convergence status injected.
> See also: `docs/specs/colony_execution.md` for full current-state spec.

---

## Tool registry

All 27 tools defined in `TOOL_SPECS` dict ([tool_dispatch.py:19–529](src/formicos/engine/tool_dispatch.py#L19-L529)).

### Productive implementation tools (what generates artifacts)

| Tool | Category | What it does |
|------|----------|-------------|
| `write_workspace_file` | write_fs | Create/overwrite file by path + content |
| `patch_file` | write_fs | Surgical search/replace operations array |
| `code_execute` | exec_code | Run Python in sandbox (Docker, 30s timeout) |
| `workspace_execute` | exec_code | Run shell command in workspace dir (120s timeout) |
| `read_workspace_file` | read_fs | Read file by path (offset + limit) |
| `list_workspace_files` | read_fs | Glob pattern file listing (max 50 results) |
| `git_commit` | write_fs | Stage all + commit with message |

### Knowledge/memory tools (escape hatches in experiments)

| Tool | Category | What it does |
|------|----------|-------------|
| `memory_search` | vector_query | Search scratch memory + workspace library + skill bank |
| `memory_write` | vector_query | Store finding/decision/pattern/note in scratch memory |
| `knowledge_detail` | vector_query | Full entry by ID (posteriors, provenance, observations) |
| `transcript_search` | vector_query | Search past colony transcripts |
| `knowledge_feedback` | vector_query | Report entry helpful/wrong |
| `artifact_inspect` | read_fs | Read artifact from completed colony |

### Observation tools

| Tool | Category | What it does |
|------|----------|-------------|
| `git_status` | read_fs | Working tree status |
| `git_diff` | read_fs | Changes (optional path filter, staged-only mode) |
| `git_log` | read_fs | Recent commit history (n=1–50) |

### Other

| Tool | Category |
|------|----------|
| `request_forage` | search_web |
| `http_fetch` | search_web |
| `query_service` | delegate |
| `file_read` / `file_write` | read_fs / write_fs (legacy) |

---

## How tools reach the model

### Step 1: Config defines caste tool list

[caste_recipes.yaml:217](config/caste_recipes.yaml#L217) (coder):
```yaml
tools: ["memory_search", "memory_write", "code_execute", "workspace_execute",
        "list_workspace_files", "read_workspace_file", "write_workspace_file",
        "patch_file", "git_status", "git_diff", "git_commit", "git_log",
        "knowledge_detail", "transcript_search", "artifact_inspect", "knowledge_feedback"]
```

**16 tools for coder.** Reviewer has 9. Researcher has 11.

### Step 2: Runner builds LLMToolSpec list

[runner.py:1361–1366](src/formicos/engine/runner.py#L1361-L1366):
```python
available_tools: list[LLMToolSpec] = []
for tool_name in agent.recipe.tools:       # From caste_recipes.yaml
    if tool_name in TOOL_SPECS:            # Must exist in registry
        available_tools.append(TOOL_SPECS[tool_name])
tools_arg = available_tools if available_tools else None
```

### Step 3: Tools passed to LLM

[runner.py:1408–1414](src/formicos/engine/runner.py#L1408-L1414):
```python
response = await llm_port.complete(
    model=effective_model,
    messages=injected_messages,
    tools=None if is_final_iteration else tools_arg,  # None on last iter
    temperature=agent.recipe.temperature,
    max_tokens=effective_output_tokens,
)
```

**Critical:** Final iteration sets `tools=None` to force text-only response.
**Critical:** `tool_choice` is NOT passed. The model can choose to respond with text even when tools are available.

### Step 4: Adapter builds payload

[llm_openai_compatible.py:237–238](src/formicos/adapters/llm_openai_compatible.py#L237-L238):
```python
if tools:
    payload["tools"] = _build_tools(tools)
# tool_choice not set — model may ignore tools
```

---

## Response parsing chain

### Primary path: Native tool_calls

[llm_openai_compatible.py:248–254](src/formicos/adapters/llm_openai_compatible.py#L248-L254):
```python
for tc in message.get("tool_calls") or []:
    func = tc["function"]
    args = _parse_args_defensive(func.get("arguments", "{}"))
    tool_calls.append({"name": func["name"], "id": tc["id"], "arguments": args})
```

This fires when the model returns structured `tool_calls` (e.g., with `tool_choice=required`).

### Fallback path: Content-based parsing

[llm_openai_compatible.py:255–263](src/formicos/adapters/llm_openai_compatible.py#L255-L263):
```python
if not tool_calls and tools and isinstance(content, str):
    known_tools = {t["name"] for t in tools}
    recovered = parse_tool_calls_defensive(content, known_tools=known_tools)
```

### 3-stage defensive parser

[parse_defensive.py:37–71](src/formicos/adapters/parse_defensive.py#L37-L71):

| Stage | Method | What it handles |
|-------|--------|----------------|
| 1 | `json.loads()` | Clean JSON in content |
| 2 | `json_repair.loads()` | Trailing commas, missing quotes, truncation |
| 3 | Regex extraction | `<think>` tag stripping, markdown fences, bare `{…}` objects |

### Fuzzy tool name matching

[parse_defensive.py:174–184](src/formicos/adapters/parse_defensive.py#L174-L184):
```python
matches = get_close_matches(name, known_tools, n=1, cutoff=0.6)
```

**Known issue:** `write_workspace_file` (a valid tool) was fuzzy-matched to `read_workspace_file` in the Qwen2.5-Coder smoke. The cutoff of 0.6 is too loose for tools with similar names.

---

## Caste permission enforcement

[tool_dispatch.py:612–650](src/formicos/engine/tool_dispatch.py#L612-L650): `check_tool_permission()`

| Caste | Allowed categories | Explicitly denied |
|-------|-------------------|------------------|
| coder | exec_code, vector_query, read_fs, write_fs, network_out | (none) |
| reviewer | vector_query, read_fs | code_execute |
| researcher | vector_query, search_web, read_fs, network_out | code_execute |
| archivist | vector_query, read_fs, write_fs | code_execute |
| queen | delegate, read_fs, vector_query | code_execute |

Deny-by-default: unknown tools, unknown castes, and tools outside permitted categories.

---

## Agent turn loop

[runner.py:1376–1502](src/formicos/engine/runner.py#L1376-L1502):

```
for iteration in range(max_iterations + 1):
    ├── Time guard (elapsed >= max_execution_time_s)
    ├── Build + inject budget block at position 1
    ├── LLM call (tools=None on final iteration)
    ├── If no tool_calls → break (text response)
    ├── If final iteration with tool_calls → graceful_stop
    ├── For each tool_call:
    │   ├── Permission check (check_tool_permission)
    │   ├── Execute tool (_execute_tool)
    │   ├── Cap output to TOOL_OUTPUT_CAP (2000 chars)
    │   └── Append assistant + tool result to messages
    └── Continue to next iteration
```

### Iteration limits (from caste recipe)

| Caste | max_iterations | max_execution_time_s | max_tokens | base_tool_calls_per_iteration |
|-------|---------------:|--------------------:|-----------:|------------------------------:|
| coder | 25 | 300 | 8192 | 25 |
| reviewer | 6 | 90 | 4096 | 6 |
| researcher | 20 | 240 | 8192 | 20 |

---

## Governance and quality scoring

### Convergence computation

[runner.py:2156–2265](src/formicos/engine/runner.py#L2156-L2265): Three-fallback system:
1. Async embeddings (embed_client)
2. Sync embedding fallback (embed_fn)
3. Heuristic Jaccard overlap (no embeddings)

```python
score = 0.4 * goal_alignment + 0.3 * stability + 0.3 * min(1.0, progress * 5.0)
is_stalled = stability > 0.95 and progress < 0.01 and round_number > 2
is_converged = score > 0.85 and stability > 0.90
```

### Stall detection

A round is stalled when ALL three conditions are true:
1. `stability > 0.95` — outputs are >95% similar to previous round
2. `progress < 0.01` — <1% forward movement toward goal
3. `round_number > 2` — not in early exploration

Stall count is cumulative consecutive: resets to 0 when not stalled.
Reset on redirect ([colony_manager.py:810](src/formicos/surface/colony_manager.py#L810)).
Reset on auto-escalation ([colony_manager.py:918](src/formicos/surface/colony_manager.py#L918)).

### Governance decision

[runner.py:2268–2291](src/formicos/engine/runner.py#L2268-L2291): `_evaluate_governance()` static method.

| Priority | Condition | Action | Reason |
|----------|-----------|--------|--------|
| 1 | stalled + (recent_successful_code_execute OR recent_productive_action) + round ≥ 2 | `complete` | verified_execution_converged |
| 2 | stalled + stall_count ≥ 4 | `force_halt` | stalled 4+ rounds |
| 3 | stalled + stall_count ≥ 2 | `warn` | stalled 2+ rounds |
| 4 | goal_alignment < 0.2 + round > 3 | `warn` | off_track |
| 5 | converged + round ≥ 2 | `complete` | converged |
| 6 | default | `continue` | in_progress |

**Key insight:** Rule 1 (verified_execution_converged) is the ONLY path where a stalled colony can complete positively. It requires EITHER `recent_successful_code_execute=True` (any `code_execute` success) OR `recent_productive_action=True` (Wave 55 broadening — any tool in the `PRODUCTIVE_TOOLS` set: `write_workspace_file`, `patch_file`, `code_execute`, `workspace_execute`, `git_commit`).

### Quality score formula

[colony_manager.py:267](src/formicos/surface/colony_manager.py#L267): `compute_quality_score()`

**5-signal weighted geometric mean** (Wave 54.5 added productivity signal, raised round_efficiency floor):

```python
round_efficiency = max(1.0 - (rounds_completed / max_rounds), 0.20)  # floor raised from 0.01 to 0.20
convergence_score = max(convergence, 0.01)
governance_score = max(1.0 - (governance_warnings / 3.0), 0.01)
stall_score = max(1.0 - (stall_rounds / rounds_completed), 0.01)
productive_ratio = max(productive_calls / total_calls, 0.01)  # Wave 54.5 new signal

quality = exp(
    0.20 * ln(round_efficiency)    # fewer rounds = better (was 0.25)
  + 0.25 * ln(convergence_score)   # higher convergence = better (was 0.30)
  + 0.20 * ln(governance_score)    # fewer warnings = better (was 0.25)
  + 0.15 * ln(stall_score)         # fewer stalls = better (was 0.20)
  + 0.20 * ln(productive_ratio)    # NEW: more productive tool calls = better
)
```

**Key changes from original 4-signal formula:**
- `round_efficiency` floor raised from 0.01 to 0.20 — prevents catastrophic single-signal drag
- `productive_ratio` signal added (w=0.20) — rewards colonies that use productive tools
- All original weights redistributed to accommodate the 5th signal

### Adaptive evaporation

[runner.py:2318–2341](src/formicos/engine/runner.py#L2318-L2341):

Rate interpolates linearly based on stall depth:
- 0 stalls or high branching (≥2.0): rate = 0.95 (normal)
- 4+ stalls + low branching: rate = 0.85 (fastest decay)

```python
t = min(stall_count, 4) / 4.0
rate = 0.95 - t * (0.95 - 0.85)
```

---

## Key integration seams

### Seam 1: Tool list filtering (caste_recipes.yaml)

The YAML `tools` array directly controls what the model sees. No code change needed to add/remove tools — just edit the array. The runner will build specs for whatever is listed.

### Seam 2: tool_choice parameter (llm_openai_compatible.py:237–238)

Currently not set. Adding `payload["tool_choice"] = "required"` forces structured output but doesn't fix tool selection quality. See [toolchoice_experiment_results.md](docs/waves/wave_53/toolchoice_experiment_results.md).

### Seam 3: Per-iteration mid-correction (runner.py:1404)

The budget block injection point ([runner.py:1404](src/formicos/engine/runner.py#L1404)) runs every iteration. A reactive correction block could be injected here based on the tool calls made so far in this turn.

### Seam 4: Governance → context feedback loop — ✅ IMPLEMENTED (Wave 54)

Convergence status is now injected into the agent's context via the budget block.
`build_budget_block()` accepts `stall_count` and `convergence_progress` parameters.
Status labels: `FINAL ROUND`, `STALLED`, `SLOW`, `ON TRACK`. The agent can now see
when it's stalling and adjust behavior.

### Seam 5: Tool output cap (tool_dispatch.py:531)

`TOOL_OUTPUT_CAP = 2000` chars. Tool results over this limit are truncated. This affects code execution output and workspace file reads. Raising or lowering this changes how much feedback the model gets per tool call.
