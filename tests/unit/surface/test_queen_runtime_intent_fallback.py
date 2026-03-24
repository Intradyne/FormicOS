"""Focused tests for Queen local-model intent fallback behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import LLMResponse
from formicos.surface.queen_runtime import QueenAgent


def _make_runtime_with_thread(thread: object, response: LLMResponse) -> MagicMock:
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.projections.get_thread.return_value = thread
    runtime.llm_router = MagicMock()
    runtime.llm_router.complete = AsyncMock(return_value=response)
    runtime.castes = None
    runtime.resolve_model.return_value = "llama-cpp/gpt-4"
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))
    runtime.spawn_colony = AsyncMock(return_value="colony-from-intent")
    runtime.colony_manager = None
    runtime.settings.system.data_dir = ""
    runtime.settings.governance.convergence_threshold = 0.85
    runtime.settings.governance.default_budget_per_colony = 5.0
    runtime.settings.governance.max_redirects_per_colony = 1
    runtime.settings.routing.tau_threshold = 0.5
    runtime.vector_store = None
    runtime.retrieve_relevant_memory = AsyncMock(return_value="")
    return runtime


@pytest.mark.anyio()
async def test_queen_respond_falls_back_on_spawn_tool_prose() -> None:
    thread = SimpleNamespace(queen_messages=[], workspace_id="ws1", thread_id="th1")
    response = LLMResponse(
        content=(
            'I will use spawn_colony to create a colony with task="build it" '
            'and castes=["coder"]. Preview complete. Ready to spawn. Confirm to proceed.'
        ),
        tool_calls=[],
        input_tokens=100,
        output_tokens=50,
        model="llama-cpp/gpt-4",
        stop_reason="end_turn",
    )
    runtime = _make_runtime_with_thread(thread, response)
    queen = QueenAgent(runtime)

    result = await queen.respond("ws1", "th1")

    assert result.actions
    assert result.actions[0]["tool"] == "spawn_colony"
    assert result.actions[0]["colony_id"] == "colony-from-intent"
    assert result.reply.startswith("\u200bPARSED\u200bColony colony-from-intent spawned.")
    assert "Preview complete" not in result.reply
    runtime.spawn_colony.assert_awaited_once()


@pytest.mark.anyio()
async def test_queen_respond_turns_preview_prose_into_preview_card() -> None:
    thread = SimpleNamespace(queen_messages=[], workspace_id="ws1", thread_id="th1")
    response = LLMResponse(
        content=(
            "Task: build it\n"
            "Team: coder (standard, 1 agent)\n"
            "Rounds: 4\n"
            "Budget: $0.50\n"
            "Why: The task is simple and deterministic.\n"
            "Preview complete. Ready to spawn. Confirm to proceed."
        ),
        tool_calls=[],
        input_tokens=120,
        output_tokens=60,
        model="llama-cpp/gpt-4",
        stop_reason="end_turn",
    )
    runtime = _make_runtime_with_thread(thread, response)
    queen = QueenAgent(runtime)

    result = await queen.respond("ws1", "th1")

    assert result.actions
    assert result.actions[0]["tool"] == "spawn_colony"
    assert result.actions[0]["preview"] is True
    assert result.reply.startswith("\u200bPARSED\u200b[PREVIEW")
    runtime.spawn_colony.assert_not_awaited()
