# ADR-005: MCP as Sole Programmatic API

**Status:** Accepted
**Date:** 2026-03-12

## Context
FormicOS needs a programmatic interface for external agents and the Queen to
spawn colonies, query state, and control workflows. Options: REST API, GraphQL,
gRPC, or MCP tools.

## Decision
All colony operations are exposed exclusively as MCP tools via FastMCP (Streamable
HTTP transport). The Queen is an MCP client. External agents are MCP clients. The
web UI sends mutations via WebSocket commands that the surface layer translates to
the same operations. No separate REST API.

Every MCP tool is workspace-scoped (Constitution Article 7.2). The web UI and
MCP have equal access — anything the UI can do, an external agent can do.

## Consequences
- **Good:** Single API surface. No REST/MCP impedance mismatch. External agents
  get first-class access identical to the Queen's.
- **Good:** MCP ecosystem compatibility (10,000+ servers, 97M monthly SDK downloads).
- **Bad:** MCP tooling is younger than REST tooling. Fewer debugging utilities.
- **Bad:** Browser-based UI cannot call MCP directly — requires WebSocket bridge.
- **Acceptable:** The WebSocket-to-MCP bridge in surface/ is thin (~50 LOC) and
  is the only place where the two transports meet.

## FormicOS Impact
Affects: surface/mcp_server.py, surface/ws_handler.py, all external integrations.
