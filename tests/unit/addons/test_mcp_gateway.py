"""Wave 88 Track A: Governed MCP gateway tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.addons.mcp_bridge.gateway import (
    GovernedMcpGateway,
    McpPermission,
    create_gateway_for_addon,
    parse_permissions,
)


def _mock_bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.call_tool = AsyncMock(return_value="result text")
    bridge.list_tools = AsyncMock(return_value=[
        {"server": "github", "name": "list_pull_requests", "description": ""},
        {"server": "github", "name": "create_issue", "description": ""},
        {"server": "github", "name": "list_commits", "description": ""},
    ])
    return bridge


class TestParsePermissions:
    def test_parses_valid_entries(self) -> None:
        raw = [
            {"server": "github", "tools": ["list_pull_requests", "list_commits"], "mode": "read"},
        ]
        result = parse_permissions(raw)
        assert len(result) == 1
        assert result[0].server == "github"
        assert "list_pull_requests" in result[0].tools
        assert result[0].mode == "read"

    def test_skips_invalid_entries(self) -> None:
        raw = [
            "not a dict",
            {"server": "", "tools": []},  # empty server
            {"server": "gh", "tools": ["a"]},  # valid
        ]
        result = parse_permissions(raw)
        assert len(result) == 1
        assert result[0].server == "gh"

    def test_empty_list(self) -> None:
        assert parse_permissions([]) == []


class TestGovernedMcpGateway:
    def _make_gateway(self) -> GovernedMcpGateway:
        return GovernedMcpGateway(
            bridge=_mock_bridge(),
            addon_name="repo-activity",
            permissions=[
                McpPermission(
                    server="github",
                    tools=["list_pull_requests", "list_commits"],
                    mode="read",
                ),
            ],
        )

    def test_is_allowed_passes_for_listed_tool(self) -> None:
        gw = self._make_gateway()
        assert gw.is_allowed("github", "list_pull_requests") is True

    def test_is_allowed_denies_unlisted_tool(self) -> None:
        gw = self._make_gateway()
        assert gw.is_allowed("github", "create_issue") is False

    def test_is_allowed_denies_wrong_server(self) -> None:
        gw = self._make_gateway()
        assert gw.is_allowed("gitlab", "list_pull_requests") is False

    @pytest.mark.asyncio()
    async def test_call_tool_allowed_succeeds(self) -> None:
        gw = self._make_gateway()
        result = await gw.call_tool("github", "list_pull_requests", {"owner": "x"})
        assert result["ok"] is True
        assert result["result"] == "result text"
        assert gw._allowed_count == 1

    @pytest.mark.asyncio()
    async def test_call_tool_denied_returns_error(self) -> None:
        gw = self._make_gateway()
        result = await gw.call_tool("github", "create_issue", {})
        assert result["ok"] is False
        assert "denied" in result["error"]
        assert gw._denied_count == 1

    @pytest.mark.asyncio()
    async def test_call_tool_bridge_error(self) -> None:
        gw = self._make_gateway()
        gw.bridge.call_tool = AsyncMock(
            return_value="Error: Cannot connect to MCP server 'github'",
        )
        result = await gw.call_tool("github", "list_pull_requests")
        assert result["ok"] is False
        assert "Error" in result["error"]

    @pytest.mark.asyncio()
    async def test_call_tool_bridge_exception(self) -> None:
        gw = self._make_gateway()
        gw.bridge.call_tool = AsyncMock(side_effect=ConnectionError("timeout"))
        result = await gw.call_tool("github", "list_pull_requests")
        assert result["ok"] is False
        assert "timeout" in result["error"]

    @pytest.mark.asyncio()
    async def test_list_allowed_tools_filters(self) -> None:
        gw = self._make_gateway()
        tools = await gw.list_allowed_tools("github")
        names = [t["name"] for t in tools]
        assert "list_pull_requests" in names
        assert "list_commits" in names
        assert "create_issue" not in names

    def test_audit_summary(self) -> None:
        gw = self._make_gateway()
        summary = gw.get_audit_summary()
        assert summary["addon"] == "repo-activity"
        assert summary["allowed_calls"] == 0
        assert summary["denied_calls"] == 0
        assert len(summary["permissions"]) == 1


class TestCreateGatewayForAddon:
    def test_factory_creates_gateway(self) -> None:
        bridge = _mock_bridge()
        raw = [{"server": "gh", "tools": ["list_prs"], "mode": "read"}]
        gw = create_gateway_for_addon(bridge, "my-addon", raw)
        assert gw.addon_name == "my-addon"
        assert len(gw.permissions) == 1
        assert gw.is_allowed("gh", "list_prs") is True

    def test_factory_empty_permissions(self) -> None:
        bridge = _mock_bridge()
        gw = create_gateway_for_addon(bridge, "empty", [])
        assert gw.permissions == []
        assert gw.is_allowed("any", "any") is False
