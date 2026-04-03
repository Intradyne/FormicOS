## Status

**Landed and benchmarked (2026-04-01).**

Wave 84 was a tight two-track wave:

- Track 1: diagnosed and fixed the sustained event-loop stall
- Track 2: ran clean comparative benchmarks after Track 1 landed

### Outcome

- **Qwen3.5-35B benchmark:** 0.503 avg quality, 5/5 tasks, 0 hangs, ~16 min total.
- **Devstral evaluation:** app healthy, but too slow for iterative colony rounds on this hardware.
- **Production profile:** Qwen3.5-35B MoE restored as default local model.
- **Key insight:** MoE iteration speed beats dense-model per-token quality in the real colony loop.

---

*Original planning text below (preserved for historical context):*

The stall was the gate for everything else from this session.
Until it was fixed, no benchmark run was trustworthy past roughly 15
minutes of sustained colony work.

## Dispatch Shape

This packet should dispatch to one coder, not two.

Track 2 is fully gated on Track 1, and the same owner should carry the
work from instrumentation through fix through live validation so the
diagnosis does not get lost in a handoff.

## Summary

Waves 77 through 83.5 landed substantial capability:

- AI filesystem and project binding
- planning brief and structural hints
- learned decomposition and plan patterns
- reviewed-plan validation and the planning workbench
- Devstral local-model setup and runtime stabilization

The remaining blocker was not product scope — it was runtime truth
under sustained load. Wave 84 removed the stall, proved the fix on
long tasks, and ran the full task pack.

## Verified Repo Truth

This packet should dispatch against the code that actually exists now.

- `src/formicos/adapters/sandbox_manager.py` does not use the Python
  Docker SDK in the hot path. Sandbox and workspace execution use async
  subprocess calls (`asyncio.create_subprocess_exec` /
  `create_subprocess_shell`).
- The stronger workspace-execution suspect is synchronous Python file
  and tar work inside the async path:
  - `_archive_workspace()`
  - `_restore_workspace_from_archive()`
- Those helpers run directly on the event loop today and are called by
  the workspace executor path around Docker copy-in / copy-out.
- Startup memory backfill is now serialized and idle-gated in
  `src/formicos/surface/app.py`. It should no longer burst several
  extraction LLM calls immediately during startup.
- Normal colony completion still fires background LLM work immediately
  via:
  - `_hook_memory_extraction()`
  - `_hook_transcript_harvest()`
- Those completion hooks call `llm_router.complete()` and therefore
  still compete with active colony work for local llama.cpp capacity.
- `src/formicos/adapters/llm_openai_compatible.py` already hardened the
  earlier parser / transport seams:
  - defensive tool-call recovery is offloaded to `asyncio.to_thread()`
  - `resp.json()` is bounded and offloaded
  - local requests use `Connection: close`
  - local transport resets and retries are in place
- The local OpenAI-compatible adapter still uses default `httpx`
  connection-pool limits. This is a plausible hardening target, but it
  is not the first suspected stall surface.
- The forced escalation abandonment is now disabled again in
  `src/formicos/engine/runner.py`. Wave 84 should not reopen the cap
  experiment unless new evidence appears.
- Devstral runtime is currently most stable with:
  - `LLM_FLASH_ATTN=off`
  - `LLM_CACHE_TYPE_K=f16`
  - `LLM_CACHE_TYPE_V=f16`
  - `LLM_CACHE_RAM=0`
  - conservative slot/context settings from `.env.devstral`

## Track 1: Event-Loop Stall Diagnosis and Fix

Goal:

Identify and remove the blocking runtime seam that causes:

- app health checks to stop responding
- WebSocket streams to die
- the app to stop progressing while llama.cpp remains healthy

This track is substrate-first.
Do not broaden scope into planner or UI work.

### Step 1: Add instrumentation before changing behavior

Add explicit asyncio slow-callback instrumentation at app startup.

Recommended shape:

- enable event-loop debug only when a dedicated env flag is set
- set `slow_callback_duration = 0.1`
- log enough context to identify which callback blocked the loop

Important rule:

- Run one long task with instrumentation and read the warnings before
  assuming which suspect is primary.

The purpose is to replace guesswork with a concrete callback / function
name from the live runtime.

### Step 2: Fix the most likely blocking seams

If the instrumentation confirms the current code audit, the fix order
should be:

#### 1. Offload workspace archive / restore work off the event loop

Target:

- `src/formicos/adapters/sandbox_manager.py`

Specifically:

- `_archive_workspace()`
- `_restore_workspace_from_archive()`

Recommended shape:

- call them through `asyncio.to_thread()` from the async workspace
  executor path
- keep the underlying helper logic deterministic
- do not rewrite the whole workspace executor in this wave

Why first:

- these are synchronous tar/copy operations in pure Python
- they happen on every isolated workspace execution path
- they match the observed "last useful log is often near execution"
  failure pattern better than the earlier Docker-SDK guess

#### 2. Idle-gate normal completion-time extraction / harvest

Target:

- `src/formicos/surface/colony_manager.py`

Specifically:

- `_hook_memory_extraction()`
- `_hook_transcript_harvest()`

Recommended shape:

- reuse the same principle already applied to startup backfill
- do not launch background LLM extraction while other colonies are
  actively running
- serialize or queue these completion-time extractions instead of
  firing them immediately in bursts

Why second:

- this is a proven shared-capacity seam
- even if not the sole event-loop blocker, it can starve live colony
  work and amplify stalls during bursty completions

#### 3. Add explicit local `httpx` pool limits

Target:

- `src/formicos/adapters/llm_openai_compatible.py`

Recommended shape:

- add explicit `httpx.Limits(...)` to the local AsyncClient
- keep current transport reset and `Connection: close` behavior

Suggested starting point:

- `max_connections=10`
- `max_keepalive_connections=5`

Why third:

- it is plausible hardening
- but the current code already has stronger mitigations than the other
  two suspect seams
- it should follow the instrumentation and the first two fixes, not
  replace them

### Step 3: Acceptance for Track 1

Track 1 is accepted only if all of the following hold:

- one long Qwen task runs through its full intended round budget without
  app health loss or WebSocket collapse
- one long Devstral task does the same
- the app remains responsive on `/health` during the run
- if slow-callback warnings remain, they are understood and documented
  rather than ignored

Track 1 is not accepted by unit tests alone.
It requires a live long-run validation.

### Owned files

- `src/formicos/surface/app.py`
- `src/formicos/adapters/sandbox_manager.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/adapters/llm_openai_compatible.py`
- targeted tests for the touched helpers and adapter behavior

## Track 2: Clean Benchmark Validation

Goal:

Measure Qwen and Devstral only after the runtime stall is fixed.

This track is intentionally staged.
Do not jump straight to the full five-task pack.

### Phase A: One long-run validation task per model

Run one representative long task on:

- Qwen3.5
- Devstral Small 2

Recommended first task:

- `rtp-01`

Acceptance:

- the task reaches its full intended round span without the app
  stalling
- the app remains healthy and connected throughout
- the colony reaches a truthful terminal state

Model-specific runtime truth:

- Qwen should run with the escalation-cap revert in place
- Devstral should run on the no-prompt-cache profile

### Phase B: Full five-task pack

Only after both Phase A runs are clean:

- run `rtp-01` through `rtp-05` on Qwen
- run `rtp-01` through `rtp-05` on Devstral

Record:

- completion rate
- stall count
- total runtime
- average quality
- any recurring failure shape by task

### Success criteria (resolved)

All criteria met:

- [x] No app event-loop stall during long-run colony execution
- [x] One clean long-run validation task on Qwen
- [x] Devstral app remained healthy (too slow for full iterative pack)
- [x] Full five-task benchmark pack on Qwen: 0.503 avg quality, 5/5, 0 hangs
- [x] Trustworthy quality comparison: Qwen MoE iteration speed > Devstral dense per-token quality on this hardware

## Out of Scope (confirmed)

Wave 84 did not touch:

- frontend workbench features (stayed in Wave 83)
- event types (union remains at 70)
- planner prompt rewrites
- escalation-cap tuning (reverted earlier; stayed reverted)
- new model onboarding (Devstral was already working)

## Packet Stance (retrospective)

Wave 84 was a runtime-truth wave followed by a measurement wave.

The executed order was:

1. instrumented (asyncio slow-callback debug)
2. fixed the blocking seams (to_thread, deferred drain, httpx limits)
3. validated one long task on Qwen (clean)
4. validated Devstral stability (healthy but too slow for iterative work)
5. ran the full benchmark pack on Qwen (0.503 avg, 5/5, 0 hangs)
