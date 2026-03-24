# Wave 22 Planning Findings

**Wave:** 22 - "Trust the Product"  
**Date:** 2026-03-16  
**Purpose:** Repo-accurate observations from live operator use and code audit that shaped the Wave 22 plan.

---

## Finding 1: The Queen still cannot pass obvious spawn controls

`runtime.spawn_colony()` already accepts:

- `max_rounds`
- `budget_limit`
- `template_id`
- `strategy`

but the Queen's `spawn_colony` tool still does not expose or pass them through.

Implication:

- trivial tasks inherit the same heavy defaults as complex tasks
- this is the clearest source of bad Queen judgment today

## Finding 2: The Queen prompt lags the live tool surface

The Queen now has 16 tools and `_MAX_TOOL_ITERATIONS = 7`, but the prompt/recipe guidance still under-teaches:

- team composition
- resource allocation
- template usage
- newer tool usage

Implication:

- the Queen has enough capability to act better than she currently does
- Wave 22 should fix guidance before inventing new control surfaces

## Finding 3: AG-UI still defaults to a single coder

The AG-UI run surface still defaults to a single coder when no castes are supplied.

Implication:

- even after Wave 21, one external entry path still bakes in a weak default
- Wave 22 should raise that floor

## Finding 4: Colony scratch memory still bleeds across the workspace

`memory_write` still writes to the workspace collection, and `memory_search` still reads the shared workspace collection back.

Implication:

- one colony's scratchpad can leak into another colony's task
- the current behavior is convenient, but not trustworthy

## Finding 5: The right scoped-memory fix does not require a port change

The current VectorPort API is already collection-scoped, and Qdrant creates collections on demand.

Implication:

- Wave 22 can implement scratch isolation by convention alone
- `scratch_{colony_id}` is enough for this wave
- a deeper namespace redesign can wait

## Finding 6: Queen memory search should remain workspace-scoped

The Queen is not a colony and should not implicitly search colony-private scratch collections.

Implication:

- Queen `search_memory` should stay on:
  - workspace memory
  - skill bank
- the docs should make that scope explicit

## Finding 7: Workspace files exist, but workspace knowledge ingestion still does not

The app already supports workspace file upload and preview, but those files are not automatically embedded into searchable workspace memory.

Implication:

- the right Wave 22 step is explicit operator-triggered ingestion
- not silent auto-embedding of every uploaded file

## Finding 8: Colony detail currently makes workspace files look suspicious

Every colony in a workspace shows the same workspace files, which is technically truthful but operator-confusing.

Implication:

- UI scope labels matter here
- "Colony Uploads" vs "Workspace Library" is the right clarification

## Finding 9: `queen_note` is still workspace-scoped on disk

Wave 21 introduced bounded Queen notes, but storage is still workspace-scoped.

Implication:

- notes can bleed across threads
- Wave 22 should move the storage path to a thread-scoped location
- this requires a thread-id-aware handler path, not just a helper-string rename

## Finding 10: Several frontend trust breaks are low-LOC fixes

The following issues are all real but mechanically straightforward:

- raw ISO timestamps
- tiny tree-toggle target
- no Queen pending state
- misleading zero-valued cloud spend displays

Implication:

- Wave 22 does not need a frontend redesign
- it needs targeted truth/usability fixes

## Finding 11: Round history still underplays the actual output

The current round-history experience is more log-shaped than outcome-shaped.

Implication:

- the UI should lead with final output and push chronological detail lower
- this is a presentation problem, not a new data problem

## Finding 12: The repo-root `AGENTS.md` was still on Wave 21

The coordination file had not yet been updated to the Wave 22 ownership and overlap model.

Implication:

- the Wave 22 docs and dispatch prompts should not assume a stale root coordination file
- updating root `AGENTS.md` is part of making the Wave 22 handoff usable
