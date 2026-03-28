# Wave 70 — Team A: MCP Bridge

**Theme:** The Queen can use any tool ecosystem the operator connects.

## Context

Read `docs/waves/wave_70/wave_70_plan.md` first. Read `CLAUDE.md` for hard
constraints.

FormicOS is already an MCP **server** (19 tools at `/mcp` via FastMCP).
This wave adds MCP **client** capability: connecting to remote MCP servers
and exposing their tools to the Queen through the existing addon
infrastructure.

**Key insight:** The addon system already handles tool registration, health
monitoring, capability metadata, and Queen routing. An MCP bridge is just
an addon whose tools are resolved from a remote server instead of local
Python handlers. The existing `register_addon()` → `tool_registry` →
Queen tool dispatch pipeline works unchanged.

## Your Files (exclusive ownership)

### New addon
- `addons/mcp-bridge/addon.yaml` — **new**, bridge manifest
- `src/formicos/addons/mcp_bridge/__init__.py` — **new**
- `src/formicos/addons/mcp_bridge/client.py` — **new**, MCP client
  connection, tool listing, tool calling
- `src/formicos/addons/mcp_bridge/discovery.py` — **new**, dynamic tool
  discovery and registration

### Surface
- `src/formicos/surface/queen_tools.py` — `discover_mcp_tools` new Queen
  tool
- `src/formicos/surface/addon_loader.py` — small extension: bridge-aware
  registration path for dynamic tools
- `config/caste_recipes.yaml` — add `discover_mcp_tools` to Queen tool
  list, update tool count

### Tests
- `tests/unit/addons/test_mcp_bridge.py` — **new**

## Do Not Touch

- `src/formicos/surface/mcp_server.py` — the MCP server is unrelated
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/surface/queen_runtime.py` — Teams B/C own
- `src/formicos/surface/self_maintenance.py` — Team C owns
- `frontend/` — no frontend changes this wave

## Overlap Coordination

- Team B adds `propose_project_milestone` and `complete_milestone` to
  `queen_tools.py` and `caste_recipes.yaml`. You add `discover_mcp_tools`.
  Both are additive to different sections. No conflict.
- Team C adds `check_autonomy_budget` to `queen_tools.py`. Same:
  additive, different section.
- All three teams touch `caste_recipes.yaml` to update the tool list.
  The changes are additive (append tool names to the array, increment
  the count). Merge last team's changes carefully.

---

## Track 1: MCP Bridge Addon

### Problem

The Queen has ~38 built-in tools and 4 addons. With Docker MCP Toolkit,
the operator could give her git, filesystem, GitHub, databases, Slack —
anything with an MCP server. But there's no way to connect to external
MCP servers.

### Architecture

The MCP bridge is an **addon** — it fits into the existing addon loader
pipeline. But unlike static addons (codebase-index, docs-index), bridge
tools are resolved dynamically from a remote MCP server.

Two design options:
- **(a) Static manifest with generic proxy tools** — the addon.yaml
  declares `mcp_call_tool` and `mcp_list_tools` as generic proxy tools.
  The Queen calls `mcp_call_tool(server_url, tool_name, args)` for any
  remote tool. Simple but the Queen sees 2 tools, not N specific tools.
- **(b) Dynamic registration** — the bridge connects at startup (or on
  demand), fetches tool specs from the remote server, and registers each
  as a named addon tool. The Queen sees `git_commit`, `git_push`,
  `read_file` etc. as first-class tools in her tool list.

**Use option (a) as the base, with option (b) as an enhancement via
Track 2.** The generic proxy is the safety net; dynamic discovery is the
power feature.

### Implementation

**1. Addon manifest: `addons/mcp-bridge/addon.yaml`.**

```yaml
name: mcp-bridge
version: "1.0.0"
description: "Connect to remote MCP servers and call their tools"
author: "formicos-core"

content_kinds:
  - external_tools
search_tool: ""

config:
  - key: servers
    type: string
    default: "[]"
    label: "JSON array of MCP server configs: [{name, url, transport}]"
  - key: request_timeout_s
    type: integer
    default: 30
    label: "Tool call timeout in seconds"
  - key: max_retries
    type: integer
    default: 2
    label: "Connection retry attempts"

tools:
  - name: mcp_call_tool
    description: "Call a tool on a connected MCP server"
    handler: client.py::handle_call_tool
    parameters:
      type: object
      properties:
        server:
          type: string
          description: "MCP server name (from configured servers list)"
        tool_name:
          type: string
          description: "Name of the tool on the remote server"
        arguments:
          type: object
          description: "Arguments to pass to the tool"
      required: ["server", "tool_name"]

  - name: mcp_list_remote_tools
    description: "List available tools on a connected MCP server"
    handler: client.py::handle_list_tools
    parameters:
      type: object
      properties:
        server:
          type: string
          description: "MCP server name (omit to list all servers)"

triggers:
  - type: manual
    handler: discovery.py::manual_refresh
```

**2. Client module: `src/formicos/addons/mcp_bridge/client.py`.**

Uses FastMCP 2.14.5's Client class (already in dependencies):

```python
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastmcp.client import Client

log = logging.getLogger(__name__)


# -- Connection pool ----------------------------------------------------------

# Module-level cache: server_name → Client instance
_connections: dict[str, Client] = {}
_connection_health: dict[str, dict[str, Any]] = {}


async def _get_client(
    server_name: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> Client | None:
    """Get or create a Client for the named server.

    Server configs live in the addon's workspace config under the 'servers'
    key: a JSON array of {name, url, transport?}.
    """
    if server_name in _connections:
        client = _connections[server_name]
        if client.is_connected():
            return client
        # Stale connection — remove and reconnect
        try:
            await client.close()
        except Exception:
            pass
        del _connections[server_name]

    # Resolve server config
    ctx = runtime_context or {}
    servers_raw = _resolve_server_config(server_name, ctx)
    if servers_raw is None:
        return None

    url = servers_raw.get("url", "")
    timeout = int(servers_raw.get("timeout", 30))

    try:
        client = Client(url, timeout=timeout)
        await client.initialize()
        _connections[server_name] = client
        _connection_health[server_name] = {
            "status": "connected",
            "error_count": 0,
            "last_error": None,
        }
        log.info("mcp_bridge.connected", server=server_name, url=url)
        return client
    except Exception as exc:
        _record_error(server_name, str(exc))
        log.warning(
            "mcp_bridge.connect_failed",
            server=server_name, url=url, error=str(exc),
        )
        return None


def _resolve_server_config(
    server_name: str, ctx: dict[str, Any],
) -> dict[str, Any] | None:
    """Look up server config from addon workspace config."""
    # The 'servers' config param holds a JSON array
    settings = ctx.get("settings")
    if settings is None:
        return None
    # Try workspace config first, then addon config default
    servers_json = ""
    projections = ctx.get("projections")
    if projections is not None:
        # Check each workspace for addon config
        for ws in projections.workspaces.values():
            raw = ws.config.get("mcp-bridge:servers", "[]")
            if raw and raw != "[]":
                servers_json = raw
                break
    if not servers_json:
        servers_json = "[]"
    try:
        servers = json.loads(servers_json) if isinstance(servers_json, str) else servers_json
    except (json.JSONDecodeError, TypeError):
        return None
    for s in servers:
        if s.get("name") == server_name:
            return s
    return None


def _record_error(server_name: str, error: str) -> None:
    health = _connection_health.get(server_name, {
        "status": "error", "error_count": 0, "last_error": None,
    })
    health["error_count"] = health.get("error_count", 0) + 1
    health["last_error"] = error
    health["status"] = "error" if health["error_count"] >= 3 else "degraded"
    _connection_health[server_name] = health


# -- Tool handlers ------------------------------------------------------------

async def handle_call_tool(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Call a tool on a remote MCP server."""
    server = inputs.get("server", "")
    tool_name = inputs.get("tool_name", "")
    arguments = inputs.get("arguments") or {}

    if not server or not tool_name:
        return "Error: 'server' and 'tool_name' are required."

    client = await _get_client(server, runtime_context=runtime_context)
    if client is None:
        health = _connection_health.get(server, {})
        return (
            f"Error: Cannot connect to MCP server '{server}'. "
            f"Status: {health.get('status', 'unknown')}. "
            f"Last error: {health.get('last_error', 'none')}"
        )

    try:
        result = await client.call_tool(tool_name, arguments)
        # Reset error count on success
        if server in _connection_health:
            _connection_health[server]["error_count"] = 0
            _connection_health[server]["status"] = "connected"
        # Serialize result
        if hasattr(result, "content"):
            # CallToolResult has .content list
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(result)
    except Exception as exc:
        _record_error(server, str(exc))
        return f"Error calling {tool_name} on {server}: {exc}"


async def handle_list_tools(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """List available tools on a remote MCP server."""
    server = inputs.get("server", "")

    if not server:
        # List all known servers and their health
        lines = ["## Connected MCP Servers"]
        for name, health in _connection_health.items():
            status = health.get("status", "unknown")
            errors = health.get("error_count", 0)
            lines.append(f"- **{name}**: {status} ({errors} errors)")
        if not _connection_health:
            lines.append("No MCP servers connected.")
        return "\n".join(lines)

    client = await _get_client(server, runtime_context=runtime_context)
    if client is None:
        return f"Cannot connect to MCP server '{server}'."

    try:
        tools = await client.list_tools()
        lines = [f"## Tools on '{server}' ({len(tools)} tools)"]
        for tool in tools:
            desc = getattr(tool, "description", "") or ""
            lines.append(f"- **{tool.name}**: {desc[:100]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing tools on {server}: {exc}"
```

**Important implementation notes:**

- `Client(url)` accepts a URL string directly — FastMCP auto-selects
  the transport (StreamableHTTP, SSE, or stdio) based on the URL scheme.
- `client.call_tool(name, args)` returns a `CallToolResult` with a
  `.content` list of content items (text, images, etc.).
- `client.list_tools()` returns `list[mcp.types.Tool]` with `.name`,
  `.description`, `.inputSchema`.
- The connection pool is module-level. This is fine for a single-process
  server. Connections are lazy — created on first use.
- Health tracking mirrors `AddonRegistration.health_status` pattern:
  0 errors = connected, 1–2 = degraded, 3+ = error.

**3. `__init__.py`** — empty or minimal:

```python
"""MCP Bridge addon — connect to remote MCP servers."""
```

---

## Track 2: Dynamic Tool Discovery

### Problem

With Track 1, the Queen calls `mcp_call_tool(server="git", tool_name="commit", arguments={...})`. This works but the Queen must first call
`mcp_list_remote_tools` to learn what tools exist, then construct the
proxy call. Ideally, the Queen would see `git:commit`, `git:push` etc.
as first-class tools in her tool list.

### Implementation

**1. Queen tool: `discover_mcp_tools`.**

Add to `queen_tools.py` — a Queen tool (not an addon tool) that:

1. Connects to the named MCP server via the bridge client
2. Fetches the tool list
3. Dynamically registers each remote tool as a namespaced addon tool
4. Returns a summary of discovered tools

```python
async def _discover_mcp_tools(self, inputs, workspace_id, thread_id):
    """Connect to an MCP server and register its tools dynamically."""
    server_name = inputs.get("server_name", "")
    server_url = inputs.get("server_url", "")
    if not server_name:
        return ("Error: server_name is required.", None)

    from formicos.addons.mcp_bridge.discovery import discover_and_register
    result = await discover_and_register(
        server_name=server_name,
        server_url=server_url,
        tool_dispatcher=self._tool_dispatcher,
        runtime_context=self._addon_runtime_context,
    )
    return (result, None)
```

Tool spec:
```python
{
    "name": "discover_mcp_tools",
    "description": (
        "Connect to a remote MCP server and register its tools. "
        "After discovery, the server's tools appear as callable tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Short name for this server (e.g., 'git', 'github')"
            },
            "server_url": {
                "type": "string",
                "description": "MCP server URL (e.g., 'http://localhost:8808/mcp')"
            }
        },
        "required": ["server_name"]
    }
}
```

**2. Discovery module: `src/formicos/addons/mcp_bridge/discovery.py`.**

```python
async def discover_and_register(
    server_name: str,
    server_url: str = "",
    tool_dispatcher: Any = None,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Connect to MCP server, fetch tools, register as addon tools."""
    from formicos.addons.mcp_bridge.client import (
        _get_client, _connection_health,
    )

    # If URL provided, temporarily store in config
    if server_url:
        # Direct connection without config lookup
        from fastmcp.client import Client
        try:
            client = Client(server_url, timeout=30)
            await client.initialize()
        except Exception as exc:
            return f"Failed to connect to {server_url}: {exc}"
    else:
        client = await _get_client(server_name, runtime_context=runtime_context)

    if client is None:
        return f"Cannot connect to MCP server '{server_name}'."

    try:
        tools = await client.list_tools()
    except Exception as exc:
        return f"Failed to list tools on '{server_name}': {exc}"

    if not tools:
        return f"Server '{server_name}' has no tools."

    registered = []
    if tool_dispatcher is not None:
        handlers = getattr(tool_dispatcher, "_handlers", {})
        addon_specs = getattr(tool_dispatcher, "_addon_tool_specs", [])

        for tool in tools:
            namespaced = f"{server_name}:{tool.name}"

            # Create a closure that calls this specific tool
            async def _make_handler(
                _client: Any, _tool_name: str, _server: str,
            ):
                async def _handler(
                    inputs: dict, workspace_id: str, thread_id: str,
                    **kwargs: Any,
                ) -> str:
                    from formicos.addons.mcp_bridge.client import (
                        handle_call_tool,
                    )
                    return await handle_call_tool(
                        {"server": _server, "tool_name": _tool_name,
                         "arguments": inputs},
                        workspace_id, thread_id,
                        runtime_context=kwargs.get("runtime_context"),
                    )
                return _handler

            handler = await _make_handler(client, tool.name, server_name)
            handlers[namespaced] = handler

            # Add to addon tool specs for Queen visibility
            desc = getattr(tool, "description", "") or ""
            schema = getattr(tool, "inputSchema", {}) or {}
            addon_specs.append({
                "name": namespaced,
                "description": f"[{server_name}] {desc}"[:200],
                "parameters": schema,
            })
            registered.append(namespaced)

    lines = [
        f"Discovered {len(tools)} tools on '{server_name}'.",
        f"Registered {len(registered)} tools:",
    ]
    for name in registered:
        lines.append(f"  - {name}")
    return "\n".join(lines)
```

**Critical notes on dynamic registration:**

- Namespaced as `server_name:tool_name` (e.g., `git:commit`) to avoid
  collisions with built-in tools.
- Registered into `_handlers` dict (same dict addon_loader.py uses at
  line 262). This makes them callable via the normal tool dispatch path.
- Added to `_addon_tool_specs` list (same list queen_tools.py reads at
  line 1411). This makes them visible in the Queen's LLM tool list.
- The handler closure delegates to `handle_call_tool` — all remote calls
  go through the same health-tracked code path.

**3. Manual refresh trigger in `discovery.py`.**

```python
async def manual_refresh(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Trigger handler for manual MCP bridge refresh."""
    # Re-discover all configured servers
    from formicos.addons.mcp_bridge.client import _connection_health
    results = []
    for server_name in list(_connection_health.keys()):
        result = await discover_and_register(
            server_name=server_name,
            runtime_context=runtime_context,
        )
        results.append(result)
    return "\n\n".join(results) if results else "No servers configured."
```

---

## Track 3: Connection Health + Graceful Degradation

### Problem

Remote MCP servers can be down, slow, or returning unexpected shapes. The
Queen needs to know when a bridge is unhealthy so she doesn't waste tool
turns on broken connections.

### Implementation

**1. Health already tracked in `_connection_health` dict (Track 1).**

Extend `handle_list_tools` to include health data in the text output:

```text
## Tools on 'git' (12 tools) — Status: connected
- **git:commit**: Create a git commit
- **git:push**: Push commits to remote
...

## Tools on 'github' (8 tools) — Status: degraded (2 errors)
- **github:create_issue**: ...
```

**2. Queen-visible health in `_list_addons()` output.**

The existing `_list_addons()` in `queen_tools.py` (Wave 68 Track 5)
already shows capability metadata per addon. For the mcp-bridge addon,
the text should include connected server health:

```text
**mcp-bridge**: Connect to remote MCP servers and call their tools
  Content: external_tools
  Servers: git (connected, 12 tools), github (degraded, 8 tools)
```

To achieve this, modify `_list_addons()` to check for mcp-bridge
specifically: if the addon name is `mcp-bridge`, append server health
summary from `client._connection_health` to the text output. This is
a small addition (~10 lines) to the existing method.

**3. Graceful degradation in `handle_call_tool`.**

Already handled in Track 1: if the client can't connect, the handler
returns an error string (not an exception). The Queen sees the error
and can decide to use a different approach.

Add one enhancement: if a server has `status == "error"` (3+ errors),
`handle_call_tool` should return a short-circuit error without attempting
connection:

```python
if server in _connection_health:
    health = _connection_health[server]
    if health.get("status") == "error":
        return (
            f"MCP server '{server}' is in error state "
            f"({health.get('error_count', 0)} consecutive errors). "
            f"Last error: {health.get('last_error', 'unknown')}. "
            f"Use mcp_list_remote_tools to check status or wait for "
            f"automatic recovery."
        )
```

**4. Automatic recovery.**

After 5 minutes since the last error, reset `error_count` to 0 on the
next connection attempt. This allows the bridge to recover without
manual intervention. Add a `last_error_time` field to the health dict
and check elapsed time in `_get_client`.

### Tests

Create `tests/unit/addons/test_mcp_bridge.py` with at least:

1. `test_handle_call_tool_returns_result` — mock FastMCP Client, assert
   result text returned.
2. `test_handle_call_tool_connection_failure` — mock Client that raises,
   assert error string returned (not exception).
3. `test_handle_list_tools_returns_tool_names` — mock Client.list_tools,
   assert formatted tool list.
4. `test_health_degrades_on_errors` — call handle_call_tool 3 times with
   failures, assert health status transitions: connected → degraded → error.
5. `test_health_recovers_after_success` — after error state, successful
   call resets error count.
6. `test_discover_registers_tools` — mock Client.list_tools returning
   tool specs, assert tools registered in handlers dict and addon_specs
   list.
7. `test_namespaced_tool_names` — assert discovered tools use
   `server:tool` format.
8. `test_error_state_short_circuits` — server in error state, assert
   handle_call_tool returns immediately without connection attempt.

---

## Acceptance Gates

- [ ] `addons/mcp-bridge/addon.yaml` exists and loads via addon discovery
- [ ] `mcp_call_tool` calls remote MCP server tools via FastMCP Client
- [ ] `mcp_list_remote_tools` shows available tools per server
- [ ] `discover_mcp_tools` Queen tool registers remote tools dynamically
- [ ] Dynamically registered tools appear in Queen's tool list
- [ ] Dynamically registered tools are callable via normal dispatch
- [ ] Connection health tracked: connected → degraded → error
- [ ] Error state short-circuits without connection attempt
- [ ] Health auto-recovers after 5 minutes
- [ ] `_list_addons()` text includes server health for mcp-bridge
- [ ] No new event types
- [ ] No frontend changes
- [ ] All tests pass

## Validation

```bash
pytest tests/unit/addons/test_mcp_bridge.py -v
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
