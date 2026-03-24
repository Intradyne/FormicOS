# Wave 5 Summary

**Completed:** 2026-03-12
**Stream:** F - Config mutation and model-registry views
**Validation at delivery:** Reported green on `ruff`, `pyright --strict`, layer lint, and surface unit tests

## What shipped

### Surface source
- `src/formicos/surface/config_endpoints.py` (101 LOC) - workspace-scoped config mutation handlers and model assignment updates.
- `src/formicos/surface/model_registry_view.py` (70 LOC) - model-registry projection helpers and provider/status shaping for the operator surface.

### Tests
- `tests/unit/surface/test_config_endpoints.py` (187 LOC) - config mutation, registry view, and workspace update coverage.

## LOC accounting

| Area | LOC |
|---|---:|
| Surface source | 171 |
| Surface tests | 187 |
| Wave total | 358 |

## Decisions made

1. **Workspace scope stays explicit on every mutation.** Config handlers require the target workspace and never fall back to implicit global edits.
2. **Registry state remains derived.** Model availability and endpoint display are computed from config/runtime inputs and projection state rather than persisted in a second store.
3. **Surface outputs mirror the frozen frontend contract.** Config and registry helpers shape data for the operator snapshot without changing the underlying core types.

## Issues found

- No new runtime seam was introduced, but feature-level validation for config and model-registry workflows still depends on T3 enabling the remaining spec coverage.
