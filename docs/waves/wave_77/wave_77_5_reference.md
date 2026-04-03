# Wave 77.5 Audit Reference

**Date:** 2026-03-29
**Scope:** Product surface polish + model upgrade planning
**Method:** Live codebase + running stack + knowledge base (122 entries)

## 1. Frontend Component Inventory

| Component | Tag | Lines | Editable Fields | API Calls | Key Issues |
|-----------|-----|-------|-----------------|-----------|------------|
| workspace-browser.ts | fc-workspace-browser | 403 | project_context.md only | 3 attempted (GET/GET/PUT files) | Project-context save points at nonexistent PUT route |
| operations-view.ts | fc-operations-view | 245 | via child procs editor | 3 (journal/procs/actions) | Dead code: `_renderJournalSlot()`, `_renderProceduresSlot()` |
| knowledge-browser.ts | fc-knowledge-browser | ~1652 | create/edit/status forms | 12+ endpoints | No bulk confirm. Massive component. |
| model-registry.ts | fc-model-registry | 534 | policy, add model | 3 (PATCH/POST/GET castes) | Timer leak on 60s refresh |
| settings-view.ts | fc-settings-view | 790 | governance, maintenance | 5 endpoints | `(ws as any).config` unsafe cast |
| formicos-app.ts | formicos-app | ~818 | workspace creator | 1 (autonomy-status) | 9 sub-views, WebSocket state |
| budget-panel.ts | fc-budget-panel | 314 | none (read-only) | 1 (GET /budget) | Shows cost/tokens, NOT context budget |
| queen-overview.ts | fc-queen-overview | 318 | none | none (children fetch) | Mounts 10+ child components |
| queen-budget-viz.ts | fc-queen-budget-viz | 102 | none (read-only) | 1 (GET /queen-budget) | Shows fractions + fallback floors ONLY |
| addon-panel.ts | fc-addon-panel | 124 | none | 1 (generic GET) | Timer leak, shows error on HTTP 500 |

### queen-budget-viz gap

The `fc-queen-budget-viz` component (queen-overview.ts child, line 77-96) shows:
- 10 slot names, fraction percentages, colored bars, fallback floor tokens
- Collapsed by default, expands on click

**Missing:** The component shows static allocation (fractions), not
**actual token consumption
per slot per Queen turn**. The operator asked for visibility into "how much is
spent on where."

**What's needed:** The `GET /api/v1/queen-budget` endpoint returns only
fractions/fallbacks. To show actual consumption, `_build_messages()` in
`queen_runtime.py:1822` would need to track how many tokens each injection
actually used, then expose that via the API or WebSocket.

Important refinement: usage should be tracked at the injection sites inside
`_build_messages()`, not reconstructed later from content markers. It should
also be stored per workspace, not as one global "last turn".

## 2. Backend API Inventory (relevant subset)

### File I/O for .formicos/

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/v1/workspaces/{id}/files` | GET | List workspace files (colony artifacts) |
| `/api/v1/workspaces/{id}/files/{path}` | GET | Read file content (truncated) |
| `/api/v1/workspaces/{id}/files/.formicos/project_context.md` | PUT | Intended by frontend, but **not actually registered** in the live backend |
| `/api/v1/workspaces/{id}/operating-procedures` | GET/PUT | Read/write procedures |
| `/api/v1/workspaces/{id}/queen-journal` | GET | Read journal (structured) |
| `/api/v1/project-plan` | GET | Read project plan (parsed) |

**Gap:** No real PUT endpoint for project context or project plan. The Queen writes
project plan via tools, but the operator can only read it in the UI. The current
workspace browser also posts project-context edits to a nonexistent `PUT /files/...`
route. Add dedicated endpoints rather than assuming the generic files preview route
is writable.

**Gap:** No endpoints for Wave 77 runtime/ or artifacts/ directories. The AI
filesystem is Queen-tool-only. A read-only `GET /api/v1/workspaces/{id}/working-memory`
endpoint would let the workspace browser show the runtime tree.

### Knowledge operations

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/v1/knowledge?workspace_id=X&limit=N` | GET | List entries |
| `/api/v1/knowledge/search?q=X&workspace_id=Y` | GET | Semantic search with score breakdown |
| `/api/v1/knowledge/{id}` | GET/PUT/DELETE | CRUD single entry |
| `/api/v1/knowledge/{id}/status` | PUT | Change status (candidate/verified/etc) |
| `/api/v1/knowledge/{id}/feedback` | POST | Thumbs up/down |
| `/api/v1/knowledge/{id}/relationships` | GET | Graph relationships |
| `/api/v1/workspaces/{id}/knowledge` | POST | Create new entry |

**Bulk confirm:** No bulk endpoint exists. The status change is per-entry via
`PUT /knowledge/{id}/status`. Bulk confirm requires either:
(a) N sequential API calls from the frontend (simple, works now), or
(b) a new `POST /api/v1/knowledge/bulk-status` endpoint (better for 100+ entries).

Option (a) is sufficient for 77.5. The frontend loops over visible entries.

### Billing

| Endpoint | Method | Response shape |
|----------|--------|---------------|
| `/api/v1/billing/status` | GET | `{period_start, period_end, input_tokens, output_tokens, reasoning_tokens, cache_read_tokens, total_tokens, total_cost, event_count, by_model: {}, computed_fee}` |

Response verified live -- currently all zeros (no TokensConsumed events in
this data root). The shape is sufficient for a billing card.

### Queen context budget

| Endpoint | Method | Response shape |
|----------|--------|---------------|
| `/api/v1/queen-budget` | GET | `{slots: [{name, fraction, fallback_tokens}]}` |

**Static only.** Returns allocation fractions, not runtime consumption.

## 2.5. Context Budget: The Real Problem

### What the operator saw

Despite an 80k context window, "only half was usable."

### Root cause: llama.cpp parallel slots

`docker-compose.yml:228` runs `-np ${LLM_SLOTS:-2}` with
`--ctx-size ${LLM_CONTEXT_SIZE:-80000}`. llama.cpp divides the context
window evenly across slots: **80000 / 2 = 40,000 tokens per slot**.

The budget system computes proportions of the raw `context_window` from
the model registry (80000), but the LLM server physically limits each
inference slot to 40k tokens. So the budget allocates 19,735 tokens for
conversation_history (26% of 75904), but the *actual* ceiling is the
per-slot limit, not the budget slot.

### The budget is a cap, not a reservation

Critical insight: the budget system uses `[:budget.X * 4]` truncation
(chars) at each injection site. It does NOT reserve empty space. If a
slot has 200 tokens of content with a 10,626 token cap, only 200 tokens
are sent to the LLM. The "waste" isn't real waste — it's unused capacity.

### Actual math at runtime

```
Model context window:   80,000 tokens
LLM slots (-np):        2
Per-slot ceiling:        40,000 tokens (80000 / 2)
Output reserve:          4,096 tokens (caste max_tokens)
Available for input:     35,904 tokens per slot

Budget computed from:    75,904 tokens (80000 - 4096)  ← WRONG
Should compute from:     35,904 tokens (40000 - 4096)  ← CORRECT

Typical actual fill:     ~12,800 tokens (early conversation)
                         ~25,000 tokens (deep conversation)
```

The budget math is harmless for early conversations (content is small
enough that caps don't bind). But for deep conversations, the system
allocates 19,735 tokens to conversation_history (26% of 75,904) while
the per-slot ceiling is only 35,904 total. If history plus other content
exceeds 35,904, the LLM server truncates silently with no warning.

### Fix needed

`compute_queen_budget()` should use `effective_context = ctx_size / slots`
instead of the raw model context window. Two options to get slot count:

1. **ENV-based:** Read `LLM_SLOTS` env var in the budget module (already
   accessible — the adapter reads it at `llm_openai_compatible.py:58`)
2. **API-based:** Query llama.cpp `GET /props` at startup to get
   `total_slots` (more accurate, handles non-local models)

Cloud models have 1 slot (no sharing), so `effective_context = context_window`.
Only local llama.cpp models need the division.

### Slot configuration trade-offs (Qwen3.5-35B-A3B Q4_K_M, RTX 5090 32GB)

| Config | Ctx/Slot | VRAM | Use case |
|--------|----------|------|----------|
| `-np 1 --ctx-size 65536` | 65k | ~23GB | Deep single-worker |
| `-np 2 --ctx-size 65536` | 32k each | ~25GB | Parallel colonies |
| `-np 2 --ctx-size 131072` | 65k each | ~30GB | Parallel + deep |
| `-np 1 --ctx-size 262144` | 262k | ~27GB | Max context solo |

Default for FormicOS colony model: **2 slots** (Queen + 1 colony in
parallel). Colony tasks are decomposed into focused subtasks that rarely
need >20k context. The Queen needs more (conversation + knowledge +
system prompt) but shares slot time.

### What the budget viz should show

The headline should be the **effective per-slot context**, not the raw
model capacity:

```
Context per slot: 40,000  |  Output reserve: 4,096  |  Available: 35,904
Content: 12,800 / 35,904 (35.6%)  |  Slots: 2
```

Per-slot bars show allocated cap vs actual content. The operator sees
that conversation_history has a 9,335 token cap (26% of 35,904) but
currently holds 4,000 tokens. If the conversation grows past 9,335
tokens, the cap truncates — visible in the viz as a full red bar.

## 3. Embedding Adapter Audit

### Current state

The Qwen3Embedder (`adapters/embedding_qwen3.py`) already supports asymmetric
embedding via `is_query: bool = False` parameter:

```python
async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
```

- `is_query=True`: prepends instruction prefix + "Query:{text}<|endoftext|>"
- `is_query=False`: uses "{text}<|endoftext|>" only
- L2-normalized output

**Call sites in vector_qdrant.py:**
- Upsert (documents): `_embed_texts(texts, is_query=False)` -- line 230
- Search (queries): `_embed_texts([query], is_query=True)` -- lines 353, 394

### Legacy sentence-transformers path

The `_build_embed_fn()` fallback in `app.py:112-139` returns a sync function
with signature `(texts: list[str]) -> list[list[float]]`. **No is_query
parameter.** The `_embed_texts` wrapper in `vector_qdrant.py:90-101` passes
`is_query` to the async client but drops it for the sync fallback.

**Plan correction:** The plan says "add asymmetric embedding" as new work, but
the Qwen3Embedder path already has it. What's actually needed for nomic is:
1. Update the legacy `embed_fn` path to accept `is_query` and prepend
   `"search_query: "` / `"search_document: "` prefixes
2. OR wrap nomic in a SentenceTransformer with `prompt_name` parameter
   (sentence-transformers supports this natively for nomic)

### Qdrant dimension handling

Collection created in `vector_qdrant.py:114-141` with `vector_dimensions`
from settings. **No auto-rebuild on mismatch.** Dimension change requires:
```bash
docker volume rm formicosa_qdrant-data
docker compose up -d
```

Knowledge entries replay from SQLite events and re-embed on startup.

## 4. LLM Adapter Audit

### Current state (`adapters/llm_openai_compatible.py`)

```python
async def complete(
    self, model, messages, tools=None, temperature=0.0,
    max_tokens=4096, tool_choice=None,
) -> LLMResponse:
```

Payload construction (lines 240-249):
```python
payload = {"model": ..., "messages": ..., "max_tokens": ..., "temperature": ...}
if tools: payload["tools"] = ...
if tool_choice: payload["tool_choice"] = ...
```

**No `extra_body` support.** The adapter sends exactly these fields to
`/chat/completions`. Per-request thinking mode control requires adding
an `extra_body: dict | None` parameter that merges into the payload.

### Per-caste parameter flow

1. Caste recipe defines `temperature`, `max_tokens`
2. Queen runtime / colony runner reads these from caste config
3. Passes to `complete()` as explicit parameters
4. Adapter has zero knowledge of calling caste

**Gap:** No mechanism to pass `chat_template_kwargs` per-request. The
llama.cpp OpenAI-compatible API does support extra fields in the request
body, but the real contract boundary is wider than one adapter:
- `core/ports.py` does not expose an `extra_body` parameter
- `surface/runtime.py` does not accept/forward it
- `CasteRecipe` in `core/types.py` has no `thinking` field
- `runner.py` cannot safely pass it until those seams exist
- If `LLMPort` changes, `llm_anthropic.py` and `llm_gemini.py` must accept
  and ignore the new optional parameter for protocol conformance

### Caste recipes (`config/caste_recipes.yaml`)

Available fields per caste: `name`, `description`, `system_prompt`,
`temperature`, `max_tokens`, `tools`, `max_iterations`,
`max_execution_time_s`, `base_tool_calls_per_iteration`.

**No `model_params` or `extra` field.** Adding a `thinking: bool` field
per caste and threading it through the adapter is the cleanest path.

## 5. Knowledge Base Findings

### Embedding models (3 relevant entries)

**"nomic-embed-text-v1.5: Optimal CPU Embedding for Technical Knowledge Retrieval"** (score 0.519)
- 137M params, 768-dim, MTEB ~62.3, 8192-token context
- Matryoshka support (truncatable to 256/512/768)
- Instruction prefixes: `"search_query: "` / `"search_document: "`
- Requires `trust_remote_code=True`
- CPU: ~40-80ms/query

**"Instruction-Prefixed Embeddings: Asymmetric Query-Document Optimization"** (score 0.432)
- Asymmetric prefixes improve retrieval quality for agent queries vs stored knowledge
- Models without prefix support get reduced cosine similarity

**"Embedding Model Migration: Breaking Changes and Strategies"**
- Dimension change invalidates all vectors
- Delete-and-rebuild simplest for <10K entries

### Thinking mode management (3 relevant entries)

**"Thinking Mode Management for Tool-Calling Agent Systems (Qwen3.5)"** (score 0.645)
- `<think>` tags break ReAct stopword parsing and tool call extraction
- Per-caste strategy: coder OFF (temp 0.6), reviewer ON (temp 0.3), researcher ON (temp 0.7)
- Control via `chat_template_kwargs` per-request, not globally
- Qwen3.5 sampling: temp=0.6, top_p=0.95, top_k=20, min_p=0.0

**"Per-Caste Thinking Mode Control"** (score 0.591)
- Same caste mapping confirmed independently
- Router/archivist OFF (fast dispatch, low cost)

**"Reasoning Mode Taxonomy"** (score 0.639)
- Qwen3/3.5 = "Controllable" family (toggle per-request)
- Prompts not portable across model families

### Context budget (2 relevant entries)

**"Context Window Budget Allocation for Production Agent Systems"** (score 0.638)
- Rule of thumb: system 20-30%, knowledge 15-25%, history 15-25%, tools 20-30%, generation 10-20%
- Avoid last 20% of context for memory-intensive tasks
- FormicOS 10-slot system documented

## 6. Plan Corrections

### C1 (Embedding): Less work than described

The plan describes adding asymmetric embedding as new infrastructure. But
`embedding_qwen3.py` already has `is_query` support, and `vector_qdrant.py`
already calls it correctly. The real work is:

1. Config changes (model name, dimensions) -- trivial
2. `_build_embed_fn()`: add `trust_remote_code=True` + prefix injection
   for the sentence-transformers path
3. Update `_embed_texts()` in vector_qdrant.py to pass `is_query` to the
   sync fallback path (currently dropped)

### C3 (Thinking mode): Runtime-path gap is real

The adapter genuinely lacks `extra_body` support. The fix is broader than one adapter:
- Add `extra_body: dict[str, object] | None = None` to `complete()`
- Merge into payload before POST
- Add `thinking: bool` field to caste_recipes.yaml
- Extend `surface/runtime.py` to accept/forward it
- Add `thinking: bool = False` to `CasteRecipe` in `core/types.py`
- Forward `extra_body` only for local `llama-cpp/` models
- Mirror the optional parameter on Anthropic/Gemini adapters and ignore it
- Thread through runner → adapter

### Team A: Need new API endpoints

The workspace browser overhaul needs:
- `PUT /api/v1/project-plan` (or PUT on the files endpoint with the plan path)
- `GET /api/v1/workspaces/{id}/working-memory` (read-only tree of runtime/)
- `GET/PUT /api/v1/workspaces/{id}/project-context` because the current
  frontend save path targets a nonexistent generic file PUT seam

### Team B: Bulk confirm is frontend-only

No new backend endpoint needed. The frontend can loop over visible entries
calling `PUT /knowledge/{id}/status` with `{status: "verified"}`. A progress
bar and error summary handle the UX.

**UI caveat:** search-first results render through `knowledge-search-results.ts`,
not just `knowledge-browser.ts`, so scoring polish there needs ownership of
that component too.

### Context budget: TWO fixes needed

**Fix 1 (Critical): Slot-aware budget computation**

`compute_queen_budget()` currently takes `context_window` from the model
registry (80000 for llama-cpp/gpt-4). But the LLM server runs with
`-np 2`, dividing KV cache into 2 × 40k slots. The budget should compute
against `effective_context = context_window / num_slots`, not raw capacity.

Implementation: `compute_queen_budget()` gains a `num_slots: int = 1`
parameter. The caller (`queen_runtime.py:940`) reads `LLM_SLOTS` from
env (for local models) or defaults to 1 (for cloud models). Budget
computation uses `context_window // num_slots - output_reserve` as the
available pool.

This changes the allocated numbers significantly:

```
Before (80k raw):  conversation_history = max(6000, 75904 * 0.26) = 19,735
After  (40k/slot): conversation_history = max(6000, 35904 * 0.26) =  9,335
```

Proportional allocations shrink but still exceed fallback floors (which
were designed for 17k total — fallbacks sum to 17,000 tokens). The system
continues to work correctly at smaller effective contexts.

**Fix 2 (Transparency): Per-turn consumption tracking**

After `_build_messages()` completes in `queen_runtime.py`, count actual
tokens per injected section using `len(content) // _CHARS_PER_TOKEN`.
Store as `self._last_budget_usage_by_workspace[workspace_id]`, not a single
global `self._last_budget_usage`.

Expose via enhanced `GET /api/v1/queen-budget`:

```json
{
  "context_window": 80000,
  "num_slots": 2,
  "effective_context": 40000,
  "output_reserve": 4096,
  "available": 35904,
  "slots": [
    {"name": "system_prompt", "fraction": 0.14,
     "allocated": 5026, "fallback": 2000,
     "consumed": 3200, "utilization": 0.64}
  ],
  "total_consumed": 12800,
  "total_utilization": 0.356
}
```

Frontend `fc-queen-budget-viz` shows:
- Headline: effective context, output reserve, total utilization
- Number of LLM slots and per-slot ceiling
- Per-slot: outer bar = cap, inner bar = actual fill
- Slots at >90% utilization get warning highlight (bottleneck)

## 7. Queen Overrides JSON Audit

`queen-overrides.ts` (294 lines) has 4 sections:

1. **Disabled Tools** (lines 202-227): Checkbox grid. No JSON. Good UX.
2. **Custom Rules** (lines 230-247): Free-text textarea. No JSON. Good UX.
3. **Team Composition** (lines 250-267): Raw JSON textarea. Bad UX.
   - Placeholder: `{"code_simple": "coder / sequential", ...}`
   - Validation: `JSON.parse()` with "Invalid JSON" error (no guidance)
   - Saves via `_emitConfig('queen.team_composition', json_string)`
4. **Round Budget** (lines 270-287): Raw JSON textarea. Bad UX.
   - Placeholder: `{"simple": {"rounds": 4, "budget": 1.5}, ...}`
   - Same parse/error pattern

**Other JSON textareas in the frontend:** `addons-view.ts:434` has a
generic JSON textarea for addon config fields typed as `array` or `object`.
This is a developer-facing addon config surface, not the primary operator
path. Lower priority fix.

The `_emitConfig()` method (line 135) dispatches `update-config` custom
event, consumed by the parent component to call
`POST /api/v1/workspaces/{id}/config-overrides`.

**Load path:** `_loadFromConfig()` (lines 100-133) parses existing JSON
back into state. The structured form builder must replicate this
bidirectional parse (JSON string → structured state for editing, and
structured state → JSON string for saving).

## 8. Hybrid Routing Verification

The per-caste env var routing (`QUEEN_MODEL`, `CODER_MODEL`, etc.) is
already wired from Wave 77 Track A in `config/formicos.yaml:29-34`.
Hybrid routing (Queen on cloud, colonies on local) works by setting:

```bash
QUEEN_MODEL=anthropic/claude-sonnet-4-6
CODER_MODEL=llama-cpp/qwen3.5-35b
```

When Queen is on cloud (`anthropic/claude-sonnet-4-6`), the budget
reads `context_window: 200000` from the registry. The `LLM_SLOTS`
division should NOT apply — cloud APIs serve one request at a time
with full context. The fix in `queen_runtime.py` must only divide
for `llama-cpp/` model addresses.

The `.env.example` currently documents only two profiles (all-cloud,
all-local). A hybrid profile needs to be added.

## 9. Shared File Conflicts

| File | Team A | Team B | Team C |
|------|--------|--------|--------|
| config/formicos.yaml | -- | -- | C1, C2 |
| docker-compose.yml | -- | -- | C2 |
| formicos-app.ts | A2 (workspace tab) | B3 (billing import) | -- |
| routes/api.py | A1 (plan PUT) | B1 (verify bulk pattern) | -- |
| app.py | -- | -- | C1 (embed_fn) |
| queen_budget.py | A4 (slot-aware budget) | -- | -- |
| queen_runtime.py | A4 (consumption tracking) | -- | -- |

**Conflict risk:** `formicos-app.ts` touched by both A and B. Coordinate:
A adds workspace structured sections, B adds billing card import. Both are
additive (different tabs), low conflict.

**Budget viz** is a separate track orthogonal to A/B/C. Can be done by any
team or as a 4th mini-track.
