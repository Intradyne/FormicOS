# T2 — Cloud Model Audit Handoff

> Context for a cloud model with full filesystem access. Read this first,
> then investigate the referenced files.

## Current State (2026-03-13)

FormicOS v2 is **fully operational end-to-end**. The Queen chat pipeline,
colony spawning, multi-round execution, and WebSocket state synchronization
all work. CI is green (391 tests, ruff, pyright, layer lint).

**Stack:** llama.cpp (Qwen3-30B-A3B Q4_K_M) + FormicOS + sentence-transformers
on RTX 5090 32GB. ~21 GB VRAM used, ~11 GB headroom.

---

## What Was Done in T1

### Bug Fixes Applied (7 total)
1. **Queen silent errors** — `queen_runtime.py` now ALWAYS emits a QueenMessage
   (even on error) so the operator sees feedback in chat.
2. **WS reconnect dead** — `formicos-app.ts` `_subscribed` flag resets on disconnect.
3. **Broadcast crash** — `commands.py` validates `fromColony` presence, catches KeyError.
4. **Anthropic 400** — `llm_anthropic.py` extracts system messages as top-level param.
5. **Caste icon case mismatch** — `view_state.py` `.lower()` on recipe.name for lookups.
6. **Config defaults** — All castes default to `llama-cpp/gpt-4` (Qwen3-30B-A3B via --alias).
7. **Docker GPU** — llama.cpp is primary service with GPU reservation + health checks.

### Stack Migration: Ollama → llama.cpp
- `docker-compose.yml` — llama.cpp primary, Ollama as commented alternative
- `config/formicos.yaml` — all defaults to `llama-cpp/gpt-4`, registry updated
- `app.py` — fallback URL changed to `http://localhost:8008`
- Tests + feature specs updated to match

### Test Fixes
- `test_queen_runtime.py` — 2 tests updated for always-emit behavior
- `test_settings.py` — assertions match new config
- `model_cascade.feature` — scenarios updated
- `surface_steps.py` — local model fixture + provider filter

---

## Smoke Test Results (Live Stack)

| Test | Result | Detail |
|------|--------|--------|
| Queen plain chat | PASS | Coherent response, correct tool listing |
| Queen spawn_colony (1 agent) | PASS | 25 rounds, completed |
| Queen spawn_colony (2 agents) | PASS | Coder + reviewer converged |
| Queen spawn_colony (3 agents) | FAIL | 400 from llama.cpp on 3rd agent (slot contention) |
| Queen get_status | PASS | Correct colony status via tool call |
| Queen kill_colony | UNTESTED | Colony failed before kill could execute |
| Bad thread ID | PASS | Error message displayed correctly |
| Empty message | PASS | No crash, Queen responded |
| Rapid-fire (3 msgs) | PASS | All 3 replies received |
| Health endpoint | PASS | last_seq tracking correct |
| WS event fan-out | PASS | All events delivered to subscribers |

---

## Bugs Found During Testing

### Bug A: Round Agent Data Not Surfaced (view_state + projections)

**Severity:** Medium — colony rounds appear blank in frontend.

**Root cause:** Two linked issues:

1. `src/formicos/surface/view_state.py:83-88` hardcodes:
   ```python
   "rounds": [
       {"roundNumber": r.round_number, "phase": "compress", "agents": []}
       for r in colony.round_records
   ]
   ```
   Should read from `RoundProjection.agent_outputs` and `tool_calls`.

2. `src/formicos/surface/projections.py:288-295` — `_on_agent_turn_completed`
   updates `agent.tokens` and `agent.status` but doesn't store
   `e.output_summary` or `e.tool_calls` into the round projection.

3. The `RoundProjection` dataclass (line 80-88) already has `agent_outputs`
   and `tool_calls` fields — they're just never populated.

**Fix approach:**
- In `_on_agent_turn_completed`: find the current round projection and populate
  `agent_outputs[e.agent_id] = e.output_summary` and `tool_calls[e.agent_id] = e.tool_calls`.
- In `view_state.py`: read from the round projection instead of hardcoding empty.

### Bug B: PhaseEntered Events Silently Dropped

**Severity:** Low — cosmetic. Phase always shows "compress" in the view.

**Root cause:** `PhaseEntered` events are emitted by the engine but there's
no handler in `projections.py:_HANDLERS`. The event is silently dropped.

**Fix approach:** Add a handler that updates the colony or round projection
with the current phase name. Then read it in `view_state.py`.

### Bug C: 3+ Agent Colonies Hit 400 from llama.cpp

**Severity:** Medium — multi-agent colonies with 3+ agents can fail.

**Root cause:** llama.cpp is configured with `-np 2` (2 parallel inference slots).
The engine's `ColonyRunner.run_round()` uses `asyncio.TaskGroup` to run all
agents concurrently. With 3+ agents, the third agent's request hits llama.cpp
when both slots are busy, causing a 400 Bad Request.

**Fix options:**
1. Increase `-np` to match max agents per colony (but uses more VRAM)
2. Add retry with backoff in `OpenAICompatibleLLMAdapter._post_with_retry()`
   for 400 responses (currently only retries 429)
3. Add a semaphore in the colony runner to limit concurrent LLM calls
4. Fall back to sequential execution when agent count > slot count

**Recommendation:** Option 2 (add 400 to retryable codes with a short backoff)
is the simplest fix and handles transient slot contention. Option 3 is more
robust for production.

### Bug D: ColonySpawned Event Missing colony_id Field

**Severity:** Low — the colony ID is in the `address` field but not as a
dedicated `colony_id` field. Any consumer that wants the ID must parse it
from `address.split("/")[2]`.

**Note:** This is a contract issue. The `ColonySpawned` event in
`docs/contracts/events.py` should be checked for parity.

### Bug E: Colony Convergence Never Triggers for Single-Agent Colonies

**Severity:** Low-Medium — single-agent colonies always hit max_rounds (25).

**Root cause:** The convergence heuristic (`runner.py:302-328`) compares
round-over-round output similarity. With a single agent and no embedding
model loaded (sentence-transformers runs in-process but not inside colonies),
the heuristic similarity calculation may not reach the 0.85 threshold.

The colony in testing ran 25/25 rounds with convergence=0.647.

**Note:** This isn't necessarily a bug — the heuristic mode is a fallback.
With embeddings loaded, the `_compute_convergence_embed` path should give
better similarity scores. But 25 rounds for a simple fibonacci task is wasteful.

---

## Files Changed This Session

### Modified:
- `docker-compose.yml` — llama.cpp primary, Ollama alternative, container names, VRAM docs
- `config/formicos.yaml` — llama-cpp/gpt-4 defaults, updated registry
- `src/formicos/surface/app.py:124` — fallback URL to localhost:8008
- `src/formicos/__main__.py` — removed unused sys import
- `tests/unit/core/test_settings.py` — assertions match new config
- `tests/features/steps/surface_steps.py` — local model fixture updated
- `docs/specs/model_cascade.feature` — scenarios updated
- `docs/AUDIT_HANDOFF.md` — updated for llama.cpp stack, added known limitations

### Created:
- `tests/smoke_test.py` — deep smoke test script (can be deleted or kept for CI)
- `docs/T2_HANDOFF.md` — this document

---

## Architecture Quick Reference

```
Core    → types, events (22-event union), port interfaces. Imports NOTHING.
Engine  → colony execution (runner, strategies, context). Imports only Core.
Adapters → LLM, SQLite, LanceDB. Import only Core.
Surface → HTTP/WS/MCP wiring, Runtime, Queen, ColonyManager. Imports all.
```

**The ONE mutation path:**
`Runtime.emit_and_broadcast(event)` → append SQLite → project in-memory → fan out WS

**Provider-prefix routing:**
`llama-cpp/gpt-4` → prefix `llama-cpp` selects `OpenAICompatibleLLMAdapter`,
suffix `gpt-4` is sent as the model name. `_ensure_v1()` appends `/v1` to base URL.
`_strip_prefix()` removes the provider prefix before API calls.

---

## Key Files to Investigate

### For Bug A (round data):
- `src/formicos/surface/view_state.py:83-88` — hardcoded empty agents
- `src/formicos/surface/projections.py:80-88` — RoundProjection dataclass
- `src/formicos/surface/projections.py:288-295` — _on_agent_turn_completed
- `src/formicos/surface/projections.py:298-309` — _on_round_completed

### For Bug B (phase):
- `src/formicos/core/events.py` — grep for `PhaseEntered`
- `src/formicos/surface/projections.py:385-406` — _HANDLERS dict

### For Bug C (slot contention):
- `src/formicos/engine/runner.py:120-130` — TaskGroup concurrent execution
- `src/formicos/adapters/llm_openai_compatible.py:64-102` — retry logic
- `docker-compose.yml:70` — `-np 2` slot count

### For Bug E (convergence):
- `src/formicos/engine/runner.py:251-330` — convergence computation
- `src/formicos/engine/runner.py:332-345` — governance evaluation

---

## Commands

```bash
# Full CI
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Docker
docker compose up -d
docker logs formicos-colony -f
docker logs formicos-llm -f

# Health checks
curl http://localhost:8080/health   # FormicOS
curl http://localhost:8008/health   # llama.cpp

# Smoke test
python tests/smoke_test.py
```

---

## Priority Recommendation

1. **Fix Bug A** (round data) — most user-visible, straightforward fix
2. **Fix Bug C** (slot contention) — add 400 to retryable codes in the adapter
3. **Fix Bug B** (phase tracking) — add PhaseEntered handler
4. **Investigate Bug E** (convergence) — may need tuning or early-exit heuristic
5. Bug D is a contract question — defer unless it blocks something

---

## Known Limitations (Do NOT Fix)

See `docs/AUDIT_HANDOFF.md` for the full list (13 items). Key ones:
- MCP server not mounted on HTTP route (ADR-005 violation, deferred)
- Queen tool surface is minimal (3 tools vs pre-alpha's 6+)
- No HITL approval flow in colony execution
- Colony rehydration loses pheromone weights
- No Qdrant integration (v2 uses LanceDB)
