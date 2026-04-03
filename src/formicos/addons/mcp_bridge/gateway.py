"""Governed MCP gateway — per-addon policy enforcement (Wave 88 Track A).

Wraps the raw ``McpBridge`` with per-addon allowlist enforcement.
Only tools explicitly declared in the addon's ``mcp_permissions``
manifest field pass through. Everything else is denied before reaching
the bridge.

Usage from addon handlers::

    from formicos.addons.mcp_bridge.gateway import GovernedMcpGateway

    gw = GovernedMcpGateway(bridge, addon_name="repo-activity", permissions=[
        {"server": "github", "tools": ["list_pull_requests", ...], "mode": "read"},
    ])
    result = await gw.call_tool("github", "list_pull_requests", {"owner": "...", "repo": "..."})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.addons.mcp_bridge.client import McpBridge

log = structlog.get_logger()


@dataclass
class McpPermission:
    """One permission entry: which tools an addon may call on a server."""

    server: str
    tools: list[str] = field(default_factory=list)
    mode: str = "read"  # only "read" supported in Wave 88


def parse_permissions(
    raw: list[dict[str, Any]],
) -> list[McpPermission]:
    """Parse raw manifest permission dicts into typed objects."""
    result: list[McpPermission] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        server = entry.get("server", "")
        tools = entry.get("tools", [])
        mode = entry.get("mode", "read")
        if server and isinstance(tools, list):
            result.append(McpPermission(
                server=server,
                tools=[str(t) for t in tools],
                mode=str(mode),
            ))
    return result


@dataclass
class GovernedMcpGateway:
    """Policy-enforcing wrapper around McpBridge for addon use.

    Checks every ``call_tool`` request against the addon's declared
    permissions before forwarding to the raw bridge.
    """

    bridge: McpBridge
    addon_name: str
    permissions: list[McpPermission] = field(default_factory=list)

    # Audit counters
    _allowed_count: int = field(default=0, repr=False)
    _denied_count: int = field(default=0, repr=False)

    def is_allowed(self, server: str, tool_name: str) -> bool:
        """Check whether a specific tool call is permitted."""
        return any(
            perm.server == server and tool_name in perm.tools
            for perm in self.permissions
        )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool through the governed gateway.

        Returns a dict with ``ok``, ``result`` (on success), or ``error``
        (on denial/failure).
        """
        if not self.is_allowed(server_name, tool_name):
            self._denied_count += 1
            log.warning(
                "mcp_gateway.denied",
                addon=self.addon_name,
                server=server_name,
                tool=tool_name,
            )
            return {
                "ok": False,
                "error": (
                    f"MCP call denied: addon '{self.addon_name}' is not "
                    f"permitted to call '{tool_name}' on '{server_name}'"
                ),
            }

        self._allowed_count += 1
        log.info(
            "mcp_gateway.allowed",
            addon=self.addon_name,
            server=server_name,
            tool=tool_name,
        )

        try:
            result_text = await self.bridge.call_tool(
                server_name, tool_name, arguments,
            )
            if result_text.startswith("Error"):
                return {"ok": False, "error": result_text}
            return {"ok": True, "result": result_text}
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "mcp_gateway.call_failed",
                addon=self.addon_name,
                server=server_name,
                tool=tool_name,
                error=str(exc)[:200],
            )
            return {
                "ok": False,
                "error": f"MCP call failed: {exc!s}",
            }

    async def list_allowed_tools(
        self, server_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List only the tools this addon is allowed to use."""
        all_tools = await self.bridge.list_tools(server_name)
        allowed_set: set[str] = set()
        for perm in self.permissions:
            if server_name is None or perm.server == server_name:
                allowed_set.update(perm.tools)

        return [t for t in all_tools if t.get("name") in allowed_set]

    def get_audit_summary(self) -> dict[str, Any]:
        """Return audit counters for this gateway instance."""
        return {
            "addon": self.addon_name,
            "allowed_calls": self._allowed_count,
            "denied_calls": self._denied_count,
            "permissions": [
                {"server": p.server, "tools": p.tools, "mode": p.mode}
                for p in self.permissions
            ],
        }


def create_gateway_for_addon(
    bridge: McpBridge,
    addon_name: str,
    mcp_permissions: list[dict[str, Any]],
) -> GovernedMcpGateway:
    """Factory: create a governed gateway from raw manifest permissions."""
    permissions = parse_permissions(mcp_permissions)
    return GovernedMcpGateway(
        bridge=bridge,
        addon_name=addon_name,
        permissions=permissions,
    )
