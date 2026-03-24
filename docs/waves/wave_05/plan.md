# Wave 05 Plan

## Goal
Implement the remaining operator configuration surfaces: workspace config, model
registry, caste recipes, and system settings.

## Dependency gate
Requires Wave 04 outputs and frozen contracts/types alignment.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| D - Frontend | `frontend/src/components/workspace-config.ts`, `frontend/src/components/model-registry.ts`, `frontend/src/components/castes-view.ts`, `frontend/src/components/settings-view.ts`, `frontend/src/components/formicos-app.ts` | `src/formicos/*` |
| F - Surface | `src/formicos/surface/config_endpoints.py`, `src/formicos/surface/model_registry_view.py`, `tests/unit/surface/test_config_endpoints.py` | core/, engine/, adapters/, frontend/ |

## LOC budget
- Stream D: <= 900 LOC
- Stream F: <= 250 LOC
- Wave total target: <= 1,150 LOC

## Stream D Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-003, `docs/contracts/types.ts`, and `docs/prototype/README.md`.
- Read `docs/prototype/ui-spec.jsx`.
- Read `docs/specs/model_cascade.feature`, `docs/specs/workspace_configuration.feature`, `docs/specs/model_registry.feature`, and `docs/specs/startup.feature`.

### Task
Implement the remaining four views and connect them to the live state/actions already exposed by the surface layer.

### Produce
- `frontend/src/components/workspace-config.ts`
- `frontend/src/components/model-registry.ts`
- `frontend/src/components/castes-view.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`

### Constraints
- Preserve existing shell/layout patterns from earlier waves.
- Do not bypass the shared state store.
- Display inherited values distinctly from overrides.

### Verify
- `npm run build`

## Stream F Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-005, `config/formicos.yaml`, and `config/caste_recipes.yaml`.
- Read the same feature files as Stream D.

### Task
Add surface handlers and projection helpers for config mutation, model registry status, and caste recipe display.

### Produce
- `src/formicos/surface/config_endpoints.py`
- `src/formicos/surface/model_registry_view.py`
- `tests/unit/surface/test_config_endpoints.py`

### Constraints
- Keep workspace scope explicit on every operator mutation.
- Surface models must mirror `docs/contracts/types.ts`.

### Verify
- `python -m py_compile src/formicos/surface/config_endpoints.py src/formicos/surface/model_registry_view.py`
- `pytest tests/unit/surface/test_config_endpoints.py -q`

## Acceptance criteria
- `docs/specs/model_cascade.feature`
- `docs/specs/workspace_configuration.feature`
- `docs/specs/model_registry.feature`
- `docs/specs/startup.feature`
