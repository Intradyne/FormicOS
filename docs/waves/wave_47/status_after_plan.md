# Wave 47: Final Status

**Date:** 2026-03-19
**Status:** Accepted. All Must items shipped. One Should item deferred.

---

## What shipped

### Team 1: Surgical Editing + Git Tools (Pillar 1 + Pillar 4)

| Item | Status | Notes |
|------|--------|-------|
| `patch_file` tool in `tool_dispatch.py` | Shipped | Registered with `write_fs` category |
| `patch_file` handler in `runner.py` | Shipped | Full failure contract: zero-match context, multi-match locations, atomic writes |
| `git_status` tool | Shipped | Structured porcelain output |
| `git_diff` tool | Shipped | Optional path filter and staged flag |
| `git_commit` tool | Shipped | Stage-all + commit, shell-safe quoting |
| `git_log` tool | Shipped | Default 10, capped at 50 |
| `git_branch` (stretch) | Deferred | Not implemented — stretch item |
| `git_checkout` (stretch) | Deferred | Not implemented — stretch item |
| Coder recipe updated | Shipped | All 5 tools added to Coder caste tool list and system prompt |
| Test coverage | Shipped | `test_patch_file.py` (393 lines), `test_git_tools.py` (290 lines) |

No new factory functions needed — `patch_file` uses `data_dir` for file
resolution; git tools delegate to the existing `workspace_execute_handler`.

### Team 2: Fast Path + Structural Context + Preview (Pillar 2 + 3 + 5)

| Item | Status | Notes |
|------|--------|-------|
| `fast_path` field on `ColonySpawned` | Shipped | `bool = False`, replay-safe via Pydantic default |
| `fast_path` in contracts | Shipped | `events.py` (core + docs), `types.ts` |
| Fast-path execution logic | Shipped | Skips convergence + pheromone; completes after first round |
| Per-round structural refresh | Shipped | Round 2+ for colonies with `target_files` |
| Visible `[Workspace Structure]` in prompt | Shipped | Budget-limited user message in round context |
| `preview=true` on `spawn_colony` | Shipped | Returns plan summary without dispatch |
| `preview=true` on `spawn_parallel` | Shipped | Returns DAG summary without dispatch |
| Frontend-derived round progress summary | Deferred | Optional item; deferred rather than expanding event model |
| Test coverage | Shipped | `test_wave47_fast_path.py` (389 lines) |

### Team 3: Recipes + Docs Truth

| Item | Status | Notes |
|------|--------|-------|
| `caste_recipes.yaml` updated | Shipped | Queen recipe: fast_path and preview guidance. Coder recipe: new tools documented (Team 1 added tool list entries) |
| `AGENTS.md` updated | Shipped | Tool count 15→20, new tool tables, Wave 47 feature sections, Coder caste tool list corrected |
| `OPERATORS_GUIDE.md` updated | Shipped | New sections: Surgical Editing, Git Workflow Primitives, Fast Path, Preview, Structural Context Refresh |
| Wave 47 status docs | Shipped | This file |

## What was deferred

| Item | Reason |
|------|--------|
| `git_branch` | Stretch item — not required for Wave 47 acceptance |
| `git_checkout` | Stretch item — not required for Wave 47 acceptance |
| Frontend-derived round progress summary | Optional; would have required event model growth or awkward frontend derivation |

## Acceptance gate status

| Gate | Result |
|------|--------|
| Gate 1: Surgical Editing Is Real | PASS — `patch_file` is a first-class tool with frozen failure contract |
| Gate 2: Fast Path Is Replay Truth | PASS — field on `ColonySpawned`, older events default to `false` |
| Gate 3: Structural Context Stays Current | PASS — per-round refresh for `target_files` colonies |
| Gate 4: Git Workflow Primitives Exist | PASS — 4 tools with structured output, no unsafe operations |
| Gate 5: Product Identity Holds | PASS — no benchmark-specific paths added |
| Gate 6: Preview Is Truthful | PASS — works on both spawn paths |
| Gate 7: Progress Summary Stays Bounded | PASS — deferred rather than expanding event model |
| Gate 8: Docs and Recipes Match Reality | PASS — this Team 3 pass |

## Scope notes

- No new event types added (contract preserved at 62)
- No new adapters or subsystems
- Fast path is a bounded mode inside the existing colony execution path, not a second engine
- Structural refresh is round-driven, catching `workspace_execute` changes
- Git tools use `shlex.quote()` for all shell arguments
- `patch_file` atomicity: partial failure leaves file unchanged
