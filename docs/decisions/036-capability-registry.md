# ADR-036: Capability Registry as Single Source of System Truth

**Status:** Accepted
**Date:** 2026-03-16
**Wave:** 21

## Decision

Add a frozen `CapabilityRegistry` built during app assembly that serves as the single authoritative source for:
- event names
- MCP tools
- Queen tools
- AG-UI events
- protocol entries
- castes
- version

All consumer surfaces read from this registry:
- Agent Card
- protocol status snapshot
- `/debug/inventory`
- parity tests

## Context

Wave 20 exposed live drift between backend snapshot data, frontend types, and docs.

The pattern was consistent:
- one surface held the real truth
- several other surfaces copied counts or names manually
- the copied values drifted during implementation

Examples:
- AG-UI event count lived as a hardcoded number instead of reading the AG-UI manifest
- protocol status and documentation needed manual correction to reflect the live protocol surface
- event and frontend mirrors still depended on explicit parity cleanup after changes

This scales badly once multiple tracks and multiple waves touch the same capability surface.

## Design

The registry is declared truth, not framework scraping.

It is built in `create_app()` from explicit manifests and mounted surfaces:
- `EVENT_TYPE_NAMES` in `events.py`
- MCP tool manifest in `mcp_server.py`
- Queen tool definitions from `queen_runtime._queen_tools()`
- `AGUI_EVENT_TYPES` in `agui_endpoint.py`
- protocol entries declared in the app factory based on what was mounted
- caste names from loaded recipes

The registry carries inventories, not just counts. Counts are derived for display.

Validation is separate from declaration:
- import-time self-check for `EVENT_TYPE_NAMES` versus the union
- parity tests for Python and TypeScript event names
- parity tests for registry contents versus live manifests

## Consequences

- one source of truth feeds multiple consumers
- adding a new event or tool becomes a small, explicit manifest update instead of a hunt across several surfaces
- `/debug/inventory` becomes a reliable operator and debugging surface
- protocol status and Agent Card stop drifting independently
- no new dependencies are required

## Rejected Alternatives

### Runtime introspection of Starlette routes and FastMCP internals

Rejected. It is brittle, indirect, and contradicts the goal of boring declared truth.

### Keep separate inventories in each consumer

Rejected. Wave 20 already showed the cost of that approach.

### Plugin-style discovery

Rejected. FormicOS does not have a plugin architecture. The capability surface is known at build time.

## Implementation Note

See:
- `docs/waves/wave_21/plan.md`
- `docs/waves/wave_21/algorithms.md`
