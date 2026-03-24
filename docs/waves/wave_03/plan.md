# Wave 03 Plan

## Goal
Expose the back-end slice over MCP and WebSocket, materialize read models,
and give the frontend a live transport and state store.

## Dependency gate
Requires Wave 02 outputs from Streams B, C, and E.

## Wave ownership
| Stream | Owns | Must not touch |
|---|---|---|
| F - Surface | `src/formicos/surface/app.py`, `src/formicos/surface/mcp_server.py`, `src/formicos/surface/ws_handler.py`, `src/formicos/surface/projections.py`, `src/formicos/surface/view_state.py`, `tests/unit/surface/test_app.py`, `tests/unit/surface/test_ws_handler.py` | core/, engine/, adapters/, frontend/ |
| D - Frontend | `frontend/src/ws/client.ts`, `frontend/src/state/store.ts`, `frontend/src/components/formicos-app.ts`, `frontend/src/components/tree-nav.ts`, `frontend/src/components/thread-view.ts`, `frontend/src/components/queen-chat.ts` | `src/formicos/*` |

## LOC budget
- Stream F: <= 650 LOC
- Stream D: <= 700 LOC
- Wave total target: <= 1,350 LOC

## Stream F Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-001, ADR-005, and the frozen contracts.
- Read `docs/waves/phase2/algorithms.md`.
- Read `docs/specs/tree_navigation.feature`, `docs/specs/queen_chat.feature`, `docs/specs/protocol_bridge.feature`, and `docs/specs/external_mcp.feature`.

### Task
Wire the engine and adapters into a Starlette/FastMCP surface with WebSocket event streaming and synchronous read-model updates.

### Produce
- `src/formicos/surface/app.py`
- `src/formicos/surface/mcp_server.py`
- `src/formicos/surface/ws_handler.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/view_state.py`
- `tests/unit/surface/test_app.py`
- `tests/unit/surface/test_ws_handler.py`

### Constraints
- UI mutations must route to the same operations exposed over MCP.
- Keep the WebSocket bridge thin.
- Projection state must derive from events, not hidden mutable stores.

### Verify
- `python -m py_compile src/formicos/surface/app.py src/formicos/surface/mcp_server.py src/formicos/surface/ws_handler.py src/formicos/surface/projections.py src/formicos/surface/view_state.py`
- `pytest tests/unit/surface/test_app.py tests/unit/surface/test_ws_handler.py -q`

## Stream D Dispatch
### Context bundle
- Read `CLAUDE.md`, `AGENTS.md`, ADR-003, `docs/contracts/types.ts`, and `docs/prototype/README.md`.
- Read `docs/prototype/ui-spec.jsx`.
- Read `docs/specs/tree_navigation.feature`, `docs/specs/queen_chat.feature`, `docs/specs/merge_prune_broadcast.feature`, and `docs/specs/thread_workspace.feature`.

### Task
Replace the placeholder shell with live tree navigation, thread view, and Queen chat wired to the WebSocket state store.

### Produce
- `frontend/src/ws/client.ts`
- `frontend/src/state/store.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/tree-nav.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/queen-chat.ts`

### Constraints
- Lit Web Components only.
- Preserve the established Void Protocol visual language.
- Do not invent fields beyond `docs/contracts/types.ts`.

### Verify
- `npm run build`

## Acceptance criteria
- `docs/specs/tree_navigation.feature`
- `docs/specs/queen_chat.feature`
- `docs/specs/protocol_bridge.feature`
- `docs/specs/thread_workspace.feature`
- `docs/specs/external_mcp.feature`
