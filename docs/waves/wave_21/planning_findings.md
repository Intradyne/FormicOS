# Wave 21 Planning Findings

**Wave:** 21 - "Alpha Complete"  
**Date:** 2026-03-16  
**Purpose:** Repo-accurate observations that shaped the Wave 21 plan.

---

## Finding 1: Wave 20 exposed real truth-surface drift

Wave 20 required live corrections across:

- backend protocol status
- frontend types
- docs/contracts types
- AG-UI event glossary

The specific bug pattern was consistent: the same truth existed in multiple places and drifted.

Implication:

- a capability registry plus manifest-based parity is not abstract cleanup
- it directly addresses a problem that just happened

## Finding 2: `input_sources` still is not persisted on `ColonyProjection`

The `ColonySpawned` event carries `input_sources`, but `ColonyProjection` does not persist it today.

Current consequence:

- transcripts expose `input_sources` through a `getattr(..., [])` fallback
- chained-colony transcript attribution can still be silently empty

Implication:

- Track C should not overstate transcript completeness until this is fixed
- the fix is small and belongs in Wave 21 core, not stretch

## Finding 3: Queen tool surface is solid but still asymmetric with the UI

Current Queen strengths:

- spawn
- inspect
- redirect
- escalate
- suggest/approve config change
- list templates/skills
- read workspace files

Current Queen gaps:

- no full round/agent output access
- no semantic memory search
- no bounded persistent note memory
- no artifact-writing path

Implication:

- the proposed four new Queen tools are grounded and high-value
- they close actual operator-facing gaps rather than inventing novelty

## Finding 4: `_MAX_TOOL_ITERATIONS = 5` is now tight

With the current tool count, five iterations is enough for a short interaction but tight for compound flows.

Example:

- `search_memory`
- `inspect_colony`
- `read_colony_output`
- `write_workspace_file`
- final response

Implication:

- raising the cap to 7 is a reasonable Wave 21 default
- model-aware scaling is optional, not required

## Finding 5: The memory-search pattern already exists

The runner already uses a simple two-collection search shape:

- skill bank collection
- workspace memory collection

That is exactly the behavior the Queen needs.

Implication:

- `search_memory` should reuse that pattern
- Wave 21 should not introduce a separate retrieval architecture for the Queen

## Finding 6: Workspace file semantics are already mostly established

The HTTP workspace file surface already uses:

- `data/workspaces/{workspace_id}/files/`

The current Queen `read_workspace_files` tool is a little broader than that surface.

Implication:

- `write_workspace_file` should write into the existing `files/` directory
- while touching Queen file tooling, Wave 21 should prefer one coherent workspace-files story

## Finding 7: The event union is still 37 members

Wave 21 does not need new runtime events.

Implication:

- the wave should focus on inventories/manifests, not event expansion
- `EVENT_TYPE_NAMES` can stay simple and explicit

## Finding 8: AG-UI already has a clean manifest source

`AGUI_EVENT_TYPES` already exists as a concrete exported set.

Implication:

- the registry should consume it directly
- there is no need to infer AG-UI capabilities indirectly

## Finding 9: `app.py` is still the biggest structural hotspot

Post-Wave-20 `app.py` still carries multiple unrelated responsibilities:

- factory wiring
- lifespan
- REST routes
- file/export routes
- protocol routes
- health/debug
- static frontend mount

Implication:

- Track B is overdue and worthwhile
- but it should stay mechanical and behavior-preserving

## Finding 10: The transcript builder is the right pattern to repeat

`transcript.py` is a good example of the repo's healthier direction:

- pure builder
- no internal HTTP dependency
- multiple consumers
- graceful fallbacks

Implication:

- the registry and evaluation reporting should follow this pattern
- prefer shared builders/manifests over surface-specific formatting logic

## Finding 11: Recent Wave 20 acceptance was strong, but this docs pass did not re-run every uv-backed tool

Recent reports indicate:

- full pytest suite green
- frontend build green
- Wave 20 smoke work completed successfully

In this docs-only pass, local direct `ruff`/`pyright` commands were not available in PATH, and `uv` cache permissions prevented easy re-verification from this shell.

Implication:

- the docs should describe Wave 21 as building on the accepted Wave 20 baseline
- they should not pretend this planning pass independently revalidated every implementation tool
