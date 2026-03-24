# Wave 07 Plan

## Goal
Run the final hardening pass: LOC-budget checks, import-boundary checks, restart
recovery checks, and Phase 3 readiness review.

## Dependency gate
Requires Wave 06 green.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| I - Integration | `tests/contract/test_loc_budget.py`, `tests/unit/test_restart_recovery.py`, `tests/unit/test_layer_boundaries.py`, `docs/waves/PROGRESS.md`, `docs/waves/wave_07/summary.md` | frozen contracts, production code except bug fixes explicitly assigned by operator |

## LOC budget
- Stream I: <= 300 LOC of new test/doc code

## Stream I Dispatch
### Context
- Read `CLAUDE.md`, `AGENTS.md`, ADR-006, `docs/waves/PROGRESS.md`, and all wave plans/summaries.
- Read the full test suite and current source tree.

### Task
Prove the implementation is ready for Phase 3 completion and document any residual risks.

### Produce
- `tests/contract/test_loc_budget.py`
- `tests/unit/test_restart_recovery.py`
- `tests/unit/test_layer_boundaries.py`
- `docs/waves/PROGRESS.md`
- `docs/waves/wave_07/summary.md`

### Constraints
- No new product features in this wave.
- If a bug fix is required to make the gate pass, keep it minimal and document it.
- Preserve the <=15K LOC ceiling across `src/formicos/{core,engine,adapters,surface}`.

### Verify
- `ruff check src/`
- `pyright src`
- `python scripts/lint_imports.py`
- `pytest`

## Acceptance criteria
- All feature specs pass
- Layer boundaries remain clean
- LOC budget remains within the hard cap
