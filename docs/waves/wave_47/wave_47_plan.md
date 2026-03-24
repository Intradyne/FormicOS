# Wave 47 -- The Fluent Colony

**Theme:** Coding ergonomics and execution fluency. Better hands, not more
brains. Plus the smallest operator-experience improvements that naturally
fall out of this work.

**Identity test:** Every Must item passes: "Would a real operator want this if
the benchmark disappeared tomorrow?"

**Prerequisite:** Wave 46 accepted. Event union remains at 62. The Forager
operator surface is live. The eval harness is truthier and cleaner, but
measurement remains a separate concern from this wave.

**Contract:**

- No new event types. One additive field on `ColonySpawned` is allowed if
  `fast_path` needs replay-safe truth.
- No new adapters or subsystems.
- No architecture rewrites.
- No benchmark-specific core paths or task-specific heuristics.
- New tools follow the existing `tool_dispatch.py` registration pattern.
- The colony model stays. This wave adds a lighter execution path alongside
  it for simple tasks.

## Why This Wave

The colony can already plan, coordinate, forage, learn, and report. But the
developer-facing surface is still awkward in the places where coding agents
spend their time:

- a Coder rewriting a whole file to change a few lines
- a simple one-file task paying full colony overhead
- structural context going stale as the workspace changes
- git operations being rebuilt as shell strings on every task

These are ergonomic gaps, not architectural ones. Wave 47 makes the system
materially better at editing code, running tests, iterating, and preparing
real developer work.

## Repo Truth At Wave Start

Grounded against the live post-Wave-46 tree:

- `write_workspace_file` still performs full-file replacement.
- no `patch_file` / search-replace tool exists in the engine tool surface.
- coding colonies can mutate files through both explicit file tools and
  `workspace_execute`.
- structural context exists, but is computed at colony start and does not
  refresh per round.
- the Queen can estimate cost during planning, but that estimate is not yet a
  clean pre-dispatch operator preview on both spawn paths.
- the product still relies on generic shell execution for git tasks.

## Pillar 1: Surgical Editing Tool

**Class:** Must

**Identity test:** Every developer wants precise edits. Nobody wants to
rewrite a whole file to change an import.

### The gap

`write_workspace_file` writes full file content. For large files, this burns
tokens, invites copy errors, and makes iterative editing clumsy.

### The solution

Add a `patch_file` tool:

```text
patch_file(
  path,
  operations: [{search: "...exact text...", replace: "...replacement..."}]
)
```

### Frozen failure contract

- Zero matches: error with closest nearby match, line numbers, and surrounding
  context.
- Multiple matches: error listing all matching locations with line numbers.
- Operations apply sequentially against the in-memory buffer.
- Empty `replace` means deletion.
- The file is written only if all operations succeed.
- Any failure leaves the file unchanged and reports the failing operation.

### Seams

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `config/caste_recipes.yaml`
- `tests/unit/engine/test_patch_file.py`

### Developmental eval

After landing, compare a small set of editing tasks with and without
`patch_file` available:

- tokens per edit
- edit corruption rate
- iterations to correct a mismatch

This is a developmental check, not benchmark work.

## Pillar 2: Solo-Worker Fast Path

**Class:** Must

**Identity test:** Most real tasks are simple. Operators feel the colony
overhead on every quick fix.

### The gap

Simple coding work still pays for multi-agent topology, pheromone routing,
convergence scoring, and related overhead that only helps when coordination is
actually needed.

### Replay-safe truth requirement

If the Queen chooses `fast_path` at spawn time, replay must preserve that
choice. This makes `fast_path` a spawn-truth concern, not a local runner-only
flag.

The intended shape is an additive `fast_path: bool = False` field on
`ColonySpawned`, mirrored anywhere the event contract is duplicated:

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- frontend/store typing that depends on the spawn shape

Older events without the field must replay as `fast_path=False`.

### The solution

When the Queen assesses a task as simple, she may choose `fast_path=True`.
That execution mode should:

- stay single-agent
- skip multi-agent topology construction
- skip pheromone routing
- skip convergence scoring and similar coordination-only overhead
- preserve normal event emission
- preserve knowledge extraction on completion

This is not a separate engine. It is a bounded mode inside the existing colony
execution path.

### Scope guard

If the runner changes begin to sprawl, the minimum truthful version is:

- single-agent only
- skip pheromone update
- skip convergence scoring

That still delivers most of the benefit without turning into a runner rewrite.

### Seams

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/engine/runner.py`
- frontend/store typing that mirrors spawn truth
- tests for replay and fast-path flow

## Pillar 3: Structural Context Refresh

**Class:** Should

**Identity test:** Multi-file editing needs current structure, not stale
structure from colony start.

### The correction from review

Refreshing only after `write_workspace_file` or `patch_file` is not enough.
Agents can change the workspace through `workspace_execute` too.

### The solution

Structural refresh is round-driven and hard-bounded:

- only colonies with non-empty `target_files` pay the cost
- at round start, recompute structural context for the current workspace
- regenerate the compact relevant context for the current target files
- inject that refreshed structure into the round context

This keeps the workspace view current without spreading re-analysis into
non-coding colonies.

### Explicit prompt visibility

The Coder should see structural context in the round prompt as a visible
"Workspace Structure" section, not only as opaque colony metadata.

### Seams

- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- `src/formicos/surface/colony_manager.py`
- `tests/unit/engine/test_structural_refresh.py`

## Pillar 4: Git Workflow Primitives

**Class:** Should

**Identity test:** Every developer works in git. Shell-string construction for
common git tasks is friction that adds nothing.

### The solution

Add thin, structured wrappers over common workspace git operations:

- `git_status()`
- `git_diff(path?)`
- `git_commit(message)`
- `git_log(n?)`

Optional stretch:

- `git_branch(name)`
- `git_checkout(branch)`

### Safety

Wave 47 excludes:

- remote push/pull/fetch
- force operations
- rebase/cherry-pick/reset workflows

### Seams

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `config/caste_recipes.yaml`
- `tests/unit/engine/test_git_tools.py`

## Pillar 5: Operator Experience Frontloading

**Class:** Should

These are the smallest operator-facing improvements that naturally fall out of
Wave 47 substrate work. They are bounded and additive.

### 5A. Preview before dispatch

Preview should work on both spawn paths:

- `spawn_colony(preview=true)`
- `spawn_parallel(preview=true)`

The result should return the plan/summary without dispatching work. This is
where fast-path estimates and cost previews belong.

### 5B. Fast-path estimate

When preview shows a fast-path colony, include a simple bounded estimate such
as cost/round hints and a coarse time expectation.

### 5C. Round progress summary

Wave 47 does **not** add a new `RoundCompleted` event field by default.
Instead, any progress summary should be frontend-derived from existing
projection/transcript/runtime state after normal stream updates.

If a truthful, bounded frontend-derived summary proves too awkward during the
wave, this item should defer to Wave 48 rather than expanding the event model
casually.

### Seams

- `src/formicos/surface/queen_tools.py`
- frontend store/detail views for preview/progress
- runtime/view glue only if needed for bounded response shaping

## Priority Order

| Priority | Item | Pillar | Class |
|----------|------|--------|-------|
| 1 | `patch_file` surgical editing | 1 | Must |
| 2 | replay-safe `fast_path` | 2 | Must |
| 3 | per-round structural refresh | 3 | Should |
| 4 | explicit structural context in round prompt | 3 | Should |
| 5 | `git_status` and `git_diff` | 4 | Should |
| 6 | `git_commit` and `git_log` | 4 | Should |
| 7 | preview on both spawn paths | 5 | Should |
| 8 | fast-path estimate in preview | 5 | Should |
| 9 | frontend-derived round progress summary | 5 | Should |
| 10 | `git_branch` and `git_checkout` | 4 | Stretch |

## Team Assignment

### Team 1: Surgical Editing + Git Tools

Owns Pillar 1 and Pillar 4.

Primary files:

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- tests for new tool handlers

Team 1 adds tool specs and handler functions. They should not modify the core
execution loop.

### Team 2: Fast Path + Structural Context + Preview

Owns Pillar 2, Pillar 3, and Pillar 5.

Primary files:

- `src/formicos/core/events.py`
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/engine/runner.py`
- `src/formicos/engine/context.py`
- frontend/store/detail files needed for preview/progress truth

Team 2 modifies spawn/replay truth and round execution behavior.

### Team 3: Recipes + Docs Truth

Owns:

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_47/*`

Team 3 updates recipe text, operator-facing explanation, and wave docs after
Teams 1 and 2 land the substrate.

## Overlap Rules

- `src/formicos/engine/runner.py`
  Team 1 owns new tool handlers only.
  Team 2 owns round logic and fast-path behavior only.

- `config/caste_recipes.yaml`
  Team 3 owns both prompt text and allowlist edits to keep this file
  single-owner during the wave.

## What Wave 47 Does Not Include

- no new event types
- no new adapters or subsystems
- no benchmark-specific logic
- no Playwright or browser automation
- no new foraging capabilities
- no contradiction or memory-substrate redesign
- no measurement/publication work
- no Queen planning rewrite
- no multi-agent routing redesign outside bounded single-agent fast path
- no remote git operations
- no directive UX overhaul
- no unified audit timeline
- no partial file-content streaming

## Smoke Test

1. `patch_file` replaces exact text correctly in a workspace file.
2. `patch_file` returns a clear zero-match error with context.
3. `patch_file` returns a clear multiple-match error with locations.
4. multi-operation `patch_file` calls apply sequentially and write atomically.
5. `ColonySpawned` carries `fast_path`, and older events replay as `False`.
6. single-agent `fast_path=True` colonies skip coordination-only overhead.
7. fast-path colonies still emit normal events and extract knowledge.
8. structural context refreshes between rounds when `target_files` exist.
9. Coder round prompts include a visible structural-context section.
10. `git_status` returns structured output from a dirty workspace.
11. `git_diff` returns useful diff output for changed files.
12. `git_commit` stages and commits workspace changes.
13. preview on both spawn paths returns a plan without dispatching.
14. any progress summary shipped in Wave 47 is frontend-derived and bounded.
15. full CI remains clean.

## After Wave 47

The colony is fluent at coding. Coders can make surgical edits instead of
rewriting entire files. Simple tasks can avoid unnecessary coordination
overhead. Structural context stays current while coding work progresses. Git
operations become first-class tools instead of repeated shell-string assembly.

Wave 48 can then focus on operator ergonomics from a much stronger base:
directive UX, richer progress streaming, unified audit surfaces, and polished
preflight confirmation flows.

**empower -> deepen -> harden -> forage -> complete -> prove -> fluency**
