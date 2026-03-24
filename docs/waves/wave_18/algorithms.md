# Wave 18 Algorithms — Implementation Reference

**Wave:** 18 — "Eyes and Hands"
**Purpose:** Technical implementation guide for all three tracks. Coder teams should read the section for their track before writing code.

---

## §1. Queen Tool Surface Expansion (Track A)

### Current Tool Architecture

The Queen's tool system lives entirely in `queen_runtime.py`. Two methods define it:

```python
def _queen_tools(self) -> list[dict[str, Any]]:
    """Returns OpenAI-format tool definitions."""

async def _execute_tool(self, tc, workspace_id, thread_id) -> tuple[str, dict | None]:
    """Dispatches tool calls by name. Returns (result_text, action_record_or_None)."""
```

Both are instance methods on `QueenAgent`. Tools have access to `self._runtime` which provides:
- `self._runtime.projections` — all workspace/thread/colony state
- `self._runtime.vector_port` — Qdrant skill bank
- `self._runtime.llm_router` — model dispatch
- `self._runtime.settings` — system config
- `self._runtime.castes` — caste recipes

No new wiring is needed. All 6 new tools read from existing data sources.

### Tool Definitions

Each tool needs an entry in `_queen_tools()` and a handler branch in `_execute_tool()`.

#### list_templates

```python
{
    "name": "list_templates",
    "description": "List available colony templates with their descriptions and team compositions.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
```

Handler loads templates via `template_manager.load_templates()` (already imported in the module's scope — add import if needed). Returns a formatted string:

```
Available templates:
1. code-review — Code review with Coder + Reviewer (tags: code, review)
   Team: coder(standard), reviewer(standard)
   Used 3 times
2. research — Deep research task (tags: research, analysis)
   Team: researcher(standard)x2, archivist(light)
   Used 0 times
...
```

Cap at 20 templates. If none exist, return "No templates available."

#### inspect_template

```python
{
    "name": "inspect_template",
    "description": "Get full details of a specific colony template by ID or name.",
    "parameters": {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Template ID or name to inspect.",
            },
        },
        "required": ["template_id"],
    },
}
```

Handler: load templates, find by ID (exact match) or name (case-insensitive substring match). Return full detail including strategy, budget_limit, max_rounds, all caste slots with tiers and counts, tags, source colony if any.

If not found, return "Template not found. Use list_templates to see available options."

#### inspect_colony

```python
{
    "name": "inspect_colony",
    "description": "Get detailed status and results of a colony by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "colony_id": {
                "type": "string",
                "description": "Colony ID to inspect.",
            },
        },
        "required": ["colony_id"],
    },
}
```

Handler: search all workspaces/threads in projections for the colony. Return:

```
Colony: {display_name or id}
Status: {status} | Round {round_number}/{max_rounds}
Quality: {quality_score:.2f} | Cost: ${cost:.4f} / ${budget_limit:.2f}
Skills extracted: {skills_extracted}
Strategy: {strategy}
Team: {caste summaries}
Models used: {models_used list}

Last round summary:
  {agent_id} ({caste}): {output[:500]}
  ...
```

If colony not found, search by substring match on display_name as fallback.

#### list_skills

```python
{
    "name": "list_skills",
    "description": "List top skills from the skill bank by confidence.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of skills to return (default 10, max 20).",
            },
        },
        "required": [],
    },
}
```

Handler: call `get_skill_bank_detail()` from `view_state.py` (already importable from the surface package). Format:

```
Skill Bank ({total} skills, avg confidence {avg:.2f}):
1. [{confidence:.2f}] {text_preview} (from colony {source_colony})
2. ...
```

Cap limit at 20. If vector_port is None or bank is empty, return "Skill bank is empty."

#### read_workspace_files

```python
{
    "name": "read_workspace_files",
    "description": "List files in the workspace data directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "Workspace ID (default: current workspace).",
            },
        },
        "required": [],
    },
}
```

Handler: read the workspace data directory at `{data_dir}/{workspace_id}/`. List files with sizes. Cap at 50 entries. If directory doesn't exist or is empty, say so honestly.

```python
import os
data_dir = self._runtime.settings.system.data_dir
ws_path = os.path.join(data_dir, ws_id)
if not os.path.isdir(ws_path):
    return (f"No files found for workspace '{ws_id}'.", None)
entries = []
for f in sorted(os.listdir(ws_path))[:50]:
    full = os.path.join(ws_path, f)
    if os.path.isfile(full):
        size = os.path.getsize(full)
        entries.append(f"  {f} ({size:,} bytes)")
```

#### suggest_config_change

```python
{
    "name": "suggest_config_change",
    "description": (
        "Propose a configuration change for operator approval. "
        "Does NOT apply the change — only formats a proposal. "
        "The operator must approve before any change takes effect."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "param_path": {
                "type": "string",
                "description": (
                    "Dot-path to the parameter (e.g., "
                    "'castes.coder.temperature', "
                    "'governance.convergence_threshold')."
                ),
            },
            "proposed_value": {
                "type": "string",
                "description": "The proposed new value (will be type-coerced).",
            },
            "reason": {
                "type": "string",
                "description": "Why this change would improve performance.",
            },
        },
        "required": ["param_path", "proposed_value", "reason"],
    },
}
```

Handler implements the two-gate validation:

```python
from formicos.surface.config_validator import validate_config_update

# Gate 1: structural safety (config_validator.py)
payload = {param_path: proposed_value}
result = validate_config_update(payload)
if not result.valid:
    return (f"Proposal rejected (safety): {result.errors[0]}", None)

# Gate 2: Queen scope (experimentable_params.yaml)
if not _is_experimentable(param_path):
    return (
        f"Proposal rejected (scope): '{param_path}' is not in the "
        "experimentable parameters whitelist. The Queen cannot propose "
        "changes to this parameter.",
        None,
    )

# Both gates pass — format proposal
current_value = _resolve_current_value(param_path)
return (
    f"**Config change proposal:**\n"
    f"  Parameter: `{param_path}`\n"
    f"  Current value: {current_value}\n"
    f"  Proposed value: {proposed_value}\n"
    f"  Reason: {reason}\n\n"
    f"This change has passed safety and scope validation. "
    f"Say 'approve' to apply, or 'no' to reject.",
    {"tool": "suggest_config_change", "param_path": param_path,
     "proposed_value": proposed_value, "status": "proposed"},
)
```

The helper `_is_experimentable(path)` loads `config/experimentable_params.yaml` (cache after first load) and checks if the path matches any entry. The helper `_resolve_current_value(path)` traverses the live caste recipes or governance/routing config to find the current value.

**Important:** The "approve" path does NOT exist in Wave 18. The Queen presents the proposal. The operator can manually apply it through the existing UI config controls or wait for Wave 19's mutation wiring.

### Iteration Limit

Change `_MAX_TOOL_ITERATIONS = 3` to `_MAX_TOOL_ITERATIONS = 5` at the top of `queen_runtime.py`.

Rationale: A typical multi-tool Queen interaction now looks like:
1. `list_templates` — find matching template
2. `inspect_template` — confirm team composition
3. `spawn_colony` — execute

Or:
1. `inspect_colony` — check result
2. `list_skills` — see what was learned
3. Respond with synthesis

3 iterations was tight for 3 tools. 5 iterations is comfortable for 9 tools without enabling runaway loops.

---

## §2. Queen Response Quality (Track B)

### System Prompt Architecture

The Queen's system prompt in `caste_recipes.yaml` should be rewritten to reference the expanded tool set. Structure:

```yaml
system_prompt: |
  You are the Queen — the operator's strategic coordinator in FormicOS.

  ## Your tools
  - **list_templates**: See available colony templates before proposing teams.
  - **inspect_template**: Get full details of a specific template.
  - **inspect_colony**: Check the status and results of any colony.
  - **list_skills**: See what the system has learned from past colonies.
  - **read_workspace_files**: See what files exist in the workspace.
  - **suggest_config_change**: Propose a config tweak for operator approval.
  - **spawn_colony**: Launch a colony to execute a task.
  - **get_status**: Check workspace state.
  - **kill_colony**: Cancel a running colony.

  ## How to respond
  When the operator gives you a task:
  1. Check if a template matches: call list_templates, then inspect_template if one fits.
  2. Propose the team using this structure:
     **Task:** Restate in one clear sentence.
     **Team:** Bullet list of castes with tiers.
     **Why:** One sentence on your team choice.
     **Next:** What happens next.
  3. If the task is clear and a good template exists, use spawn_colony immediately.

  When asked about a colony's results, call inspect_colony and summarize.
  When asked about system knowledge, call list_skills first.

  ## Rules
  - If the request is ambiguous, propose a sensible default. Ask at most one question.
  - Never narrate what you're about to do. Act.
  - Keep responses short. No filler. No preamble.
  - When spawning, restate the task clearly in the tool call.
```

Key changes from current prompt:
- Tools are listed by name with one-line descriptions
- Workflow guidance: check templates before proposing
- Inspection guidance: use inspect_colony for results
- Same structural format (Task/Team/Why/Next)
- Same behavioral rules (act don't narrate, short responses)
- Still under 800 tokens

### Colony Completion Follow-up

In `colony_manager.py`, after emitting `ColonyCompleted`:

```python
# Existing: schedule colony naming
asyncio.create_task(self._queen_agent.name_colony(...))

# New: schedule colony result follow-up
asyncio.create_task(self._queen_agent.follow_up_colony(
    colony_id=colony_id,
    workspace_id=workspace_id,
    thread_id=thread_id,
))
```

In `queen_runtime.py`, add `follow_up_colony()`:

```python
async def follow_up_colony(
    self,
    colony_id: str,
    workspace_id: str,
    thread_id: str,
) -> None:
    """Proactively summarize a completed colony in the operator's thread.

    Only fires if:
    1. The colony was spawned in this thread (already guaranteed by caller)
    2. The thread has recent operator activity (last 30 min)
    """
    thread = self._runtime.projections.get_thread(workspace_id, thread_id)
    if thread is None:
        return

    # Check recency: last operator message within 30 minutes
    recent_cutoff = _now() - timedelta(minutes=30)
    has_recent = any(
        m.role == "operator" and m.timestamp >= recent_cutoff.isoformat()
        for m in thread.queen_messages
    )
    if not has_recent:
        return

    # Find colony in projections
    colony = self._find_colony(colony_id)
    if colony is None:
        return

    # Build concise summary
    status = colony.status
    quality = getattr(colony, "quality_score", None)
    skills = getattr(colony, "skills_extracted", 0)
    cost = getattr(colony, "cost", 0.0)
    name = getattr(colony, "display_name", colony_id)

    summary = (
        f"Colony **{name}** finished ({status}). "
        f"Quality: {quality:.2f}. " if quality else ""
        f"Skills extracted: {skills}. "
        f"Cost: ${cost:.4f}."
    )

    await self._emit_queen_message(workspace_id, thread_id, summary)
```

### Max Tokens Alignment

Current `_queen_max_tokens()`:
```python
def _queen_max_tokens(self) -> int:
    if self._runtime.castes:
        recipe = self._runtime.castes.castes.get("queen")
        if recipe:
            return recipe.max_tokens
    return 4096
```

Updated to also consider model capability:
```python
def _queen_max_tokens(self) -> int:
    caste_max = 4096
    if self._runtime.castes:
        recipe = self._runtime.castes.castes.get("queen")
        if recipe:
            caste_max = recipe.max_tokens

    # Also consider the model's max_output_tokens
    queen_model = self._resolve_queen_model(
        # Use first workspace as fallback for model resolution
        next(iter(self._runtime.projections.workspaces), "default"),
    )
    for m in self._runtime.settings.models.registry:
        if m.address == queen_model:
            return min(caste_max, m.max_output_tokens)

    return caste_max
```

---

## §3. Blackwell Image + High-Context Completion (Track C)

### The Build Script

Port `AnyLoom/scripts/build_llm_image.sh` to `FormicOS/scripts/build_llm_image.sh`. The script is self-contained — it clones llama.cpp to `/tmp`, builds with CUDA 12.8 + sm_120, and tags as `local/llama.cpp:server-cuda-blackwell`.

Key build flags (from the proven anyloom build):
- `GGML_CUDA_NO_PINNED=1` — avoids GDDR7 pinned-memory issues on RTX 5090
- `GGML_CUDA_FORCE_CUBLAS=ON` — fixes prompt processing bug on Blackwell
- `GGML_CUDA_FA_ALL_QUANTS=ON` — enables sub-f16 KV cache with flash attention
- `GGML_CUDA_GRAPHS=ON` — batches kernel launches
- `GGML_FLASH_ATTN=ON` — flash attention kernels

The script requires Docker with WSL2 integration. Build time: ~10-20 minutes first run, faster on rebuild.

### Docker Compose Changes

```yaml
llm:
    image: ${LLM_IMAGE:-local/llama.cpp:server-cuda-blackwell}
    # ... (everything else unchanged)
    command: >
      # ... all existing flags ...
      --ctx-size ${LLM_CONTEXT_SIZE:-131072}
      # ... rest unchanged ...

formicos-embed:
    image: ${LLM_IMAGE:-local/llama.cpp:server-cuda-blackwell}
    # ... (rest unchanged)
```

Two changes:
1. `LLM_IMAGE` default: `ghcr.io/ggml-org/llama.cpp:server-cuda` → `local/llama.cpp:server-cuda-blackwell`
2. `LLM_CONTEXT_SIZE` default: `32768` → `131072`

### VRAM Budget at 131k Context

With the Blackwell image (native sm_120 kernels), VRAM utilization on RTX 5090 (32 GB):

| Component | VRAM |
|-----------|------|
| Qwen3-30B-A3B Q4_K_M weights | ~17.3 GB |
| KV cache (131k ctx × 2 slots × q8_0) | ~6.5 GB |
| Compute buffers | ~2.4 GB |
| Embedding sidecar (Qwen3-Embedding Q8_0) | ~0.7 GB |
| **Total** | **~26.9 GB** |
| **Headroom** | **~5.1 GB** |

`--fit on` auto-sizes the KV cache to fit. If VRAM is tighter than expected, it sizes down gracefully. `--cache-ram 1024` keeps prompt caching in system RAM, not VRAM.

The generic CUDA image wastes VRAM on PTX JIT overhead and unoptimized kernel dispatch, which is why `--fit on` sizes down to 16k on the same hardware. The Blackwell image eliminates this overhead.

### Context Assembly Budget Scaling

Formula: `total_budget_tokens = min(effective_ctx × 0.4, 65536)`

At 131k: `min(131072 × 0.4, 65536)` = 52,429 → round to 52,000.

The 0.4 ratio reserves 60% of the window for:
- System prompt (~500 tokens)
- LLM output generation (up to `max_output_tokens`)
- Tool results and conversation history
- Safety margin for tokenizer variance

Updated `formicos.yaml` context section:

```yaml
# Tiered context assembly budgets (ADR-008).
# Formula: total = min(effective_context × 0.4, 65536).
# At 131k context: 52,000. At 32k: 12,800. At 16k: 6,400.
# Tier budgets scale proportionally from the total.
context:
  total_budget_tokens: 52000
  tier_budgets:
    goal: 4000
    routed_outputs: 20000
    max_per_source: 6000
    merge_summaries: 6000
    prev_round_summary: 6000
    skill_bank: 10000
  compaction_threshold: 4000
```

### Configured vs. Effective Context in UI

`view_state.py` already computes both values:
- **Configured:** `m.context_window` from `formicos.yaml` (131072)
- **Effective:** `_derive_context_window()` reads `/props` → `default_generation_settings.n_ctx` (runtime-probed)

Currently, only the effective value is surfaced as `ctx`. Add `configuredCtx` to the `LocalModel` dict:

```python
# In _build_local_models():
models.append({
    # ... existing fields ...
    "ctx": runtime_ctx,           # effective (from /props)
    "configuredCtx": m.context_window,  # from formicos.yaml
    "maxCtx": runtime_ctx,
    # ...
})
```

Frontend `model-registry.ts`: when `configuredCtx !== ctx`, display both:
```
Context: 131,072 configured → 65,536 effective
```
When they match, display one number. Add a tooltip: "effective context is auto-sized by --fit on to available VRAM."

Update `frontend/src/types.ts`:
```typescript
interface LocalModel {
  // ... existing fields ...
  configuredCtx: number;  // from config
  ctx: number;            // effective runtime
}
```

---

## §4. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/surface/queen_runtime.py` | Add 6 tools to `_queen_tools()` + handlers in `_execute_tool()`. Add `_is_experimentable()` and `_resolve_current_value()` helpers. Bump `_MAX_TOOL_ITERATIONS` to 5. |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `config/caste_recipes.yaml` | Rewrite queen system_prompt with tool guidance |
| `src/formicos/surface/queen_runtime.py` | Add `follow_up_colony()`. Update `_queen_max_tokens()`. **(Read after Coder 1)** |
| `src/formicos/surface/colony_manager.py` | Schedule follow-up after ColonyCompleted |
| `config/formicos.yaml` | Add `anthropic/claude-opus-4.6` registry entry + routing table entry |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `scripts/build_llm_image.sh` | New — port from anyloom |
| `docker-compose.yml` | Flip `LLM_IMAGE` default, bump `LLM_CONTEXT_SIZE` to 131072 |
| `config/formicos.yaml` | Update `context_window` for llama-cpp, scale `context` section |
| `src/formicos/surface/view_state.py` | Add `configuredCtx` to `_build_local_models()` |
| `frontend/src/types.ts` | Add `configuredCtx` to `LocalModel` |
| `frontend/src/components/model-registry.ts` | Render configured vs. effective context |
| `.env.example` | Update defaults, add Blackwell build docs |
| `docs/LOCAL_FIRST_QUICKSTART.md` | Add Blackwell build step |
