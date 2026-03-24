# T3 Bug Fix Sprint — Orchestrator Prompt

> **For:** Orchestrator / Queen coordinating three parallel coder teams
> **Input:** T2 smoke test found 5 bugs. All are projection-layer or adapter-layer — no architectural issues.
> **Goal:** Fix all 5 bugs in one parallel sprint. Ship a clean `pytest` + `ruff` + `pyright` run.

---

## System State

- CI is green: 391 tests, ruff, pyright, layer lint all pass
- Stack: llama.cpp (Qwen3-30B-A3B Q4_K_M, `-np 2`) + FormicOS + sentence-transformers on RTX 5090
- All bugs are in `engine/` or `surface/` or `adapters/` — no `core/` changes needed except one dataclass field addition (Bug D)

---

## Team Assignments

Spawn three coder subagent teams. They have **zero file overlap** and can run fully in parallel.

---

### TEAM ALPHA — Projection Pipeline (Bugs A + B + D)

**Objective:** Make colony round data visible in the frontend. Three linked issues where events are emitted but projections don't consume or surface them.

**Files to modify:**

1. `src/formicos/surface/projections.py`
2. `src/formicos/surface/view_state.py`
3. `src/formicos/core/events.py` (one field addition only)

**Bug A — Round agent data hardcoded empty:**
- Location: `src/formicos/surface/view_state.py` lines 83-88
- Problem: Returns `"agents": []` and `"phase": "compress"` for every round instead of reading from `RoundProjection`
- Fix: Replace the hardcoded list comprehension to read `r.agent_outputs`, `r.tool_calls`, and `r.current_phase` from the `RoundProjection` dataclass

**Bug B — `_on_agent_turn_completed` doesn't populate round projection:**
- Location: `src/formicos/surface/projections.py` lines 288-295
- Problem: Handler updates `agent.tokens` and `agent.status` but ignores `e.output_summary` and `e.tool_calls`
- The `RoundProjection` dataclass (lines 80-88) already HAS `agent_outputs` and `tool_calls` fields — they're just never written to
- Fix: In `_on_agent_turn_completed`, find the current `RoundProjection` and set `agent_outputs[e.agent_id] = e.output_summary` and `tool_calls[e.agent_id] = e.tool_calls`

**Bug C (relabeled from handoff Bug B) — `PhaseEntered` has no projection handler:**
- Location: `src/formicos/surface/projections.py` lines 385-406 (the `_HANDLERS` dict)
- Problem: `PhaseEntered` events are emitted by the engine but silently dropped — no handler registered
- Fix: Add a handler that updates `RoundProjection.current_phase` with the phase name from the event. Register it in `_HANDLERS`.

**Bug D — `ColonySpawned` missing `colony_id` field:**
- Location: `src/formicos/core/events.py` — find `ColonySpawned` dataclass
- Problem: Colony ID only exists inside the `address` field. Consumers must parse it with `address.split("/")[2]`
- Fix: Add explicit `colony_id: str` field to the `ColonySpawned` dataclass. Update the emission site (grep for `ColonySpawned(` in `engine/`) to pass the colony_id. Check `docs/contracts/events.py` for parity.

**Verification:** After fixes, run a colony via smoke test and confirm the frontend round detail view shows agent outputs, tool calls, correct phase names, and colony_id is accessible without address parsing.

**Sweep task:** While in `projections.py`, grep every `emit(` call in `engine/orchestrator.py` and `engine/colony.py`. Cross-reference against `_HANDLERS`. If any other events are emitted but have no handler, flag them in a comment block at the bottom of your commit message.

---

### TEAM BETA — LLM Slot Contention (Bug E from handoff Bug C)

**Objective:** 3+ agent colonies must not fail when llama.cpp has fewer slots than concurrent agents.

**Files to modify:**

1. `src/formicos/adapters/llm_openai_compatible.py`
2. `docker-compose.yml` (comment/docs only)

**The problem:**
- llama.cpp runs with `-np 2` (2 parallel inference slots)
- `ColonyRunner.run_round()` uses `asyncio.TaskGroup` to run all agents concurrently
- With 3+ agents, the 3rd request gets HTTP 400 because both slots are busy
- Currently the adapter only retries on 429, not 400

**Fix 1 — Retry with backoff (required):**
- Location: `src/formicos/adapters/llm_openai_compatible.py` lines 64-102 (retry logic)
- Add HTTP 400 to the retryable status codes alongside 429
- Use exponential backoff: 3 attempts, starting at 500ms, doubling each retry
- Log a warning on each retry so operators can see slot contention in logs

**Fix 2 — Concurrency semaphore (required):**
- In the same adapter file, add an `asyncio.Semaphore` that limits concurrent requests to local endpoints
- The semaphore count should come from config. Add a `max_concurrent_slots` field to the model config or adapter constructor, defaulting to 2
- Only apply the semaphore when the endpoint is a local URL (localhost / 127.0.0.1). Cloud endpoints (Anthropic, OpenAI) should NOT be throttled.
- The semaphore goes in the adapter, NOT in the orchestrator or runner — the adapter owns the transport concern

**Documentation:**
- Add a comment in `docker-compose.yml` near the `-np 2` flag explaining: "Match this value to max_concurrent_slots in llm_openai_compatible.py. If you increase -np, update the adapter config to match."

**Verification:** Spawn a 3-agent colony. All three agents should complete their turns without 400 errors. Check llama.cpp logs (`docker logs formicos-llm`) to confirm requests are serialized when slots are full, not rejected.

**Do NOT touch:** `src/formicos/engine/runner.py` — the TaskGroup concurrent execution is correct. The fix belongs in the adapter layer.

---

### TEAM GAMMA — Convergence Heuristic (Bug F from handoff Bug E)

**Objective:** Single-agent colonies should converge before hitting the 25-round max. Current heuristic reaches only 0.647 similarity on a fibonacci task — well below the 0.85 threshold.

**Files to modify:**

1. `src/formicos/engine/runner.py` (convergence logic, lines 251-345)

**The problem:**
- `_compute_convergence_heuristic` compares round N output to round N-1 output
- Without embeddings, string-level similarity can't detect semantic convergence
- Single-agent colonies always hit `max_rounds` (25), wasting tokens

**Fix approach — two-pronged:**

**Prong 1 — Task-complete signal detection (quick win):**
- After computing heuristic similarity, check the agent's output for explicit completion signals
- Look for patterns like: agent used no tools this round, agent output contains "task complete" / "no further changes" / "nothing left to do", or agent's output is substantially shorter than previous rounds (< 30% token count)
- If any completion signal is detected AND heuristic similarity > 0.5 (relaxed threshold), treat as converged
- This is a heuristic on top of a heuristic — keep it simple, don't over-engineer

**Prong 2 — Embedding path activation (if time permits):**
- Check whether `_compute_convergence_embed` is reachable. The handoff says sentence-transformers is installed and running but "not inside colonies"
- If the VectorPort is available to the runner, wire up the embedding path: embed round N and round N-1 compressed summaries, compute cosine similarity
- If the VectorPort is NOT available at that scope, add a TODO comment explaining what's needed to wire it in

**Governance evaluation:**
- Location: `src/formicos/engine/runner.py` lines 332-345
- After fixing convergence detection, verify that `evaluate_convergence` correctly transitions the colony to completed state when convergence is detected
- A single-agent fibonacci colony should converge in 3-5 rounds, not 25

**Verification:** Run `python tests/smoke_test.py` with a single-agent colony on a simple task. Confirm it converges in < 10 rounds. Check that multi-agent colonies still converge correctly (no regression).

**Do NOT touch:** The 0.85 threshold for embedding-based convergence. That's calibrated for the embedding path. Only relax the threshold for the heuristic+signal-detection path.

---

## Coordination Rules

1. **No file overlap.** Teams touch different files. If a team discovers they need to modify a file assigned to another team, stop and report back — do not edit it.
2. **Core layer is read-only** except for Team Alpha's one-field addition to `ColonySpawned` in `events.py`. No other core changes.
3. **Run the full CI after your fixes:** `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest`
4. **Layer lint must pass.** Adapters import only core. Engine imports only core. Surface imports all. Do not violate this.
5. **Each team reports back with:**
   - Files modified (with line ranges)
   - Tests added or updated
   - CI result (pass/fail)
   - Any other silently-dropped events or issues discovered during the sweep

---

## After All Teams Complete

Run the full smoke test: `python tests/smoke_test.py`

Expected results:
- All 10 checks PASS (including the 3-agent colony that previously failed)
- Frontend round detail view shows agent outputs, tool calls, and correct phase
- Single-agent colonies converge in < 10 rounds
- `colony_id` is a first-class field on `ColonySpawned`

If all pass, write `docs/T3_RESULTS.md` with the summary and mark the sprint complete.
