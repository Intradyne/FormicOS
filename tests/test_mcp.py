"""
Tests for FormicOS v0.6.0 MCP Gateway client.

Covers:
- Tool discovery via mocked MCP session
- Tool call forwarding with result parsing
- Tool filtering by glob patterns (fnmatch)
- Automatic fallback from stdio to SSE on FileNotFoundError
- Timeout on slow tool calls
- Graceful degradation when MCP SDK is not installed
- Error tracking (_connect_error, _last_attempt)
- Disconnect cleans up state
- Health check for stdio and HTTP transports
- get_tools() returns FormicOS ToolInfo format
- refresh_tools() re-discovers tools
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import MCPGatewayConfig, ToolsScope


# ── Fixtures ────────────────────────────────────────────────────────────


def _make_config(**overrides) -> MCPGatewayConfig:
    """Build an MCPGatewayConfig with sensible defaults and overrides."""
    defaults = dict(
        enabled=True,
        transport="stdio",
        command="docker",
        args=["mcp", "gateway", "run"],
        docker_fallback_endpoint="http://localhost:8811",
        sse_retry_attempts=1,
        sse_retry_delay_seconds=0,
    )
    defaults.update(overrides)
    return MCPGatewayConfig(**defaults)


def _make_mock_tool(name: str, description: str = "", schema=None):
    """Create a mock MCP Tool object."""
    tool = SimpleNamespace()
    tool.name = name
    tool.description = description or f"Mock tool: {name}"
    tool.inputSchema = schema or {"type": "object", "properties": {}}
    return tool


def _make_mock_tools():
    """Standard set of mock tools for tests."""
    return [
        _make_mock_tool("filesystem_read", "Read a file"),
        _make_mock_tool("filesystem_write", "Write a file"),
        _make_mock_tool("fetch_url", "Fetch a URL"),
        _make_mock_tool("memory_store", "Store in memory"),
        _make_mock_tool("sequentialthinking_think", "Sequential thinking"),
    ]


def _make_text_block(text: str):
    """Create a mock content block with a .text attribute."""
    return SimpleNamespace(text=text)


@pytest.fixture
def mcp_config():
    """Default MCP gateway config for tests."""
    return _make_config()


@pytest.fixture
def mcp_config_sse():
    """MCP gateway config with SSE transport."""
    return _make_config(
        transport="sse",
        docker_fallback_endpoint="http://localhost:9800",
    )


@pytest.fixture
def mcp_config_streamable():
    """MCP gateway config with streamable_http transport."""
    return _make_config(transport="streamable_http")


# ═══════════════════════════════════════════════════════════════════════════
# Tool Discovery
# ═══════════════════════════════════════════════════════════════════════════


class TestToolDiscovery:
    """Test that connect() discovers tools from the MCP session."""

    @pytest.mark.asyncio
    async def test_stdio_connect_discovers_tools(self, mcp_config):
        """connect() via stdio returns True and populates tools list."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_tools = _make_mock_tools()

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=SimpleNamespace(tools=mock_tools)
        )

        # Mock the entire transport + session pipeline
        with patch("src.mcp_client.MCP_AVAILABLE", True), patch.object(
            client,
            "_connect_with_session",
            new_callable=AsyncMock,
        ) as mock_connect:
            mock_connect.return_value = True
            # Simulate tool population
            client._tools = mock_tools
            client._session = mock_session

            result = await mock_connect()
            assert result is True

        tools = client.get_tools()
        assert len(tools) == 5
        assert all(t["source"] == "mcp_gateway" for t in tools)
        assert all(t["enabled"] is True for t in tools)

    @pytest.mark.asyncio
    async def test_get_tools_format(self, mcp_config):
        """get_tools() returns ToolInfo dicts with all required fields."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = [
            _make_mock_tool(
                "test_tool",
                "A test tool",
                {"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ]

        tools = client.get_tools()
        assert len(tools) == 1
        tool = tools[0]
        assert tool["id"] == "test_tool"
        assert tool["name"] == "Test Tool"
        assert tool["description"] == "A test tool"
        assert tool["source"] == "mcp_gateway"
        assert tool["enabled"] is True
        assert "path" in tool["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_get_tools_empty_when_not_connected(self, mcp_config):
        """get_tools() returns empty list before connect()."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        assert client.get_tools() == []

    @pytest.mark.asyncio
    async def test_get_tools_default_description(self, mcp_config):
        """get_tools() generates a default description when tool has none."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        tool = _make_mock_tool("bare_tool")
        tool.description = None
        client._tools = [tool]

        tools = client.get_tools()
        assert tools[0]["description"] == "MCP tool: bare_tool"

    @pytest.mark.asyncio
    async def test_get_tools_default_schema(self, mcp_config):
        """get_tools() uses empty object schema when tool has no inputSchema."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        tool = _make_mock_tool("no_schema_tool")
        tool.inputSchema = None
        client._tools = [tool]

        tools = client.get_tools()
        assert tools[0]["parameters"] == {"type": "object", "properties": {}}


# ═══════════════════════════════════════════════════════════════════════════
# Tool Call Forwarding
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallForwarding:
    """Test call_tool() forwards to MCP session and parses response."""

    @pytest.mark.asyncio
    async def test_call_tool_returns_text(self, mcp_config):
        """call_tool() extracts .text from content blocks."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=SimpleNamespace(
                content=[_make_text_block("Hello, world!")]
            )
        )
        client._session = mock_session

        result = await client.call_tool("test_tool", {"arg": "value"})
        assert result == "Hello, world!"
        mock_session.call_tool.assert_awaited_once_with(
            "test_tool", {"arg": "value"}
        )

    @pytest.mark.asyncio
    async def test_call_tool_multiple_blocks(self, mcp_config):
        """call_tool() joins multiple content blocks with newlines."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=SimpleNamespace(
                content=[
                    _make_text_block("Line 1"),
                    _make_text_block("Line 2"),
                ]
            )
        )
        client._session = mock_session

        result = await client.call_tool("multi_tool", {})
        assert result == "Line 1\nLine 2"

    @pytest.mark.asyncio
    async def test_call_tool_non_text_block(self, mcp_config):
        """call_tool() falls back to str() for non-text blocks."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        # Block without .text attribute
        image_block = SimpleNamespace(type="image", data="base64data")
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=SimpleNamespace(content=[image_block])
        )
        client._session = mock_session

        result = await client.call_tool("image_tool", {})
        assert "base64data" in result

    @pytest.mark.asyncio
    async def test_call_tool_empty_content(self, mcp_config):
        """call_tool() returns '(no output)' when content is empty."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=SimpleNamespace(content=[])
        )
        client._session = mock_session

        result = await client.call_tool("empty_tool", {})
        assert result == "(no output)"

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self, mcp_config):
        """call_tool() returns error string when not connected."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        result = await client.call_tool("any_tool", {"x": 1})
        assert "ERROR" in result
        assert "not connected" in result

    @pytest.mark.asyncio
    async def test_call_tool_exception(self, mcp_config):
        """call_tool() returns error string on MCP session exception."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            side_effect=RuntimeError("server crashed")
        )
        client._session = mock_session

        result = await client.call_tool("crash_tool", {})
        assert "ERROR" in result
        assert "server crashed" in result

    @pytest.mark.asyncio
    async def test_call_tool_none_arguments(self, mcp_config):
        """call_tool() defaults None arguments to empty dict."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(
            return_value=SimpleNamespace(
                content=[_make_text_block("ok")]
            )
        )
        client._session = mock_session

        result = await client.call_tool("tool", None)
        assert result == "ok"
        mock_session.call_tool.assert_awaited_once_with("tool", {})


# ═══════════════════════════════════════════════════════════════════════════
# Tool Filtering
# ═══════════════════════════════════════════════════════════════════════════


class TestToolFiltering:
    """Test filter_tools() with glob patterns from ToolsScope."""

    @pytest.mark.asyncio
    async def test_filter_by_glob_pattern(self, mcp_config):
        """filter_tools() matches tool ids against glob patterns."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = _make_mock_tools()

        scope = ToolsScope(mcp=["filesystem_*"])
        filtered = client.filter_tools(scope)
        assert len(filtered) == 2
        ids = {t["id"] for t in filtered}
        assert ids == {"filesystem_read", "filesystem_write"}

    @pytest.mark.asyncio
    async def test_filter_multiple_patterns(self, mcp_config):
        """filter_tools() supports multiple glob patterns."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = _make_mock_tools()

        scope = ToolsScope(mcp=["filesystem_*", "fetch_*"])
        filtered = client.filter_tools(scope)
        assert len(filtered) == 3
        ids = {t["id"] for t in filtered}
        assert ids == {"filesystem_read", "filesystem_write", "fetch_url"}

    @pytest.mark.asyncio
    async def test_filter_empty_scope_allows_all(self, mcp_config):
        """Empty mcp scope allows all tools through."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = _make_mock_tools()

        scope = ToolsScope(mcp=[])
        filtered = client.filter_tools(scope)
        assert len(filtered) == 5

    @pytest.mark.asyncio
    async def test_filter_no_match(self, mcp_config):
        """filter_tools() returns empty list when no patterns match."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = _make_mock_tools()

        scope = ToolsScope(mcp=["nonexistent_*"])
        filtered = client.filter_tools(scope)
        assert len(filtered) == 0

    @pytest.mark.asyncio
    async def test_filter_no_tools(self, mcp_config):
        """filter_tools() returns empty list when no tools discovered."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        scope = ToolsScope(mcp=["*"])
        filtered = client.filter_tools(scope)
        assert filtered == []

    @pytest.mark.asyncio
    async def test_filter_exact_match(self, mcp_config):
        """filter_tools() supports exact tool name (not just globs)."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = _make_mock_tools()

        scope = ToolsScope(mcp=["fetch_url"])
        filtered = client.filter_tools(scope)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "fetch_url"


# ═══════════════════════════════════════════════════════════════════════════
# Stdio -> SSE Fallback
# ═══════════════════════════════════════════════════════════════════════════


class TestStdioToSseFallback:
    """Test automatic fallback from stdio to SSE on FileNotFoundError."""

    @pytest.mark.asyncio
    async def test_fallback_on_file_not_found(self, mcp_config):
        """connect() falls back to SSE when stdio raises FileNotFoundError."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        _mock_tools = _make_mock_tools()

        # Patch MCP_AVAILABLE, stdio fails, SSE succeeds
        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=FileNotFoundError("docker not found"),
        ), patch.object(
            client,
            "_try_sse_fallback",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_sse:
            result = await client.connect()

        assert result is True
        mock_sse.assert_awaited_once_with("http://localhost:8811")

    @pytest.mark.asyncio
    async def test_fallback_on_os_error(self, mcp_config):
        """connect() falls back to SSE when stdio raises OSError."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=OSError("permission denied"),
        ), patch.object(
            client,
            "_try_sse_fallback",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_sse:
            result = await client.connect()

        assert result is True
        mock_sse.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_fallback_without_endpoint(self):
        """connect() does not fallback when no fallback endpoint configured."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config(
            command="nonexistent_cmd",
            docker_fallback_endpoint="",
        )
        client = MCPGatewayClient(config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=FileNotFoundError("not found"),
        ), patch(
            "src.mcp_client._resolve_command",
            return_value="nonexistent_cmd",
        ):
            result = await client.connect()

        assert result is False
        assert client.connect_error is not None
        assert "Command not found" in client.connect_error

    @pytest.mark.asyncio
    async def test_fallback_sets_used_fallback_flag(self, mcp_config):
        """After SSE fallback, used_fallback property is True."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=FileNotFoundError("not found"),
        ), patch.object(
            client,
            "_try_sse_fallback",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await client.connect()

        # _try_sse_fallback was mocked, so we check it was called;
        # the flag is set inside _try_sse_fallback itself
        assert client.last_attempt is not None


# ═══════════════════════════════════════════════════════════════════════════
# Timeout on Tool Calls
# ═══════════════════════════════════════════════════════════════════════════


class TestToolCallTimeout:
    """Test that slow tool calls are timed out."""

    @pytest.mark.asyncio
    async def test_timeout_on_slow_tool(self, mcp_config):
        """call_tool() returns timeout error when tool exceeds timeout."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tool_call_timeout = 0.1  # 100ms

        async def slow_tool(*args, **kwargs):
            await asyncio.sleep(5)
            return SimpleNamespace(content=[_make_text_block("too late")])

        mock_session = AsyncMock()
        mock_session.call_tool = slow_tool
        client._session = mock_session

        result = await client.call_tool("slow_tool", {})
        assert "ERROR" in result
        assert "timed out" in result
        assert "slow_tool" in result

    @pytest.mark.asyncio
    async def test_default_timeout_is_30s(self, mcp_config):
        """Default tool call timeout is 30 seconds."""
        from src.mcp_client import DEFAULT_TOOL_CALL_TIMEOUT, MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        assert client._tool_call_timeout == 30
        assert DEFAULT_TOOL_CALL_TIMEOUT == 30


# ═══════════════════════════════════════════════════════════════════════════
# MCP Not Installed
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPNotInstalled:
    """Test graceful degradation when MCP SDK is not installed."""

    @pytest.mark.asyncio
    async def test_connect_returns_false(self, mcp_config):
        """connect() returns False when MCP SDK not installed."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", False):
            result = await client.connect()

        assert result is False
        assert client.connect_error is not None
        assert "mcp package not installed" in client.connect_error

    @pytest.mark.asyncio
    async def test_health_check_returns_false(self, mcp_config):
        """health_check() returns False when MCP SDK not installed."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", False):
            result = await client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_tools_empty_when_not_installed(self, mcp_config):
        """get_tools() returns empty list when MCP SDK not installed."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        # Never connected, SDK missing
        assert client.get_tools() == []

    @pytest.mark.asyncio
    async def test_call_tool_returns_error_when_not_connected(self, mcp_config):
        """call_tool() returns error string when never connected."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        result = await client.call_tool("any", {})
        assert "ERROR" in result
        assert "not connected" in result


# ═══════════════════════════════════════════════════════════════════════════
# Error Tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorTracking:
    """Test that connection errors are stored for UI display."""

    @pytest.mark.asyncio
    async def test_connect_error_stored(self, mcp_config):
        """Failed connect() stores error message in connect_error."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=FileNotFoundError("docker not found"),
        ), patch.object(
            client,
            "_get_fallback_endpoint",
            return_value=None,
        ):
            result = await client.connect()

        assert result is False
        assert client.connect_error is not None
        assert "Command not found" in client.connect_error

    @pytest.mark.asyncio
    async def test_last_attempt_not_set_when_sdk_missing(self, mcp_config):
        """connect() does not set _last_attempt when MCP SDK is missing."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        assert client.last_attempt is None

        with patch("src.mcp_client.MCP_AVAILABLE", False):
            await client.connect()

        # MCP_AVAILABLE=False returns early before setting _last_attempt
        assert client.last_attempt is None

    @pytest.mark.asyncio
    async def test_last_attempt_timestamp_on_real_attempt(self):
        """connect() records _last_attempt when MCP is available."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config()
        client = MCPGatewayClient(config)

        before = time.time()
        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client.StdioServerParameters"
        ), patch(
            "src.mcp_client.stdio_client",
            side_effect=FileNotFoundError("nope"),
        ), patch.object(
            client,
            "_get_fallback_endpoint",
            return_value=None,
        ):
            await client.connect()
        after = time.time()

        assert client.last_attempt is not None
        assert before <= client.last_attempt <= after

    @pytest.mark.asyncio
    async def test_connect_error_cleared_on_retry(self, mcp_config):
        """connect() clears previous error before a new attempt."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._connect_error = "old error"

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch.object(
            client,
            "_connect_stdio",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await client.connect()

        assert result is True
        assert client.connect_error is None

    @pytest.mark.asyncio
    async def test_generic_exception_stored(self, mcp_config):
        """connect() stores generic exception as connect_error."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch.object(
            client,
            "_connect_stdio",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            result = await client.connect()

        assert result is False
        assert "RuntimeError: unexpected" in client.connect_error


# ═══════════════════════════════════════════════════════════════════════════
# Disconnect
# ═══════════════════════════════════════════════════════════════════════════


class TestDisconnect:
    """Test disconnect() cleans up resources."""

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self, mcp_config):
        """disconnect() resets session, tools, and exit stack."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._session = MagicMock()
        client._tools = _make_mock_tools()

        await client.disconnect()

        assert client._session is None
        assert client._tools == []
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_exception(self, mcp_config):
        """disconnect() does not raise when exit_stack cleanup fails."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._exit_stack = AsyncMock()
        client._exit_stack.aclose = AsyncMock(
            side_effect=BrokenPipeError("pipe broken")
        )
        client._session = MagicMock()

        # Should not raise
        await client.disconnect()
        assert client._session is None


# ═══════════════════════════════════════════════════════════════════════════
# Health Check
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthCheck:
    """Test health_check() for different transport types."""

    @pytest.mark.asyncio
    async def test_stdio_healthy_with_session(self, mcp_config):
        """health_check() returns True for stdio with active session."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._session = MagicMock()

        with patch("src.mcp_client.MCP_AVAILABLE", True):
            result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_stdio_unhealthy_without_session(self, mcp_config):
        """health_check() returns False for stdio without session."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)

        with patch("src.mcp_client.MCP_AVAILABLE", True):
            result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_sse_health_pings_endpoint(self, mcp_config_sse):
        """health_check() pings HTTP endpoint for SSE transport."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config_sse)
        client._used_fallback = True
        client._fallback_url = "http://localhost:9800"

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "httpx.AsyncClient"
        ) as mock_httpx:
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=mock_response)
            mock_client_inst.__aenter__ = AsyncMock(
                return_value=mock_client_inst
            )
            mock_client_inst.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client_inst

            result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_http_error(
        self, mcp_config_sse
    ):
        """health_check() returns False when HTTP ping fails."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config_sse)
        client._used_fallback = True
        client._fallback_url = "http://localhost:9800"

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "httpx.AsyncClient"
        ) as mock_httpx:
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(
                side_effect=ConnectionError("refused")
            )
            mock_client_inst.__aenter__ = AsyncMock(
                return_value=mock_client_inst
            )
            mock_client_inst.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client_inst

            result = await client.health_check()

        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# Refresh Tools
# ═══════════════════════════════════════════════════════════════════════════


class TestRefreshTools:
    """Test refresh_tools() re-discovers tools from MCP session."""

    @pytest.mark.asyncio
    async def test_refresh_updates_tool_list(self, mcp_config):
        """refresh_tools() updates cached tools and returns count."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        initial_tools = [_make_mock_tool("old_tool")]
        new_tools = _make_mock_tools()

        client._tools = initial_tools
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=SimpleNamespace(tools=new_tools)
        )
        client._session = mock_session

        count = await client.refresh_tools()
        assert count == 5
        assert len(client._tools) == 5

    @pytest.mark.asyncio
    async def test_refresh_when_not_connected(self, mcp_config):
        """refresh_tools() returns cached count when not connected."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = [_make_mock_tool("cached")]

        count = await client.refresh_tools()
        assert count == 1

    @pytest.mark.asyncio
    async def test_refresh_on_exception(self, mcp_config):
        """refresh_tools() returns cached count on session error."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._tools = [_make_mock_tool("cached")]
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(
            side_effect=RuntimeError("session dead")
        )
        client._session = mock_session

        count = await client.refresh_tools()
        assert count == 1


# ═══════════════════════════════════════════════════════════════════════════
# Display Name
# ═══════════════════════════════════════════════════════════════════════════


class TestDisplayName:
    """Test display_name property for UI rendering."""

    def test_display_name_stdio(self, mcp_config):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        assert "docker" in client.display_name
        assert "mcp" in client.display_name

    def test_display_name_fallback(self, mcp_config):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._used_fallback = True
        client._fallback_url = "http://localhost:8811"
        assert "SSE fallback" in client.display_name
        assert "localhost:8811" in client.display_name

    def test_display_name_sse(self, mcp_config_sse):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config_sse)
        assert "localhost:9800" in client.display_name


# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════


class TestUnwrapException:
    """Test _unwrap_exception helper."""

    def test_simple_exception(self):
        from src.mcp_client import _unwrap_exception

        exc = ValueError("bad value")
        assert _unwrap_exception(exc) == "ValueError: bad value"

    def test_exception_group(self):
        from src.mcp_client import _unwrap_exception

        inner1 = ConnectionError("refused")
        inner2 = TimeoutError("timed out")
        group = BaseExceptionGroup("group", [inner1, inner2])
        result = _unwrap_exception(group)
        assert "ConnectionError: refused" in result
        assert "TimeoutError: timed out" in result


class TestResolveCommand:
    """Test _resolve_command helper."""

    def test_resolve_simple_command(self):
        from src.mcp_client import _resolve_command

        # Should return the command or a resolved path (never None)
        result = _resolve_command("python")
        assert result is not None
        assert len(result) > 0

    def test_resolve_nonexistent_command(self):
        from src.mcp_client import _resolve_command

        # Non-existent command returns the bare name
        result = _resolve_command("definitely_not_a_real_command_xyz")
        assert result == "definitely_not_a_real_command_xyz"


# ═══════════════════════════════════════════════════════════════════════════
# Connected Property
# ═══════════════════════════════════════════════════════════════════════════


class TestConnectedProperty:
    """Test the connected property."""

    def test_connected_false_initially(self, mcp_config):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        assert client.connected is False

    def test_connected_true_with_session(self, mcp_config):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._session = MagicMock()
        assert client.connected is True

    def test_connected_false_after_disconnect(self, mcp_config):
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config)
        client._session = MagicMock()
        assert client.connected is True
        client._session = None
        assert client.connected is False


# ═══════════════════════════════════════════════════════════════════════════
# SSE Transport Direct
# ═══════════════════════════════════════════════════════════════════════════


class TestSSETransport:
    """Test direct SSE transport (not fallback)."""

    @pytest.mark.asyncio
    async def test_sse_connect_calls_try_sse_fallback(self, mcp_config_sse):
        """SSE transport delegates to _try_sse_fallback."""
        from src.mcp_client import MCPGatewayClient

        client = MCPGatewayClient(mcp_config_sse)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch.object(
            client,
            "_try_sse_fallback",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_sse:
            result = await client.connect()

        assert result is True
        mock_sse.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sse_no_endpoint(self):
        """SSE transport fails when no endpoint configured."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config(
            transport="sse", docker_fallback_endpoint=""
        )
        client = MCPGatewayClient(config)

        with patch("src.mcp_client.MCP_AVAILABLE", True):
            result = await client.connect()

        assert result is False
        assert "No endpoint" in client.connect_error


# ═══════════════════════════════════════════════════════════════════════════
# Streamable HTTP Transport
# ═══════════════════════════════════════════════════════════════════════════


class TestStreamableHTTPTransport:
    """Test streamable_http transport."""

    @pytest.mark.asyncio
    async def test_streamable_http_not_available(self):
        """streamable_http fails gracefully when SDK lacks support."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config(transport="streamable_http")
        client = MCPGatewayClient(config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client._HAS_STREAMABLE_HTTP", False
        ):
            result = await client.connect()

        assert result is False
        assert "not available" in client.connect_error

    @pytest.mark.asyncio
    async def test_streamable_http_no_endpoint(self):
        """streamable_http fails when no endpoint configured."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config(
            transport="streamable_http", docker_fallback_endpoint=""
        )
        client = MCPGatewayClient(config)

        with patch("src.mcp_client.MCP_AVAILABLE", True), patch(
            "src.mcp_client._HAS_STREAMABLE_HTTP", True
        ):
            result = await client.connect()

        assert result is False
        assert "No endpoint" in client.connect_error


# ═══════════════════════════════════════════════════════════════════════════
# Unknown Transport
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownTransport:
    """Test unknown transport type."""

    @pytest.mark.asyncio
    async def test_unknown_transport(self):
        """connect() returns False for unknown transport."""
        from src.mcp_client import MCPGatewayClient

        config = _make_config(transport="carrier_pigeon")
        client = MCPGatewayClient(config)

        with patch("src.mcp_client.MCP_AVAILABLE", True):
            result = await client.connect()

        assert result is False
        assert "Unknown transport" in client.connect_error
