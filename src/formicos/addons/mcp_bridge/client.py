"""MCP bridge client — manages connections to remote MCP servers.

Provides connection caching, per-server health tracking, and a structured
health export for generic consumption by addon_loader / queen_tools.
"""
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
# pyright: reportMissingTypeArgument=false, reportUnknownParameterType=false
# pyright: reportUnknownArgumentType=false, reportAttributeAccessIssue=false

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from fastmcp.client import Client

log = structlog.get_logger()


@dataclass
class ServerHealth:
    """Health state for a single MCP server connection."""

    name: str
    url: str
    connected: bool = False
    last_connected: str | None = None
    last_error: str | None = None
    tool_count: int = 0
    call_count: int = 0
    error_count: int = 0


@dataclass
class McpBridge:
    """Manages connections to multiple remote MCP servers.

    Connections are lazily established and cached. Health is tracked
    per-server and exported as a structured dict for generic consumption.
    """

    servers: list[dict[str, str]] = field(default_factory=list)
    _clients: dict[str, Client] = field(default_factory=dict, repr=False)
    _health: dict[str, ServerHealth] = field(default_factory=dict, repr=False)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict, repr=False)

    def configure(self, servers: list[dict[str, str]]) -> None:
        """Set or replace the server list. Does not eagerly connect."""
        self.servers = list(servers)
        # Initialise health entries for newly-configured servers
        for s in servers:
            name = s.get("name", "")
            if name and name not in self._health:
                self._health[name] = ServerHealth(
                    name=name, url=s.get("url", ""),
                )

    async def _get_client(self, name: str) -> Client | None:
        """Return a connected client for *name*, or None on failure."""
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()

        async with self._locks[name]:
            # Return cached if still connected
            existing = self._clients.get(name)
            if existing is not None and existing.is_connected():
                return existing

            # Find server config
            server_cfg = next(
                (s for s in self.servers if s.get("name") == name), None,
            )
            if server_cfg is None:
                return None

            url = server_cfg.get("url", "")
            if not url:
                return None

            health = self._health.setdefault(
                name, ServerHealth(name=name, url=url),
            )

            try:
                client = Client(url, timeout=10)
                await client.__aenter__()
                health.connected = True
                health.last_connected = datetime.now(UTC).isoformat()
                health.last_error = None
                self._clients[name] = client
                log.info("mcp_bridge.connected", server=name, url=url)
                return client
            except Exception as exc:  # noqa: BLE001
                health.connected = False
                health.last_error = str(exc)[:200]
                health.error_count += 1
                log.warning(
                    "mcp_bridge.connect_failed",
                    server=name, error=str(exc)[:200],
                )
                return None

    async def list_tools(self, server_name: str | None = None) -> list[dict[str, Any]]:
        """List tools from one or all configured servers."""
        targets = (
            [s for s in self.servers if s.get("name") == server_name]
            if server_name
            else self.servers
        )
        results: list[dict[str, Any]] = []
        for srv in targets:
            name = srv.get("name", "")
            client = await self._get_client(name)
            if client is None:
                continue
            try:
                tools = await client.list_tools()
                health = self._health.get(name)
                if health:
                    health.tool_count = len(tools)
                for t in tools:
                    results.append({
                        "server": name,
                        "name": t.name,
                        "description": getattr(t, "description", "") or "",
                        "inputSchema": (
                            t.inputSchema if hasattr(t, "inputSchema") else {}
                        ),
                    })
            except Exception as exc:  # noqa: BLE001
                health = self._health.get(name)
                if health:
                    health.error_count += 1
                    health.last_error = str(exc)[:200]
                log.warning(
                    "mcp_bridge.list_tools_failed",
                    server=name, error=str(exc)[:200],
                )
        return results

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """Call a tool on a specific server. Returns result text."""
        client = await self._get_client(server_name)
        if client is None:
            return f"Error: Cannot connect to MCP server '{server_name}'"

        health = self._health.get(server_name)
        try:
            result = await client.call_tool(tool_name, arguments)
            if health:
                health.call_count += 1
            # Extract text from CallToolResult
            if hasattr(result, "content") and result.content:
                parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                return "\n".join(parts) if parts else str(result)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            if health:
                health.error_count += 1
                health.last_error = str(exc)[:200]
            return f"Error calling {tool_name} on {server_name}: {exc!s}"

    async def close(self) -> None:
        """Disconnect all cached clients."""
        for name, client in list(self._clients.items()):
            try:
                await client.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._clients.pop(name, None)
                health = self._health.get(name)
                if health:
                    health.connected = False

    # ------------------------------------------------------------------
    # Structured health export (generic capability protocol)
    # ------------------------------------------------------------------

    def get_bridge_health(self) -> dict[str, Any]:
        """Return machine-readable bridge health for addon summary consumers.

        This is the capability-protocol export: if an addon registration's
        ``runtime_context`` contains a ``get_bridge_health`` callable,
        generic code (queen_tools, routes/api) can consume it without
        hardcoding addon names.
        """
        servers: list[dict[str, Any]] = []
        total_tools = 0
        connected_count = 0
        unhealthy_count = 0

        for s in self.servers:
            name = s.get("name", "")
            health = self._health.get(name)
            if health is None:
                servers.append({
                    "name": name,
                    "status": "unconfigured",
                })
                unhealthy_count += 1
                continue

            status = "connected" if health.connected else "disconnected"
            if health.error_count >= 3:
                status = "error"

            if health.connected:
                connected_count += 1
            else:
                unhealthy_count += 1

            total_tools += health.tool_count
            servers.append({
                "name": name,
                "status": status,
                "toolCount": health.tool_count,
                "callCount": health.call_count,
                "lastError": health.last_error,
            })

        return {
            "connectedServers": connected_count,
            "unhealthyServers": unhealthy_count,
            "totalRemoteTools": total_tools,
            "servers": servers,
        }
