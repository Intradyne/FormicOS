# Wave 78 Plan: Safe Autonomy, Local Swarm, Tool Architecture

**Theme:** File safety for autonomous operation, tool dispatch cleanup,
local swarm execution with a stable default profile plus an opt-in
10-agent stress profile, and opt-in self-creating playbooks.

**Teams:** 4 tracks, merge order: Track 1 first (safety prerequisite),
Tracks 2-4 in parallel after.

**Estimated total change:** ~730 new, ~1200 deleted, net -470 lines.

**Research basis:** `docs/waves/wave_77/wave_77_5_reference.md`, 8 knowledge
base entries, live codebase audit (29 Mar 2026).

---

## Audit corrections from the operator's draft

The original plan had several claims that don't match the live codebase.
All corrections are incorporated below.

| Draft claim | Live reality | Correction |
|-------------|-------------|------------|
| Dispatch is an if/elif chain | Dict lookup: `self._handlers.get(name)` at queen_tools.py:1614 | Track 2 is a registry extraction, not a chain replacement |
| tool_specs() is ~800 lines | 1,648 lines (lines 236-1884, post-77.5) | Corrected estimate; makes toolset filtering MORE valuable |
| ~6000 tokens for tool schemas | ~14,784 tokens (42 tools, ~352 tokens each) | 2.5x underestimate; dynamic loading saves ~8-10K tokens |
| 44 tools | 44 tools (42 base + 2 from Wave 77 Track B) | Correct after Wave 77 |
| Git available in Docker | NOT installed - `python:3.12-slim` base, no git | Must add `git` to Dockerfile |
| checkpoint.py in engine/ | engine/ cannot import surface/ (layer constraint) | Move to surface/ or pass paths as params |
| `_post_colony_hooks` has strategy/castes params | Not explicit params; extracted from `colony` object | Track 4 uses `colony` object attributes |
| Playbook YAML has status/source fields | No such fields exist | New fields, must update PlaybookData interface |
| Playbook write endpoints exist | Only `GET /api/v1/playbooks` | Must add POST + DELETE endpoints |
| `llama-cpp-swarm/` routes automatically | Unknown-prefix fallback in `app.py` already builds OpenAI-compatible adapters for endpoint-backed providers | Track 3 can use a registry entry + endpoint + `max_concurrent` without new provider wiring |

---

## Track 1: Shadow Git Checkpoints + File Safety

### Why now

The Queen has `edit_file`, `write_workspace_file`, `delete_file`, and
`run_command` - four tools that mutate the operator's filesystem. The
operational sweep dispatches autonomous work. Without checkpoints, a bad
autonomous file write requires manual recovery.

### Audit-verified seams

- **Dispatch hook site:** queen_tools.py:1614-1617. Dict lookup then handler
  call. Pre-mutation hook inserts between lookup and call.
- **File-mutating handlers:**
  - `_write_workspace_file` (line 2811)
  - `_edit_file` (line 4094, returns diff for approval)
  - `_delete_file` (line 4216, returns deletion proposal)
  - `_run_command` (line 3975, async, executes shell commands)
- **Layer constraint:** engine/ cannot import surface/. Checkpoint module
  goes in `surface/checkpoint.py` where it has access to workspace paths.

### Docker prerequisite

**Git is NOT in the container.** The Dockerfile uses a multi-stage build:
Stage 1 is `FROM node:22-slim AS frontend-build`, Stage 2 is
`FROM python:3.12-slim AS runtime`. The git install MUST go in Stage 2,
early (before COPY commands) so it's in a cached layer:

```dockerfile
FROM python:3.12-slim AS runtime

# System dependencies (git required for shadow checkpoints)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install uv...
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
```

This is ~15MB added to the image. Required for shadow repos.

### What to build

**`src/formicos/surface/checkpoint.py` (~200 lines NEW)**

`CheckpointManager` class:
- Shadow repos at `.formicos/checkpoints/{sha256(abs_dir)[:16]}/`
- `GIT_DIR` + `GIT_WORK_TREE` env vars (no `.git` in operator's directory)
- `create_checkpoint(directory, reason)` - `git add -A && git commit -m reason`
- `list_checkpoints(directory)` - returns recent checkpoints
- `rollback_to(directory, checkpoint_hash)` - `git checkout`
- `auto_prune(max_count=50)` - keeps shadow repo bounded
- All git operations via `subprocess.run()` with timeout, not gitpython

**Pre-mutation hooks in `queen_tools.py`**

In `dispatch()` at line 1614-1617, before calling the handler:

```python
handler = self._handlers.get(name)
if handler is None:
    return (f"Unknown tool: {name}", None)

# Pre-mutation checkpoint
if name in _FILE_MUTATION_TOOLS:
    await self._checkpoint_mgr.create_checkpoint(
        workspace_dir, f"pre-{name}: {_summarize_inputs(inputs)}"
    )
```

Where `_FILE_MUTATION_TOOLS = {"edit_file", "write_workspace_file", "delete_file"}`.

For `run_command`, check destructive patterns before checkpointing:

```python
DESTRUCTIVE_PATTERNS = [
    r"rm\s+(-\w*r|-\w*f)",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-\w*f",
    r"DROP\s+TABLE",
    r"TRUNCATE\s+TABLE",
]
```

**New Queen tool: `rollback_file`**

Register in `_handlers` dict and add spec to `tool_specs()`:
- Parameters: `directory` (required), `checkpoint_id` (optional)
- Returns summary of restored files
- 44 -> 45 Queen tools

**Working memory file viewing (~15 lines in workspace-browser.ts)**

The Wave 77.5 workspace browser shows runtime/artifacts file listings but
files are not clickable. The API endpoint
`GET /api/v1/workspaces/{id}/files/{path}` already supports reading
arbitrary `.formicos/` files. Add a click handler to the Working Memory section that fetches and
displays file content in the existing content viewer panel.

The pattern: `_renderAiFsEntry()` at line 542 renders file entries as
static `<div class="aifs-row">`. Add `@click` that sets `_selectedFile`
to the `.formicos/{prefix}{name}` path and calls `_loadFileContent()`.
The content viewer panel (right side, line 434+) already handles
`_selectedFile` — it fetches via
`GET /api/v1/workspaces/{id}/files/{path}` and renders in `<pre><code>`.

This completes the operator's filesystem visibility: they can see what
the Queen wrote, read reflection files, and inspect working notes.

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/checkpoint.py` | **NEW** ~200 lines |
| `src/formicos/surface/queen_tools.py` | Pre-mutation hooks (~20 lines) + rollback_file tool (~50 lines) |
| `Dockerfile` | Add `git` installation (~2 lines) |
| `config/formicos.yaml` | Checkpoint config section (~5 lines) |
| `frontend/src/components/workspace-browser.ts` | Working memory file click-to-view (~15 lines) |
| `tests/unit/surface/test_checkpoint.py` | **NEW** ~100 lines |

### Do not touch

Any engine/ file, `queen_runtime.py`, `colony_manager.py`,
`docker-compose.yml`.

### Validation

```bash
ruff check src/formicos/surface/checkpoint.py
pyright src/formicos/surface/checkpoint.py
pytest tests/unit/surface/test_checkpoint.py -v
# Integration: edit_file -> verify checkpoint exists -> rollback -> verify restored
```

---

## Track 2: Self-Describing Tool Registry + Keyword Model Routing

### Why now

44 tool specs in a 1,648-line `tool_specs()` method (lines 236-1884,
post-77.5) consume ~15,400 tokens per Queen request. The handler dict at
lines 167-220 is already clean dispatch (not an if/elif chain), but specs,
dispatch metadata, and capability export are still split across multiple
places.

A self-describing tool layer lets one source of truth drive dispatch,
LLM tool schemas, capability export, and Track 1 checkpoint behavior.
Colocating spec + handler + metadata per tool and grouping into toolsets
enables:
- Phase 1 (Wave 78): Single-file tool addition, central error handling
- Phase 2 (Wave 79): Dynamic toolset loading (~8-10K token savings per request)

### Audit-verified seams

- **_handlers dict:** Lines 167-220, 44 entries, mix of direct method refs
  and lambda wrappers
- **tool_specs():** Lines 236-1884, 1,648 lines (post-77.5), returns list of dicts
- **Dispatch:** Line 1614 `self._handlers.get(name)`, async-aware at
  lines 1618-1619
- **DELEGATE_THREAD special cases:** Lines 1610-1611, two tools
  (`archive_thread`, `define_workflow_steps`) bypass the `_handlers` dict
  entirely and return a sentinel `DELEGATE_THREAD` value that tells
  `queen_runtime.py` to handle them at thread-management level
- **Consumer:** `queen_runtime.py:2219-2221` calls
  `self._tool_dispatcher.tool_specs()`
- **Capability export:** `app.py` rebuilds Queen tool name/description from
  `queen._queen_tools()` when building `CapabilityRegistry`
- **Existing registry module:** `surface/registry.py` already defines
  `ToolEntry` for capability export, so Wave 78 should avoid introducing a
  second unrelated registry concept if one richer entry type can serve both

### What to build

**Extend `src/formicos/surface/registry.py` with Queen tool metadata**

```python
@dataclass
class QueenToolEntry:
    name: str
    toolset: str
    schema: dict              # OpenAI function-calling format
    handler_name: str
    check_fn_name: str | None = None
    is_async: bool = True
    mutates_workspace: bool = False
    checkpoint_mode: str = "none"  # none | always | destructive_only

def queen_tool(
    *,
    name: str,
    toolset: str,
    schema: dict,
    check_fn_name: str | None = None,
    is_async: bool = True,
    mutates_workspace: bool = False,
    checkpoint_mode: str = "none",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
```

The decorator writes a `_queen_tool_entry` attribute onto the handler method.
`QueenToolDispatcher.__init__()` scans bound methods once and builds the
runtime registry from those entries.

**No second registry module under `engine/`.** This is a Queen surface
concern, and the app already has a registry module.

**Toolset groupings (45 tools -> 9 toolsets):**

| Toolset | Tools | Count |
|---------|-------|-------|
| `colony` | spawn_colony, spawn_parallel, kill_colony, redirect_colony, escalate_colony, retry_colony, inspect_colony, read_colony_output | 8 |
| `knowledge` | memory_search, queen_note, query_service, query_briefing, search_codebase | 5 |
| `workspace` | read_workspace_files, write_workspace_file, edit_file, delete_file, run_command, run_tests, batch_command | 7 |
| `planning` | propose_plan, mark_plan_step, set_thread_goal, complete_thread, propose_project_milestone, complete_project_milestone, define_workflow_steps | 7 |
| `operations` | get_status, suggest_config_change, approve_config_change, list_templates, inspect_template, list_addons, trigger_addon, set_workspace_tags, check_autonomy_budget, post_observation | 10 |
| `documents` | draft_document, summarize_thread | 2 |
| `working_memory` | write_working_note, promote_to_artifact | 2 |
| `analysis` | query_outcomes, analyze_colony | 2 |
| `safety` | rollback_file (from Track 1) | 1 |

**Refactor `queen_tools.py`:**

- Decorate each handler with its spec + toolset + checkpoint metadata
- Delete the hand-maintained `_handlers` dict
- Delete most of the giant `tool_specs()` list body
- Build dispatch + schema export from decorated methods
- Move Track 1's pre-mutation hooks behind per-tool metadata:
  `mutates_workspace=True` or `checkpoint_mode="destructive_only"`
- Update `app.py` capability export to read the same Queen tool entries
  instead of rebuilding names/descriptions from a separate path
- **Preserve DELEGATE_THREAD special cases.** Two tools (`archive_thread`,
  `define_workflow_steps`) are NOT in the `_handlers` dict. They return
  `DELEGATE_THREAD` before the dict lookup (lines 1610-1611), telling
  `queen_runtime.py` to handle them at thread-management level. Options:
  (a) register them with a handler that returns DELEGATE_THREAD,
  (b) keep the pre-dispatch check and document it, (c) make
  DELEGATE_THREAD a registry-level concept. **Option (b) is safest for
  a behavioral no-op refactor.** Keep the pre-dispatch sentinel check,
  add a comment explaining why these two tools are not decorated.

**Phase 1 (Wave 78):** Always load all toolsets. Pure refactoring, NO
behavioral change. The `{TOOL_INVENTORY}` system prompt macro in
`caste_recipes.yaml` continues to list all tools.

### Keyword model routing (~50 lines)

**`classify_complexity()` function** in queen_runtime.py:

```python
_COMPLEX_KEYWORDS = {
    "debug", "implement", "refactor", "architecture", "design",
    "analyze", "investigate", "optimize", "review", "benchmark",
    "compare", "patch", "traceback", "exception", "plan",
    "delegate", "parallel", "colony", "spawn", "knowledge",
    "pheromone", "convergence", "sweep", "playbook",
}

def classify_complexity(message: str) -> str:
    if len(message) > 160: return "complex"
    if len(message.split()) > 28: return "complex"
    if "```" in message: return "complex"
    if any(kw in message.lower() for kw in _COMPLEX_KEYWORDS): return "complex"
    return "simple"
```

**Integration in `_resolve_queen_model()`** (line 1634):

Current flow: `runtime.resolve_model("queen", workspace_id)` ->
workspace override -> system default.

New flow: if `cheap_queen` is configured and message is "simple", resolve
`cheap_queen` instead. The operator's last message is available in the
`respond()` method before `_resolve_queen_model()` is called.

```yaml
# formicos.yaml
defaults:
  queen: "${QUEEN_MODEL:anthropic/claude-sonnet-4-6}"
  cheap_queen: "${CHEAP_QUEEN_MODEL:}"  # empty = disabled
```

When `cheap_queen` is empty (default), routing is unchanged. When set
(e.g., `anthropic/claude-haiku-4-5`), simple messages route there.
Only run `classify_complexity()` when `cheap_queen` is non-empty.

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/registry.py` | Add `QueenToolEntry` + `@queen_tool` decorator (~60 lines) |
| `src/formicos/surface/queen_tools.py` | Refactor: decorate handlers, derive registry/specs, delegate dispatch (~1200 deleted, ~260 added) |
| `src/formicos/surface/queen_runtime.py` | Use registry.get_definitions(), add classify_complexity + cheap routing (~50 lines) |
| `src/formicos/surface/app.py` | Capability registry reads Queen tool entries from the same source (~10 lines) |
| `config/formicos.yaml` | Add `cheap_queen` default (~2 lines) |
| `tests/unit/surface/test_tool_registry.py` | **NEW** ~80 lines |

### Do not touch

`colony_manager.py`, any adapter file, any frontend file,
`docker-compose.yml`, `engine/runner.py`.

### Validation

```bash
# ALL existing tests must pass unchanged (behavioral no-op)
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Verify tool count preserved
python -c "
from formicos.surface.queen_tools import QueenToolDispatcher
# verify 45 decorated tools discovered
"

# Verify keyword routing
python -c "
from formicos.surface.queen_runtime import classify_complexity
assert classify_complexity('hi') == 'simple'
assert classify_complexity('spawn a colony to refactor the auth module') == 'complex'
"
```

---

## Track 3: Multi-Model Local Swarm

### Why now

FormicOS has stigmergic coordination, pheromone-weighted topology, and
convergence detection - never stress-tested at scale. Qwen3.5-4B scores
97.5% on tool-calling benchmarks at ~2.5GB weights. Wave 78 should ship
an 8-slot stable default and document a 10-slot stress profile, rather
than making the stress setting the operator baseline.

### Audit-verified seams

- **Adapter registration:** `app.py:268-334`, `provider:endpoint` keyed dict
- **Constructor:** `OpenAICompatibleLLMAdapter(base_url, max_concurrent=10)`
  at `llm_openai_compatible.py:117-143`. `max_concurrent > 0` creates
  semaphore directly.
- **Unknown-prefix fallback:** `app.py:316-338` already creates an
  `OpenAICompatibleLLMAdapter` for endpoint-backed providers that are not in
  `_KNOWN_PROVIDERS`
- **Model registry:** `ModelRecord.max_concurrent` already exists and can
  carry the swarm slot count without any new runtime field
- **Telemetry classification:** `view_state.py` and `ws_handler.py` only
  treat `{"llama-cpp", "ollama", "local"}` as local providers today, so
  `llama-cpp-swarm` must be added there or the swarm model will route fine
  but render incorrectly in local model status/telemetry
- **GPU sharing:** Both llm and embed services use `CUDA_DEVICE=${CUDA_DEVICE:-0}`.
  Two llama.cpp instances on the same GPU works (CUDA time-sharing).
- **Metering:** `metering.py` reads `cost` from `TokensConsumed` events
  directly (line 130), not from provider classification. The swarm model
  registry entry has `cost_per_input_token: 0.0`, so metering is correct
  without code changes.

### What to build

**`docker-compose.local-swarm.yml` (~40 lines NEW)**

Override file adding a second llama.cpp service:

```yaml
services:
  llm-swarm:
    profiles: [local-gpu]
    image: ${LLM_IMAGE:-local/llama.cpp:server-cuda-blackwell}
    container_name: formicos-llm-swarm
    volumes:
      - ${LLM_MODEL_DIR:-./.models}:/models:ro
    environment:
      - CUDA_VISIBLE_DEVICES=${CUDA_DEVICE:-0}
    command: >-
      --model /models/${LLM_SWARM_MODEL:-Qwen3.5-4B-Q4_K_M.gguf}
      --alias qwen3.5-4b-swarm
      --ctx-size ${LLM_SWARM_CTX:-128000}
      -np ${LLM_SWARM_SLOTS:-4}
      --flash-attn on
      --jinja
      --chat-template-kwargs '{"enable_thinking":false}'
      --host 0.0.0.0
      --port 8080
    ports:
      - "127.0.0.1:${LLM_SWARM_PORT:-8009}:8080"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['${CUDA_DEVICE:-0}']
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
```

**No special `app.py` provider wiring required**

Track 3 should ride the existing unknown-prefix fallback. The new
`llama-cpp-swarm/...` model registry entry supplies:
- provider prefix
- endpoint
- `max_concurrent`

That is enough for the existing app assembly path to create the adapter.

**Model registry entry in `formicos.yaml`:**

```yaml
- address: "llama-cpp-swarm/qwen3.5-4b-swarm"
  endpoint: "${LLM_SWARM_HOST:}"
  context_window: 128000
  supports_tools: true
  max_concurrent: ${LLM_SWARM_SLOTS:-4}
  cost_per_input_token: 0.0
  cost_per_output_token: 0.0
  max_output_tokens: 4096
```

**Colony sizing guidance (ops heuristic, not runtime-enforced math):**

```
Colony minimum per-slot context:
  Tool schemas:     ~4,685 tokens (21 tools in engine/tool_dispatch.py)
  System prompt:    ~800 tokens (caste recipe + instructions)
  Task description: ~200 tokens
  Knowledge:        ~500 tokens (retrieved entries)
  Round history:    ~500 tokens (prior round outputs)
  Output reserve:   4,096 tokens (max_tokens for coder)
  ─────────────────────────────────
  Minimum:          ~10,781 tokens per slot
  Recommended:      16,000 tokens per slot (headroom for larger tasks)
```

This is a sizing heuristic for the swarm profile, not a code path the
runtime currently enforces. Queen budgeting divides local context by slot
count in `queen_budget.py`, but colony prompt assembly does not. Use this
math to choose conservative defaults, not as proof of a server invariant.

**Three swarm profiles:**

| Profile | Queen (`LLM_SLOTS`) | Swarm (`LLM_SWARM_SLOTS`) | Queen ctx/slot | Worker ctx/slot | Total VRAM | Use case |
|---------|-------|-------|-------|--------|------|----------|
| **Deep Queen (RECOMMENDED)** | 1 | 4 | 65K | 32K | ~29.5GB | Deep Queen context + adequate parallelism |
| Max parallelism | 2 | 8 | 32K | 16K | ~29.5GB | Stress testing parallel coordination |
| Benchmark | 2 | 10 | 32K | 16K | ~31GB | Full 10-agent benchmark, tight VRAM |

**Default: Deep Queen + 4 workers.** The Queen is the bottleneck for
reasoning quality, not the workers. With `LLM_SLOTS=1`, the Queen gets
65K of undivided context — the 44 tool schemas (~15,488 tokens) consume
only 25% of available context, leaving ~45,952 for actual content. With
`LLM_SLOTS=2`, tools consume 54% of available context. This is the
strongest argument for `LLM_SLOTS=1` in swarm mode.

4 parallel workers is already 4x what FormicOS has ever tested. Colony
tasks are bounded and rarely need more than 4 simultaneous agents.

**VRAM budget — Deep Queen profile (RTX 5090 32GB):**

| Component | VRAM |
|-----------|------|
| Qwen3.5-35B Q4_K_M weights | ~18GB |
| 35B KV cache (1 slot, 65K ctx) | ~4GB |
| Qwen3.5-4B Q4_K_M weights | ~2.5GB |
| 4B KV cache (4 slots, 32K ctx each) | ~5GB |
| **Total** | **~29.5GB** |

Fits RTX 5090 (32GB) with ~2.5GB headroom. The max-parallelism and
benchmark profiles use the same VRAM by trading Queen depth for worker
count.

**`scripts/setup-local-swarm.sh` (~30 lines NEW)**

Downloads Qwen3.5-4B GGUF, appends swarm config to `.env`.

**Queen slot trade-off note in `.env.example`**

Present the three profiles with the Deep Queen as the recommended default:

```bash
# Swarm: Deep Queen + parallel workers (RECOMMENDED)
# Queen gets full 65K context (no slot split), 4 parallel colony workers at 32K each
LLM_SLOTS=1
LLM_SWARM_CTX=128000
LLM_SWARM_SLOTS=4

# Swarm: Max parallelism (stress testing)
# Queen context halved (32K), 8 parallel colony workers at 16K each
# LLM_SLOTS=2
# LLM_SWARM_CTX=128000
# LLM_SWARM_SLOTS=8

# Swarm: Benchmark (10 agents, tight VRAM)
# LLM_SLOTS=2
# LLM_SWARM_CTX=160000
# LLM_SWARM_SLOTS=10
```

### Files

| File | Change |
|------|--------|
| `docker-compose.local-swarm.yml` | **NEW** ~40 lines |
| `config/formicos.yaml` | Swarm model registry entry (~8 lines) |
| `src/formicos/surface/view_state.py` | Add `llama-cpp-swarm` to local provider classification (~3 lines) |
| `src/formicos/surface/ws_handler.py` | Add `llama-cpp-swarm` to local endpoint probing (~3 lines) |
| `scripts/setup-local-swarm.sh` | **NEW** ~30 lines |
| `.env.example` | 3 swarm profiles: Deep Queen (1+4, recommended), max parallelism (2+8), benchmark (2+10) (~30 lines) |

### Do not touch

`queen_runtime.py`, `queen_tools.py`, any engine file, any frontend file.

### Validation

```bash
# Verify both LLM instances healthy
curl -s http://localhost:8008/health  # Queen model
curl -s http://localhost:8009/health  # Swarm model

# Verify slot counts (Deep Queen default)
curl -s http://localhost:8009/props | python -c "import sys,json; print(json.load(sys.stdin)['total_slots'])"  # -> 4

# Optional stress profile
# set LLM_SWARM_SLOTS=8 (or 10) in .env, restart, then verify

# VRAM check
nvidia-smi --query-gpu=memory.used --format=csv  # stable default should stay comfortably under 32GB
```

---

## Track 4: Self-Creating Playbooks (Opt-In)

### Why now

FormicOS extracts knowledge facts from colony work but doesn't extract
reusable process templates. Successful multi-step colonies represent
proven approaches that future colonies should follow.

### Audit-verified seams

- **`_post_colony_hooks`:** colony_manager.py:1176-1190. Parameters:
  `colony_id, colony, quality, total_cost, rounds_completed, skills_count,
  retrieved_skill_ids, governance_warnings, stall_count, succeeded,
  productive_calls, total_calls`. Strategy and castes are on the `colony`
  object, not explicit params.
- **Current playbook format:** 13 YAML files in `config/playbooks/`.
  Fields: `task_class, castes, workflow, steps, productive_tools,
  observation_tools, observation_limit, example`. No `status` or `source`
  fields - these are new.
- **Playbook API:** Only `GET /api/v1/playbooks` exists (routes/api.py:1220).
  No write or delete endpoints.
- **Frontend:** `playbook-view.ts` fetches `/api/v1/playbooks`, renders cards.
  `PlaybookData` interface has no `status` or `source` fields.

### What to build

**Post-colony playbook proposal (~80 lines in colony_manager.py)**

In `_post_colony_hooks`, after a successful colony meeting the quality gate:

```python
async def _hook_playbook_proposal(
    self, colony_id: str, colony: Any, quality: float,
    rounds_completed: int, productive_calls: int, total_calls: int,
) -> None:
    """Propose a reusable playbook from a successful colony."""
    # Quality gate
    if quality < 0.7 or rounds_completed < 3:
        return
    if productive_calls / max(total_calls, 1) < 0.5:
        return
    # Extract approach from colony object
    strategy = getattr(colony, "strategy", "sequential")
    castes = list(getattr(colony, "castes", []))
    if len(castes) < 2:
        return  # Single-caste colonies aren't novel workflows
    task = getattr(colony, "task", "")[:200]
    # ... call archivist model with structured prompt ...
    # ... save via playbook loader/store helper ...
```

The YAML output includes new fields:
```yaml
source: agent
status: candidate
proposed_by: colony-abc12345
proposed_at: "2026-03-30T12:00:00Z"
task_class: auto_generated
castes: [coder, reviewer]
# ... standard playbook fields ...
```

**Extend `engine/playbook_loader.py` with write helpers**

The loader already owns `config/playbooks/`, parsing, and cache invalidation.
Track 4 should extend that seam instead of writing YAML directly inside
`routes/api.py`.

Add helper functions:
- `save_playbook(data, filename=None) -> dict`
- `delete_playbook(filename) -> bool`
- `approve_playbook(filename) -> dict`
- `clear_cache()` call after any mutation

**Playbook write/delete endpoints (~30 lines in routes/api.py)**

```python
# Thin wrappers over playbook_loader helpers:
# POST /api/v1/playbooks
# DELETE /api/v1/playbooks/{filename}
# PUT /api/v1/playbooks/{filename}/approve
```

**Frontend candidate indicator (~20 lines in playbook-view.ts)**

Update `PlaybookData` interface to include optional `source`, `status`,
`proposed_by` fields. Render auto-created playbooks with:
- Orange "Proposed" badge
- "Proposed by colony {id}" subtitle
- "Approve" / "Dismiss" action buttons

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/colony_manager.py` | `_hook_playbook_proposal` (~80 lines) |
| `src/formicos/engine/playbook_loader.py` | Add save/delete/approve helpers + cache clear (~60 lines) |
| `src/formicos/surface/routes/api.py` | Thin playbook write/delete/approve wrappers (~30 lines) |
| `frontend/src/components/playbook-view.ts` | Candidate indicator + approve/dismiss (~30 lines) |

### Do not touch

`queen_tools.py`, `queen_runtime.py`, any engine file except
`playbook_loader.py`,
`docker-compose.yml`.

### Validation

```bash
# Spawn a multi-caste colony (3+ rounds, quality >= 0.7)
# Verify auto_*.yaml appears in config/playbooks/
# Verify GET /api/v1/playbooks includes the new playbook with status: candidate
# Visual: Playbook tab shows "Proposed" badge
# Click Approve -> verify status changes to approved
# Click Dismiss on another -> verify file deleted
```

---

## Cross-track file ownership

| File | Track 1 | Track 2 | Track 3 | Track 4 |
|------|---------|---------|---------|---------|
| `surface/checkpoint.py` | NEW | -- | -- | -- |
| `surface/registry.py` | -- | Queen tool metadata | -- | -- |
| `surface/queen_tools.py` | hooks + rollback | refactor dispatch | -- | -- |
| `surface/queen_runtime.py` | -- | registry + routing | -- | -- |
| `surface/colony_manager.py` | -- | -- | -- | playbook proposal |
| `surface/app.py` | -- | capability export (~10 lines) | -- | -- |
| `surface/routes/api.py` | -- | -- | -- | playbook endpoints |
| `surface/view_state.py` | -- | -- | local provider classification | -- |
| `surface/ws_handler.py` | -- | -- | local endpoint probing | -- |
| `engine/playbook_loader.py` | -- | -- | -- | playbook store helpers |
| `docker-compose.local-swarm.yml` | -- | -- | NEW | -- |
| `workspace-browser.ts` | file click-to-view | -- | -- | -- |
| `Dockerfile` | git install | -- | -- | -- |
| `config/formicos.yaml` | checkpoints | cheap_queen | swarm model | -- |
| `playbook-view.ts` | -- | -- | -- | candidate UI |

**Conflict: `queen_tools.py` touched by Track 1 and Track 2.**

Resolution: **Track 1 lands first.** Adds pre-mutation hooks + rollback_file
to the existing `_handlers` dict and `tool_specs()`. Track 2 then refactors
everything (including Track 1's additions) into the decorated registry pattern.

Track 2's coder prompt must specify: "Read the post-Track-1 code. The
pre-mutation hooks and rollback_file handler are already in queen_tools.py.
Migrate them into decorated tool entries alongside everything else."

**`formicos.yaml` touched by Tracks 1, 2, and 3** - all additive in
different sections (checkpoints, cheap_queen, swarm model). No conflict.

---

## What this wave does NOT do

- No background review agent / automatic preference capture (operator
  controls behavior explicitly via UI and override forms)
- No context budget redistribution (77.5 made waste visible)
- No dynamic toolset loading (registry ships with all toolsets always
  loaded; selective loading is Wave 79)
- No GGUF manager UI
- No new event types
- No new MCP tools (rollback_file is a Queen tool, not MCP)
- No tool trace metadata on colony completion events (Wave 79 candidate,
  requires event schema discussion)

---

## Success conditions

1. File mutations (`edit_file`, `write_workspace_file`, `delete_file`)
   create automatic checkpoints before executing
2. Destructive commands (`rm -rf`, `git reset --hard`) create checkpoints
3. The Queen can `rollback_file` to undo mutations
4. Checkpoint creation is <100ms (no LLM calls)
5. All 45 Queen tools dispatch through the self-describing tool registry with central
   error handling
6. Adding a new tool requires one decorated handler / one entry source of
   truth (spec + handler + metadata colocated)
7. Simple Queen messages route to the cheap model when `cheap_queen` is
   configured
8. A second llama.cpp instance runs the 4B model with Deep Queen default
   (4 slots, 128K ctx, 32K per slot), fitting within 32GB VRAM. Stress
   profiles (8-slot, 10-slot) documented as opt-in.
9. Colonies can route coder/archivist castes to the swarm endpoint
10. Successful multi-step colonies with productive-call ratio >= 0.5
    produce candidate playbook proposals
11. Auto-created playbooks appear in the Playbook tab with approve/dismiss
12. All existing tests pass unchanged (Track 2 is a behavioral no-op)
13. CapabilityRegistry reads Queen tool names/descriptions from the same
    source as dispatch + schema export
14. Working memory files in the workspace browser are viewable
    (click to read content)
