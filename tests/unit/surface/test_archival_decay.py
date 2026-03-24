"""Tests for thread archival confidence decay (Wave 31 B3, updated Wave 32 A2).

Given: A thread with knowledge entries is archived.
When: archive_thread Queen tool fires.
Then: MemoryConfidenceUpdated events emitted with symmetric gamma-burst
      at 30-day equivalent (ADR-041 D2), hard floor: alpha >= 1.0, beta >= 1.0.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.queen_runtime import QueenAgent


def _make_queen(*, memory_entries: dict | None = None) -> QueenAgent:
    """Build a QueenAgent with mocked runtime."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.projections = MagicMock()
    runtime.parse_tool_input = lambda tc: tc.get("input", {})

    ws = MagicMock()
    thread = MagicMock()
    thread.status = "completed"
    ws.threads = {"t-1": thread}
    runtime.projections.workspaces = {"ws-1": ws}
    runtime.projections.memory_entries = memory_entries or {}

    return QueenAgent(runtime=runtime)


class TestArchivalDecay:
    """Verify archival decay formula and hard floor enforcement."""

    @pytest.mark.asyncio
    async def test_decay_formula_applied(self) -> None:
        """Archival decay: symmetric gamma-burst at 30-day equivalent (ADR-041 D2)."""
        queen = _make_queen(memory_entries={
            "mem-1": {
                "id": "mem-1",
                "thread_id": "t-1",
                "workspace_id": "ws-1",
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            },
        })

        tc = {"name": "archive_thread", "input": {"reason": "test archival"}}
        result_text, _ = await queen._execute_tool(tc, "ws-1", "t-1")

        emit = queen._runtime.emit_and_broadcast
        confidence_calls = [
            call
            for call in emit.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        assert len(confidence_calls) == 1
        event = confidence_calls[0].args[0]
        assert event.old_alpha == 10.0
        assert event.old_beta == 5.0
        # gamma = 0.98^30 ≈ 0.5455; new_alpha = 0.5455*10 + 0.4545*5 ≈ 7.73
        assert abs(event.new_alpha - (0.98**30 * 10.0 + (1 - 0.98**30) * 5.0)) < 0.01
        # new_beta = 0.5455*5 + 0.4545*5 = 5.0
        assert abs(event.new_beta - (0.98**30 * 5.0 + (1 - 0.98**30) * 5.0)) < 0.01
        assert event.reason == "archival_decay"

    @pytest.mark.asyncio
    async def test_hard_floor_alpha(self) -> None:
        """Entry with alpha=1.0 before decay: alpha stays at 1.0 (not 0.8)."""
        queen = _make_queen(memory_entries={
            "mem-low": {
                "id": "mem-low",
                "thread_id": "t-1",
                "workspace_id": "ws-1",
                "conf_alpha": 1.0,
                "conf_beta": 1.0,
            },
        })

        tc = {"name": "archive_thread", "input": {"reason": "test floor"}}
        await queen._execute_tool(tc, "ws-1", "t-1")

        emit = queen._runtime.emit_and_broadcast
        confidence_calls = [
            call
            for call in emit.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        assert len(confidence_calls) == 1
        event = confidence_calls[0].args[0]
        # Hard floor: alpha >= 1.0 and beta >= 1.0
        assert event.new_alpha >= 1.0, f"Alpha floor violated: {event.new_alpha}"
        assert event.new_beta >= 1.0, f"Beta floor violated: {event.new_beta}"

    @pytest.mark.asyncio
    async def test_multiple_entries_all_decayed(self) -> None:
        """All thread entries should receive decay events."""
        queen = _make_queen(memory_entries={
            "mem-1": {
                "id": "mem-1",
                "thread_id": "t-1",
                "workspace_id": "ws-1",
                "conf_alpha": 10.0,
                "conf_beta": 5.0,
            },
            "mem-2": {
                "id": "mem-2",
                "thread_id": "t-1",
                "workspace_id": "ws-1",
                "conf_alpha": 8.0,
                "conf_beta": 8.0,
            },
            "mem-other": {
                "id": "mem-other",
                "thread_id": "t-other",
                "workspace_id": "ws-1",
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
            },
        })

        tc = {"name": "archive_thread", "input": {"reason": "test multi"}}
        await queen._execute_tool(tc, "ws-1", "t-1")

        emit = queen._runtime.emit_and_broadcast
        confidence_calls = [
            call
            for call in emit.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        # Only 2 entries in thread t-1 should be decayed
        assert len(confidence_calls) == 2
        decayed_ids = {c.args[0].entry_id for c in confidence_calls}
        assert decayed_ids == {"mem-1", "mem-2"}
