# Wave 6 Summary

**Completed:** 2026-03-12
**Stream:** T3 - Contract parity and feature test scaffolds
**Validation at delivery:** 350 tests passing, layer lint clean, no regressions

## What shipped

### Contract tests
- `tests/contract/test_events_contract.py` - Runtime `core/events.py` mirrors frozen `docs/contracts/events.py` exactly: union parity, per-event field parity, model config, enum parity, `__all__` exports, serialization helpers.
- `tests/contract/test_typescript_contract_sync.py` - Python event models align with `docs/contracts/types.ts`: EventTypeName union, FormicOSEvent union order, BaseEvent/EventEnvelope fields, per-event interface field parity with snake_to_camel transform.
- `tests/contract/test_loc_budget.py` - Enforces the 15K LOC hard limit across core+engine+adapters+surface.

### Feature test infrastructure
- All 12 `.feature` files enabled in `tests/features/test_specs.py` (was 1).
- `tests/features/conftest.py` - Shared fixtures: `EventCollector` (implements `EventStorePort`), `proj_env` (ProjectionStore + collector), `setup_*` factory helpers.
- `tests/features/steps/surface_steps.py` - 8 features implemented: merge_prune_broadcast, persistence, thread_workspace, external_mcp, startup, protocol_bridge, approval_workflow, model_registry.
- `tests/features/steps/tree_steps.py` - 3 scenarios: navigate, breadcrumb, sidebar collapse.
- `tests/features/steps/queen_steps.py` - 3 scenarios: send message, spawn colony, independent threads.
- `tests/features/steps/config_steps.py` - 7 scenarios: workspace governance, clear override, caste recipes, system default, workspace override, clear cascade, model change without restart.

## Test count progression

| Phase | Tests |
|---|---:|
| Before Wave 6 | ~310 |
| After Wave 6 | 350 |
| Feature tests | 42 (was 4) |

## Approach

All Surface-layer feature tests run at the Python level using `ProjectionStore` and `handle_command()` directly. No HTTP server, no WebSocket, no browser. This validates the same code paths that the WS handler and MCP server use, without infrastructure overhead.

Shared `Then` steps that appear across multiple features (e.g., `a MergeCreated event is emitted`, `a QueenMessage event is emitted with role`) use the `event_collector` fixture directly to avoid fixture-name collisions between context dicts (`merge_ctx`, `thread_ctx`, `mcp_ctx`).

## Decisions made

1. **EventCollector doubles as EventStorePort.** Added `query()`, `replay()`, and `close()` methods so `handle_command()` can use it directly without a separate mock.
2. **setup_* helpers accept optional collector.** Persistence tests need events tracked in both the ProjectionStore and the EventCollector for replay verification.
3. **Shared Then steps use event_collector fixture.** Avoids pytest-bdd fixture collisions when the same Gherkin step appears in scenarios with different context fixture names.
4. **Queen responses simulated in test.** The engine would generate queen responses in production; tests inject a QueenMessage with `role="queen"` after the operator message.

## Issues found

None blocking. The `pytest_plugins` registration in root `conftest.py` (established in prior work) remains the correct pattern for step discovery.
