## Role

You own the Wave 47 Team 2 implementation track.

This is the execution-fluency and bounded operator-preview track. Your job is
to make simple coding tasks cheaper to run, structural context more current,
and previews more honest.

## Mission

Land the replay-safe and round-execution parts of Wave 47:

1. replay-safe `fast_path`
2. round-driven structural context refresh
3. bounded preview support on both spawn paths
4. frontend-derived progress summary only if it stays truthful and small

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Faster simple-task execution, fresher coding context, and better operator
previews help arbitrary real work.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_47/wave_47_plan.md`
4. `docs/waves/wave_47/acceptance_gates.md`
5. `src/formicos/core/events.py`
6. `src/formicos/core/types.py`
7. `docs/contracts/events.py`
8. `docs/contracts/types.ts`
9. `src/formicos/surface/runtime.py`
10. `src/formicos/surface/projections.py`
11. `src/formicos/surface/colony_manager.py`
12. `src/formicos/surface/queen_tools.py`
13. `src/formicos/engine/runner.py`
14. `src/formicos/engine/context.py`
15. frontend/store/detail files related to colony status and preview

## Owned Files

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- frontend/store typing that mirrors spawn truth
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- frontend/store/detail files needed for truthful preview/progress behavior
- tests for replay, fast path, structural refresh, and preview behavior

## Do Not Touch

- `src/formicos/engine/tool_dispatch.py`
- tool-handler-only sections of `src/formicos/engine/runner.py`
- docs files under `docs/waves/wave_47/`
- `config/caste_recipes.yaml`

## Required Work

### Track A: Replay-safe `fast_path`

`fast_path` must be preserved through spawn/replay truth.

Expected shape:

- additive `fast_path: bool = False` field on `ColonySpawned`
- matching contract mirrors updated
- runtime/spawn tools can request it
- projections persist it
- replay of older event logs defaults safely to `False`

Implementation note:

- `docs/contracts/types.ts` may contain a duplicated `ColonySpawnedEvent`
  interface. When adding `fastPath`, check both occurrences and fix any
  duplication rather than updating only one copy.

Execution behavior:

- bounded to simple/single-agent use
- skip coordination-only overhead
- do not create a second execution engine
- preserve normal event emission and knowledge extraction

If implementation starts sprawling, the minimum viable truthful version is:

- single-agent only
- skip pheromone updates
- skip convergence scoring

### Track B: Structural Context Refresh

The agreed correction is:

- refresh is round-driven, not tool-write-driven
- only colonies with non-empty `target_files` pay this cost

Required outcome:

- at round start, refresh structural context from the current workspace
- inject a visible structural section into the Coder round context
- ensure changes made through `workspace_execute` are naturally covered

Implementation note:

- `src/formicos/engine/context.py` currently does not reference
  `structural_context` at all.
- the field already exists on `ColonyContext` in `src/formicos/core/types.py`
  and is populated by `src/formicos/surface/colony_manager.py`
- you are adding the first prompt injection point, not modifying an existing
  structural-context block

Do not broaden this into whole-workspace constant analysis for every colony.

### Track C: Preview on Both Spawn Paths

Preview must work on:

- `spawn_colony(preview=true)`
- `spawn_parallel(preview=true)`

Preview returns a truthful plan/summary without dispatching work.

If you include fast-path-specific time hints, keep them obviously coarse.

### Track D: Progress Summary

This is explicitly lower priority than Tracks A-C.

If you can ship a bounded, frontend-derived progress summary from existing
truth, do it. If not, defer honestly.

Hard rule:

- do not casually expand `RoundCompleted` just to get a nicer status line

## Hard Constraints

- No new event types
- No architecture rewrite
- No benchmark-specific execution paths
- No unbounded event-model expansion
- No fake preview support for paths that do not really honor preview

## Overlap Rules

- In `src/formicos/engine/runner.py`, own round logic, fast-path behavior,
  and structural refresh only.
- Do not edit Team 1's tool-handler section beyond what is absolutely required
  for shared imports/types.
- If you need frontend work, keep it bounded to preview/progress surfaces and
  reread the latest files first.

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. targeted tests for replay-safe fast path
3. targeted tests for structural refresh and prompt/context inclusion
4. targeted tests for preview behavior on both spawn paths

If progress summary lands, add targeted frontend/store coverage for that too.

## Summary Must Include

- exactly where `fast_path` is persisted for replay
- what fast-path execution skips and what it still preserves
- how structural refresh is bounded
- whether preview works on both spawn paths
- whether progress summary shipped or was deferred
- what you deliberately kept out to stay bounded
