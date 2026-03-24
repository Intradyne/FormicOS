"""Tests for LLMRouter fallback chain on blocked responses (ADR-014)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from formicos.core.types import LLMResponse
from formicos.surface.runtime import LLMRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocked_response(model: str = "test/model") -> LLMResponse:
    return LLMResponse(
        content="", tool_calls=[], input_tokens=10,
        output_tokens=0, model=model, stop_reason="blocked",
    )


def _ok_response(model: str = "test/model", content: str = "OK") -> LLMResponse:
    return LLMResponse(
        content=content, tool_calls=[], input_tokens=10,
        output_tokens=5, model=model, stop_reason="stop",
    )


def _make_adapter(response: LLMResponse) -> AsyncMock:
    adapter = AsyncMock()
    adapter.complete = AsyncMock(return_value=response)
    return adapter


# ---------------------------------------------------------------------------
# Fallback chain tests
# ---------------------------------------------------------------------------


class TestFallbackChain:
    """LLMRouter.complete should try fallback models on blocked responses."""

    @pytest.mark.asyncio
    async def test_no_fallback_on_success(self) -> None:
        """Non-blocked response should return immediately without fallback."""
        primary = _make_adapter(_ok_response("gemini/gemini-2.5-flash"))
        fallback = _make_adapter(_ok_response("llama-cpp/gpt-4"))

        router = LLMRouter(
            adapters={"gemini": primary, "llama-cpp": fallback},
            fallback_chain=["gemini/gemini-2.5-flash", "llama-cpp/gpt-4"],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.content == "OK"
        primary.complete.assert_called_once()
        fallback.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_blocked(self) -> None:
        """Blocked response should trigger fallback to next model in chain."""
        primary = _make_adapter(_blocked_response("gemini/gemini-2.5-flash"))
        fallback = _make_adapter(_ok_response("llama-cpp/gpt-4", "fallback OK"))

        router = LLMRouter(
            adapters={"gemini": primary, "llama-cpp": fallback},
            fallback_chain=["gemini/gemini-2.5-flash", "llama-cpp/gpt-4"],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.content == "fallback OK"
        assert result.model == "llama-cpp/gpt-4"
        primary.complete.assert_called_once()
        fallback.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_skips_same_model(self) -> None:
        """Fallback chain should skip the model that was already tried."""
        gemini = _make_adapter(_blocked_response("gemini/gemini-2.5-flash"))
        local = _make_adapter(_ok_response("llama-cpp/gpt-4", "local OK"))

        router = LLMRouter(
            adapters={"gemini": gemini, "llama-cpp": local},
            fallback_chain=[
                "gemini/gemini-2.5-flash",
                "llama-cpp/gpt-4",
            ],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.content == "local OK"
        # Gemini called once (primary), not again in fallback
        gemini.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_skips_missing_adapter(self) -> None:
        """Fallback models without registered adapters should be skipped."""
        primary = _make_adapter(_blocked_response("gemini/gemini-2.5-flash"))
        cloud = _make_adapter(_ok_response("anthropic/claude-sonnet-4.6", "cloud OK"))

        router = LLMRouter(
            adapters={"gemini": primary, "anthropic": cloud},
            # llama-cpp is in chain but has no adapter
            fallback_chain=[
                "gemini/gemini-2.5-flash",
                "llama-cpp/gpt-4",
                "anthropic/claude-sonnet-4.6",
            ],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.content == "cloud OK"

    @pytest.mark.asyncio
    async def test_all_blocked_returns_last(self) -> None:
        """If all fallback models are blocked, return the last blocked response."""
        gemini = _make_adapter(_blocked_response("gemini/gemini-2.5-flash"))
        local = _make_adapter(_blocked_response("llama-cpp/gpt-4"))
        cloud = _make_adapter(_blocked_response("anthropic/claude-sonnet-4.6"))

        router = LLMRouter(
            adapters={
                "gemini": gemini, "llama-cpp": local, "anthropic": cloud,
            },
            fallback_chain=[
                "gemini/gemini-2.5-flash",
                "llama-cpp/gpt-4",
                "anthropic/claude-sonnet-4.6",
            ],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.stop_reason == "blocked"
        # All three adapters should have been called
        gemini.complete.assert_called_once()
        local.complete.assert_called_once()
        cloud.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_fallback_chain_returns_blocked(self) -> None:
        """Empty fallback chain should return blocked response as-is."""
        primary = _make_adapter(_blocked_response("gemini/gemini-2.5-flash"))

        router = LLMRouter(
            adapters={"gemini": primary},
            fallback_chain=[],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.stop_reason == "blocked"

    @pytest.mark.asyncio
    async def test_tool_use_not_treated_as_blocked(self) -> None:
        """tool_use stop reason should NOT trigger fallback."""
        tool_response = LLMResponse(
            content="", tool_calls=[{"name": "search", "arguments": {}}],
            input_tokens=10, output_tokens=5,
            model="gemini/gemini-2.5-flash", stop_reason="tool_use",
        )
        primary = _make_adapter(tool_response)
        fallback = _make_adapter(_ok_response("llama-cpp/gpt-4"))

        router = LLMRouter(
            adapters={"gemini": primary, "llama-cpp": fallback},
            fallback_chain=["gemini/gemini-2.5-flash", "llama-cpp/gpt-4"],
        )
        result = await router.complete(
            "gemini/gemini-2.5-flash",
            [{"role": "user", "content": "test"}],
        )

        assert result.stop_reason == "tool_use"
        fallback.complete.assert_not_called()
