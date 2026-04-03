# Wave 84 Team A Prompt

## Outcome (2026-04-01)

All phases completed:

1. Instrumented asyncio slow-callback debug (opt-in via `FORMICOS_ASYNCIO_DEBUG`).
2. Fixed 3 blocking seams: `to_thread` for archive/restore, deferred post-colony drain, explicit httpx limits.
3. Qwen long-run validation: clean, no stalls.
4. Devstral: app healthy, too slow for iterative colony work on this hardware.
5. Full benchmark: 0.503 avg quality, 5/5 tasks, 0 hangs, ~16 min.

---

*Original dispatch prompt preserved below.*

## Mission

Own Wave 84 end to end:

1. instrument the event-loop stall
2. fix the blocking seam the runtime data identifies
3. prove the fix with one long validation task on Qwen
4. prove the fix with one long validation task on Devstral
5. only then run the full benchmark pack

This is a single-owner sequential packet.
Do not split diagnosis, fix, and validation into separate handoffs.

This is not a feature wave.
It is a runtime-truth wave followed by a measurement wave.
Do not broaden scope into planner work, frontend work, or new subsystems.

## Owned Files

- `src/formicos/surface/app.py`
- `src/formicos/adapters/sandbox_manager.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/adapters/llm_openai_compatible.py`
- `tests/unit/adapters/test_sandbox_manager.py`
- `tests/unit/surface/test_colony_manager.py`
- `tests/unit/adapters/test_llm_openai_compatible.py`
- `docs/waves/wave_84/wave_84_plan.md`

## Do Not Touch

- `src/formicos/engine/runner.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/planning_brief.py`
- `src/formicos/surface/planning_signals.py`
- frontend components
- workbench and plan-pattern surfaces

The escalation-cap experiment is already settled for this wave.
Do not reopen it here.

## Repo Truth To Read First

1. `src/formicos/adapters/sandbox_manager.py`

   `_archive_workspace()` and `_restore_workspace_from_archive()` are
   synchronous Python tar/copy helpers.
   They are called from the async workspace-execution path today.

2. `src/formicos/surface/colony_manager.py`

   `_hook_memory_extraction()` and `_hook_transcript_harvest()` are
   fire-and-forget completion hooks.
   They do not hard-deadlock the colony directly, but they can steal
   local LLM capacity at exactly the wrong time.

3. `src/formicos/surface/app.py`

   Startup backfill is already serialized and idle-gated.
   That is the pattern to reuse if normal completion-time extraction
   also needs gating.

4. `src/formicos/adapters/llm_openai_compatible.py`

   The local adapter already has:

   - semaphore throttling
   - `Connection: close`
   - transport reset / retry
   - bounded `resp.json()`

   Explicit `httpx` pool limits are still a plausible hardening step,
   but they are not the first assumed root cause.

## The Rule For This Packet

Instrument first.
Read the slow-callback data.
Then fix what the data shows.

If the warnings point somewhere other than archive / restore or the
completion hooks, follow the instrumentation and document the divergence.
Do not blindly implement the predicted order if the runtime evidence says
something else.

## Phase 1: Instrument Before Changing Behavior

Add asyncio slow-callback instrumentation at app startup.

Recommended shape:

- gate it behind a dedicated env flag such as
  `FORMICOS_ASYNCIO_DEBUG`
- enable loop debug only when that flag is on
- set `slow_callback_duration = 0.1`
- log enough callback context to identify the blocking function

Sketch:

```python
if os.environ.get("FORMICOS_ASYNCIO_DEBUG", "").lower() in ("1", "true", "yes"):
    loop = asyncio.get_running_loop()
    loop.set_debug(True)
    loop.slow_callback_duration = 0.1
```

Use one long real task to gather evidence before changing the hot path.
Recommended first task: `rtp-01`.

Deliverable from this phase:

- the actual callback / function names that block the loop
- a short note in the wave docs if the live evidence differs from the
  predicted suspects

## Phase 2: Fix The Blocking Seam

If the instrumentation confirms the current audit, fix in this order.

### Fix 1: Move workspace archive / restore off the event loop

Target:

- `src/formicos/adapters/sandbox_manager.py`

The current call sites are in the async workspace executor.
Keep the helper logic deterministic.
Do not rewrite the whole executor.

Correct shape:

```python
workspace_archive = await asyncio.to_thread(_archive_workspace, work_path)
...
await asyncio.to_thread(_restore_workspace_from_archive, archive_bytes, work_path)
```

Why this is first:

- it is synchronous Python tar/copy work
- it sits directly in the async execution path
- it matches the observed stall shape better than the earlier Docker-SDK
  guess

### Fix 2: Idle-gate or serialize completion-time extraction / harvest

Target:

- `src/formicos/surface/colony_manager.py`

The current hooks are:

- `_hook_memory_extraction()`
- `_hook_transcript_harvest()`

Use the same principle already applied to startup backfill:

- do not launch background LLM extraction while live colonies are still
  active
- prefer a small queue, deferred retry, or drain-on-idle helper over
  bursty immediate `create_task()` calls
- use the real live-work signal in this manager
  (`self._active` / `self.active_count`), not an invented state bag

Sketch:

```python
if self.active_count > 0:
    self._queue_post_colony_work(...)
    return
```

Important nuance:

- this seam looks more like starvation / contention than a strict
  deadlock
- the goal is to keep completion-time LLM work from competing with live
  colonies during the exact period where the app is most fragile

### Fix 3: Add explicit local `httpx` limits

Target:

- `src/formicos/adapters/llm_openai_compatible.py`

Only do this after the first two fixes unless instrumentation clearly
points at the client pool.

Suggested starting point:

```python
limits=httpx.Limits(
    max_connections=10,
    max_keepalive_connections=5,
)
```

Keep the current local hardening behavior:

- `Connection: close`
- transport reset
- bounded response parsing

## Phase 3: Validation Gates

Unit tests are required, but they are not the acceptance gate.
This wave is accepted only by live long-run validation.

### Code/Test Validation

Add focused regressions for whichever seam you change.

Good examples:

- archive / restore call path uses `asyncio.to_thread()`
- completion hooks defer or queue work while live colonies remain active
- local adapter client factory applies explicit limits if you add them
- instrumentation stays gated behind the env flag

Run:

- `python -m py_compile src/formicos/surface/app.py src/formicos/adapters/sandbox_manager.py src/formicos/surface/colony_manager.py src/formicos/adapters/llm_openai_compatible.py`
- `python -m pytest tests/unit/adapters/test_sandbox_manager.py -q`
- `python -m pytest tests/unit/surface/test_colony_manager.py -q`
- `python -m pytest tests/unit/adapters/test_llm_openai_compatible.py -q`

### Live Validation: One Long Task Per Model

Do not jump straight to the full pack.

First run one long validation task on Qwen and one on Devstral.
Recommended first task: `rtp-01`.

Qwen truth for this wave:

- escalation-cap revert stays in place

Devstral truth for this wave:

- use the stable no-prompt-cache profile
- do not change the working Devstral runtime profile unless the stall
  diagnosis proves it is necessary

Acceptance for this phase:

- task reaches its intended round span
- app `/health` stays responsive
- WebSocket stream stays alive
- no mid-run freeze with idle LLM slots and dead app surface

If slow-callback warnings still appear after the fix:

- understand them
- decide whether they are benign or still blocking
- document the answer

## Phase 4: Full Benchmark Pack

Only after both long validation runs are clean:

- run `rtp-01` through `rtp-05` on Qwen
- run `rtp-01` through `rtp-05` on Devstral

Record at minimum:

- completion rate
- stall count
- total runtime
- average quality
- recurring failure shape by task

If the full pack still fails after Track 1 looks healthy, classify what
remains precisely:

- blocker
- runtime/deployment debt
- tuning debt

Do not blur those together.

## Expected Deliverables

1. The actual stall seam identified from live instrumentation
2. The minimal code fix that removes it
3. Focused regression coverage for the touched seam
4. One clean long-run validation task on Qwen
5. One clean long-run validation task on Devstral
6. Full-pack results only after the long-run gate passes

## Final Reminder

The prompt's predicted fix order is based on the current code audit.
It is not a substitute for the runtime evidence.

Instrument first.
Read the warnings.
Fix the blocking seam the data reveals.
