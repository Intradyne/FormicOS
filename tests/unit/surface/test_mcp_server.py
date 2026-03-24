"""Tests for surface/mcp_server.py (Wave 32.5 Team 3).

Covers spawn_colony return metadata (_next_actions, _context).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.mcp_server import create_mcp_server


def _make_runtime(colony_id: str = "colony-abc") -> MagicMock:
    runtime = MagicMock()
    runtime.spawn_colony = AsyncMock(return_value=colony_id)
    runtime.colony_manager = MagicMock()
    runtime.colony_manager.start_colony = AsyncMock()
    runtime.projections = MagicMock()
    return runtime


async def _call_spawn_colony(runtime: MagicMock, **kwargs: object) -> dict:  # type: ignore[type-arg]
    """Helper: get the spawn_colony tool from the MCP server and call it."""
    mcp = create_mcp_server(runtime)
    tool = await mcp.get_tool("spawn_colony")
    return await tool.fn(**kwargs)  # type: ignore[return-value]


class TestSpawnColonyReturnMetadata:
    """spawn_colony MCP tool includes _next_actions and _context metadata."""

    @pytest.mark.asyncio
    async def test_returns_colony_id(self) -> None:
        runtime = _make_runtime("col-123")
        result = await _call_spawn_colony(
            runtime,
            workspace_id="ws-1",
            thread_id="t-1",
            task="Test task",
            castes=[{"caste": "coder"}],
        )
        assert result["colony_id"] == "col-123"

    @pytest.mark.asyncio
    async def test_returns_next_actions(self) -> None:
        runtime = _make_runtime("col-123")
        result = await _call_spawn_colony(
            runtime,
            workspace_id="ws-1",
            thread_id="t-1",
            task="Test task",
            castes=[{"caste": "coder"}],
        )
        assert "_next_actions" in result
        assert isinstance(result["_next_actions"], list)
        assert "get_status" in result["_next_actions"]
        assert "chat_colony" in result["_next_actions"]

    @pytest.mark.asyncio
    async def test_returns_context(self) -> None:
        runtime = _make_runtime("col-123")
        result = await _call_spawn_colony(
            runtime,
            workspace_id="ws-1",
            thread_id="t-1",
            task="Test task",
            castes=[{"caste": "coder"}],
        )
        assert "_context" in result
        assert result["_context"]["thread_id"] == "t-1"
        assert result["_context"]["workspace_id"] == "ws-1"
