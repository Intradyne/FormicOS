# Wave 10 Dispatch — "Real Infrastructure"

**Date:** 2026-03-14
**Status:** Draft — pending orchestrator review
**Depends on:** Wave 9 complete and validated (579 tests, 24 hard gates + 1 advisory)
**Exit gate:** `docker compose build && docker compose up`, spawn a colony with mixed
castes, verify: Qdrant serves skill retrieval (not LanceDB), Gemini adapter handles
researcher/archivist routing, defensive parser recovers from malformed tool calls,
skill browser renders in frontend with confidence bars and sort controls.
Full `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest` green.
`cd frontend && npm run build` clean.

---

## Read Order (mandatory before writing any code)

1. `CLAUDE.md` — project rules (esp. Rule 3: no new deps without justification, Rule 5: event union closed)
2. `AGENTS.md` — ownership and coordination for THIS wave (updated below)
3. `docs/decisions/001-event-sourcing.md` — single mutation path
4. `docs/decisions/005-mcp-sole-api.md` — MCP vs WS boundary
5. `docs/decisions/007-agent-tool-system.md` — tool loop design
6. `docs/decisions/010-skill-crystallization.md` — learning loop, confidence evolution
7. `docs/decisions/012-compute-router.md` — routing architecture from W9
8. `docs/decisions/013-qdrant-migration.md` — **NEW — write before coding starts**
9. `docs/decisions/014-gemini-provider.md` — **NEW — write before coding starts**
10. `docs/contracts/events.py` — 22-event union (**DO NOT MODIFY**)
11. `docs/contracts/ports.py` — 5 port interfaces (**DO NOT MODIFY**)
12. `docs/waves/wave_09/plan.md` — predecessor wave (what you're building on)
13. Current implementations you will modify (see your terminal's file list below)

---

## Scope Locks — 3 Terminals

| Terminal | Owns (may modify) | Does NOT touch |
|----------|-------------------|----------------|
| **T1 — Qdrant Migration** | new `adapters/vector_qdrant.py`, `surface/app.py` (VectorPort wiring block only), `config/formicos.yaml` (vector section only), new `scripts/migrate_lancedb_to_qdrant.py`, tests for these | `core/*`, `docs/contracts/*`, `engine/*`, `frontend/*`, `surface/runtime.py`, `surface/skill_lifecycle.py`, `surface/colony_manager.py`, `adapters/llm_*.py` |
| **T2 — Gemini + Output Hardening** | new `adapters/llm_gemini.py`, new `adapters/parse_defensive.py`, `adapters/llm_openai_compatible.py` (tool-call parsing only), `adapters/llm_anthropic.py` (tool-call parsing only), `surface/runtime.py` (adapter factory + fallback wiring), `config/formicos.yaml` (routing + model registry sections only), tests for these | `core/*`, `docs/contracts/*`, `engine/runner.py`, `engine/context.py`, `frontend/*`, `adapters/vector_*.py`, `surface/colony_manager.py`, `surface/skill_lifecycle.py` |
| **T3 — Skill Browser + Frontend** | new `frontend/src/components/skill-browser.ts`, `frontend/src/components/queen-overview.ts`, `frontend/src/components/colony-detail.ts`, `frontend/src/types.ts`, `surface/view_state.py` (skill detail endpoint function only), new REST route in `surface/app.py` (skill endpoint only — coordinate with T1 on app.py), tests for these | `core/*`, `docs/contracts/*`, `engine/*`, `adapters/*`, `surface/runtime.py`, `surface/colony_manager.py`, `surface/skill_lifecycle.py` |

**Merge order: T1 first, T2 second, T3 last.**

T1 first because the Qdrant adapter validates the VectorPort contract that all skill
operations depend on. If anything is subtly wrong in the port mapping, we catch it
before adding more moving parts.

T2 is independent of T1 (different adapter files, no shared code) but merges second
for sequencing discipline.

T3 merges last because it surfaces data produced by T1 (skill bank via Qdrant) and
T2 (Gemini routing decisions).

### app.py coordination (T1 + T3)

Both T1 and T3 modify `surface/app.py`. Their changes are in different sections:
- T1 modifies the VectorPort construction block (replacing LanceDB with Qdrant based on config flag)
- T3 adds a REST route for `GET /api/v1/skills`

T1 merges first. T3 must rebase onto T1's changes before adding the route. The sections
do not overlap — T1 touches adapter wiring in the lifespan function, T3 adds a route
to the Starlette app.

### Critical reminders (all terminals)

- **No contract changes.** The 22-event union stays frozen. The 5 port interfaces stay frozen.
- **New dependencies (justified):** `qdrant-client>=1.16` (T1), `json-repair>=0.30` (T2). Both require operator approval per Rule 3. Approval is granted by this plan.
- **No hidden mutable state.** Every new datum has documented provenance (see table below).
- **Pydantic v2 only.** structlog only. No print(). Layer boundaries enforced.
- **ADR-013 and ADR-014 must be read before coding starts.**

---

## Data Provenance Table

Every new datum introduced in Wave 10, with exact source. Coders: if you need data
not listed here, STOP and flag it.

| Datum | Source | Persisted? | Survives restart? |
|-------|--------|-----------|-------------------|
| Skill vectors in Qdrant | Migrated from LanceDB on first run, then upserted by `skill_lifecycle.py` on crystallization | Qdrant named volume | Yes |
| Skill payload fields (confidence, algorithm_version, extracted_at, source_colony, namespace) | Carried from LanceDB metadata, then maintained by `skill_lifecycle.py` | Qdrant point payloads | Yes |
| Qdrant collection config (dimensions, distance, indexes) | Created by `ensure_collection()` on startup | Qdrant storage | Yes |
| Gemini API responses | Parsed by `GeminiAdapter` into normalized `LLMResponse` | Not persisted | No |
| Defensive parse stage used | structlog field `parse_stage` on each tool-call parse | Runtime log only | No |
| Fallback chain traversal | structlog fields `fallback_triggered`, `fallback_from` | Runtime log only | No |
| Gemini thinking tokens | `usageMetadata.thoughtsTokenCount` from Gemini response, surfaced in `LLMResponse` | Not persisted | No |
| Skill bank detail list | Qdrant `scroll()` or broad search, fetched on-demand by REST endpoint | Not cached | N/A |
| Vector backend selection | `config.vector.backend` read at startup | Config file | Yes |

---

## T1 — Qdrant Migration

### Goal

Replace LanceDB with Qdrant behind the existing `VectorPort` interface. Qdrant is
already running in docker-compose. This is an adapter swap — the engine never knows.

### ADR prerequisite: Read ADR-013 before starting.

### What changes

**1. New file: `adapters/vector_qdrant.py`** (~250 LOC)

Implements `VectorPort` protocol using `qdrant-client` v1.16+ async API.

Key mapping (from ADR-013):
- `VectorPort.search(collection, query, top_k)` → embed `query` via `embed_fn`, then `client.query_points(collection, query=vector, limit=top_k, with_payload=True)`
- `VectorPort.upsert(collection, docs)` → embed each doc's content via `embed_fn`, then `client.upsert(collection, points=[PointStruct(...)])`
- `VectorPort.delete(collection, ids)` → `client.delete(collection, points_selector=PointIdsList(points=ids))`

Constructor receives:
- `url: str` — Qdrant endpoint (default `http://qdrant:6333`)
- `embed_fn: Callable[[list[str]], list[list[float]]]` — same injection pattern as LanceDB adapter
- `prefer_grpc: bool = True` — gRPC is faster for batch uploads

The adapter calls `ensure_collection()` lazily on first operation. Collection creation
is idempotent. Payload indexes are created alongside the collection.

**Embedding dimension:** Read from `config.embedding.dimensions`. Do NOT hardcode 1024.
The current config says 384 (snowflake-arctic-embed-s). If the docker-compose BGE-M3
is active instead, the operator must update the config to 1024. The adapter trusts config.

**Graceful degradation:** All Qdrant operations wrapped in try/except. On connection
failure → return empty results for search, log warning, never crash.

Delegate to 3 parallel sub-agents:
- **Sub-agent A:** Core `QdrantVectorPort` class (~180 LOC) — search, upsert, delete, ensure_collection, connection management, graceful degradation
- **Sub-agent B:** Migration script `scripts/migrate_lancedb_to_qdrant.py` (~80 LOC) — read LanceDB table, convert to Qdrant PointStruct, upload, verify count
- **Sub-agent C:** Wiring in `surface/app.py` + config + tests — read `vector.backend` from config, instantiate `QdrantVectorPort` or `LanceDBVectorPort`, pass to engine. Add `vector` section to `formicos.yaml`.

**2. `config/formicos.yaml`** — Add vector section:

```yaml
vector:
  backend: "qdrant"              # "lancedb" or "qdrant"
  qdrant_url: "${QDRANT_URL:http://localhost:6333}"
  qdrant_prefer_grpc: true
  collection_name: "skill_bank"
```

**3. `pyproject.toml`** — Add dependency:

```toml
"qdrant-client>=1.16",
```

Keep `lancedb` for one more wave behind the feature flag.

### Acceptance criteria

- [ ] `QdrantVectorPort` passes the same behavioral tests as LanceDB adapter
- [ ] `query_points()` used for search (NOT removed `search()` method)
- [ ] Payload indexes created on namespace, confidence, algorithm_version, created_at, source_colony
- [ ] `namespace` field uses `is_tenant=True` indexing
- [ ] Embedding dimension read from config (not hardcoded)
- [ ] `embed_fn` injected at construction (same pattern as LanceDB adapter)
- [ ] Migration script transfers all LanceDB data with zero re-embedding
- [ ] Migration script verifies point count matches source
- [ ] Feature flag `vector.backend` switches adapter at startup
- [ ] Graceful degradation: Qdrant down → empty results, structlog warning, no crash
- [ ] Skill lifecycle functions (confidence update, dedup gate, ingestion) work unchanged
- [ ] All 579+ existing tests pass with `VECTOR_BACKEND=qdrant`
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/adapters/test_vector_qdrant.py` — search, upsert, delete, ensure_collection idempotency, graceful degradation on connection failure, namespace isolation
- `tests/unit/adapters/test_vector_qdrant_filters.py` — confidence range, source_colony exclusion, datetime range, combined filters (mock Qdrant client)
- `tests/integration/test_lancedb_migration.py` — seed LanceDB → run script → verify Qdrant data matches

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## T2 — Gemini Adapter + Structured Output Hardening

### Goal

Add Gemini as a third LLM provider. Harden tool-call parsing across all three
providers. Extend the routing table with Gemini entries.

### ADR prerequisite: Read ADR-014 before starting.

### What changes

**1. New file: `adapters/llm_gemini.py`** (~300 LOC)

Implements `LLMPort` protocol via raw `httpx.AsyncClient` to Gemini generateContent API.

Key implementation points (from ADR-014):
- Endpoint: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- Auth: `x-goog-api-key` header from `GEMINI_API_KEY` env var
- Role mapping: `"assistant"` → `"model"` in Gemini format
- Tool call detection: check for `functionCall` in parts (NOT `finishReason`)
- `thoughtSignature` preservation: stash on ToolCall, round-trip through message conversion
- `functionCall.args` is already a JSON object (unlike OpenAI which returns a string)
- Safety settings: `BLOCK_ONLY_HIGH` for code-heavy workloads
- Retry: exponential backoff on 429/500/503. Do NOT retry RECITATION/SAFETY blocks.
- Streaming: `?alt=sse` endpoint, `data:` lines with full response JSON per chunk

**Thinking budget:** Accept `thinking_budget: int | None` kwarg. Set `thinkingBudget: 0`
on Flash for simple tasks to avoid hidden thinking token costs ($2.50/M at output rate).
Pass through to `generationConfig.thinkingConfig`.

Delegate to 3 parallel sub-agents:
- **Sub-agent A:** `GeminiAdapter` class — complete(), stream(), close(), request building, response parsing, retry logic (~300 LOC)
- **Sub-agent B:** `parse_defensive.py` — 3-stage defensive tool-call parser (~150 LOC)
- **Sub-agent C:** Adapter factory extension in `runtime.py` + routing table update in `formicos.yaml` + fallback chain wiring + integration tests

**2. New file: `adapters/parse_defensive.py`** (~150 LOC)

Three-stage defensive tool-call parser. Applied to every LLM response expecting tool calls.

- **Stage 1:** `json.loads()` — clean JSON fast path
- **Stage 2:** `json_repair.loads()` — trailing commas, missing quotes, truncation
- **Stage 3:** Regex — strip `<think>` tags, extract from markdown fences, find bare JSON objects

Additional normalization:
- Fuzzy-match hallucinated tool names: `difflib.get_close_matches(name, known_tools, cutoff=0.6)`
- Handle args-as-string: `isinstance(args, str)` → `json.loads(args)` → `json_repair.loads(args)`
- Normalize diverse JSON shapes: `{name, arguments}`, `{function_call: {…}}`, `[{…}]`, `{tool_calls: [{…}]}`

Public API:
```python
def parse_tool_calls_defensive(
    text: str,
    known_tools: set[str] | None = None,
) -> list[ToolCall]:
    """Parse tool calls with 3-stage fallback. Returns empty list on total failure."""
```

**3. Harden existing adapters.**

In `adapters/llm_openai_compatible.py` and `adapters/llm_anthropic.py`, replace bare
`json.loads()` on tool-call arguments with `parse_tool_calls_defensive()`. This is a
surgical change — find the tool-call parsing code, wrap it with the defensive pipeline.

For the OpenAI-compatible adapter specifically: `tool_calls[].function.arguments` is a
JSON **string** that must be parsed. This is where Qwen3's malformed JSON breaks today.
The defensive parser fixes it.

For the Anthropic adapter: `content[].input` is already a JSON **object** but the
defensive parser still validates structure and catches edge cases (truncated tool_use
at max_tokens).

**4. `surface/runtime.py`** — Adapter factory extension:

```python
elif model_address.startswith("gemini/"):
    return gemini_adapter
```

Add fallback chain support: when `complete()` returns `finish_reason == "blocked"`,
try the fallback model from the routing entry. This is ~20 lines in the existing
`_resolve_adapter_and_call()` or equivalent method.

**5. `config/formicos.yaml`** — Routing table + model registry:

```yaml
routing:
  model_routing:
    execute:
      queen: "anthropic/claude-sonnet-4.6"
      coder: "anthropic/claude-sonnet-4.6"
      reviewer: "llama-cpp/gpt-4"
      researcher: "gemini/gemini-2.5-flash"     # was llama-cpp
      archivist: "gemini/gemini-2.5-flash"      # was llama-cpp
    goal:
      queen: "anthropic/claude-sonnet-4.6"

models:
  registry:
    # ... existing entries unchanged ...
    - address: "gemini/gemini-2.5-flash"
      endpoint: "https://generativelanguage.googleapis.com/v1beta"
      api_key_env: "GEMINI_API_KEY"
      context_window: 1000000
      supports_tools: true
      supports_vision: true
      cost_per_input_token: 0.0000003     # $0.30 per 1M
      cost_per_output_token: 0.0000025    # $2.50 per 1M

    - address: "gemini/gemini-2.5-flash-lite"
      endpoint: "https://generativelanguage.googleapis.com/v1beta"
      api_key_env: "GEMINI_API_KEY"
      context_window: 1000000
      supports_tools: true
      supports_vision: false
      cost_per_input_token: 0.0000001     # $0.10 per 1M
      cost_per_output_token: 0.0000004    # $0.40 per 1M
```

**6. `pyproject.toml`** — Add dependency:

```toml
"json-repair>=0.30",
```

### Acceptance criteria

- [ ] `GeminiAdapter.complete()` returns normalized `LLMResponse` for text and tool calls
- [ ] `GeminiAdapter.stream()` yields chunks with text accumulation
- [ ] Tool calls detected via `functionCall` in parts (not via `finishReason`)
- [ ] `thoughtSignature` preserved on round-trip
- [ ] `RECITATION` and `SAFETY` blocks surface as `finish_reason: "blocked"`
- [ ] Retry with backoff on 429/500/503
- [ ] `parse_tool_calls_defensive()` recovers from: trailing commas, markdown fences, `<think>` tags, string-args bug, hallucinated tool names
- [ ] All three adapters use `parse_tool_calls_defensive()` for tool-call parsing
- [ ] Adapter factory routes `gemini/` prefix to GeminiAdapter
- [ ] Routing table includes Gemini entries for researcher and archivist
- [ ] Model registry includes gemini-flash and gemini-flash-lite with cost rates
- [ ] Fallback chain: blocked → next model in chain
- [ ] structlog entries include: `provider`, `parse_stage`, `fallback_triggered`, `thinking_tokens`
- [ ] All 579+ existing tests pass (tool-call parsing must not break existing flows)
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/adapters/test_gemini_adapter.py` — text completion, tool call round-trip, streaming, RECITATION block, 429 retry, thinking token counting. Use `respx` or `unittest.mock.AsyncMock` for httpx mocking.
- `tests/unit/adapters/test_parse_defensive.py` — Stage 1/2/3 progression, trailing comma, markdown fence, `<think>` tags, string-args, hallucinated tool name fuzzy match, unknown tool rejection
- `tests/unit/adapters/test_adapter_factory.py` — prefix routing for all three providers
- `tests/unit/surface/test_router_fallback.py` — blocked response triggers fallback, budget gate forces cheapest

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## T3 — Skill Browser + Frontend Polish

### Goal

Surface the skill bank as a browsable, filterable component. Polish routing
visualization for three providers. Fix the colony creation navigation gap.

### Depends on: T1 + T2 merged

### What changes — Backend

**1. `surface/view_state.py`** — Add skill detail function:

```python
async def get_skill_bank_detail(
    vector_port: VectorPort,
    namespace: str | None = None,
    sort_by: str = "confidence",   # "confidence" | "freshness"
    limit: int = 50,
) -> list[dict]:
    """Fetch skills with full metadata for the skill browser.

    Returns list of: {id, text_preview, confidence, algorithm_version,
                      extracted_at, source_colony}

    Uses VectorPort.search() with a broad query to retrieve entries,
    then sorts application-side by the requested field.
    """
```

**2. `surface/app.py`** — Add REST endpoint (T3's section, after T1's VectorPort wiring):

```python
@app.route("/api/v1/skills")
async def get_skills(request):
    sort_by = request.query_params.get("sort", "confidence")
    limit = int(request.query_params.get("limit", "50"))
    skills = await get_skill_bank_detail(app.state.vector_port, sort_by=sort_by, limit=limit)
    return JSONResponse(skills)
```

### What changes — Frontend

Delegate to 3 parallel sub-agents:

**Sub-agent A — Skill browser component** (`frontend/src/components/skill-browser.ts`, new, ~200 LOC)

- Fetches from `GET /api/v1/skills` on mount
- Table/card layout: skill text preview (first 100 chars), confidence bar (red < 0.3, amber 0.3–0.6, green > 0.6), source colony, age (relative time from extracted_at), algorithm version badge
- Sort controls: confidence (default), freshness
- Filter: minimum confidence threshold slider
- Empty state: "No skills yet. Complete a colony to start building the skill bank."
- Auto-refresh on WebSocket colony completion events
- Mount location: Queen Overview tab, collapsible panel or "Skills" sub-section

**Sub-agent B — Routing visualization** (modify existing, ~100 LOC)

`colony-detail.ts`:
- Model column gets colored prefix: green dot (local/llama-cpp), blue dot (gemini), amber dot (anthropic)
- Routing summary line above agent table: "3 local, 2 Gemini Flash, 1 Claude Sonnet"

`queen-overview.ts`:
- Colony card routing badge shows 3 colors (green/blue/amber) not just mixed/local/cloud
- Tooltip shows model breakdown per caste

**Sub-agent C — Types + colony creation flow** (~100 LOC)

`types.ts`:
- Add `SkillEntry` type: `{ id: string; text_preview: string; confidence: number; algorithm_version: string; extracted_at: string; source_colony: string }`
- Ensure `modelsUsed` handles `gemini/` addresses in provider detection

Colony creation auto-navigation:
- After successful `POST` colony create via WS command, switch to colony detail view
- Brief loading state → tab switch → streaming events start flowing
- This was flagged in research docs as "the single most damaging UX gap"

### Acceptance criteria

- [ ] `GET /api/v1/skills` returns skill list with metadata
- [ ] Skill browser renders skills with colored confidence bars
- [ ] Sort by confidence/freshness works
- [ ] Empty state displayed when no skills exist
- [ ] 3-color routing badges (green/blue/amber) on colony cards
- [ ] Colony detail model column shows provider-colored dots
- [ ] Colony creation auto-navigates to colony detail view
- [ ] TypeScript compiles clean (`npm run build`)
- [ ] No console errors in browser
- [ ] All existing tests pass

### New tests

- `tests/unit/surface/test_skill_endpoint.py` — REST endpoint returns correct shape, respects sort and limit, handles empty collection
- Frontend: `npm run build` + manual browser verification

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build
```

---

## Integration Gate

After all three terminals merge (T1 → T2 → T3):

```bash
# Build and start
docker compose build formicos && docker compose up -d
sleep 15 && curl http://localhost:8080/health

# Test 1: Qdrant serving skill bank
# Verify collection exists:
curl http://localhost:6333/collections/skill_bank
# Should return collection info (points_count >= 0)

# Test 2: Skill lifecycle through Qdrant
# Spawn a colony → skills crystallize → verify in Qdrant:
#   structlog: skill_lifecycle.ingestion_check
#   structlog: skill_lifecycle.confidence_updated

# Test 3: Gemini routing (requires GEMINI_API_KEY)
# Spawn colony with researcher + archivist:
#   structlog: compute_router.route caste=researcher selected=gemini/gemini-2.5-flash
#   structlog: compute_router.route caste=archivist selected=gemini/gemini-2.5-flash
# If no GEMINI_API_KEY: router falls back to cascade default (local)

# Test 4: Defensive parsing
# If local model returns malformed tool JSON:
#   structlog: llm_call parse_stage=2 (or 3)

# Test 5: Fallback chain
# If Gemini returns RECITATION:
#   structlog: provider_blocked_fallback primary=gemini/... fallback=llama-cpp/...

# Test 6: Skill browser (browser test)
# Navigate to Queen Overview → skill browser section
# Verify: skills listed with confidence bars (or empty state if no skills)
# Verify: sort controls work

# Test 7: 3-color routing badges (browser test)
# Colony card → colored routing badge (green/blue/amber)
# Colony detail → model column with colored provider dots

# Test 8: Colony creation navigation (browser test)
# Create colony → auto-navigates to colony detail within 500ms

# Full CI
docker compose exec formicos bash -c \
  "ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest"
cd frontend && npm run build
```

---

## Explicit Deferrals (NOT in Wave 10)

| Deferred | Why | Earliest |
|----------|-----|----------|
| Colony templates | Requires opening 22-event union. Need 3+ real patterns first. | Wave 11 |
| Experimentation engine | Need production routing + skill data. This wave generates it. | Wave 11 |
| `SkillConfidenceTierChanged` event | Requires contract change. Bundle with templates. | Wave 11 |
| Bayesian confidence (Beta distribution) | ±0.1 sufficient at < 100 skills. | Wave 11 |
| LLM-gated dedup (Mem0 pattern) | Need 50+ skills and observed duplicate patterns. | Wave 11 |
| Meta-skill synthesis | Need HDBSCAN clusters of 3+ related skills. | Wave 11+ |
| Remove LanceDB dependency | Keep as fallback this wave. Remove after Qdrant validation. | Wave 11 |
| Qdrant hybrid search (BM25 + dense) | Overkill at < 1K entries. | Wave 12+ |
| Knowledge graph (SQLite adjacency) | No consumer. Flat skill bank covers alpha. | Wave 12+ |
| SGLang inference server | Multi-week infra, orthogonal. | Wave 12+ |
| Dashboard composition | Needs components, A2UI, frontend maturity. | Wave 13+ |

---

## Constraints

1. **No contract changes.** 22-event union frozen. 5 port interfaces frozen.
2. **Two new dependencies:** `qdrant-client>=1.16` (T1), `json-repair>=0.30` (T2).
3. **Pydantic v2 only.** structlog only. No print(). Layer boundaries enforced.
4. **Layer boundaries.** `adapters/` imports only `core/`. `parse_defensive.py` lives in `adapters/`.
5. **No hidden state.** Every datum has documented provenance (see table).
6. **Tests required.** Every behavioral change needs a test.
7. **Merge order: T1 → T2 → T3.**
8. **LanceDB stays in pyproject.toml this wave.** Feature flag controls active backend.
9. **ADR-013 and ADR-014 read before coding starts.**
