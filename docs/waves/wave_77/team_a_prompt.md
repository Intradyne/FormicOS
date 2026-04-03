# Wave 77.5 Team A — Context Budget Transparency + Workspace Browser + Override Forms + Compaction

You are a coder agent. Follow the plan precisely. Do not touch files outside your ownership list. Run validation before declaring done.

## Coordination

- **Active wave:** `docs/waves/wave_77/wave_77_5_plan.md`
- **Evergreen rules:** `CLAUDE.md` (hard constraints, prohibited alternatives, architecture layers)
- **Reference audit:** `docs/waves/wave_77/wave_77_5_reference.md`
- If anything in this prompt conflicts with `CLAUDE.md`, `CLAUDE.md` wins.

## Owned files

| File | Tracks |
|------|--------|
| `src/formicos/surface/queen_budget.py` | A1 |
| `src/formicos/surface/queen_runtime.py` | A1, A2, A8 |
| `src/formicos/surface/routes/api.py` | A3, A5 |
| `frontend/src/components/queen-budget-viz.ts` | A4 |
| `frontend/src/components/queen-overview.ts` | A5 (1 line) |
| `frontend/src/components/workspace-browser.ts` | A5 |
| `frontend/src/components/addon-panel.ts` | A6 |
| `frontend/src/components/queen-overrides.ts` | A7 |

## Do NOT touch

`queen_tools.py`, `colony_manager.py`, `mcp_server.py`, `formicos.yaml`,
`docker-compose.yml`, any adapter file, any engine file, `formicos-app.ts`,
`knowledge-browser.ts`, `knowledge-search-results.ts`, `operations-view.ts`,
`billing-card.ts`, any `core/` file, any `config/` file.

---

## Track A1: Context budget slot-aware fix (Critical)

**Problem:** `queen_runtime.py:929-940` reads `context_window` from the model registry (80000) and passes it raw to `compute_queen_budget()`. But llama.cpp divides KV cache across `LLM_SLOTS` (default 2) — each slot only has ~40k. Budget allocates 75,901 tokens when only 36,096 fit.

**Fix in `queen_budget.py`:**

Add a `num_slots` parameter to `compute_queen_budget()`:

```python
def compute_queen_budget(
    context_window: int | None,
    output_reserve: int,
    *,
    num_slots: int = 1,
) -> QueenContextBudget:
    """Compute proportional token budgets from the model's context window."""
    if context_window is None or context_window <= 0:
        return FALLBACK_BUDGET

    effective_window = (
        context_window // max(1, num_slots)
        if num_slots > 1
        else context_window
    )
    available = max(0, effective_window - output_reserve)
    if available <= 0:
        return FALLBACK_BUDGET
    # ... rest unchanged, uses `available` ...
```

Also add `num_slots` to the structlog debug call.

**Fix in `queen_runtime.py` (~line 940):**

Resolve `num_slots` before computing budget. `import os` is NOT currently imported — add it to the imports at the top.

```python
import os   # <-- add to imports

# At line ~934, after resolving _model_addr and _ctx_window:
_num_slots = 1
if _model_addr and _model_addr.startswith("llama-cpp/"):
    _num_slots = max(1, int(os.environ.get("LLM_SLOTS", "1")))
budget = compute_queen_budget(_ctx_window, _output_reserve, num_slots=_num_slots)
```

Cloud models (`anthropic/`, `openai/`, `gemini/`, `deepseek/`) are unaffected. Only `llama-cpp/` addresses get the division.

**Files changed:** `queen_budget.py` (~8 lines), `queen_runtime.py` (~5 lines)

---

## Track A2: Context budget consumption tracking

Track actual token usage per budget slot during `_build_messages()` (starts at line 1822) and its subsequent injection sites.

**Add to `QueenRuntime.__init__`:**
```python
self._last_budget_usage_by_workspace: dict[str, dict[str, Any]] = {}
```

**Important:** Do NOT implement this by re-classifying messages from content markers after `_build_messages()` returns. That is brittle. Instead, track usage **at the injection sites** inside the Queen turn method (the method that calls `_build_messages()` at ~line 942 and then injects memory, project context, procedures, journal, session context, thread context in sequence through lines ~950-1170).

After all injections complete and before the LLM call, compute per-slot token estimates:

```python
def _track_budget_usage(
    self,
    messages: list[dict[str, str]],
    budget: QueenContextBudget,
    workspace_id: str,
) -> None:
    """Record per-slot token consumption for budget transparency."""
    _CHARS_PER_TOKEN = 4
    usage: dict[str, int] = {}
    for msg in messages:
        content = msg.get("content", "")
        tokens = len(content) // _CHARS_PER_TOKEN
        if content.startswith("You are") or content.startswith("## Tools"):
            usage["system_prompt"] = usage.get("system_prompt", 0) + tokens
        elif "# Project Context" in content:
            usage["project_context"] = tokens
        elif "# Project Plan" in content or "milestone" in content[:100].lower():
            usage["project_plan"] = tokens
        elif "# Operating Procedures" in content:
            usage["operating_procedures"] = tokens
        elif "# Queen Journal" in content:
            usage["queen_journal"] = tokens
        elif "# Prior Session Context" in content or "thread_context" in content[:50].lower():
            usage["thread_context"] = usage.get("thread_context", 0) + tokens
        elif "saved notes" in content[:80].lower() or "Prior tool results" in content[:50]:
            usage["tool_memory"] = usage.get("tool_memory", 0) + tokens
        elif "# Working Memory" in content:
            usage["working_memory"] = tokens
        elif msg.get("role") == "system" and "relevant knowledge" in content[:100].lower():
            usage["memory_retrieval"] = tokens
        elif msg.get("role") != "system":
            usage["conversation_history"] = usage.get("conversation_history", 0) + tokens
        else:
            usage["system_prompt"] = usage.get("system_prompt", 0) + tokens

    self._last_budget_usage_by_workspace[workspace_id] = {
        "slots": usage,
        "total_consumed": sum(usage.values()),
    }
```

Call `self._track_budget_usage(messages, budget, workspace_id)` after the last injection (thread context at ~line 1139) and before the LLM call.

**Files changed:** `queen_runtime.py` (~50 lines)

---

## Track A3: Enhanced queen-budget API endpoint

Rewrite `GET /api/v1/queen-budget` in `routes/api.py` (currently lines 1029-1040). Current implementation only returns slot fractions and fallback tokens. Replace with full allocation + consumption data.

Make the endpoint workspace-aware via query param. The live seam to the Queen is `runtime.queen` (not `runtime._queen_runtime`).

```python
async def get_queen_budget(request: Request) -> JSONResponse:
    """Return the Queen's 9-slot context budget with allocation and consumption."""
    import os  # noqa: PLC0415
    from formicos.surface.queen_budget import (  # noqa: PLC0415
        _FALLBACKS,
        _FRACTIONS,
        compute_queen_budget,
    )

    workspace_id = request.query_params.get("workspace_id", "")
    ctx_window: int | None = None
    output_reserve = 4096
    num_slots = 1
    queen_model = ""

    queen_rt = runtime.queen
    if queen_rt:
        queen_model = queen_rt._resolve_queen_model(workspace_id) or ""
        output_reserve = queen_rt._queen_max_tokens(workspace_id)
        for rec in runtime.settings.models.registry:
            if rec.address == queen_model:
                ctx_window = rec.context_window
                break
        if queen_model.startswith("llama-cpp/"):
            num_slots = max(1, int(os.environ.get("LLM_SLOTS", "1")))

    budget = compute_queen_budget(ctx_window, output_reserve, num_slots=num_slots)

    effective = 0
    if ctx_window and ctx_window > 0:
        effective = max(0, (ctx_window // max(1, num_slots) if num_slots > 1 else ctx_window) - output_reserve)

    slot_list = []
    for name, frac in _FRACTIONS.items():
        allocated = getattr(budget, name, 0)
        consumed = 0
        if queen_rt and hasattr(queen_rt, "_last_budget_usage_by_workspace"):
            ws_usage = queen_rt._last_budget_usage_by_workspace.get(workspace_id, {})
            consumed = ws_usage.get("slots", {}).get(name, 0)
        slot_list.append({
            "name": name,
            "fraction": frac,
            "fallback_tokens": _FALLBACKS.get(name, 0),
            "allocated": allocated,
            "consumed": consumed,
            "utilization": round(consumed / allocated, 3) if allocated > 0 else 0,
        })

    total_consumed = sum(s["consumed"] for s in slot_list)

    return JSONResponse({
        "queen_model": queen_model,
        "queen_model_type": "local" if queen_model.startswith("llama-cpp/") else "cloud",
        "context_window": ctx_window or 0,
        "num_slots": num_slots,
        "effective_context": (ctx_window // max(1, num_slots) if ctx_window and num_slots > 1 else ctx_window) or 0,
        "output_reserve": output_reserve,
        "available": max(0, effective),
        "slots": slot_list,
        "total_consumed": total_consumed,
        "total_utilization": round(total_consumed / effective, 3) if effective > 0 else 0,
    })
```

**Files changed:** `routes/api.py` (~45 lines replacing ~12)

---

## Track A4: Budget viz upgrade

Rewrite `fc-queen-budget-viz` (currently 102 lines in `queen-budget-viz.ts`) to show the full budget math from the enhanced API.

**New interface:**
```typescript
interface BudgetSlot {
  name: string;
  fraction: number;
  fallback_tokens: number;
  allocated: number;
  consumed: number;
  utilization: number;
}
interface BudgetData {
  queen_model: string;
  queen_model_type: string;
  context_window: number;
  num_slots: number;
  effective_context: number;
  output_reserve: number;
  available: number;
  slots: BudgetSlot[];
  total_consumed: number;
  total_utilization: number;
}
```

**Add `workspaceId` property:**
```typescript
@property() workspaceId = '';
```

**Fetch with workspace_id:**
```typescript
const resp = await fetch(`/api/v1/queen-budget?workspace_id=${encodeURIComponent(this.workspaceId)}`);
```

Poll every 30 seconds while expanded (use `setInterval` in `connectedCallback`, clear in `disconnectedCallback`).

**Headline row:**
- For cloud: `Queen: claude-sonnet-4-6 (cloud) | Context: 200,000 | Available: 191,808`
- For local: `Queen: qwen3.5-35b (local, 2 slots) | Per-slot: 40,192 | Available: 36,096`
- Second line: `Used: 28,500 / 191,808 (14.9%)`

**Per-slot dual bars:**
- Outer bar (dim): allocated capacity (the full bar width at 100%)
- Inner bar (bright): actual consumed tokens as proportion of allocated
- Slots at >90% utilization get a warning accent color (e.g., `#ef4444`)
- Show both allocated and consumed numbers per row

Keep existing `SLOT_COLORS`, `displayName()`, and general `voidTokens`/`sharedStyles` usage.

**Files changed:** `queen-budget-viz.ts` (~150 lines, replacing current 102)

---

## Track A5: Workspace browser structured sections + API endpoints

### Frontend: `workspace-browser.ts`

Replace the flat file tree with three structured sections. Keep the existing file tree view as Section 3 at the bottom.

**Section 1: Operator Files**

| File | Label | Mode | Backend |
|------|-------|------|---------|
| `.formicos/project_context.md` | Project Context | Edit (textarea + Save + Revert) | `GET/PUT /api/v1/workspaces/{id}/project-context` (NEW) |
| `.formicos/project_plan.md` | Project Plan | Edit (textarea + Save + Revert) | `GET /api/v1/project-plan?workspace_id={id}` (exists) + `PUT /api/v1/workspaces/{id}/project-plan` (NEW) |
| Operating Procedures | Read-only preview | Text hint: "Edit in Operations tab" | Read-only |
| Queen Journal | View (last 10 entries as formatted text) | `GET /api/v1/workspaces/{id}/queen-journal` (exists) | Read-only |

**Section 2: Working Memory (AI Filesystem)**

Read-only directory listing of the AI Filesystem tree. Backend: `GET /api/v1/workspaces/{id}/ai-filesystem` (NEW).

Display as:
```
runtime/queen/          2 files
runtime/colonies/       1 directory
artifacts/              0 files
```

**Section 3: Workspace Files**

The existing file tree, moved below sections 1 and 2. Unchanged logic.

### Backend: `routes/api.py`

Add three new endpoint groups:

**1. Project context GET/PUT:**
```python
async def get_project_context(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    data_dir = runtime.settings.system.data_dir
    path = Path(data_dir) / ".formicos" / "workspaces" / workspace_id / "project_context.md"
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    return JSONResponse({"content": content})

async def put_project_context(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    body = await request.json()
    data_dir = runtime.settings.system.data_dir
    path = Path(data_dir) / ".formicos" / "workspaces" / workspace_id / "project_context.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})
```

**2. Project plan PUT:**
```python
async def put_project_plan(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    body = await request.json()
    data_dir = runtime.settings.system.data_dir
    path = Path(data_dir) / ".formicos" / "project_plan.md"
    # workspace-scoped path takes precedence
    ws_path = Path(data_dir) / ".formicos" / "workspaces" / workspace_id / "project_plan.md"
    target = ws_path if ws_path.is_file() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.get("content", ""), encoding="utf-8")
    return JSONResponse({"ok": True})
```

**3. AI Filesystem listing:**
```python
async def get_ai_filesystem(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    from formicos.surface.ai_filesystem import _runtime_root, _artifacts_root  # noqa: PLC0415
    data_dir = runtime.settings.system.data_dir

    def walk_dir(root: Path) -> list[dict[str, Any]]:
        if not root.is_dir():
            return []
        entries = []
        for item in sorted(root.iterdir()):
            if item.is_file():
                entries.append({"name": item.name, "type": "file", "size": item.stat().st_size})
            elif item.is_dir():
                children = walk_dir(item)
                entries.append({"name": item.name, "type": "dir", "children": children})
        return entries

    return JSONResponse({
        "runtime": walk_dir(_runtime_root(data_dir, workspace_id)),
        "artifacts": walk_dir(_artifacts_root(data_dir, workspace_id)),
    })
```

Register these routes using the existing pattern in `api.py`.

### `queen-overview.ts` (1 line)

Pass workspaceId to the budget viz. At line 173, change:
```html
<fc-queen-budget-viz></fc-queen-budget-viz>
```
to:
```html
<fc-queen-budget-viz .workspaceId=${this.activeWorkspaceId}></fc-queen-budget-viz>
```

**Files changed:** `workspace-browser.ts` (~120 lines net), `queen-overview.ts` (1 line), `routes/api.py` (~65 lines for 3 endpoint groups)

---

## Track A6: Git-control addon panel suppression

In `addon-panel.ts` (124 lines), the addon returns HTTP 500 when git-control runs inside Docker (no repo). The error card is ugly. Suppress it.

Find the fetch error/response handling. When `resp.status === 500`, set `this._error = ''` and `this._data = null` and return early. This hides the panel for server errors while still showing 4xx errors.

**Files changed:** `addon-panel.ts` (~3 lines)

---

## Track A7: Queen overrides form builders

Replace the two JSON textareas in `queen-overrides.ts` with structured form builders.

**Team Composition form** (replaces the JSON textarea for team_composition):

State:
```typescript
@state() private _teamRules: Array<{taskType: string; castes: string[]; strategy: string}> = [];
@state() private _newTaskType = '';
@state() private _newCastes: string[] = [];
@state() private _newStrategy = 'sequential';
```

Render: dropdown for task type (predefined: `code_simple`, `code_complex`, `research`, `analysis`, `review`, `documentation`, plus custom text input), multi-select pills for castes (coder, reviewer, researcher, archivist), dropdown for strategy (sequential, stigmergic). "Add Rule" button appends to `_teamRules`. Active rules listed with delete (x) buttons.

Save serializes to JSON: `{ "code_simple": "coder + researcher / sequential", ... }`

Load parses existing JSON back into structured state from the config.

**Round Budget form** (replaces the JSON textarea for round_budget):

State:
```typescript
@state() private _budgetTiers: Array<{tier: string; rounds: number; budget: number}> = [];
```

Render: dropdown for tier (simple, standard, complex, critical, custom), number inputs for rounds (1-50) and budget (0.10-100.00). Same add/delete pattern.

Save serializes: `{ "simple": {"rounds": 5, "budget": 0.50}, ... }`

**Files changed:** `queen-overrides.ts` (~150 lines net, replacing ~80 lines)

---

## Track A8: Structured compression template + tool result pruning

Two improvements to `_compact_thread_history()` at line 174 of `queen_runtime.py`:

**Phase 1: Prune old tool results (no LLM call).**

Add a helper function `_prune_old_tool_results()`:

```python
def _prune_old_tool_results(
    messages: list[dict[str, str]],
    protect_recent: int = 9,
) -> list[dict[str, str]]:
    """Replace old tool results with stubs to reclaim context."""
    if len(messages) <= protect_recent:
        return messages
    cutoff = len(messages) - protect_recent
    pruned = []
    for i, msg in enumerate(messages):
        if i < cutoff and msg.get("role") == "tool" and len(msg.get("content", "")) > 200:
            pruned.append({**msg, "content": "[Earlier tool output cleared]"})
        else:
            pruned.append(msg)
    return pruned
```

**Phase 2: Structured summary template.**

In `_compact_thread_history()`, replace the flat "Earlier conversation:" summary block (lines 218-248) with a structured 7-section format:

```
## Goal
[thread goal if available, else inferred from first operator message]

## Progress
### Done
[colony results with status and cost]
### In Progress
[preview cards, active tasks]

## Key Decisions
[config changes, strategy choices]

## Relevant Files
[files mentioned in conversation]

## Next Steps
[inferred from recent context]

## Critical Context
[specific values, error messages, knowledge entries referenced]
```

Build this by categorizing the `compactable` messages into sections based on their `render`/`meta` attributes and content patterns, then join into the structured template. The existing `result_card` / `preview_card` metadata is already parsed — route those into the appropriate sections.

Also apply `_prune_old_tool_results()` to the message list built by `_build_messages()` — call it in the Queen turn method, after `_track_budget_usage()` and before the LLM call.

**Files changed:** `queen_runtime.py` (~35 lines)

---

## Validation (run before declaring done)

```bash
ruff check src/formicos/surface/queen_budget.py src/formicos/surface/queen_runtime.py src/formicos/surface/routes/api.py
pyright src/formicos/surface/queen_budget.py src/formicos/surface/queen_runtime.py src/formicos/surface/routes/api.py
python scripts/lint_imports.py
pytest tests/unit/surface/test_queen_budget.py -v
cd frontend && npm run build
```

If `test_queen_budget.py` tests fail because `compute_queen_budget` signature changed, update the tests to pass the new `num_slots` parameter (default 1 means existing calls work, but verify).

If any linter/type error appears, fix it before moving on.

## Track execution order

A1 first (budget fix — everything else depends on correct budget math), then A2 (tracking data for A3/A4), then A3 (API for A4), then A4 (viz), then A5-A8 in any order (independent).
