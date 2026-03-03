"""
MCP Gateway client -- connects to MCP tool servers via multiple transports.

Discovers tools and forwards tool calls from colony agents to MCP servers.

Supports three transports with automatic fallback:
  - stdio: spawns an MCP command as a subprocess (e.g. `docker mcp gateway run`)
  - sse: connects to an HTTP SSE endpoint
  - streamable_http: connects via streamable HTTP transport

When configured for stdio but the command is not found (e.g. inside a Docker
container where the host CLI is unavailable), automatically falls back to SSE
transport targeting a configured fallback endpoint.

The MCP SDK is optional. If not installed, the gateway degrades gracefully:
connect() returns False, health_check() returns False, tools list is empty.
"""

import asyncio
import fnmatch
import json
import logging
import os
import time
from contextlib import AsyncExitStack

from src.models import MCPGatewayConfig, ToolsScope

logger = logging.getLogger(__name__)

# ── Optional MCP SDK imports ────────────────────────────────────────────
try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.sse import sse_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Streamable HTTP may not exist in older MCP SDK versions
_HAS_STREAMABLE_HTTP = False
if MCP_AVAILABLE:
    try:
        from mcp.client.streamable_http import streamable_http_client

        _HAS_STREAMABLE_HTTP = True
    except ImportError:
        pass

# ── Constants ───────────────────────────────────────────────────────────

DEFAULT_TOOL_CALL_TIMEOUT = 30  # seconds


# ── Helpers ─────────────────────────────────────────────────────────────


def _unwrap_exception(exc: BaseException) -> str:
    """
    Extract a human-readable message from an exception, unwrapping
    ExceptionGroups (which the MCP SDK's anyio TaskGroup produces
    when SSE connections fail).
    """
    if isinstance(exc, BaseExceptionGroup):
        causes = []
        for sub in exc.exceptions:
            causes.append(_unwrap_exception(sub))
        return "; ".join(causes)
    return f"{type(exc).__name__}: {exc}"


def _resolve_command(command: str) -> str:
    """
    Resolve a bare command name to a full path.

    For 'docker' with 'mcp' in args, finds the docker-mcp CLI plugin
    directly (Docker Desktop's docker.exe wrapper doesn't route to
    plugins when spawned as a subprocess).
    """
    import shutil
    from pathlib import Path

    resolved = shutil.which(command) or command

    # Docker Desktop special case: `docker mcp` needs the CLI plugin
    # binary directly because `docker.exe` can't route to plugins
    # when spawned as a subprocess (missing Desktop context).
    if command == "docker":
        plugin_dirs = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Docker/Docker/resources/cli-plugins",
            Path.home() / ".docker/cli-plugins",
        ]
        for d in plugin_dirs:
            for ext in ("", ".exe"):
                candidate = d / f"docker-mcp{ext}"
                if candidate.exists():
                    logger.info("Resolved docker -> %s", candidate)
                    return str(candidate)

    return resolved


# ── Hardware Interrupt (v0.7.7) ─────────────────────────────────────────


class MCPHardwareInterrupt(Exception):
    """Raised when an MCP tool call hits a hardware constraint.

    Attributes
    ----------
    tool_name : str
        The tool that triggered the interrupt.
    tool_args : dict
        Arguments passed to the tool.
    duration_ms : float
        Wall-clock time before the interrupt.
    interrupt_type : str
        One of: "timeout", "memory", "sandbox", "error".
    """

    def __init__(
        self,
        message: str,
        *,
        tool_name: str = "",
        tool_args: dict | None = None,
        duration_ms: float = 0.0,
        interrupt_type: str = "error",
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.duration_ms = duration_ms
        self.interrupt_type = interrupt_type


# ── Main Client ─────────────────────────────────────────────────────────


class MCPGatewayClient:
    """
    Client that connects to MCP tool servers and proxies tool calls.

    Accepts an MCPGatewayConfig from formicos.yaml. Manages the full
    connection lifecycle: transport negotiation, tool discovery, call
    forwarding, filtering, refresh, health checks, and error tracking.
    """

    def __init__(self, config: MCPGatewayConfig) -> None:
        self._config = config
        self._exit_stack = AsyncExitStack()
        self._session = None  # mcp.ClientSession when connected
        self._tools: list = []  # raw MCP Tool objects
        self._connect_error: str | None = None
        self._last_attempt: float | None = None
        self._used_fallback: bool = False
        self._fallback_url: str | None = None
        self._tool_call_timeout: float = DEFAULT_TOOL_CALL_TIMEOUT
        self._last_call_duration_ms: float = 0.0  # v0.7.7: timing capture
        self._mock_mode: bool = False  # v0.7.8: test flight sandbox

    # ── Properties ──────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """True when an active MCP session exists."""
        return self._session is not None

    def enable_mock_mode(self) -> None:
        """Enable mock mode — call_tool returns static success instead of executing."""
        self._mock_mode = True

    def disable_mock_mode(self) -> None:
        """Disable mock mode — call_tool executes normally."""
        self._mock_mode = False

    @property
    def connect_error(self) -> str | None:
        """Last connection error message (for UI display)."""
        return self._connect_error

    @property
    def last_attempt(self) -> float | None:
        """Timestamp of last connection attempt (for UI display)."""
        return self._last_attempt

    @property
    def used_fallback(self) -> bool:
        """True if currently connected via SSE fallback instead of primary."""
        return self._used_fallback

    @property
    def display_name(self) -> str:
        """Human-readable connection target for UI display."""
        if self._used_fallback:
            return f"SSE fallback -> {self._fallback_url}"
        if self._config.transport == "stdio":
            return f"{self._config.command} {' '.join(self._config.args)}"
        return self._config.docker_fallback_endpoint or "unknown"

    # ── Transport helpers ───────────────────────────────────────────

    def _get_fallback_endpoint(self) -> str | None:
        """
        Determine SSE fallback endpoint when stdio transport fails.

        Priority:
        1. Explicit docker_fallback_endpoint from config
        2. Inside Docker container -> mcp-gateway sidecar (same Docker network)
        3. On host -> localhost (for dev workflows)
        """
        if self._config.docker_fallback_endpoint:
            return self._config.docker_fallback_endpoint
        # Only auto-fallback for docker command (MCP Toolkit)
        if self._config.command != "docker":
            return None
        if os.path.exists("/.dockerenv") or os.environ.get("container"):
            return "http://mcp-gateway:8811"
        return "http://localhost:8811"

    async def _connect_with_session(self, transport_ctx) -> bool:
        """Finish connection setup: create session, initialize, list tools."""
        transport = await self._exit_stack.enter_async_context(transport_ctx)
        read_stream, write_stream = transport[0], transport[1]
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await asyncio.wait_for(self._session.initialize(), timeout=30.0)

        response = await asyncio.wait_for(self._session.list_tools(), timeout=30.0)
        self._tools = response.tools
        logger.info(
            "MCP Gateway connected: %d tools discovered via %s",
            len(self._tools),
            self.display_name,
        )
        return True

    async def _try_sse_fallback(self, fallback_url: str) -> bool:
        """
        Attempt SSE connection as fallback when stdio is not available.

        Retries with exponential backoff because the MCP gateway sidecar
        may still be starting. Unwraps ExceptionGroups from the MCP SDK's
        anyio TaskGroup to surface the real connection error.
        """
        self._fallback_url = fallback_url
        self._used_fallback = True
        url = fallback_url.rstrip("/") + "/sse"

        last_error: BaseException | None = None
        max_attempts = self._config.sse_retry_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "SSE fallback attempt %d/%d -> %s",
                    attempt,
                    max_attempts,
                    url,
                )
                return await self._connect_with_session(sse_client(url))
            except (Exception, BaseExceptionGroup) as e:
                last_error = e
                readable = _unwrap_exception(e)
                if attempt < max_attempts:
                    delay = self._config.sse_retry_delay_seconds * (
                        2 ** (attempt - 1)
                    )
                    logger.info(
                        "  attempt %d failed (%s) -- retrying in %.0fs",
                        attempt,
                        readable,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "  attempt %d failed (%s) -- no more retries",
                        attempt,
                        readable,
                    )

        self._connect_error = (
            f"SSE fallback to {fallback_url} failed after "
            f"{max_attempts} attempts: "
            f"{_unwrap_exception(last_error)}"
        )
        logger.warning(self._connect_error)
        return False

    # ── Public API ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Connect to the MCP Gateway. Returns True on success.

        Transport negotiation:
          1. stdio -- spawn command as subprocess
          2. sse -- connect to HTTP SSE endpoint
          3. streamable_http -- connect via HTTP transport

        If stdio fails with FileNotFoundError/OSError, automatically
        falls back to SSE at the configured docker_fallback_endpoint.
        """
        if not MCP_AVAILABLE:
            self._connect_error = (
                "mcp package not installed -- gateway disabled"
            )
            logger.warning(self._connect_error)
            return False

        self._last_attempt = time.time()
        self._connect_error = None
        self._used_fallback = False

        try:
            if self._config.transport == "stdio":
                return await self._connect_stdio()
            elif self._config.transport == "sse":
                return await self._connect_sse()
            elif self._config.transport == "streamable_http":
                return await self._connect_streamable_http()
            else:
                self._connect_error = (
                    f"Unknown transport: {self._config.transport}"
                )
                logger.warning(self._connect_error)
                return False

        except (Exception, BaseExceptionGroup) as e:
            self._connect_error = _unwrap_exception(e)
            logger.warning(
                "MCP Gateway connection failed (%s): %s",
                self.display_name,
                self._connect_error,
            )
            return False

    async def _connect_stdio(self) -> bool:
        """Connect via stdio transport with automatic SSE fallback."""
        if not self._config.command:
            self._connect_error = (
                "No command configured for stdio transport"
            )
            logger.warning(self._connect_error)
            return False

        resolved_cmd = _resolve_command(self._config.command)
        args = list(self._config.args)

        # If we resolved `docker` -> `docker-mcp`, strip the leading
        # "mcp" from args since it is now part of the binary name.
        if (
            self._config.command == "docker"
            and "docker-mcp" in resolved_cmd
            and args
            and args[0] == "mcp"
        ):
            args = args[1:]

        # Pass full environment so subprocess gets ProgramData, PATH,
        # and other vars needed by Docker Desktop on Windows.
        env = dict(os.environ)

        server_params = StdioServerParameters(
            command=resolved_cmd,
            args=args,
            env=env,
        )
        try:
            return await self._connect_with_session(
                stdio_client(server_params)
            )
        except (FileNotFoundError, OSError) as exc:
            # stdio failed -- likely inside a Docker container without
            # the docker binary. Try SSE fallback.
            fallback = self._get_fallback_endpoint()
            if fallback:
                logger.info(
                    "stdio command '%s' not found (%s) -- "
                    "falling back to SSE via %s",
                    resolved_cmd,
                    exc,
                    fallback,
                )
                return await self._try_sse_fallback(fallback)
            self._connect_error = (
                f"Command not found: {resolved_cmd}. "
                f"Set docker_fallback_endpoint in mcp_gateway config "
                f"to use SSE transport instead."
            )
            logger.warning(self._connect_error)
            return False

    async def _connect_sse(self) -> bool:
        """Connect via SSE transport."""
        endpoint = self._config.docker_fallback_endpoint
        if not endpoint:
            self._connect_error = "No endpoint configured for SSE transport"
            logger.warning(self._connect_error)
            return False
        return await self._try_sse_fallback(endpoint.rstrip("/"))

    async def _connect_streamable_http(self) -> bool:
        """Connect via streamable HTTP transport."""
        if not _HAS_STREAMABLE_HTTP:
            self._connect_error = (
                "streamable_http transport not available in this MCP SDK version"
            )
            logger.warning(self._connect_error)
            return False
        endpoint = self._config.docker_fallback_endpoint
        if not endpoint:
            self._connect_error = (
                "No endpoint configured for streamable_http transport"
            )
            logger.warning(self._connect_error)
            return False
        url = endpoint.rstrip("/") + "/mcp"
        return await self._connect_with_session(
            streamable_http_client(url)
        )

    async def disconnect(self) -> None:
        """Clean up the MCP connection and release resources."""
        try:
            await self._exit_stack.aclose()
        except (Exception, BaseExceptionGroup):
            pass  # stdio subprocess cleanup can raise BrokenResourceError
        self._session = None
        self._tools = []
        self._exit_stack = AsyncExitStack()

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict | None = None,
        *,
        raise_on_interrupt: bool = False,
    ) -> str:
        """
        Forward a tool call to the MCP Gateway.

        Returns the tool output as a string. On error or timeout,
        returns an error string (never raises to the calling agent)
        unless ``raise_on_interrupt=True``, in which case
        ``MCPHardwareInterrupt`` is raised instead.
        """
        # v0.7.8: Test flight mock mode — return static success
        if getattr(self, "_mock_mode", False):
            self._last_call_duration_ms = 0.0
            return json.dumps({
                "status": "ok",
                "mock": True,
                "tool": tool_name,
                "message": "Test flight mock — no side effects executed",
            })

        if not self._session:
            if raise_on_interrupt:
                raise MCPHardwareInterrupt(
                    "MCP Gateway not connected",
                    tool_name=tool_name, tool_args=arguments,
                    interrupt_type="error",
                )
            return "ERROR: MCP Gateway not connected."

        _start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments or {}),
                timeout=self._tool_call_timeout,
            )
            self._last_call_duration_ms = (time.monotonic() - _start) * 1000

            texts = []
            for block in result.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
                else:
                    texts.append(str(block))
            return "\n".join(texts) if texts else "(no output)"
        except asyncio.TimeoutError:
            self._last_call_duration_ms = (time.monotonic() - _start) * 1000
            if raise_on_interrupt:
                raise MCPHardwareInterrupt(
                    f"Tool '{tool_name}' timed out after {self._tool_call_timeout}s",
                    tool_name=tool_name, tool_args=arguments,
                    duration_ms=self._last_call_duration_ms,
                    interrupt_type="timeout",
                )
            return (
                f"ERROR: Tool call '{tool_name}' timed out after "
                f"{self._tool_call_timeout}s"
            )
        except MCPHardwareInterrupt:
            raise
        except (Exception, BaseExceptionGroup) as e:
            self._last_call_duration_ms = (time.monotonic() - _start) * 1000
            if raise_on_interrupt:
                raise MCPHardwareInterrupt(
                    f"MCP Gateway call failed: {_unwrap_exception(e)}",
                    tool_name=tool_name, tool_args=arguments,
                    duration_ms=self._last_call_duration_ms,
                    interrupt_type="error",
                )
            return f"ERROR: MCP Gateway call failed: {_unwrap_exception(e)}"

    def get_tools(self) -> list[dict]:
        """
        Return discovered tools in FormicOS ToolInfo format.

        Each dict has: id, name, description, parameters, source, enabled.
        """
        result = []
        for tool in self._tools:
            result.append(
                {
                    "id": tool.name,
                    "name": tool.name.replace("_", " ")
                    .replace("-", " ")
                    .title(),
                    "description": tool.description
                    or f"MCP tool: {tool.name}",
                    "parameters": tool.inputSchema
                    if tool.inputSchema
                    else {"type": "object", "properties": {}},
                    "source": "mcp_gateway",
                    "enabled": True,
                }
            )
        return result

    def filter_tools(self, scope: ToolsScope) -> list[dict]:
        """
        Filter discovered tools by a ToolsScope configuration.

        If scope.mcp contains glob patterns, only tools whose id matches
        at least one pattern are returned. An empty scope.mcp list means
        all MCP tools are allowed.
        """
        if not self._tools:
            return []

        all_tools = self.get_tools()

        if not scope.mcp:
            # Empty mcp list = all MCP tools allowed
            return all_tools

        filtered = []
        for tool in all_tools:
            tool_id = tool["id"]
            if any(fnmatch.fnmatch(tool_id, pat) for pat in scope.mcp):
                filtered.append(tool)
        return filtered

    async def refresh_tools(self) -> int:
        """
        Re-discover tools from the MCP gateway.

        Returns the number of tools discovered. If not connected or
        the refresh fails, returns the count of previously cached tools.
        """
        if not self._session:
            logger.warning("MCP tool refresh skipped: not connected")
            return len(self._tools)

        try:
            response = await self._session.list_tools()
            self._tools = response.tools
            logger.info(
                "MCP tools refreshed: %d tools discovered", len(self._tools)
            )
            return len(self._tools)
        except (Exception, BaseExceptionGroup) as e:
            logger.warning(
                "MCP tool refresh failed: %s", _unwrap_exception(e)
            )
            return len(self._tools)

    async def health_check(self) -> bool:
        """
        Check if the MCP gateway is responsive.

        For stdio transport (without fallback), checks if the session exists.
        For HTTP transports or SSE fallback, pings the endpoint.
        If MCP SDK is not installed, always returns False.
        """
        if not MCP_AVAILABLE:
            return False

        if (
            self._config.transport == "stdio"
            and not self._used_fallback
        ):
            return self._session is not None

        # HTTP-based transports: ping the endpoint
        try:
            import httpx

            url = (
                self._fallback_url
                if self._used_fallback
                else self._config.docker_fallback_endpoint
                or ""
            ).rstrip("/")
            if not url:
                return self._session is not None
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code < 500
        except Exception:
            return False
