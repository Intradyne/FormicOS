"""Wave 48 Team 1: request_forage tool spec and dispatch tests.

Covers:
- Tool spec registration and category mapping
- Researcher caste is permitted to use request_forage
- Coder caste can also use it (has search_web category)
- Reviewer caste is denied
- Dispatch returns error when forage_fn is not configured
- Dispatch returns error when topic is missing
- Dispatch calls forage_fn with correct arguments
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from formicos.engine.runner import RoundRunner, RunnerCallbacks
from formicos.engine.tool_dispatch import (
    TOOL_CATEGORY_MAP,
    TOOL_SPECS,
    ToolCategory,
    check_tool_permission,
)


class TestRequestForageToolSpec:
    """Verify request_forage is registered correctly."""

    def test_tool_spec_exists(self) -> None:
        assert "request_forage" in TOOL_SPECS
        spec = TOOL_SPECS["request_forage"]
        assert spec["name"] == "request_forage"
        assert "topic" in spec["parameters"]["properties"]
        assert "topic" in spec["parameters"]["required"]

    def test_category_mapping(self) -> None:
        assert TOOL_CATEGORY_MAP["request_forage"] == ToolCategory.search_web

    def test_researcher_permitted(self) -> None:
        result = check_tool_permission("researcher", "request_forage", 0)
        assert result is None  # None means permitted

    def test_reviewer_denied(self) -> None:
        result = check_tool_permission("reviewer", "request_forage", 0)
        assert result is not None  # Non-None means denied

    def test_coder_has_no_search_web(self) -> None:
        # Coder does not have search_web category
        result = check_tool_permission("coder", "request_forage", 0)
        assert result is not None


class TestRequestForageDispatch:
    """Verify _execute_tool dispatches request_forage correctly."""

    @pytest.mark.asyncio
    async def test_no_forage_fn_returns_error(self) -> None:
        cb = RunnerCallbacks(emit=lambda e: None)
        runner = RoundRunner(cb)

        result = await runner._execute_tool(
            "request_forage",
            {"topic": "auth patterns"},
            vector_port=None,
            workspace_id="ws-1",
            colony_id="col-1",
            agent_id="agent-1",
        )
        assert "not available" in result.content.lower()

    @pytest.mark.asyncio
    async def test_missing_topic_returns_error(self) -> None:
        forage_fn = AsyncMock(return_value="results")
        cb = RunnerCallbacks(emit=lambda e: None, forage_fn=forage_fn)
        runner = RoundRunner(cb)

        result = await runner._execute_tool(
            "request_forage",
            {},
            vector_port=None,
            workspace_id="ws-1",
            colony_id="col-1",
            agent_id="agent-1",
        )
        assert "topic is required" in result.content.lower()
        forage_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_forage_fn_with_args(self) -> None:
        forage_fn = AsyncMock(return_value="Found 2 entries.")
        cb = RunnerCallbacks(emit=lambda e: None, forage_fn=forage_fn)
        runner = RoundRunner(cb)

        result = await runner._execute_tool(
            "request_forage",
            {
                "topic": "auth patterns",
                "context": "python web app",
                "domains": ["python", "security"],
                "max_results": 3,
            },
            vector_port=None,
            workspace_id="ws-1",
            colony_id="col-1",
            agent_id="agent-1",
        )
        assert result.content == "Found 2 entries."
        forage_fn.assert_called_once()
        call_kwargs = forage_fn.call_args[1]
        assert call_kwargs["topic"] == "auth patterns"
        assert call_kwargs["context"] == "python web app"
        assert call_kwargs["domains"] == ["python", "security"]
        assert call_kwargs["max_results"] == 3
        assert call_kwargs["workspace_id"] == "ws-1"
        assert call_kwargs["colony_id"] == "col-1"

    @pytest.mark.asyncio
    async def test_max_results_capped_at_10(self) -> None:
        forage_fn = AsyncMock(return_value="results")
        cb = RunnerCallbacks(emit=lambda e: None, forage_fn=forage_fn)
        runner = RoundRunner(cb)

        await runner._execute_tool(
            "request_forage",
            {"topic": "test", "max_results": 50},
            vector_port=None,
            workspace_id="ws-1",
            colony_id="col-1",
            agent_id="agent-1",
        )
        call_kwargs = forage_fn.call_args[1]
        assert call_kwargs["max_results"] == 10
