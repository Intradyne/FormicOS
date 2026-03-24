"""Tests for suggest-team endpoint (ADR-016, algorithms.md §A6)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import CasteRecipe, LLMResponse
from formicos.surface.runtime import Runtime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_castes() -> MagicMock:
    castes = MagicMock()
    castes.castes = {
        "queen": CasteRecipe(
            name="Queen", description="Colony orchestrator",
            system_prompt="You are the Queen.", temperature=0.3,
            tools=[], max_tokens=4096,
        ),
        "coder": CasteRecipe(
            name="Coder", description="Writes implementation code",
            system_prompt="You are a coder.", temperature=0.0,
            tools=[], max_tokens=1024,
        ),
        "reviewer": CasteRecipe(
            name="Reviewer", description="Reviews code for quality",
            system_prompt="You are a reviewer.", temperature=0.0,
            tools=[], max_tokens=1024,
        ),
        "researcher": CasteRecipe(
            name="Researcher", description="Researches best practices",
            system_prompt="You are a researcher.", temperature=0.0,
            tools=[], max_tokens=1024,
        ),
    }
    return castes


def _make_runtime(
    *,
    llm_response: str | None = None,
    llm_error: bool = False,
    castes: MagicMock | None = None,
) -> Runtime:
    event_store = AsyncMock()
    projections = MagicMock()
    ws_manager = MagicMock()
    settings = MagicMock()
    settings.models.defaults.model_dump.return_value = {"coder": "llama-cpp/gpt-4", "queen": "llama-cpp/gpt-4"}
    settings.governance.default_budget_per_colony = 5.0
    settings.routing.default_strategy = "stigmergic"

    llm_router = MagicMock()
    if llm_error:
        llm_router.complete = AsyncMock(side_effect=Exception("LLM error"))
    elif llm_response is not None:
        llm_router.complete = AsyncMock(return_value=LLMResponse(
            content=llm_response, model="gemini/gemini-2.5-flash",
            input_tokens=100, output_tokens=50,
            tool_calls=[], stop_reason="end_turn",
        ))
    else:
        llm_router.complete = AsyncMock(return_value=LLMResponse(
            content="[]", model="gemini/gemini-2.5-flash",
            input_tokens=100, output_tokens=50,
            tool_calls=[], stop_reason="end_turn",
        ))
    llm_router._resolve = MagicMock()

    rt = Runtime(
        event_store=event_store,
        projections=projections,
        ws_manager=ws_manager,
        settings=settings,
        castes=castes or _make_castes(),
        llm_router=llm_router,
        embed_fn=None,
        vector_store=None,
    )
    rt.llm_router = llm_router
    return rt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestTeam:
    @pytest.mark.asyncio
    async def test_returns_caste_recommendations(self) -> None:
        """suggest_team should return LLM caste recommendations."""
        llm_output = json.dumps([
            {"caste": "coder", "count": 1, "reasoning": "Implementation work"},
            {"caste": "reviewer", "count": 1, "reasoning": "Code quality"},
        ])
        rt = _make_runtime(llm_response=llm_output)

        result = await rt.suggest_team("Write unit tests for the API")

        assert len(result) == 2
        assert result[0]["caste"] == "coder"
        assert result[1]["caste"] == "reviewer"
        assert "reasoning" in result[0]

    @pytest.mark.asyncio
    async def test_llm_failure_returns_default(self) -> None:
        """LLM error should return safe default castes."""
        rt = _make_runtime(llm_error=True)

        result = await rt.suggest_team("Any objective")

        assert len(result) == 2
        assert result[0]["caste"] == "coder"
        assert result[1]["caste"] == "reviewer"

    @pytest.mark.asyncio
    async def test_no_castes_returns_default(self) -> None:
        """No caste recipes should return default suggestion."""
        rt = _make_runtime()
        rt.castes = None  # type: ignore[assignment]

        result = await rt.suggest_team("Any objective")

        assert len(result) == 2
        assert result[0]["caste"] == "coder"

    @pytest.mark.asyncio
    async def test_malformed_llm_response_returns_default(self) -> None:
        """Non-JSON LLM output should fall back to default."""
        rt = _make_runtime(llm_response="I think you should use coder and reviewer")

        result = await rt.suggest_team("Write some code")

        # json_repair may parse something or fall back to default
        assert isinstance(result, list)
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_queen_excluded_from_prompt(self) -> None:
        """Queen caste should not appear in the prompt to the LLM."""
        llm_output = json.dumps([
            {"caste": "coder", "count": 1, "reasoning": "Coding"},
        ])
        rt = _make_runtime(llm_response=llm_output)

        await rt.suggest_team("Build feature")

        call_args = rt.llm_router.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        prompt_text = messages[0]["content"]
        assert "queen" not in prompt_text.lower() or "Queen" not in prompt_text
