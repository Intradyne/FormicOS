# ADR-034: MCP Streamable HTTP Transport

**Status:** Accepted
**Date:** 2026-03-15
**Wave:** 20

## Decision

Mount the existing 19-tool FastMCP server on a Streamable HTTP endpoint at `/mcp`, making FormicOS callable by external MCP clients.

## Context

FormicOS has a fully implemented MCP server (`mcp_server.py`, 19 tools) that ADR-005 designates as the "sole programmatic API." However, this server has no transport. It exists purely as an in-process tool registry. External MCP clients (Claude Desktop, Cursor, VS Code Copilot, Goose) cannot connect to FormicOS.

Meanwhile, a parallel REST API (`/api/v1/*`) and WebSocket command bridge grew organically to fill the gap. The REST endpoints duplicate most MCP tool functionality.

The MCP transport landscape has also settled. SSE transport (two-endpoint, stateful) was deprecated in favor of Streamable HTTP (single-endpoint, optionally stateless). FastMCP 3.x (pinned in `pyproject.toml` as `fastmcp>=3.0,<4.0`) ships `create_streamable_http_app()` which returns a mountable Starlette sub-application.

## Implementation

```python
from fastmcp.server.http import create_streamable_http_app

mcp_http = create_streamable_http_app(
    server=mcp,
    streamable_http_path="/mcp",
    stateless_http=True,
)
routes.append(Mount("/mcp", app=mcp_http))
```

`stateless_http=True` because FormicOS MCP tools are stateless request/response — no session continuity needed between tool calls.

Lifespan coordination: the sub-app's `StreamableHTTPSessionManager` needs a running task group. Starlette handles nested app lifespans for mounted sub-apps. Smoke test this path.

## Consequences

- External MCP clients can connect to `http://localhost:8080/mcp` and call all 19 FormicOS tools
- Agent Card (`/.well-known/agent.json`) advertises the MCP endpoint
- The REST API (`/api/v1/*`) remains available but is now redundant for programmatic access
- No authentication in this wave (single-operator, localhost). OAuth 2.1 support via FastMCP's `AuthProvider` is a future option.
- ~20 LOC in `app.py`

## Rejected Alternatives

**SSE transport (deprecated MCP transport)**
Rejected. SSE transport is officially deprecated in favor of Streamable HTTP. Mounting the deprecated transport would create immediate technical debt.

**Custom transport implementation**
Rejected. FastMCP provides the mount in a single function call. Building a custom transport adds complexity for no benefit.

**Defer until authentication is ready**
Rejected. FormicOS is a single-operator local-first system. Adding auth before the transport exists inverts the useful ordering. The transport should work first; auth layers on top when needed.

**Remove REST endpoints in favor of MCP-only**
Rejected for this wave. The REST endpoints serve the skill browser, knowledge view, and colony export — all fetched directly by the Lit frontend. They can be deprecated later but don't need to be removed now.

## Implementation Note

See `docs/waves/wave_20/algorithms.md`, §3.
