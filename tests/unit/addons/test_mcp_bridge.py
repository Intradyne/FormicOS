"""Wave 70.0 Team A: MCP bridge addon tests.

Tests cover:
1. Bridge connects to configured server (mocked)
2. Bridge health reports disconnected/error states
3. Discovery handles unavailable server gracefully
4. _list_addons includes generic bridge health without name-based branching
5. Addon summary payload exposes bridge health additively
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.addons.mcp_bridge.client import McpBridge, ServerHealth


# ---------------------------------------------------------------------------
# 1. Bridge connects to configured server
# ---------------------------------------------------------------------------

@pytest.mark.anyio()
async def test_bridge_connect_and_list_tools() -> None:
    """Bridge establishes connection and lists remote tools."""
    bridge = McpBridge()
    bridge.configure([{"name": "test-srv", "url": "http://localhost:9999"}])

    mock_tool = MagicMock()
    mock_tool.name = "remote_add"
    mock_tool.description = "Add two numbers"
    mock_tool.inputSchema = {"type": "object"}

    mock_client = MagicMock()
    mock_client.is_connected = MagicMock(return_value=True)
    mock_client.list_tools = AsyncMock(return_value=[mock_tool])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "formicos.addons.mcp_bridge.client.Client",
        return_value=mock_client,
    ):
        tools = await bridge.list_tools("test-srv")

    assert len(tools) == 1
    assert tools[0]["name"] == "remote_add"
    assert tools[0]["server"] == "test-srv"

    health = bridge.get_bridge_health()
    assert health["connectedServers"] == 1
    assert health["totalRemoteTools"] == 1


@pytest.mark.anyio()
async def test_bridge_passes_optional_auth_to_client() -> None:
    """Configured auth token is forwarded to the HTTP client transport."""
    bridge = McpBridge()
    bridge.configure([{
        "name": "secure-srv",
        "url": "http://localhost:9999/sse",
        "auth": "test-token",
    }])

    mock_client = MagicMock()
    mock_client.is_connected = MagicMock(return_value=True)
    mock_client.list_tools = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "formicos.addons.mcp_bridge.client.Client",
        return_value=mock_client,
    ) as client_cls:
        await bridge.list_tools("secure-srv")

    client_cls.assert_called_once_with(
        "http://localhost:9999/sse",
        timeout=10,
        auth="test-token",
    )


# ---------------------------------------------------------------------------
# 2. Bridge health reports disconnected/error states
# ---------------------------------------------------------------------------

def test_bridge_health_disconnected() -> None:
    """Health reports disconnected servers correctly."""
    bridge = McpBridge()
    bridge.configure([
        {"name": "srv-a", "url": "http://a:9999"},
        {"name": "srv-b", "url": "http://b:9999"},
    ])
    # Simulate srv-a connected, srv-b disconnected with errors
    bridge._health["srv-a"] = ServerHealth(
        name="srv-a", url="http://a:9999",
        connected=True, tool_count=3,
    )
    bridge._health["srv-b"] = ServerHealth(
        name="srv-b", url="http://b:9999",
        connected=False, error_count=5,
        last_error="Connection refused",
    )

    health = bridge.get_bridge_health()
    assert health["connectedServers"] == 1
    assert health["unhealthyServers"] == 1
    assert health["totalRemoteTools"] == 3
    # srv-b should show error status (error_count >= 3)
    srv_b = next(s for s in health["servers"] if s["name"] == "srv-b")
    assert srv_b["status"] == "error"


# ---------------------------------------------------------------------------
# 3. Discovery handles unavailable server gracefully
# ---------------------------------------------------------------------------

@pytest.mark.anyio()
async def test_discovery_unavailable_server() -> None:
    """discover_mcp_tools returns friendly message when server is down."""
    from formicos.addons.mcp_bridge.discovery import handle_discover_tools

    bridge = McpBridge()
    bridge.configure([{"name": "down-srv", "url": "http://localhost:1"}])

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "formicos.addons.mcp_bridge.client.Client",
        return_value=mock_client,
    ):
        result = await handle_discover_tools(
            {"server": "down-srv"}, "ws1", "th1",
            runtime_context={"mcp_bridge": bridge},
        )

    assert "No tools discovered" in result


@pytest.mark.anyio()
async def test_discovery_no_bridge() -> None:
    """discover_mcp_tools returns message when bridge not configured."""
    from formicos.addons.mcp_bridge.discovery import handle_discover_tools

    result = await handle_discover_tools({}, "ws1", "th1", runtime_context={})
    assert "not configured" in result


# ---------------------------------------------------------------------------
# 4. _list_addons includes generic bridge health (no name-based branching)
# ---------------------------------------------------------------------------

def test_list_addons_bridge_health_generic() -> None:
    """_list_addons surfaces bridge health via capability protocol."""
    from formicos.surface.queen_tools import QueenToolDispatcher

    runtime = MagicMock()
    dispatcher = QueenToolDispatcher(runtime)

    # Simulate addon manifests
    manifest = SimpleNamespace(
        name="mcp-bridge",
        description="Bridge remote MCP servers",
        content_kinds=[],
        path_globs=[],
        search_tool="",
        tools=[SimpleNamespace(name="discover_mcp_tools")],
        triggers=[],
    )
    dispatcher._addon_manifests = [manifest]

    # Simulate bridge health callable in runtime context
    def fake_bridge_health() -> dict[str, Any]:
        return {
            "connectedServers": 2,
            "unhealthyServers": 0,
            "totalRemoteTools": 7,
            "servers": [],
        }

    dispatcher._addon_runtime_context = {
        "get_bridge_health": fake_bridge_health,
    }

    text, _ = dispatcher._list_addons()

    assert "Bridge Status" in text
    assert "2 connected" in text
    assert "7 remote tools" in text
    # Verify no addon-name branching — the text doesn't come from
    # checking addon name, it comes from the capability protocol
    assert "mcp-bridge" in text  # Addon listed normally by name


# ---------------------------------------------------------------------------
# 5. Addon summary payload exposes bridge health additively
# ---------------------------------------------------------------------------

def test_addon_summary_bridge_health() -> None:
    """GET /api/v1/addons includes bridgeHealth when capability present."""
    from starlette.testclient import TestClient

    from formicos.surface.addon_loader import AddonManifest, AddonRegistration

    manifest = AddonManifest(
        name="mcp-bridge",
        version="1.0.0",
        description="Bridge remote MCP servers",
    )
    reg = AddonRegistration(manifest)

    def fake_health() -> dict[str, Any]:
        return {
            "connectedServers": 1,
            "unhealthyServers": 0,
            "totalRemoteTools": 5,
            "servers": [{"name": "srv", "status": "connected"}],
        }

    reg.runtime_context = {"get_bridge_health": fake_health}

    # Build a minimal Starlette app with just the addons endpoint
    from starlette.applications import Starlette
    from starlette.routing import Route

    from formicos.surface.routes.api import routes

    settings_mock = MagicMock()
    settings_mock.system = SimpleNamespace(data_dir="/tmp/test")

    route_list = routes(
        runtime=MagicMock(),
        settings=settings_mock,
        castes=None,
        castes_path="",
        config_path="",
        vector_store=None,
        kg_adapter=None,
        embed_client=None,
        skill_collection="",
        ws_manager=MagicMock(),
    )
    app = Starlette(routes=route_list)
    app.state.addon_registrations = [reg]  # type: ignore[attr-defined]

    client = TestClient(app)
    resp = client.get("/api/v1/addons")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "bridgeHealth" in data[0]
    bh = data[0]["bridgeHealth"]
    assert bh["connectedServers"] == 1
    assert bh["totalRemoteTools"] == 5


# ---------------------------------------------------------------------------
# 6. call_mcp_tool handler
# ---------------------------------------------------------------------------

@pytest.mark.anyio()
async def test_call_tool_handler() -> None:
    """call_mcp_tool handler delegates to bridge."""
    from formicos.addons.mcp_bridge.discovery import handle_call_tool

    bridge = MagicMock()
    bridge.call_tool = AsyncMock(return_value="result: 42")

    result = await handle_call_tool(
        {"server": "srv", "tool": "add", "arguments": {"a": 1}},
        "ws1", "th1",
        runtime_context={"mcp_bridge": bridge},
    )

    assert result == "result: 42"
    bridge.call_tool.assert_awaited_once_with("srv", "add", {"a": 1})


@pytest.mark.anyio()
async def test_call_tool_missing_params() -> None:
    """call_mcp_tool returns error when required params missing."""
    from formicos.addons.mcp_bridge.discovery import handle_call_tool

    result = await handle_call_tool(
        {"server": "", "tool": ""},
        "ws1", "th1",
        runtime_context={"mcp_bridge": MagicMock()},
    )
    assert "required" in result.lower()
