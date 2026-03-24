# FormicOS v2 — Audit Handoff Prompt

> Context document for an AI auditor with full filesystem access. Read this first, then investigate the files referenced below.

---

## What This Is

FormicOS is a stigmergic multi-agent colony framework. AI agents coordinate through shared environmental signals (pheromones) rather than direct messaging. Python backend, Lit Web Components frontend, event-sourced, local-first (llama.cpp with Qwen3-30B-A3B) with cloud model support (Anthropic).

**Status:** Alpha — all 391+ tests pass, Docker builds, system boots and runs end-to-end, but there are known runtime issues with the Queen chat flow and small model support.

---

## Architecture (4 layers, strict inward dependency)

```
Core    → types, events (22-event closed union), port interfaces. Imports NOTHING.
Engine  → colony execution (runner, strategies). Imports only Core.
Adapters → LLM (Anthropic, OpenAI-compatible), SQLite, LanceDB. Import only Core.
Surface → HTTP/WS/MCP wiring, Runtime, Queen, ColonyManager. Imports all layers.
```

Enforced by `scripts/lint_imports.py`. Backward imports fail the build.

**The ONE mutation path:** `Runtime.emit_and_broadcast(event)` → append to SQLite → project into in-memory store → fan out to WS subscribers. Both MCP tools and WS commands delegate to Runtime.

---

## Key Files to Read First

| File | What It Does | Why It Matters |
|------|-------------|----------------|
| `CLAUDE.md` | Project rules, commands, constraints | Defines what's allowed |
| `docs/contracts/events.py` | Event type contracts | 22-event closed union, types.ts must mirror |
| `docs/contracts/ports.py` | Port interface contracts | Adapters must satisfy these |
| `docs/contracts/types.ts` | Frontend type contracts | Must match Python events/types |
| `docs/decisions/` | ADR-001 through ADR-006 | Architectural constraints |
| `docs/waves/PROGRESS.md` | Completed work log | Current state of the system |

---

## Critical Code Paths to Audit

### 1. Queen Chat Flow (KNOWN ISSUES)

**The Problem:** User sends message in frontend chat → backend processes it → Queen LLM responds → but messages may not appear in the frontend.

**Trace the full path:**
1. `frontend/src/components/queen-chat.ts` → dispatches `send-message` CustomEvent
2. `frontend/src/components/formicos-app.ts:255-258` → `store.send('send_queen_message', wsId, e.detail)`
3. `frontend/src/ws/client.ts:84-89` → sends JSON over WebSocket
4. `src/formicos/surface/ws_handler.py:137-166` → `ws_endpoint` receives, dispatches command
5. `src/formicos/surface/commands.py:62-69` → `_handle_send_queen_message` → calls `runtime.send_queen_message()` + schedules `runtime.queen.respond()` via `asyncio.create_task`
6. `src/formicos/surface/runtime.py:196-203` → `send_queen_message` → `emit_and_broadcast(QueenMessage(role="operator"))`
7. `src/formicos/surface/runtime.py:130-136` → `emit_and_broadcast` → append → project → `ws_manager.fan_out_event`
8. `src/formicos/surface/ws_handler.py:64-80` → `fan_out_event` → serializes event, sends to subscribers
9. `frontend/src/state/store.ts:67-73` → `handleMessage` → `applyEvent` or `applySnapshot`
10. `frontend/src/state/store.ts:127-137` → QueenMessage event handler → patches `queenThreads`

**After command returns:**
11. `src/formicos/surface/ws_handler.py:128-134` → sends full state snapshot to workspace subscribers

**Queen response (async):**
12. `src/formicos/surface/queen_runtime.py:40-95` → `respond()` → LLM loop with tool calls (up to 3 iterations) → emits `QueenMessage(role="queen")` via `emit_and_broadcast`

**Known issues in this path:**
- State snapshot (step 11) arrives AFTER the incremental event (step 8) — does `applySnapshot` clobber the event update?
- The Queen's async response (step 12) only fans out the event — no state snapshot follows. Does the frontend correctly append it?
- With llama3.2:3b, the model returns garbage tool inputs (`'null'`, `'<current workspace ID>'`, `'<empty string>'` as literal strings). After 3 failed iterations, content is often empty.
- `fan_out_event` determines workspace from `event.address.split("/")[0]` — verify this matches subscriber keys
- Thread ID matching: backend `_build_queen_threads` uses `thread.id` (= thread name = `"main"`), frontend `applyEvent` matches on `e.thread_id` — verify these always match

### 2. WebSocket State Synchronization

**Potential race conditions:**
- `dispatch_command` calls `emit_and_broadcast` (sends event) then `send_state_to_workspace` (sends snapshot). The snapshot should include the just-projected data, but verify ordering.
- `asyncio.create_task` for Queen/Colony operations runs in a separate task. Events from these tasks are fanned out independently. If multiple tasks emit events concurrently, projection state may be inconsistent during fan-out.
- `WebSocketManager._subscribers` is a plain dict. No locking. Multiple concurrent coroutines could modify it (subscribe/unsubscribe during fan_out).

### 3. MCP Server Mount

**Check:** The MCP server (`surface/mcp_server.py`) is created via `create_mcp_server(runtime)` but I don't see it mounted on any Starlette route in `app.py`. The `mcp` variable is stored on `app.state.mcp` but never mounted. **This means MCP tools are inaccessible over HTTP.** Verify whether FastMCP self-mounts or if explicit route registration is needed.

### 4. Colony Manager Lifecycle

- `colony_manager.py` → `start_colony` creates `asyncio.Task` per colony
- `rehydrate()` restarts colonies that were "running" at shutdown — but pheromone weights and round summaries are lost
- What happens if two `start_colony` calls fire for the same colony? (e.g., Queen spawns colony + MCP spawns same colony)
- Colony round loop calls `runner.run_round()` — check if runner handles LLM failures gracefully

### 5. Event Serialization Parity

- Python events use Pydantic `model_dump_json()` → snake_case fields (`thread_id`, `colony_id`, `edge_id`)
- Frontend store handles both snake_case and camelCase: `(e.thread_id ?? e.threadId)`
- Verify ALL event types in `store.ts:applyEvent` handle both cases
- Verify `model_dump_json()` includes the `type` discriminator field (it should — each event has `type: Literal["EventName"]`)

### 6. Docker / LLM Integration

- Default stack is llama.cpp with Qwen3-30B-A3B (Q4_K_M). Ollama is a commented alternative.
- `_ensure_v1()` in `app.py:55-60` appends `/v1` to OpenAI-compatible endpoints. Verify this doesn't double-append if endpoint already has `/v1`.
- Model GGUF must be downloaded manually to `.models/` before first boot. No auto-download. The bootstrap QueenMessage will show an error (Bug 1 fix) if model isn't available.
- Docker image is ~4GB due to sentence-transformers/PyTorch. Consider if this is avoidable.
- llama.cpp `--alias gpt-4` maps to `llama-cpp/gpt-4` in formicos.yaml. The `_strip_prefix()` helper removes the provider prefix before sending to the API.

### 7. Layer Boundary Integrity

Run `python scripts/lint_imports.py` and verify:
- No surface/ imports in core/ or engine/ or adapters/
- No engine/ imports in core/ or adapters/
- The `from __future__ import annotations` trick doesn't hide runtime circular imports

---

## Files to Audit (by priority)

### P0 — Core Data Flow
- `src/formicos/surface/runtime.py` — THE central service layer
- `src/formicos/surface/ws_handler.py` — WebSocket manager + command dispatch
- `src/formicos/surface/commands.py` — WS command handlers
- `src/formicos/surface/queen_runtime.py` — Queen LLM loop
- `src/formicos/surface/app.py` — Application factory, adapter wiring
- `src/formicos/surface/projections.py` — Event-sourced read models
- `src/formicos/surface/view_state.py` — Snapshot builder for frontend

### P1 — Frontend State
- `frontend/src/state/store.ts` — Reactive state store, event handlers
- `frontend/src/ws/client.ts` — WebSocket transport
- `frontend/src/components/queen-chat.ts` — Chat rendering
- `frontend/src/components/formicos-app.ts` — Main app, wiring
- `frontend/src/types.ts` — Type definitions (must match Python contracts)

### P2 — Adapters
- `src/formicos/adapters/llm_openai_compatible.py` — OpenAI/Ollama adapter
- `src/formicos/adapters/llm_anthropic.py` — Anthropic adapter
- `src/formicos/adapters/store_sqlite.py` — SQLite event store
- `src/formicos/adapters/vector_lancedb.py` — LanceDB vector store

### P3 — Engine
- `src/formicos/engine/runner.py` — Colony round execution
- `src/formicos/engine/context.py` — Context assembly
- `src/formicos/engine/strategies/` — Routing strategies

### P4 — Supporting
- `src/formicos/surface/colony_manager.py` — Colony lifecycle
- `src/formicos/surface/mcp_server.py` — MCP tool definitions
- `src/formicos/surface/config_endpoints.py` — Config mutation
- `src/formicos/core/events.py` — Event types (22-event union)
- `src/formicos/core/types.py` — Core value objects
- `src/formicos/core/ports.py` — Port interfaces
- `src/formicos/core/settings.py` — Config loading
- `config/formicos.yaml` — System config defaults
- `config/caste_recipes.yaml` — Agent caste definitions

---

## Specific Questions to Answer

1. **Why don't Queen messages appear in the frontend chat?** Trace the exact bytes from `emit_and_broadcast` through `fan_out_event` to the frontend `applyEvent` handler. Is there a serialization mismatch, a subscriber registration gap, or a rendering issue?

2. **Is the MCP server actually accessible?** The FastMCP instance is created but I don't see it mounted on a Starlette route. Check if `FastMCP` auto-mounts via ASGI middleware or if it needs explicit wiring.

3. **Are there concurrency bugs in the asyncio task scheduling?** `asyncio.create_task` is used for Queen responses and colony starts. These tasks call `emit_and_broadcast` which modifies shared state (projections, subscriber dict). Is this safe under asyncio's cooperative concurrency?

4. **Does the event replay path handle all 22 event types?** Check `projections.py:_HANDLERS` against `events.py` event classes. Any missing handlers = silent data loss on replay.

5. **Is the model cascade resolution correct?** `runtime.resolve_model(caste, workspace_id)` checks workspace config overrides then system defaults. Does it handle missing/None values correctly? What if a workspace config has a caste_model key set to empty string?

6. **Does the frontend handle WebSocket reconnection properly?** After reconnect, the client gets a fresh state snapshot, but does it re-subscribe to workspaces? Check the reconnection flow in `ws/client.ts` and whether `formicos-app.ts._subscribed` flag causes issues.

7. **Are there any SQL injection vectors in the SQLite store?** Check `store_sqlite.py` query methods for parameterized queries.

8. **Does `_ensure_v1` handle edge cases?** What if base_url is empty? What if it already has `/v1/`? What about trailing slashes?

9. **Is the LOC budget still under 15K?** Check the actual count with `find src/ -name '*.py' | xargs wc -l`.

10. **Are there any unclosed resources?** HTTP clients in LLM adapters, SQLite connections, WebSocket connections — do they all close properly on shutdown?

---

## Commands

```bash
# Install deps
uv sync

# Run all CI gates
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Run just tests
pytest -v

# Build frontend
cd frontend && npm ci && npm run build

# Docker
docker compose build && docker compose up

# LOC count
find src/ -name '*.py' | xargs wc -l
```

---

## Test Coverage Summary

- 391+ tests total (pytest)
- 42 feature scenarios across 12 .feature files
- Unit tests for: runtime, queen_runtime, colony_manager, ws_handler, projections, settings, engine
- Contract parity tests (Python ↔ TypeScript event alignment)
- Layer boundary tests (AST import analysis)
- LOC budget test

---

## Known Limitations (Alpha)

1. Queen LLM loop requires a running LLM endpoint; llama3.2:3b is too small for tool calling — use Qwen3-30B-A3B via llama.cpp
2. Sandbox execution port is defined but unimplemented
3. AG-UI and A2A protocols are interface-only
4. Embedding model downloads ~100MB on first boot
5. Docker image ~4GB (PyTorch/CUDA from sentence-transformers)
6. Colony rehydration loses pheromone weights and round summaries
7. MCP server may not be mounted (needs verification)
8. No authentication — single operator assumed
9. No rate limiting on WS commands
10. Frontend doesn't persist active view/thread selection across page refreshes
11. Queen tool surface is minimal (spawn_colony, get_status, kill_colony) vs pre-alpha 0.9.0 (6+ tools including file I/O, code execution, qdrant search, propose_diff). Tool expansion is planned for later waves.
12. No Qdrant integration — v2 uses LanceDB instead (lighter, embedded)
13. No HITL approval flow in colony execution
