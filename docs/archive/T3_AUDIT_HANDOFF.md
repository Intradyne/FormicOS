# T3 Audit & Planning Handoff

**Date:** 2026-03-13
**From:** Local coder (Claude Code, Opus 4.6)
**To:** Cloud planning model
**Purpose:** Full codebase audit, then produce hardened task specs for coder teams to execute polish/upgrades based on new research

---

## Mission

1. **Audit** the entire codebase against contracts, ADRs, and known bugs
2. **Plan** polish and upgrade work informed by new research the operator will provide
3. **Produce** hardened task documents that local coder agents can execute without ambiguity

This document gives you everything you need for step 1. The operator will supply research context for step 2.

---

## System Summary

FormicOS v2 is a stigmergic multi-agent colony framework. AI agents coordinate through shared environmental signals (pheromones) rather than direct messaging. Tree-structured data model. Event-sourced. Single operator. Local-first with cloud model support.

**Current stage:** Alpha (v2.0.0a1). Fully operational end-to-end. Docker stack runs, Queen spawns colonies, rounds execute, UI renders.

---

## Architecture (4 layers, strict inward dependency)

```
Core     types, events, port interfaces. Imports NOTHING.
Engine   colony execution (runner, strategies, context). Imports only Core.
Adapters tech bindings (LLM, SQLite, LanceDB). Import only Core.
Surface  wiring + HTTP/WS/MCP + Queen + colony lifecycle. Imports all layers.
```

**Enforced by CI** (`python scripts/lint_imports.py`). Backward imports fail the build.

**Single mutation path:** `Runtime.emit_and_broadcast(event)` -> append SQLite -> project in-memory -> fan out WS. No exceptions.

---

## Current Metrics

| Metric | Value |
|--------|-------|
| Python source LOC (src/formicos/) | 5,134 (hard limit: 15K) |
| Frontend source LOC (frontend/src/) | 2,253 |
| Total tests | 425 (all passing) |
| Feature scenarios | 42 (12 .feature files) |
| Event types | 22 (closed union) |
| MCP tools | 12 |
| WS command types | 9 |
| Frontend components | 19 (Lit Web Components) |
| Bundle size | 25.14 KB gzip |
| CI gates | ruff, pyright strict, layer lint, pytest -- all green |

---

## Tech Stack

Python 3.12+, uv, Pydantic v2 (sole serialization), asyncio, httpx, aiosqlite, lancedb, sentence-transformers (snowflake-arctic-embed-s), FastMCP >= 3.0, Starlette, uvicorn, structlog, sse-starlette. Frontend: Lit 3.2+ Web Components, Vite 6, TypeScript 5.7.

**Default LLM:** Qwen3-30B-A3B via llama.cpp (`--alias gpt-4`), ~21 GB VRAM on RTX 5090.
**Cloud fallback:** Anthropic Claude Sonnet 4.6 / Haiku 4.5.

---

## File Map (read in this order for audit)

### Contracts (DO NOT MODIFY without operator approval)
- `docs/contracts/events.py` -- 22-event Pydantic union (frozen, closed)
- `docs/contracts/ports.py` -- 5 Protocol interfaces (LLM, EventStore, Vector, Strategy, Sandbox)
- `docs/contracts/types.ts` -- TypeScript mirror for frontend

### ADRs (understand WHY before changing anything)
- `docs/decisions/001-event-sourcing.md` -- append-only events, no shadow DB
- `docs/decisions/002-pydantic-only.md` -- Pydantic v2 sole serializer
- `docs/decisions/003-lit-web-components.md` -- Lit, not React
- `docs/decisions/004-typing-protocol.md` -- Protocol-based ports, no ABC
- `docs/decisions/005-mcp-sole-api.md` -- MCP tools = programmatic API, WS bridges to same ops
- `docs/decisions/006-trunk-based-development.md` -- short branches, feature flags

### Core Layer (~450 LOC)
- `src/formicos/core/events.py` -- 22 frozen Pydantic events, serialize/deserialize
- `src/formicos/core/types.py` -- value objects (LLMMessage, LLMResponse, AgentConfig, ColonyContext, etc.)
- `src/formicos/core/ports.py` -- 5 Protocol interfaces
- `src/formicos/core/settings.py` -- YAML config loading, env interpolation, SystemSettings model

### Engine Layer (~600 LOC)
- `src/formicos/engine/runner.py` -- 5-phase round loop (goal/intent/route/execute/compress), convergence heuristic + embedding mode, pheromone update, governance decisions
- `src/formicos/engine/context.py` -- context assembly, token trimming, merge injection
- `src/formicos/engine/strategies/stigmergic.py` -- DyTopo routing, pheromone-weighted topology
- `src/formicos/engine/strategies/sequential.py` -- simple sequential agent ordering

### Adapters Layer (~1,200 LOC)
- `src/formicos/adapters/llm_openai_compatible.py` -- OpenAI/Ollama/llama.cpp adapter, semaphore concurrency limiting, 400/429 retry
- `src/formicos/adapters/llm_anthropic.py` -- Anthropic Messages API, tool use, SSE streaming
- `src/formicos/adapters/store_sqlite.py` -- WAL, append/query/replay, seq assignment
- `src/formicos/adapters/vector_lancedb.py` -- LanceDB wrapper, embed_fn injection

### Surface Layer (~2,000 LOC)
- `src/formicos/surface/app.py` -- Starlette factory, adapter wiring, lifespan, first-run bootstrap, frontend serving
- `src/formicos/surface/runtime.py` -- Runtime service (THE mutation path), LLMRouter, model cascade, agent building
- `src/formicos/surface/projections.py` -- ProjectionStore, 21 event handlers, in-memory read models
- `src/formicos/surface/view_state.py` -- OperatorStateSnapshot builder for WS state messages
- `src/formicos/surface/ws_handler.py` -- WS manager, subscribe/unsubscribe, fan-out, command dispatch
- `src/formicos/surface/commands.py` -- 9 WS command handlers (thin wrappers to Runtime)
- `src/formicos/surface/queen_runtime.py` -- Queen LLM loop, 3 tools (spawn_colony, get_status, kill_colony), up to 3 iterations
- `src/formicos/surface/colony_manager.py` -- asyncio.Task per colony, round loop, governance, rehydration
- `src/formicos/surface/mcp_server.py` -- 12 FastMCP tools (same operations as WS commands)
- `src/formicos/surface/view_models.py` -- colony_detail, approval_queue, round_history, workspace_colonies
- `src/formicos/surface/config_endpoints.py` -- config mutation, model assignment
- `src/formicos/surface/model_registry_view.py` -- registry status derivation

### Frontend (~2,253 LOC)
- `frontend/src/types.ts` -- full type mirror of Python events/types (camelCase)
- `frontend/src/ws/client.ts` -- WSClient, auto-reconnect, exponential backoff
- `frontend/src/state/store.ts` -- FormicStore singleton, event application, tree utils
- `frontend/src/components/formicos-app.ts` -- main shell, tabs, sidebar, auto-subscribe
- `frontend/src/components/queen-overview.ts` -- dashboard, colony cards, approval queue
- `frontend/src/components/colony-detail.ts` -- topology SVG, metrics, agents table, round history
- `frontend/src/components/thread-view.ts` -- Queen chat + colony list + merge controls
- `frontend/src/components/queen-chat.ts` -- chat panel
- `frontend/src/components/round-history.ts` -- round records
- 10 more components (tree-nav, breadcrumb, workspace-config, model-registry, castes, settings, approval-queue, atoms)
- `frontend/src/styles/shared.ts` -- Void Protocol design tokens

### Config
- `config/formicos.yaml` -- system, models (registry + defaults), embedding, governance, routing
- `config/caste_recipes.yaml` -- caste definitions (queen, coder, reviewer, researcher, archivist)

### Tests (425 passing)
- `tests/unit/` -- core, engine, adapters, surface unit tests
- `tests/features/` -- 12 .feature files with step definitions
- `tests/contract/` -- event parity, TS sync, LOC budget, layer boundaries
- `tests/unit/surface/test_round_projections.py` -- 10 tests for round projection pipeline (newly added)

---

## Critical Data Flows

### Queen Chat -> Colony Spawn
```
Frontend WS cmd -> ws_handler -> commands -> runtime.send_queen_message()
  -> emit QueenMessage(role=operator)
  -> asyncio.create_task(queen.respond())
     -> LLM loop (up to 3 tool iterations)
     -> tool: spawn_colony -> runtime.spawn_colony()
        -> emit ColonySpawned
        -> colony_manager.start_colony() -> asyncio.Task
           -> round loop (runner.run_round)
              -> emit RoundStarted, PhaseEntered(x5), AgentTurn*, RoundCompleted
           -> governance check -> emit ColonyCompleted or loop
```

### State Synchronization
```
Runtime.emit_and_broadcast(event)
  -> store.append(event)        [SQLite, seq assigned]
  -> projections.apply(event)   [in-memory read model update]
  -> ws_manager.fan_out(event)  [broadcast to subscribed WS clients]
```

### Provider-Prefix Model Routing
```
"llama-cpp/gpt-4"  -> OpenAICompatibleLLMAdapter -> http://llm:8080/v1
"ollama/qwen3:30b"  -> OpenAICompatibleLLMAdapter -> http://ollama:11434/v1
"anthropic/claude-sonnet-4.6" -> AnthropicLLMAdapter -> https://api.anthropic.com
```

---

## Known Bugs (5 total, 3 fixed)

### FIXED in this session

**Bug A: Round agent data not surfaced in UI**
- Root cause: `projections.py` didn't populate `RoundProjection.agent_outputs`/`tool_calls`; `view_state.py` hardcoded empty agents
- Fix: Added `_get_or_create_round()` helper, updated `_on_agent_turn_completed` to record outputs, updated `view_state.py` to use real data

**Bug B: PhaseEntered events silently dropped**
- Root cause: No handler registered in `_HANDLERS` for PhaseEntered
- Fix: Added `_on_phase_entered` handler, added `current_phase` field to `RoundProjection`

**Bug C: 3+ agent colonies hit HTTP 400 from llama.cpp**
- Root cause: llama.cpp `-np 2` with 3 concurrent agents -> slot exhaustion
- Fix: Added semaphore concurrency limiting (`_LOCAL_CONCURRENCY_LIMIT = 2`) and 400 retry in `llm_openai_compatible.py`

### OPEN

**Bug D: ColonySpawned missing colony_id field** (Low)
- The `ColonySpawned` event has no `colony_id` field -- colony ID is derived from address parsing (`address.rsplit("/", 1)[-1]`)
- Workaround: Address parsing works but is fragile
- Fix: Requires contract update (operator approval needed to modify events.py)
- **Files:** `docs/contracts/events.py`, `src/formicos/core/events.py`

**Bug E: Convergence never reaches threshold** (Medium)
- All colonies hit max 25 rounds. Convergence stays ~0.65, never reaches 0.85
- `runner.py` convergence check: `is_converged = score > 0.85 and stability > 0.90`
- Heuristic mode: `goal_alignment` fixed at 0.5, caps effective score
- Embedding mode: requires vector store integration that may not be wired
- **Files:** `src/formicos/engine/runner.py` (convergence logic), `config/formicos.yaml` (threshold tuning)

---

## Docker Smoke Test Results (2026-03-13)

All tests run against live Docker stack (llama.cpp + FormicOS):

| Test | Result | Notes |
|------|--------|-------|
| Plain Queen chat | PASS | QueenMessage events emitted, Queen responded |
| 1-agent colony | PASS | 25 rounds, completed. Round detail: phase=compress, 1 agent with output |
| 2-agent colony | PASS | 25 rounds, completed (took ~4min). Round detail: 2 agents with output |
| 3-agent colony | PASS | Semaphore throttling works, no 400 errors |
| get_status | PASS | Queen called tool, returned colony info |
| WS fan-out | PASS | Both subscribers received events |
| Round detail in snapshot | PASS | phase + agents + convergence + cost + durationMs all populated |

**Zero errors in either container's logs.**

---

## Audit Checklist

When auditing, verify:

1. **Contract compliance**: Do all 22 event types serialize/deserialize correctly? Does every emitter match the contract fields?
2. **Layer boundaries**: Any backward imports? (CI enforces, but check manually)
3. **Single mutation path**: Is `emit_and_broadcast` truly the only way state changes? Any sneaky direct mutations?
4. **Event handler coverage**: All 22 event types handled in projections? (21 handled, ContextUpdated is not emitted)
5. **MCP/WS parity**: Do MCP tools and WS commands produce identical behavior? (ADR-005)
6. **Error handling**: What happens when LLM is down? When store is full? When colony loops infinitely?
7. **Convergence logic**: Is the heuristic convergence formula correct? Why does it never converge? (Bug E)
8. **Colony lifecycle**: Are all terminal states (completed/failed/killed) handled? Can a colony zombie?
9. **Projection rebuild**: Does replaying all events produce identical state? Any order-dependent bugs?
10. **Frontend type parity**: Does `types.ts` match `events.py` exactly? Any drift?
11. **Security**: Any injection vectors in WS command handling? Unsanitized inputs to LLM?
12. **Resource cleanup**: Are asyncio tasks cancelled on colony kill? Are HTTP clients closed?

---

## Constraints for Coder Task Documents

When writing task specs for local coders, follow these rules:

1. **Scope lock**: List exactly which files may be modified. Coders must not touch files outside scope.
2. **Read order**: Specify which files to read first (contracts, ADRs, then implementation).
3. **Validation commands**: Every task must end with `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`.
4. **No contract changes** without operator approval.
5. **Event union is closed** -- adding events requires explicit approval.
6. **15K LOC hard limit** -- current: 5,134. Budget exists but don't waste it.
7. **Pydantic v2 only** -- no dataclasses for serialized types, no msgspec.
8. **structlog only** -- no print().
9. **Feature flags** wrap incomplete work.
10. **Tests required** -- every behavioral change needs a test.

---

## What the Operator Will Provide Next

The operator will supply new research/context for planned upgrades. Your job after audit:

1. Identify what in the current codebase needs to change to support the upgrades
2. Design the implementation plan (which layers, which files, what order)
3. Break into parallelizable coder tasks (matching the AGENTS.md stream model)
4. Write hardened task specs with explicit scope, read order, acceptance criteria, and validation

---

## Quick Reference: Running the System

```bash
# Install
uv sync

# Full CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Docker
docker compose build formicos && docker compose up -d

# Health
curl http://localhost:8080/health

# Logs
docker compose logs formicos --tail 200
docker compose logs llm --tail 200
```

---

## Files Changed in This Session

| File | Change |
|------|--------|
| `src/formicos/surface/projections.py` | Added PhaseEntered handler, RoundProjection.current_phase, _get_or_create_round(), agent turn -> round projection, address-based colony disambiguation for AgentTurnCompleted |
| `src/formicos/surface/view_state.py` | Round detail uses real RoundProjection data instead of hardcoded empty |
| `src/formicos/surface/view_models.py` | Added "phase" to _serialize_round |
| `src/formicos/adapters/llm_openai_compatible.py` | Semaphore concurrency limiting, local URL detection, 400 retry for local endpoints |
| `tests/unit/surface/test_round_projections.py` | NEW: 10 tests for round projection pipeline |
| `docker-compose.yml` | Fixed YAML comment-in-folded-block bug, moved comment outside command block |
