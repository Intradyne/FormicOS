"""Tests for Queen colony naming (ADR-016, algorithms.md §A5)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.types import LLMResponse
from formicos.surface.queen_runtime import QueenAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(
    *,
    llm_content: str = "Auth Refactor Sprint",
    llm_timeout: bool = False,
    llm_error: bool = False,
) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.castes = MagicMock()
    runtime.castes.castes = {"queen": MagicMock(temperature=0.3, max_tokens=4096)}

    if llm_timeout:
        runtime.llm_router.complete = AsyncMock(
            side_effect=asyncio.TimeoutError(),
        )
    elif llm_error:
        runtime.llm_router.complete = AsyncMock(
            side_effect=Exception("LLM unavailable"),
        )
    else:
        runtime.llm_router.complete = AsyncMock(
            return_value=LLMResponse(
                content=llm_content,
                model="gemini/gemini-2.5-flash",
                input_tokens=10,
                output_tokens=5,
                tool_calls=[],
                stop_reason="end_turn",
            ),
        )

    # resolve_model returns a valid model string
    runtime.resolve_model = MagicMock(return_value="llama-cpp/gpt-4")
    return runtime


def _make_colony_projection(
    colony_id: str = "colony-abc12345",
    task: str = "Refactor the auth module",
    workspace_id: str = "ws-1",
    thread_id: str = "th-1",
) -> MagicMock:
    colony = MagicMock()
    colony.id = colony_id
    colony.task = task
    colony.workspace_id = workspace_id
    colony.thread_id = thread_id
    return colony


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueenNaming:
    @pytest.mark.asyncio
    async def test_naming_success(self) -> None:
        """Queen generates a name and emits ColonyNamed event."""
        runtime = _make_runtime(llm_content="Auth Refactor Sprint")
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="colony-abc",
            task="Refactor the auth module",
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert name == "Auth Refactor Sprint"
        runtime.emit_and_broadcast.assert_awaited_once()
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.colony_id == "colony-abc"
        assert event.display_name == "Auth Refactor Sprint"
        assert event.named_by == "queen"

    @pytest.mark.asyncio
    async def test_naming_strips_quotes(self) -> None:
        """Quotes around the name should be stripped."""
        runtime = _make_runtime(llm_content='"Data Pipeline Sprint"')
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Build data pipeline",
            workspace_id="ws-1", thread_id="th-1",
        )
        assert name == "Data Pipeline Sprint"

    @pytest.mark.asyncio
    async def test_naming_timeout_returns_none(self) -> None:
        """500ms timeout returns None, no event emitted."""
        runtime = _make_runtime(llm_timeout=True)
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Fix bug",
            workspace_id="ws-1", thread_id="th-1",
        )

        assert name is None
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_naming_llm_error_returns_none(self) -> None:
        """LLM error returns None gracefully."""
        runtime = _make_runtime(llm_error=True)
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Fix bug",
            workspace_id="ws-1", thread_id="th-1",
        )

        assert name is None
        runtime.emit_and_broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_naming_empty_response_returns_none(self) -> None:
        """Empty LLM response (< 2 chars) returns None."""
        runtime = _make_runtime(llm_content="")
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Fix bug",
            workspace_id="ws-1", thread_id="th-1",
        )

        assert name is None

    @pytest.mark.asyncio
    async def test_naming_too_long_returns_none(self) -> None:
        """Name > 50 chars is rejected."""
        runtime = _make_runtime(llm_content="A" * 60)
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Fix bug",
            workspace_id="ws-1", thread_id="th-1",
        )

        assert name is None

    @pytest.mark.asyncio
    async def test_naming_newline_rejected(self) -> None:
        """Names with newlines are rejected."""
        runtime = _make_runtime(llm_content="Line One\nLine Two")
        queen = QueenAgent(runtime)

        name = await queen.name_colony(
            colony_id="col-1", task="Fix bug",
            workspace_id="ws-1", thread_id="th-1",
        )

        assert name is None


class TestColonyManagerNaming:
    @pytest.mark.asyncio
    async def test_start_colony_triggers_naming(self) -> None:
        """ColonyManager.start_colony should fire naming as a background task."""
        from formicos.surface.colony_manager import ColonyManager

        runtime = MagicMock()
        runtime.projections.get_colony.return_value = _make_colony_projection(
            colony_id="colony-xyz",
        )
        runtime.projections.get_colony.return_value.status = "running"
        runtime.queen = MagicMock()
        runtime.queen.name_colony = AsyncMock(return_value="Test Name")

        mgr = ColonyManager(runtime)

        with patch.object(mgr, "_run_colony", new_callable=AsyncMock):
            await mgr.start_colony("colony-xyz")

        # Give background tasks a moment to execute
        await asyncio.sleep(0.05)

        # Verify the naming method was called
        runtime.queen.name_colony.assert_awaited_once_with(
            colony_id="colony-xyz",
            task=runtime.projections.get_colony.return_value.task,
            workspace_id="ws-1",
            thread_id="th-1",
        )
