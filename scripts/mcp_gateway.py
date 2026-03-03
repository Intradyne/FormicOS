#!/usr/bin/env python3
"""
MCP Gateway — runs MCP servers as subprocesses and serves a unified SSE endpoint.

This is the Docker-native replacement for `docker mcp gateway run`. It reads
server definitions from formicos.yaml, spawns each as a stdio subprocess
(typically via `npx -y <package>`), aggregates all discovered tools, and
serves them over HTTP SSE at port 8811.

Runs as the `mcp-gateway` service in docker-compose.yml — starts automatically
with the rest of the FormicOS stack.

Configuration (in config/formicos.yaml):

    mcp_gateway:
      enabled: true
      servers:
        filesystem:
          command: npx
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
        fetch:
          command: uvx
          args: ["mcp-server-fetch"]

Environment variables:
    MCP_GATEWAY_PORT    — HTTP port (default: 8811)
    MCP_GATEWAY_CONFIG  — Path to formicos.yaml (default: /app/config/formicos.yaml)
"""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("mcp-gateway")


def load_server_configs() -> dict:
    """Load MCP server definitions from formicos.yaml."""
    config_path = os.environ.get(
        "MCP_GATEWAY_CONFIG", "/app/config/formicos.yaml"
    )
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Config not found: %s", config_path)
        sys.exit(1)

    gateway_cfg = config.get("mcp_gateway", {})
    servers = gateway_cfg.get("servers", {})
    if not servers:
        logger.warning("No MCP servers defined in mcp_gateway.servers")
    return servers


async def main():
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    from mcp.types import TextContent
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    servers_cfg = load_server_configs()

    # ── 1. Connect to each MCP server via stdio ──────────
    stack = AsyncExitStack()
    tool_to_session: dict[str, ClientSession] = {}
    all_tools = []
    server_tool_counts: dict[str, int] = {}

    for name, cfg in servers_cfg.items():
        command = cfg.get("command", "npx")
        args = cfg.get("args", [])
        env_overrides = cfg.get("env", {})

        # Build environment: inherit current + overrides
        env = {**os.environ, **env_overrides}

        logger.info("Starting MCP server '%s': %s %s", name, command, " ".join(args))

        try:
            params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
            )
            transport = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(
                ClientSession(transport[0], transport[1])
            )
            await session.initialize()

            result = await session.list_tools()
            count = 0
            for tool in result.tools:
                tool_to_session[tool.name] = session
                all_tools.append(tool)
                count += 1
            server_tool_counts[name] = count
            logger.info("  '%s' ready: %d tools", name, count)
        except Exception as e:
            logger.warning("  '%s' failed to start: %s: %s", name, type(e).__name__, e)
            server_tool_counts[name] = 0

    total = len(all_tools)
    ok = sum(1 for c in server_tool_counts.values() if c > 0)
    logger.info(
        "Gateway ready: %d tools from %d/%d servers",
        total, ok, len(servers_cfg),
    )

    # ── 2. Create aggregating proxy MCP Server ────────────
    proxy = Server("formicos-mcp-gateway")

    @proxy.list_tools()
    async def handle_list_tools():
        return all_tools

    @proxy.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None):
        session = tool_to_session.get(name)
        if not session:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = await session.call_tool(name, arguments or {})
            return result.content
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Tool call failed ({name}): {type(e).__name__}: {e}",
            )]

    # ── 3. Serve via SSE ──────────────────────────────────
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await proxy.run(
                streams[0],
                streams[1],
                proxy.create_initialization_options(),
            )

    async def handle_messages(request):
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    app = Starlette(
        routes=[
            Route("/sse", handle_sse),
            Route("/messages/{rest:path}", handle_messages, methods=["POST"]),
        ],
    )

    port = int(os.environ.get("MCP_GATEWAY_PORT", "8811"))
    logger.info("MCP Gateway SSE endpoint: http://0.0.0.0:%d/sse", port)

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await stack.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Gateway stopped")
        sys.exit(0)
