"""MCP bridge tool handlers — registered by addon.yaml.

These handlers follow the standard addon tool signature:
``async def handler(inputs, workspace_id, thread_id, *, runtime_context)``
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


def _get_bridge(runtime_context: dict[str, Any]) -> Any:
    """Extract the McpBridge instance from runtime_context."""
    return runtime_context.get("mcp_bridge")


async def handle_discover_tools(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Discover tools available on connected MCP servers."""
    ctx = runtime_context or {}
    bridge = _get_bridge(ctx)
    if bridge is None:
        return "MCP bridge is not configured. No remote servers available."

    server = inputs.get("server") or None
    tools = await bridge.list_tools(server)

    if not tools:
        target = f"server '{server}'" if server else "any connected server"
        return f"No tools discovered on {target}."

    parts = [f"Discovered {len(tools)} remote tool(s):"]
    for t in tools:
        parts.append(
            f"- [{t['server']}] {t['name']}: {t.get('description', '')[:120]}"
        )
    return "\n".join(parts)


async def handle_call_tool(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Call a tool on a remote MCP server."""
    ctx = runtime_context or {}
    bridge = _get_bridge(ctx)
    if bridge is None:
        return "MCP bridge is not configured."

    server = inputs.get("server", "")
    tool = inputs.get("tool", "")
    arguments: dict[str, Any] = inputs.get("arguments") or {}

    if not server or not tool:
        return "Error: 'server' and 'tool' are required."

    return await bridge.call_tool(server, tool, arguments)
