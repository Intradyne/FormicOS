# Wave 1 Summary

**Completed:** 2026-03-12
**CI status:** All green (ruff, pyright strict, layer lint, 81 tests)

## What shipped

### Stream A — Core Types + Events + Ports (critical path)
- `src/formicos/core/types.py` (272 LOC) — 15 Pydantic v2 models, 1 StrEnum, 2 TypedDicts
- `src/formicos/core/events.py` (450 LOC) — 22 frozen events, discriminated union, serialize/deserialize
- `src/formicos/core/ports.py` (176 LOC) — 5 Protocol interfaces (LLMPort, EventStorePort, VectorPort, CoordinationStrategy, SandboxPort)
- `src/formicos/core/__init__.py` (33 LOC) — re-exports
- `tests/unit/core/test_types.py` — 14 tests (NodeAddress, frozen models, validation)
- `tests/unit/core/test_events.py` — 49 tests (round-trip all 22 events via JSON and Mapping, union size, frozen mutation)

### Stream G — Config Loading
- `src/formicos/core/settings.py` (134 LOC) — SystemSettings, CasteRecipeSet, load_config(), load_castes(), ${VAR:default} interpolation
- `tests/unit/core/test_settings.py` — 5 tests
- Added `_enrich_registry()` to derive `provider` from model `address` (YAML doesn't include it but ModelRecord requires it)

### Stream H — Bootstrap Scaffold
- `src/formicos/__main__.py` (48 LOC) — CLI entry point with argparse stubs
- `tests/contract/test_contract_bootstrap.py` (99 LOC) — 4 contract validation tests
- `tests/features/steps/__init__.py` — empty, for pytest-bdd

## Decisions made

1. **Pyright strict + Pydantic discriminator pattern:** The standard Pydantic `type: Literal["X"]` override on `type: str` triggers `reportIncompatibleVariableOverride` in pyright strict mode. Suppressed with a file-level `# pyright: reportIncompatibleVariableOverride=false` directive in events.py. This is the canonical Pydantic pattern.

2. **Ruff TC rules vs Pydantic runtime imports:** Pydantic models need types available at runtime (not just under TYPE_CHECKING). Added per-file-ignores in `pyproject.toml` for TCH001/TCH003 on Pydantic model files.

3. **UP040/UP007 suppressed on FormicOSEvent union:** The `type` keyword (PEP 695) and `X | Y` syntax don't work with `Annotated[Union[...], Field(discriminator=...)]` + `TypeAdapter`. Kept the `TypeAlias` + `Union` pattern with noqa comments.

4. **ModelRecord.provider derived from address:** The YAML config specifies `address: "anthropic/claude-sonnet-4.6"` without a separate `provider` field. Stream G's `_enrich_registry()` derives it by splitting on `/`. Wave 2 adapters should be aware of this convention.

## LOC accounting

| Stream | Budget | Actual | Note |
|--------|--------|--------|------|
| A (4 core files) | 550 | 931 | events.py alone is 450 LOC (22 events); budget was set before contract size was known |
| G | 250 | 134 | Under budget |
| H | 150 | 147 | On budget |
| **Total** | **950** | **1212** | Overshoot driven entirely by event model verbosity |

The budget overshoot is structural — faithfully mirroring 22 frozen event classes with Pydantic Field descriptors requires ~20 LOC per event. The contract itself is 451 LOC. No logic bloat was introduced.

## Issues for Wave 2

- **ModelRecord.status values:** types.py defines `Literal["available", "disabled", "error"]` but types.ts uses `"available" | "unavailable" | "no_key" | "loaded"`. The Python side should align with TS in Wave 2 when adapters implement model status tracking.
- **ColonyContext.pheromone_weights** uses `Mapping[tuple[str, str], float]` which is not JSON-serializable. Engine code (Wave 3+) will need a serialization strategy for this field.
- **CasteRecipe.description** is in the YAML but not in the Pydantic model (CasteRecipe only has: name, system_prompt, temperature, model_override, tools, max_tokens). If description is needed downstream, add it to CasteRecipe.
