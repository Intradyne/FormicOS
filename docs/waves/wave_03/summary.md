# Wave 3 Summary

**Completed:** 2026-03-12
**Stream:** F - Surface wiring
**Validation at delivery:** Reported green on `ruff`, `pyright --strict`, layer lint, and surface unit tests

## What shipped

### Surface source
- `src/formicos/surface/projections.py` (420 LOC) - `ProjectionStore` handlers for the full 22-event vocabulary plus materialized workspace/thread/colony/read-model state.
- `src/formicos/surface/view_state.py` (236 LOC) - snapshot builder that projects Python state into the frozen TypeScript operator state shape.
- `src/formicos/surface/mcp_server.py` (228 LOC) - FastMCP tool surface for workspace, thread, colony, merge, approval, and Queen operations.
- `src/formicos/surface/ws_handler.py` (171 LOC) - WebSocket subscription manager, event fanout, command dispatch into `commands.py`, and state rebroadcast.
- `src/formicos/surface/app.py` (167 LOC) - Starlette composition root, provider routing, replay-on-startup, and adapter/engine/surface wiring.

### Tests
- `tests/unit/surface/test_app.py` (37 LOC) - app factory and composition-root coverage.
- `tests/unit/surface/test_ws_handler.py` (238 LOC) - subscribe/unsubscribe, event fanout, command dispatch, and state rebroadcast coverage.

## LOC accounting

| Area | LOC |
|---|---:|
| Surface source | 1,222 |
| Surface tests | 275 |
| Wave total | 1,497 |

The source budget was exceeded because `projections.py` is the central read-model implementation and carries all 22 event handlers. That verbosity is structural, not accidental.

## Decisions made

1. **Projection state is the only read model.** The frontend snapshot, MCP responses, and WS payloads all derive from `ProjectionStore`; no second mutable cache was introduced.
2. **The composition root owns heavy dependency injection.** Sentence embedding, provider-prefix routing, adapter creation, and replay wiring all stay in `app.py` rather than leaking into `engine/` or `adapters/`.
3. **MCP and WebSocket share the same operational seam.** Surface mutations are event-emitting operations first; protocol-specific layers stay thin.
4. **WebSocket command routing remains a bridge.** The final Wave 3 surface includes command dispatch into `commands.py`, event fanout from the event store, and workspace snapshot rebroadcast after mutation.

## Issues found

- `projections.py` dominates the wave budget. If further growth is needed, split helper logic without introducing a second source of truth.
- WebSocket command routing was initially too thin; the final integration pass wired it into `commands.py` and added direct tests for command-driven event/state fanout.
- End-to-end feature coverage was intentionally deferred to T3 once the surface layer existed.
