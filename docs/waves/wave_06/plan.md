# Wave 06 Plan

## Goal
Lock contract parity and end-to-end behavior with integration, contract, and
feature coverage across the full stack.

## Dependency gate
Requires Waves 01 through 05.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| I - Integration | `tests/contract/test_events_contract.py`, `tests/contract/test_typescript_contract_sync.py`, `tests/features/steps/tree_steps.py`, `tests/features/steps/queen_steps.py`, `tests/features/steps/round_steps.py`, `tests/features/steps/config_steps.py`, `tests/features/test_specs.py` | frozen contract files except for generated snapshots approved by operator |

## LOC budget
- Stream I: <= 900 LOC

## Stream I Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, all ADRs, all frozen contracts, and all `.feature` files in `docs/specs/`.
- Read `docs/waves/phase2/algorithms.md`.
- Read `docs/prototype/ui-spec.jsx`.
- Read the completed runtime modules before adding tests.

### Task
Implement contract tests and feature-test step definitions that prove the runtime matches the frozen Phase 2 artifacts.

### Produce
- `tests/contract/test_events_contract.py`
- `tests/contract/test_typescript_contract_sync.py`
- `tests/features/steps/tree_steps.py`
- `tests/features/steps/queen_steps.py`
- `tests/features/steps/round_steps.py`
- `tests/features/steps/config_steps.py`
- `tests/features/test_specs.py`

### Constraints
- Do not mutate the contracts to make tests pass.
- Prefer contract and behavior assertions over implementation-detail assertions.
- Keep step definitions thin; reusable helpers belong in test support modules only if used more than once.

### Verify
- `pytest tests/contract -q`
- `pytest tests/features -q`

## Acceptance criteria
- All files under `docs/specs/*.feature`
- Contract parity between Python models and `docs/contracts/types.ts`
