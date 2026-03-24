# ADR-037: Scoped Colony Scratch Memory

**Status:** Accepted  
**Date:** 2026-03-16  
**Wave:** 22

## Decision

Adopt per-colony scratch memory collections using the naming convention:

- `scratch_{colony_id}`

Colony memory behavior becomes:

- colony scratch writes -> `scratch_{colony_id}`
- colony memory search -> `scratch_{colony_id}` + workspace memory + skill bank
- Queen memory search -> workspace memory + skill bank only

No VectorPort API change is required.

## Context

Before Wave 22:

- colony `memory_write` wrote into the shared workspace collection
- colony `memory_search` read the shared workspace collection back

That meant one colony's working notes could immediately leak into another colony's task if they shared a workspace. For a system built to manage many distinct tasks, that is the wrong default.

The live adapter and port surfaces already support collection-scoped reads and writes. The defect is in collection choice, not in infrastructure capability.

## Design

Wave 22 uses collection naming convention rather than a new namespace/filtering abstraction.

The collection rules are:

- `scratch_{colony_id}` is colony-private scratch memory
- `workspace_id` remains workspace-shared library memory
- skill bank remains the skill-bank collection

Read layering becomes:

1. colony scratch
2. workspace library
3. skill bank

The Queen remains outside colony-private scratch scope by default.

## Consequences

- colony scratch stops bleeding across unrelated colony work
- workspace-shared knowledge remains available where it should be
- no port or adapter changes are needed
- Qdrant will accumulate one scratch collection per colony until later cleanup tooling exists

## Rejected Alternatives

**Keep workspace-wide scratch memory**  
Rejected. It is convenient but untrustworthy.

**Add a new VectorPort namespace/filter API now**  
Rejected for Wave 22. It is a larger architectural move than needed for the current problem.

**Let the Queen search colony scratch by default**  
Rejected. Colony-private scratch and Queen/shared-memory recall should remain distinct.

## Implementation Note

See:

- `docs/waves/wave_22/plan.md`
- `docs/waves/wave_22/algorithms.md`
