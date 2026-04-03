# Wave 77.5 Plan: Product Surface Polish + Context Budget Fix + Model Upgrade

**Theme:** Fix the context budget bug (210% overcommit from slot-unaware
allocation), make the budget math visible to the operator, upgrade embedding
and LLM models, humanize JSON-textarea overrides, and add missing bulk
operations to the knowledge browser.

**Teams:** 3 parallel coder teams + context budget fix woven into Team A.
Merge order: C first (models, Qdrant rebuild), then A and B together.

**Estimated total change:** ~685 lines (Team A ~385, Team B ~180, Team C ~120).

**Research basis:** `docs/waves/wave_77/wave_77_5_reference.md` (live codebase
audit, 29 Mar 2026), 8 knowledge base entries (embedding, thinking mode,
context budgets), live llama.cpp `/slots` endpoint verification.

---

## Critical bug: Context budget 210% overcommit

`compute_queen_budget()` allocates proportional slices of the raw model
`context_window` (80,000 from registry). But llama.cpp divides KV cache
evenly across `-np 2` slots: each slot has `n_ctx: 40192` (verified via
`GET /slots`). The budget allocates 75,901 tokens across all slots when
only 36,096 tokens fit per inference slot.

In practice this is harmless for short conversations (content < 36k), but
in deep conversations the system silently relies on llama.cpp truncation
instead of its own budget caps. This is a correctness bug, not cosmetic.

**Fix:** Team A, Tracks A1-A4. Details below.

---

## Team A: Context Budget Transparency + Workspace Browser + Override Forms

**Owned files:**
- `src/formicos/surface/queen_budget.py`
- `src/formicos/surface/queen_runtime.py` (budget tracking only)
- `src/formicos/surface/routes/api.py` (4 route changes: queen-budget enhancement + 3 endpoints)
- `frontend/src/components/queen-budget-viz.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/workspace-browser.ts`
- `frontend/src/components/addon-panel.ts`
- `frontend/src/components/queen-overrides.ts`

**Do not touch:** `queen_tools.py`, `colony_manager.py`, `mcp_server.py`,
`formicos.yaml`, `docker-compose.yml`, any adapter file, any engine file.

### A1: Context budget slot-aware fix (Critical)

**Problem:** `queen_runtime.py:933-940` reads `context_window` from the
model registry (80000) and passes it to `compute_queen_budget()`. This
ignores the llama.cpp slot division.

**Fix in `queen_budget.py` + `queen_runtime.py`:**

Do not inline slot math in multiple callers. The correct seam is
`compute_queen_budget()` itself.

```python
def compute_queen_budget(
    context_window: int | None,
    output_reserve: int,
    *,
    num_slots: int = 1,
) -> QueenContextBudget:
    effective_window = (
        context_window // max(1, num_slots)
        if context_window and num_slots > 1
        else context_window
    )
    ...
```

Then in `queen_runtime.py`, resolve `num_slots` once and pass it through:

```python
_num_slots = 1
if _model_addr and _model_addr.startswith("llama-cpp/"):
    _num_slots = max(1, int(os.environ.get("LLM_SLOTS", "1")))
budget = compute_queen_budget(_ctx_window, _output_reserve, num_slots=_num_slots)
```

Cloud models (`anthropic/`, `openai/`, `gemini/`, `deepseek/`) are
unaffected — their APIs serve one request with full context. Only
`llama-cpp/` addresses get the division. This matches the adapter's
existing `LLM_SLOTS` env var usage at `llm_openai_compatible.py:58`.

Add `import os` at the top of queen_runtime.py if not already present.

**Verification:**
```python
# Before: available = 80000 - 4096 = 75904. Overcommit: 210%.
# After:  available = 40000 - 4096 = 35904. Overcommit: 102% (normal).
```

**Files:** `queen_budget.py` (~8 lines), `queen_runtime.py` (~4 lines)

### A2: Context budget consumption tracking

After `_build_messages()` runs and all injections complete (memory
retrieval at ~975, project context at ~1006, project plan at ~1033,
procedures at ~1061, journal at ~1087, session context at ~1122, thread
context at ~1130), track actual tokens per section.

Illustrative sketch of the tracking shape:

```python
def _track_budget_usage(
    self,
    messages: list[dict[str, str]],
    budget: QueenContextBudget,
    model_addr: str,
) -> None:
    """Record per-slot token consumption for budget transparency."""
    _CHARS_PER_TOKEN = 4
    usage: dict[str, int] = {}
    for msg in messages:
        content = msg.get("content", "")
        tokens = len(content) // _CHARS_PER_TOKEN
        # Categorize by content markers
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
            # Uncategorized system messages → system_prompt bucket
            usage["system_prompt"] = usage.get("system_prompt", 0) + tokens

    # Compute effective context
    ctx_window = budget.system_prompt + budget.memory_retrieval + budget.project_context + \
        budget.project_plan + budget.operating_procedures + budget.queen_journal + \
        budget.thread_context + budget.tool_memory + budget.conversation_history + \
        budget.working_memory
    # Actually: just sum from the budget object
    total_consumed = sum(usage.values())

    self._last_budget_usage_by_workspace[workspace_id] = {
        "queen_model": model_addr,
        "queen_model_type": "local" if model_addr.startswith("llama-cpp/") else "cloud",
        "slots": usage,
        "total_consumed": total_consumed,
    }
```

Call after the last injection completes, before the LLM call.

Store as `self._last_budget_usage_by_workspace: dict[str, dict[str, Any]] = {}`
(init in `__init__`).

**Audit refinement:** Do not implement this by re-classifying messages from
content markers after `_build_messages()` returns. That is brittle and will
miscount as prompts evolve. Track usage at the injection sites inside
`_build_messages()` and persist the latest usage **per workspace** as
`self._last_budget_usage_by_workspace[workspace_id]`, not a single global
`_last_budget_usage`.

**Files:** `queen_runtime.py` (~50 lines)

### A3: Enhanced queen-budget API endpoint

Modify `GET /api/v1/queen-budget` in `routes/api.py` (currently lines
1029-1040) to return both allocation AND consumption:

Illustrative sketch:

```python
async def get_queen_budget(request: Request) -> JSONResponse:
    workspace_id = request.query_params.get("workspace_id", "")
    ctx_window = None
    output_reserve = 4096
    num_slots = 1
    queen_model = ""

    # Resolve queen model context
    queen_rt = runtime.queen
    if queen_rt:
        queen_model = queen_rt._resolve_queen_model(workspace_id) or ""
        output_reserve = queen_rt._queen_max_tokens(workspace_id)
        for rec in runtime.settings.models.registry:
            if rec.address == queen_model:
                ctx_window = rec.context_window
                break
        if queen_model.startswith("llama-cpp/"):
            num_slots = int(os.environ.get("LLM_SLOTS", "1"))
            if num_slots > 1 and ctx_window:
                ctx_window = ctx_window // num_slots

    effective = (ctx_window or 0) - output_reserve
    budget = compute_queen_budget(ctx_window, output_reserve, num_slots=num_slots)

    # Per-slot allocation
    slot_list = []
    for name, frac in _FRACTIONS.items():
        allocated = getattr(budget, name, 0)
        consumed = 0
        if queen_rt and hasattr(queen_rt, "_last_budget_usage_by_workspace"):
            usage = queen_rt._last_budget_usage_by_workspace.get(workspace_id, {}) or {}
            consumed = usage.get("slots", {}).get(name, 0)
        slot_list.append({
            "name": name,
            "fraction": frac,
            "allocated": allocated,
            "fallback": _FALLBACKS.get(name, 0),
            "consumed": consumed,
            "utilization": round(consumed / allocated, 3) if allocated > 0 else 0,
        })

    total_consumed = sum(s["consumed"] for s in slot_list)

    return JSONResponse({
        "queen_model": queen_model,
        "queen_model_type": "local" if queen_model.startswith("llama-cpp/") else "cloud",
        "context_window": (ctx_window or 0) * (num_slots if num_slots > 1 else 1),
        "num_slots": num_slots,
        "effective_context": ctx_window or 0,
        "output_reserve": output_reserve,
        "available": max(0, effective),
        "slots": slot_list,
        "total_consumed": total_consumed,
        "total_utilization": round(total_consumed / effective, 3) if effective > 0 else 0,
    })
```

**Audit refinement:** The live seam is `runtime.queen`, not
`runtime._queen_runtime`. Also make the endpoint workspace-aware:
- accept `workspace_id` as a query param
- read usage from `runtime.queen._last_budget_usage_by_workspace`
- report both raw `context_window` and per-slot `effective_context`
- call `compute_queen_budget(..., num_slots=num_slots)` instead of manually
  duplicating slot math in the route

**Files:** `routes/api.py` (~40 lines replacing ~12)

### A4: Budget viz upgrade

Rewrite `fc-queen-budget-viz` (currently 102 lines) to show the full math.

**Headline row:**
```
Queen: claude-sonnet-4-6 (cloud)  |  Context: 200,000  |  Available: 191,808
Used: 28,500 / 191,808 (14.9%)
```
Or for local:
```
Queen: qwen3.5-35b (local, 2 slots)  |  Per-slot: 40,192  |  Available: 36,096
Used: 12,800 / 36,096 (35.5%)
```

**Per-slot dual bars:**
- Outer bar (dim): allocated capacity (the cap)
- Inner bar (bright): actual consumed tokens
- Slots at >90% utilization get a warning accent color
- Show both allocated and consumed numbers per row

**Data source:** `GET /api/v1/queen-budget?workspace_id=...` (enhanced in A3). Fetch on
mount and every 30 seconds while expanded.

**Add `working_memory` to SLOT_COLORS** (already fixed: `#14b8a6`).

**Files:** `queen-budget-viz.ts` (~150 lines, replacing current 102)

### A5: Workspace browser structured sections

Replace the flat file tree in `workspace-browser.ts` (403 lines) with
three structured sections.

**Section 1: Operator Files**

| File | Label | Mode | Backend |
|------|-------|------|---------|
| `.formicos/project_context.md` | Project Context | Edit | **NEW:** `GET/PUT /api/v1/workspaces/{id}/project-context` |
| `.formicos/project_plan.md` | Project Plan | Edit | **NEW:** `PUT /api/v1/project-plan` |
| `.formicos/operations/{ws}/operating_procedures.md` | Operating Procedures | Preview | Read-only preview with "Edit in Operations tab" hint |
| `.formicos/operations/{ws}/queen_journal.md` | Queen Journal | View | `GET /api/v1/workspaces/{id}/queen-journal` (exists) |

Each editable file: textarea + Save + Revert, matching the existing
project context pattern. Journal is read-only (last 10 entries rendered
as formatted text, not raw markdown).

**Audit refinement:**
- The live backend does **not** currently register `PUT /api/v1/workspaces/{id}/files/{file_name}`.
  `workspace-browser.ts` is posting to a nonexistent save seam today.
- Add a dedicated `GET/PUT /api/v1/workspaces/{id}/project-context` endpoint in
  `routes/api.py` and point the Project Context editor at that endpoint.
- Do not depend on a clickable "Link to Operations tab" unless you also own the
  shell handoff. A read-only preview with "Edit in Operations tab" copy is
  sufficient inside `workspace-browser.ts`.

**Section 2: Working Memory (Wave 77)**

Read-only directory listing of the AI Filesystem tree:
```
runtime/queen/          2 files
runtime/colonies/       1 directory
artifacts/              0 files
```

Backend: **NEW** `GET /api/v1/workspaces/{id}/ai-filesystem` returns a
tree structure. Implementation in `routes/api.py`: read from
`ai_filesystem._runtime_root()` and `_artifacts_root()`, walk directory,
return `{runtime: [{name, size, modified}], artifacts: [...]}`. ~25 lines.

**Section 3: Workspace Files**

The existing file tree view, moved below the structured sections. Unchanged
except for position.

Also pass the active workspace ID into `fc-queen-budget-viz` from
`queen-overview.ts` so the budget panel does not show another workspace's
last Queen turn:

```html
<fc-queen-budget-viz .workspaceId=${this.activeWorkspaceId}></fc-queen-budget-viz>
```

**Files:** `workspace-browser.ts` (~120 lines net change), `queen-overview.ts`
(~1 line), `routes/api.py` (~25 lines for ai-filesystem endpoint, ~20 lines
for project-plan PUT, ~20 lines for project-context GET/PUT)

### A6: Git-control addon panel suppression

`addon-panel.ts` (124 lines) shows an error card when the addon returns
HTTP 500 (git-control inside Docker has no repo). Change the error render
to return `nothing` when the error status is 500:

```typescript
// In the fetch catch/error handling:
if (resp.status === 500) { this._error = ''; this._data = null; return; }
```

This suppresses the panel entirely rather than showing an ugly error.
Addons that return 4xx or other errors still render their error state.

**Files:** `addon-panel.ts` (~3 lines)

### A7: Queen overrides form builders

Replace the two JSON textareas in `queen-overrides.ts` (294 lines) with
structured form builders.

**Team Composition form** (replaces lines 250-267):

State:
```typescript
@state() private _teamRules: Array<{taskType: string; castes: string[]; strategy: string}> = [];
@state() private _newTaskType = '';
@state() private _newCastes: string[] = [];
@state() private _newStrategy = 'sequential';
```

Render: dropdown for task type (predefined: `code_simple`, `code_complex`,
`research`, `analysis`, `review`, `documentation`, plus custom text input),
multi-select pills for castes (coder, reviewer, researcher, archivist),
dropdown for strategy (sequential, stigmergic). "Add Rule" button appends
to `_teamRules`. Active rules listed with delete (x) buttons.

Save serializes to JSON:
```typescript
private _saveTeamComp() {
  const obj: Record<string, string> = {};
  for (const rule of this._teamRules) {
    obj[rule.taskType] = `${rule.castes.join(' + ')} / ${rule.strategy}`;
  }
  this._emitConfig('queen.team_composition', JSON.stringify(obj));
}
```

Load parses existing JSON back into structured state in `_loadFromConfig()`:
```typescript
// Parse "coder + researcher / sequential" → {castes: ["coder","researcher"], strategy: "sequential"}
const parts = value.split(' / ');
const strategy = parts[1]?.trim() || 'sequential';
const castes = parts[0].split('+').map(c => c.trim());
```

**Round Budget form** (replaces lines 270-287):

State:
```typescript
@state() private _budgetTiers: Array<{tier: string; rounds: number; budget: number}> = [];
```

Render: dropdown for tier (simple, standard, complex, critical, custom),
number inputs for rounds (1-50) and budget (0.10-100.00). Same add/delete
pattern.

Save serializes:
```typescript
const obj: Record<string, {rounds: number; budget: number}> = {};
for (const t of this._budgetTiers) obj[t.tier] = {rounds: t.rounds, budget: t.budget};
this._emitConfig('queen.round_budget', JSON.stringify(obj));
```

**Files:** `queen-overrides.ts` (~150 lines net, replacing ~80 lines of
JSON textarea sections)

### A8: Structured compression template + tool result pruning

`compact_conversation()` in `queen_runtime.py` currently generates a flat
prose summary when conversation history exceeds budget. Two improvements
from agent architecture research, both pure quality gains with no API changes:

**Phase 1: Prune old tool results (no LLM call).**

Before triggering LLM summarization, walk backward through messages and
replace tool results older than the most recent N*3 messages with
`"[Earlier tool output cleared]"`. The Queen uses tool calling heavily —
colony status checks, knowledge searches, file reads — all producing
large results that age out quickly. This reclaims 30-50% of context
without any LLM call, often avoiding summarization entirely.

```python
def _prune_old_tool_results(
    messages: list[dict[str, str]],
    protect_recent: int = 9,  # 3 turns * 3 messages per turn
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

Replace the flat prose summary prompt with a 7-section structured template
that preserves categorized information through compression:

```
## Goal
[What the operator is trying to accomplish]

## Progress
### Done
[Completed work — colony outcomes, file changes, results]
### In Progress
[Active colonies or pending actions]
### Blocked
[Any blockers or issues encountered]

## Key Decisions
[Config changes, strategy choices, and why]

## Relevant Files
[Files read, modified, or created — with brief note on each]

## Next Steps
[What needs to happen next]

## Critical Context
[Specific values, error messages, knowledge entries referenced]
```

The sections map directly to FormicOS concepts: Goal = thread goal,
Progress = colony outcomes, Key Decisions = config changes, Critical
Context = knowledge entries referenced. This preserves more actionable
information than prose and survives iterative re-compression (each
re-compression refines the same sections rather than summarizing a
summary).

**Files:** `queen_runtime.py` (~35 lines: pruning function + template
replacement in `compact_conversation()`)

### Team A validation

```bash
ruff check src/formicos/surface/queen_budget.py src/formicos/surface/queen_runtime.py src/formicos/surface/routes/api.py
pyright src/formicos/surface/queen_budget.py src/formicos/surface/queen_runtime.py src/formicos/surface/routes/api.py
python scripts/lint_imports.py
pytest tests/unit/surface/test_queen_budget.py -v
cd frontend && npm run build
```

Verify budget API:
```bash
curl -s 'http://localhost:8080/api/v1/queen-budget?workspace_id=default' | python -c "
import sys, json; d = json.load(sys.stdin)
print(f'effective_context: {d[\"effective_context\"]}')
print(f'num_slots: {d[\"num_slots\"]}')
print(f'total_utilization: {d[\"total_utilization\"]}')
assert d['effective_context'] < d['context_window'] or d['num_slots'] == 1
"
```

---

## Team B: Knowledge Browser Polish + Billing Surface

**Owned files:**
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/components/knowledge-search-results.ts`
- `frontend/src/components/billing-card.ts` (NEW)
- `frontend/src/components/operations-view.ts`

**Do not touch:** `queen-budget-viz.ts`, `workspace-browser.ts`,
`queen-overrides.ts`, any backend Python file, `formicos-app.ts`.

### B1: Bulk knowledge confirmation

122 entries at `candidate` status. Add "Confirm All Visible" to the
knowledge browser toolbar.

**Implementation:**

Add a button next to the existing search/filter controls:
```html
<button class="bulk-btn" @click=${this._confirmAllVisible}
  ?disabled=${this._bulkInProgress}>
  ${this._bulkInProgress
    ? `Confirming ${this._bulkProgress}/${this._bulkTotal}...`
    : 'Confirm All Visible'}
</button>
```

State:
```typescript
@state() private _bulkInProgress = false;
@state() private _bulkProgress = 0;
@state() private _bulkTotal = 0;
```

Handler:
```typescript
private async _confirmAllVisible() {
  const visible = this.items.filter(e => e.status === 'candidate');
  if (!visible.length) return;
  this._bulkInProgress = true;
  this._bulkTotal = visible.length;
  this._bulkProgress = 0;
  let errors = 0;
  for (const entry of visible) {
    try {
      await fetch(`/api/v1/knowledge/${entry.id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'verified' }),
      });
    } catch { errors++; }
    this._bulkProgress++;
  }
  this._bulkInProgress = false;
  await this._loadEntries(); // refresh
}
```

No new backend endpoint. Uses existing `PUT /knowledge/{id}/status`.
Progress bar updates per-entry. On completion, refreshes the entry list.

This belongs in the detail-mode catalog toolbar, where `this.items` is the
actual visible list.

**Files:** `knowledge-browser.ts` (~40 lines)

### B2: Score breakdown in search results

The search API (`GET /api/v1/knowledge/search`) already returns score
breakdown data per result. Surface it in the components that actually render
search results:
- `knowledge-browser.ts` for detail-mode catalog search
- `knowledge-search-results.ts` for search-first unified results

Add a "Show Scoring" toggle in the search toolbar:
```typescript
@state() private _showScoring = false;
```

Under each search result card (when `_showScoring` is true and the entry
has a `score_breakdown`), render signal pills:

```html
<div class="score-breakdown">
  ${Object.entries(entry.score_breakdown || {}).map(([signal, value]) => html`
    <span class="score-pill" title=${signal}>
      ${signal.replace('_', ' ')}: ${(value as number).toFixed(2)}
    </span>
  `)}
</div>
```

Style the pills as small mono-font badges with signal-specific colors
(semantic=purple, thompson=green, freshness=blue, etc.). The composite
score is already shown on the card; the breakdown explains why.

**Audit refinement:** search-first mode renders through
`fc-knowledge-search-results`, so Team B needs ownership of that component too.

**Files:** `knowledge-browser.ts` (~20 lines), `knowledge-search-results.ts`
(~30 lines)

### B3: Billing dashboard card

New component `fc-billing-card` mounted in the Operations tab.

**Data source:** `GET /api/v1/billing/status` (Wave 75, verified live).

**Render:**
```
Billing — March 2026
Tokens: 0 (input: 0 / output: 0 / reasoning: 0)
Fee: $0.00 (Tier 1 — Free)
```

When tokens are non-zero, show by-model breakdown as small bar segments
grouped by provider type (cloud vs local). This helps the operator see
whether hybrid routing is working — if 90% of tokens are cloud, the local
LLM isn't being utilized. The `by_model` field in the billing response
already contains model addresses; group by prefix (`anthropic/`, `openai/`,
`llama-cpp/`, etc.).

Cache-read tokens shown as informational (not billed).

The component is ~100 lines. Mount it in `operations-view.ts` after the
existing summary cards:

```html
<fc-billing-card .workspaceId=${this.workspaceId}></fc-billing-card>
```

Add the import to `operations-view.ts`.

**Files:** `billing-card.ts` (NEW, ~100 lines), `operations-view.ts` (~5
lines for mount + import)

### Team B validation

```bash
cd frontend && npm run build
# Visual: open localhost:8080, Knowledge tab
# - Filter to status=candidate, click "Confirm All Visible"
# - Search a term, toggle "Show Scoring", verify breakdowns appear
# Visual: Operations tab — billing card renders with current period
```

---

## Team C: Model Upgrade (nomic embedding + Qwen3.5 LLM + thinking mode)

**Owned files:**
- `config/formicos.yaml`
- `docker-compose.yml` (llm service command only)
- `src/formicos/surface/app.py` (`_build_embed_fn()` only)
- `src/formicos/adapters/llm_anthropic.py`
- `src/formicos/adapters/llm_gemini.py`
- `src/formicos/adapters/llm_openai_compatible.py`
- `src/formicos/adapters/vector_qdrant.py` (`_embed_texts()` only)
- `src/formicos/core/types.py`
- `src/formicos/core/ports.py`
- `src/formicos/surface/runtime.py`
- `config/caste_recipes.yaml`
- `src/formicos/engine/runner.py` (thinking passthrough only)
- `.env.example`
- `scripts/setup-local-gpu.sh`

**Do not touch:** `queen_runtime.py`, `queen_budget.py`, `queen_tools.py`,
`routes/api.py`, any frontend file.

### C1: Swap embedding to nomic-embed-text-v1.5 at 768-dim

Per the audit, the Qwen3Embedder async path already supports `is_query`
asymmetric embedding. The work is only on the sentence-transformers
fallback path (cloud-first default).

**`config/formicos.yaml`** embedding section:
```yaml
embedding:
  model: "${EMBED_MODEL:nomic-ai/nomic-embed-text-v1.5}"
  endpoint: "${EMBED_URL:}/v1/embeddings"
  dimensions: ${EMBED_DIMENSIONS:768}
```

**`app.py` in `_build_embed_fn()`** (~line 112-139):

1. Add `trust_remote_code=True` to `SentenceTransformer()`:
   ```python
   model = SentenceTransformer(model_name, trust_remote_code=True)
   ```

2. Change the returned closure signature and add prefix injection:
   ```python
   def embed_fn(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
       prefix = "search_query: " if is_query else "search_document: "
       prefixed = [prefix + t for t in texts]
       return model.encode(prefixed, normalize_embeddings=True).tolist()
   ```

**`vector_qdrant.py` in `_embed_texts()`** (~line 90-101):

Pass `is_query` through to the sync fallback path:
```python
# Current (drops is_query for sync):
vectors = self._embed_fn(texts)
# Fixed:
vectors = self._embed_fn(texts, is_query=is_query)
```

**`.env.example`**: Update defaults in the local-GPU section:
```bash
# EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5
# EMBED_DIMENSIONS=768
```

**Qdrant rebuild required:** 384→768 dimension change. Instructions in
validation section.

**Files:** `formicos.yaml` (~3 lines), `app.py` (~8 lines), `vector_qdrant.py`
(~2 lines), `.env.example` (~2 lines)

### C2: Swap LLM to Qwen3.5-35B-A3B

**`docker-compose.yml`** llm service command:
```yaml
command: >
  --model /models/${LLM_MODEL_FILE:-Qwen3.5-35B-A3B-Q4_K_M.gguf}
  --alias qwen3.5-35b
  --ctx-size ${LLM_CONTEXT_SIZE:-65536}
  --n-gpu-layers 99
  --flash-attn on
  --fit on
  --kv-unified
  --cache-type-k bf16
  --cache-type-v bf16
  --batch-size 8192
  --ubatch-size 4096
  --threads 8
  --threads-batch 16
  --jinja
  --chat-template-kwargs '{"enable_thinking":false}'
  --slots
  -np ${LLM_SLOTS:-2}
  -sps ${LLM_SLOT_PROMPT_SIMILARITY:-0.5}
  --cache-ram ${LLM_CACHE_RAM:-1024}
  --host 0.0.0.0
  --port 8080
```

Key changes from current Qwen3-Coder-30B config:
- `--kv-unified` (Qwen3.5 MoE benefit)
- `--cache-type-k bf16 --cache-type-v bf16` (better quality than q8_0)
- `--chat-template-kwargs '{"enable_thinking":false}'` (server-level default)
- `--alias qwen3.5-35b` (new alias)
- `--reasoning-format none` removed (handled by chat template kwargs)
- Default context reduced to 65536 (bf16 KV cache uses more VRAM than q8_0)

**`config/formicos.yaml`**: Update local-gpu model address and registry:
- Default model alias: `llama-cpp/qwen3.5-35b`
- Registry entry: `address: "llama-cpp/qwen3.5-35b"`, `context_window: 65536`
- Update VRAM comment in docker-compose

**`.env.example`**: Update defaults:
```bash
# LLM_MODEL_FILE=Qwen3.5-35B-A3B-Q4_K_M.gguf
# LLM_CONTEXT_SIZE=65536
```

**`scripts/setup-local-gpu.sh`**: Update download commands and model filename.

**Hybrid routing profile** — add to `.env.example`:
```bash
# Profile 2: Hybrid (GPU + API keys — RECOMMENDED for local GPU users)
# Queen on cloud (unlimited context), colonies on local GPU (fast parallel).
# COMPOSE_PROFILES=local-gpu
# QUEEN_MODEL=anthropic/claude-sonnet-4-6
# CODER_MODEL=llama-cpp/qwen3.5-35b
# REVIEWER_MODEL=llama-cpp/qwen3.5-35b
# RESEARCHER_MODEL=anthropic/claude-haiku-4-5
# ARCHIVIST_MODEL=llama-cpp/qwen3.5-35b
# LLM_SLOTS=3
```

**Files:** `docker-compose.yml` (~15 lines), `formicos.yaml` (~10 lines),
`.env.example` (~15 lines), `setup-local-gpu.sh` (~10 lines)

### C3: Per-caste thinking mode control

The adapter gap is real (verified). llama.cpp supports per-request
`chat_template_kwargs` via the OpenAI-compatible API request body.

**`adapters/llm_openai_compatible.py`**: Add `extra_body` parameter:

```python
async def complete(
    self,
    model: str,
    messages: Sequence[LLMMessage],
    tools: Sequence[LLMToolSpec] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    tool_choice: object | None = None,
    extra_body: dict[str, object] | None = None,  # NEW
) -> LLMResponse:
```

In payload construction (~line 249):
```python
if extra_body:
    payload.update(extra_body)
```

**`config/caste_recipes.yaml`**: Add `thinking` field per caste:

| Caste | thinking | Rationale |
|-------|----------|-----------|
| queen | false | Tool calling, fast response |
| coder | false | Tool calling, fast code generation |
| reviewer | true | Deeper analysis, fewer tool calls |
| researcher | true | Broader exploration, extended reasoning |
| archivist | false | Fast extraction, low cost |

Because caste recipes are validated by `CasteRecipe` in `core/types.py`,
add `thinking: bool = False` there. Otherwise the new YAML field is ignored
at load time.

**`core/ports.py` + `surface/runtime.py` + `engine/runner.py`**: thread
`thinking` through the actual runtime path.

1. Extend `LLMPort.complete(...)` in `core/ports.py` with
   `extra_body: dict[str, object] | None = None`
2. Extend `LLMRouter.complete(...)` and `_complete_with_fallback(...)` in
   `surface/runtime.py` to accept `extra_body`
3. Mirror the optional parameter on `llm_anthropic.py` and `llm_gemini.py`
   and ignore it there, so the adapters still conform to `LLMPort`
4. Forward `extra_body` only for `llama-cpp/` models
5. In `engine/runner.py`, read `agent.recipe.thinking` (default `False`) and pass:
```python
extra_body=(
    {"chat_template_kwargs": {"enable_thinking": True}}
    if getattr(caste, "thinking", False)
    else None
)
```

Only effective for local llama.cpp models. Do **not** rely on cloud providers
"ignoring" unknown fields; the FormicOS router/adapter layer is the actual
contract boundary, so omit `extra_body` for non-local models.

**Files:** `llm_openai_compatible.py` (~6 lines), `llm_anthropic.py` (~2 lines),
`llm_gemini.py` (~2 lines), `core/types.py` (~1 line), `core/ports.py` (~2 lines),
`surface/runtime.py` (~12 lines), `caste_recipes.yaml` (~5 lines),
`runner.py` (~8 lines)

### Team C validation

```bash
# CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Stack rebuild with new models
docker compose down
docker volume rm formicosa_qdrant-data    # Required: 384→768 dim change
docker compose up -d --build

# Verify embedding upgrade
curl -s http://localhost:8080/health | python -c "
import sys, json; d = json.load(sys.stdin)
print(f'entries: {d[\"memory_entries\"]}')
assert d['memory_entries'] > 0, 'Entries must re-embed on startup'
"

# Verify LLM upgrade (local GPU only)
curl -s http://localhost:8008/props | python -c "
import sys, json; d = json.load(sys.stdin)
print(f'model: {d[\"model_alias\"]}')
print(f'slots: {d[\"total_slots\"]}')
"

# Verify thinking mode (local GPU only)
# Send a reviewer task, check llm container logs for enable_thinking
docker logs formicos-llm --tail 20
```

---

## Merge order and coordination

```
1. Team C lands first
   → docker compose down
   → docker volume rm formicosa_qdrant-data  (embedding dim change)
   → docker compose up -d --build
   → Verify health shows memory_entries > 0

2. Team A lands second
   → docker compose build formicos && docker compose up -d
   → Verify GET /api/v1/queen-budget shows effective_context < context_window
   → Verify budget viz shows dual bars in the UI

3. Team B lands third
   → docker compose build formicos && docker compose up -d
   → Visual verification of bulk confirm + score breakdown + billing card
```

### Shared file coordination

| File | Team A | Team B | Team C |
|------|--------|--------|--------|
| `config/formicos.yaml` | -- | -- | C1, C2 |
| `docker-compose.yml` | -- | -- | C2 |
| `routes/api.py` | A3, A5 (budget/project-context/project-plan/ai-filesystem) | -- | -- |
| `queen_runtime.py` | A1, A2 | -- | -- |
| `queen-budget-viz.ts` | A4 | -- | -- |
| `queen-overview.ts` | A5 (workspaceId passthrough only) | -- | -- |
| `workspace-browser.ts` | A5 | -- | -- |
| `queen-overrides.ts` | A7 | -- | -- |
| `knowledge-browser.ts` | -- | B1, B2 | -- |
| `knowledge-search-results.ts` | -- | B2 | -- |
| `operations-view.ts` | -- | B3 | -- |
| `llm_openai_compatible.py` | -- | -- | C3 |
| `llm_anthropic.py` | -- | -- | C3 |
| `llm_gemini.py` | -- | -- | C3 |
| `core/types.py` | -- | -- | C3 |
| `core/ports.py` | -- | -- | C3 |
| `app.py` | -- | -- | C1 |
| `vector_qdrant.py` | -- | -- | C1 |
| `runtime.py` | -- | -- | C3 |
| `runner.py` | -- | -- | C3 |
| `formicos-app.ts` | -- | -- | -- |

No file conflicts between teams.

---

## What this wave does NOT do

- No context budget REDISTRIBUTION (making unused slot capacity available
  to other slots). This wave makes the waste VISIBLE. A future wave can
  implement watermark-style packing.
- No GGUF download manager UI
- No model A/B testing or benchmark runner
- No Queen-assisted natural language configuration (future enhancement
  on top of the structured forms)
- No new event types
- No new MCP tools
- No tool trace metadata on colony completion events (per-tool-call
  breakdown of name, args size, result size, duration — Wave 78 candidate,
  requires event schema discussion)
- No keyword-based model routing for the Queen (40-word complexity
  heuristic to route simple requests to cheap models — Wave 78 candidate,
  requires model cascade schema for "cheap queen" model)
- No background review agent for operator preference capture (post-turn
  hook that reviews conversation for preferences worth persisting —
  Wave 78 candidate, ~120 lines, uses existing event types)
- No shadow git checkpoints for file safety (snapshot workspace before
  file mutations — Wave 78 candidate, required before edit_file becomes
  production-grade)

---

## Success conditions

1. `GET /api/v1/queen-budget?workspace_id=...` returns `effective_context` < `context_window`
   when Queen is on local LLM with 2+ slots
2. Budget viz shows effective context, slot count, and per-slot allocated
   vs consumed with dual bars
3. Operator can answer "why is only half my context used?" by reading the
   budget panel
4. Workspace tab shows structured Operator Files / Working Memory / Files
5. Project plan is editable from the Workspace tab
6. Project context save uses a real dedicated endpoint, not the nonexistent `PUT /files/...` seam
7. Git-control addon panel does not show HTTP 500
8. Team composition and round/budget overrides use structured forms, not
   JSON textareas
9. Knowledge entries can be bulk-confirmed via "Confirm All Visible"
10. Search results show 7-signal score breakdowns when toggled
11. Billing summary visible in the Operations tab
12. Embedding uses nomic-embed-text-v1.5 at 768-dim with instruction prefixes
13. LLM uses Qwen3.5-35B-A3B with thinking disabled by default
14. Reviewer and researcher castes enable thinking per-request on local llama.cpp
15. All 122+ knowledge entries survive the embedding model upgrade
16. Conversation compaction uses structured 7-section template and prunes
    old tool results before triggering LLM summarization
