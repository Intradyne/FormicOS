# Wave 4 Summary

**Completed:** 2026-03-12
**Stream:** F - Surface commands and colony-detail views
**Validation at delivery:** Reported green on `ruff`, `pyright --strict`, layer lint, and surface unit tests

## What shipped

### Surface source
- `src/formicos/surface/view_models.py` (112 LOC) - derived colony-detail, approval-queue, round-history, and workspace-colony helpers.
- `src/formicos/surface/commands.py` (235 LOC) - typed command handlers for the frozen WebSocket command vocabulary and shared operator actions.

### Tests
- `tests/unit/surface/test_view_models.py` (126 LOC) - view-model derivation coverage and command-surface expectations.

## LOC accounting

| Area | LOC |
|---|---:|
| Surface source | 347 |
| Surface tests | 126 |
| Wave total | 473 |

The source budget landed modestly above the original 250 LOC target because the full command vocabulary was implemented instead of stubbing edge cases.

## Decisions made

1. **Commands emit events; they do not mutate projections directly.** `commands.py` treats the event store as the write seam and leaves read-model updates to projection replay/application.
2. **View models stay projection-backed.** Colony detail, approvals, and round history are derived convenience shapes, not a parallel state container.
3. **The command vocabulary matches the frozen TypeScript contract.** No protocol-only commands were added on the Python side.

## Issues found

- Command execution depended on the Wave 3 WebSocket bridge being wired correctly; that integration seam was closed in the final pass.
- Full behavior validation for operator flows was deferred to the feature suite once T1 and T2 had both landed.
