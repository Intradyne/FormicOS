# Wave 2 Summary

**Completed:** 2026-03-12
**CI status:** All green (ruff, pyright strict, layer lint, 113 tests)

## Pre-dispatch fixes applied

1. **ModelRecord.status** expanded from `Literal["available", "disabled", "error"]` to `Literal["available", "unavailable", "no_key", "loaded", "error"]` — aligned with types.ts contract.
2. **CasteRecipe.description** added as `str = Field(default="")` — YAML has it on every caste.
3. **ColonyContext.pheromone_weights** — added serialization comment documenting the tuple-key to string-key conversion needed for JSON.

## What shipped

### Stream B — SQLite Event Store + LanceDB Vector (316 LOC)
- `adapters/store_sqlite.py` (150 LOC) — `SqliteEventStore`:
  - WAL journal mode, lazy connection, schema auto-creation
  - `append()` extracts envelope fields (type, timestamp, address, trace_id) plus full JSON payload
  - `query()` with parameterized SQL, address prefix LIKE, event_type filter
  - `replay()` async generator in seq order
  - `checkpoint()` and `close()` lifecycle
- `adapters/vector_lancedb.py` (166 LOC) — `LanceDBVectorStore`:
  - Sync lancedb API wrapped in `asyncio.to_thread()`
  - Caller-injected `embed_fn` (no sentence-transformers loaded inside adapter)
  - `upsert()` creates table on first use, delete-then-add for overwrites
  - `search()` embeds query, vector search, returns VectorSearchHit
  - `delete()` by id filter with count

### Stream C — LLM Adapters (386 LOC)
- `adapters/llm_anthropic.py` (193 LOC) — `AnthropicLLMAdapter`:
  - httpx async client, Messages API
  - Tool use: Anthropic schema format, parses tool_use blocks
  - SSE streaming via `aiter_lines()`
  - Retry on 429/529 with exponential backoff (1s/2s/4s, 3 attempts)
- `adapters/llm_openai_compatible.py` (193 LOC) — `OpenAICompatibleLLMAdapter`:
  - chat/completions endpoint, OpenAI function-calling format
  - Optional auth header (omitted for local models)
  - Same retry pattern (429 only)
  - Configurable base_url (default Ollama)

### Stream E — Engine Runner + Strategies (725 LOC)
- `engine/context.py` (114 LOC):
  - `assemble_context()` builds message list in priority order (§4)
  - `trim_to_budget()` removes from end, always keeps system prompt
  - `estimate_tokens()` = len(text) // 4
- `engine/runner.py` (400 LOC):
  - `RoundRunner` drives the 5-phase loop (goal, intent, route, execute, compress)
  - `ConvergenceResult`, `GovernanceDecision`, `RoundResult` frozen Pydantic models
  - Dual convergence path: embedding-based (§7) or text-overlap heuristic fallback
  - Governance decisions per §8 (force_halt, warn, complete, continue)
  - Pheromone update per §6 (evaporate → strengthen/weaken → clamp)
  - `_emit_event()` handles both sync and async callbacks
- `engine/strategies/sequential.py` (25 LOC): one agent per group, definition order
- `engine/strategies/stigmergic.py` (186 LOC):
  - DyTopo routing from §2: embed → cosine similarity → pheromone multiply → tau threshold → k_in cap → cycle break → topological sort → parallel groups
  - Uses caste descriptions as fallback descriptors (intent phase skipped in alpha)

## LOC accounting

| Stream | Budget | Actual | Note |
|--------|--------|--------|------|
| B (2 adapter files) | 500 | 316 | Under budget |
| C (2 LLM files) | 450 | 386 | Under budget |
| E (4 engine files) | 700 | 725 | On budget |
| **Total** | **1,650** | **1,427** | 14% under budget |

## Decisions made

1. **Intent phase (Phase 2) skipped in alpha.** Generating query/key descriptors requires an LLM call per agent — expensive and slow. The stigmergic strategy uses caste descriptions as fallback descriptors instead. Full descriptor generation deferred to Wave 4+ optimization.

2. **Convergence scoring has dual path.** If `embed_fn` is provided to RoundRunner, it uses the full embedding-based convergence formula from §7. Otherwise, it falls back to a text-overlap heuristic. This lets the engine run in tests and environments without sentence-transformers.

3. **LanceDB sync API wrapped with asyncio.to_thread.** The lancedb package's async API is incomplete. Wrapping sync calls is the pragmatic alpha approach — profile in Wave 5+ if it becomes a bottleneck.

4. **Embedding function is injected, not loaded.** Both `LanceDBVectorStore` and `StigmergicStrategy` receive an `embed_fn` callable. The surface layer is responsible for loading sentence-transformers and providing the function. This keeps adapters and engine free of heavy ML dependencies.

5. **Extended ruff per-file-ignores.** Added `TCH001`/`TCH003` ignores for all adapter and engine files in pyproject.toml. These files use runtime type annotations in function signatures with `from __future__ import annotations`.

## Issues for Wave 3

- **Surface wiring not implemented.** The adapters and engine are built but not wired together. Wave 3's surface layer must: instantiate adapters, load sentence-transformers, inject embed_fn, create RoundRunner with emit callback.
- **Provider routing (`route_model_to_adapter`)** per §11 is not yet implemented. Surface layer needs a dispatcher mapping provider prefixes to adapter instances.
- **Event address format convention.** The event store uses address prefix matching for queries. Wave 3 must establish consistent address formatting (e.g., `workspace_id/thread_id/colony_id`).
- **Merge resolution (`resolve_merged_context`)** is referenced in context assembly but not fully implemented. The context module has a placeholder for `merged_summaries` parameter — callers must provide it.
- **Skill extraction (`extract_skills`)** is referenced in algorithms.md but not implemented. Currently a no-op.
- **Colony lifecycle management.** The runner executes individual rounds but doesn't manage the multi-round loop, colony state, or scheduling. That's colony orchestrator territory (Wave 3+).
