## Role

You own the Wave 47 Team 1 implementation track.

This is the tool-surface track. Your job is to make coding agents more fluent
with better editing and git primitives, not to redesign colony execution.

## Mission

Land the two tool-oriented Wave 47 capabilities:

1. `patch_file` as a first-class surgical editing tool
2. bounded git workflow primitives as first-class tools

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Precise file edits and structured git operations help normal developer
work every day.

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_47/wave_47_plan.md`
4. `docs/waves/wave_47/acceptance_gates.md`
5. `src/formicos/engine/tool_dispatch.py`
6. `src/formicos/engine/runner.py`
7. `config/caste_recipes.yaml`

## Owned Files

- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- tests for the new tool handlers

## Do Not Touch

- `src/formicos/core/events.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/engine/context.py`
- frontend files
- docs files
- `config/caste_recipes.yaml` prompt prose

Team 3 owns the recipe text. If a mechanical allowlist edit is needed in
`config/caste_recipes.yaml`, reread the latest file first and keep the edit
minimal.

## Required Work

### Track A: `patch_file`

Add a first-class `patch_file` tool following the existing engine tool pattern.

Target shape:

```text
patch_file(path, operations=[{search, replace}, ...])
```

Required semantics:

- sequential operations against the updated in-memory buffer
- atomic write only after all operations succeed
- empty `replace` means deletion

Required failure contract:

- zero matches -> error with nearby context, line numbers, and the closest
  useful match signal you can provide truthfully
- multiple matches -> error listing all match locations with line numbers
- any failed operation aborts the whole call with no file write

This contract is not optional. The ability for agents to self-correct after a
mismatch is the point of the tool.

### Track B: Git Primitives

Add thin registered tools for the safe subset:

- `git_status`
- `git_diff`
- `git_commit`
- `git_log`

Desired behavior:

- bounded/structured output where useful
- workspace-local execution only
- no remote operations
- no force/rebase/reset workflow in this wave

If you include `git_branch` / `git_checkout`, treat them as stretch only after
the core set is solid.

## Hard Constraints

- No new event types
- No new adapters or subsystems
- No benchmark-specific shortcuts
- No changes to colony execution/replay behavior
- Do not turn git tools into a broad VCS subsystem

## Overlap Rules

- In `src/formicos/engine/runner.py`, stay in the tool-handler section.
- Do not modify round execution, fast-path logic, or structural-context logic.
- If you must touch `config/caste_recipes.yaml`, limit yourself to minimal
  allowlist changes and reread the file first so you do not clobber Team 3.

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. targeted unit tests for patch-file and git-tool behavior
3. any broader engine test slice needed if shared dispatch behavior changes

## Summary Must Include

- the exact `patch_file` failure contract you implemented
- the exact git tools that landed
- any stretch git items you deferred
- anything you deliberately kept out to stay bounded
