# Wave 04 Plan

## Goal
Finish the operator's core working surfaces: colony detail, approvals, and the
thread-to-colony execution flow.

## Dependency gate
Requires Wave 03 outputs from Streams F and D.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| D - Frontend | `frontend/src/components/colony-detail.ts`, `frontend/src/components/queen-overview.ts`, `frontend/src/components/breadcrumb-nav.ts`, `frontend/src/components/approval-queue.ts`, `frontend/src/components/round-history.ts` | `src/formicos/*` |
| F - Surface | `src/formicos/surface/view_models.py`, `src/formicos/surface/commands.py`, `tests/unit/surface/test_view_models.py` | core/, engine/, adapters/, frontend/ |

## LOC budget
- Stream D: <= 900 LOC
- Stream F: <= 250 LOC
- Wave total target: <= 1,150 LOC

## Stream D Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-003, `docs/contracts/types.ts`, and `docs/prototype/README.md`.
- Read `docs/prototype/ui-spec.jsx`.
- Read `docs/specs/round_execution.feature`, `docs/specs/approval_workflow.feature`, and `docs/specs/thread_workspace.feature`.

### Task
Implement the colony detail and Queen overview surfaces with topology, pheromone state, approvals, and round history.

### Produce
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/breadcrumb-nav.ts`
- `frontend/src/components/approval-queue.ts`
- `frontend/src/components/round-history.ts`

### Constraints
- Reuse existing store and transport modules.
- Keep each component <= 200 lines where practical; split when needed.
- Match contract field names exactly.

### Verify
- `npm run build`

## Stream F Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-001, ADR-005, and `docs/contracts/types.ts`.
- Read the same feature files as Stream D.

### Task
Expose surface-level view-model helpers and command handlers needed by the new operator surfaces without leaking adapter details to the browser.

### Produce
- `src/formicos/surface/view_models.py`
- `src/formicos/surface/commands.py`
- `tests/unit/surface/test_view_models.py`

### Constraints
- Surface view models are projections, not a second source of truth.
- Commands must map to existing engine/surface operations only.

### Verify
- `python -m py_compile src/formicos/surface/view_models.py src/formicos/surface/commands.py`
- `pytest tests/unit/surface/test_view_models.py -q`

## Acceptance criteria
- `docs/specs/round_execution.feature`
- `docs/specs/approval_workflow.feature`
- `docs/specs/merge_prune_broadcast.feature`
