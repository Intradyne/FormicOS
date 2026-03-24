# Wave 01 Plan

## Goal
Implement the frozen core contracts as runtime Python modules, add config loading,
and put the test/bootstrap scaffolding in place for downstream streams.

## Dependency gate
This wave starts only after Phase 2 freezes:
- `docs/contracts/events.py`
- `docs/contracts/ports.py`
- `docs/contracts/types.ts`

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| A - Core | `src/formicos/core/types.py`, `src/formicos/core/events.py`, `src/formicos/core/ports.py`, `src/formicos/core/__init__.py` | engine/, adapters/, surface/, frontend/, `config/*` |
| G - Config | `src/formicos/core/settings.py`, `tests/unit/core/test_settings.py` | engine/, adapters/, surface/, frontend/, contract files |
| H - Scaffold | `src/formicos/__main__.py`, `tests/contract/test_contract_bootstrap.py`, `tests/features/steps/__init__.py` | layer implementations, contract files |

## LOC budget
- Stream A: <= 550 LOC
- Stream G: <= 250 LOC
- Stream H: <= 150 LOC
- Wave total target: <= 950 LOC

## Stream A Dispatch
### Context
- Read `CLAUDE.md`, `AGENTS.md`, ADR-001 through ADR-004.
- Read frozen contracts in `docs/contracts/events.py` and `docs/contracts/ports.py`.
- Read acceptance criteria in `docs/specs/model_cascade.feature`, `docs/specs/persistence.feature`, and `docs/specs/round_execution.feature`.

### Task
Implement the runtime core models that exactly mirror the frozen contracts.

### Produce
- `src/formicos/core/types.py`
- `src/formicos/core/events.py`
- `src/formicos/core/ports.py`
- `src/formicos/core/__init__.py`

### Constraints
- Use Pydantic v2 only.
- Event union is closed. Do not add or rename event types.
- Keep core import-free from engine, adapters, surface, and frontend.
- Match field names and discriminators exactly to the contract files.

### Verify
- `python -m py_compile src/formicos/core/types.py src/formicos/core/events.py src/formicos/core/ports.py`
- `pytest tests/unit/core -q`
- `pyright src`

## Stream G Dispatch
### Context
- Read `CLAUDE.md`, `AGENTS.md`, ADR-002, and ADR-006.
- Read `config/formicos.yaml` and `config/caste_recipes.yaml`.
- Read `docs/specs/model_cascade.feature` and `docs/specs/workspace_configuration.feature`.

### Task
Implement typed config loading for system settings, model registry entries, and caste recipes.

### Produce
- `src/formicos/core/settings.py`
- `tests/unit/core/test_settings.py`

### Constraints
- Do not change the config file schema in this wave.
- Reuse core Pydantic types from Stream A; do not duplicate schemas.
- No implicit defaults beyond what is already frozen in config/contracts.

### Verify
- `python -m py_compile src/formicos/core/settings.py`
- `pytest tests/unit/core/test_settings.py -q`

## Stream H Dispatch
### Context
- Read `CLAUDE.md`, `AGENTS.md`, ADR-006, and `tests/unit/test_bootstrap.py`.
- Read the frozen contracts to understand required import targets.

### Task
Add minimal bootstrap and contract-test scaffolding so later waves can attach concrete implementations without reshaping the test tree.

### Produce
- `src/formicos/__main__.py`
- `tests/contract/test_contract_bootstrap.py`
- `tests/features/steps/__init__.py`

### Constraints
- Do not implement business logic here.
- Keep all scaffolding import-safe even if later waves are incomplete.
- No feature flags needed in this wave because no operator-visible behavior ships yet.

### Verify
- `python -m py_compile src/formicos/__main__.py`
- `pytest tests/contract/test_contract_bootstrap.py -q`

## Acceptance criteria
- `docs/specs/model_cascade.feature`
- `docs/specs/persistence.feature`
- `docs/specs/round_execution.feature`
- `tests/unit/test_bootstrap.py`
