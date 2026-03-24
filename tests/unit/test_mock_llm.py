"""Tests for MockLLM utility (Wave 32 C6)."""

from __future__ import annotations

import pytest

from tests.conftest import MockLLM, MockResponse


class TestMockLLM:
    """Verify MockLLM records calls and returns configurable responses."""

    @pytest.mark.asyncio
    async def test_records_call_arguments(self) -> None:
        mock = MockLLM()
        messages = [{"role": "user", "content": "hello"}]
        await mock.complete(model="test-model", messages=messages)

        assert len(mock.calls) == 1
        assert mock.calls[0]["model"] == "test-model"
        assert mock.calls[0]["messages"] == messages
        assert mock.calls[0]["tools"] is None
        assert mock.calls[0]["temperature"] == 0.0
        assert mock.calls[0]["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_returns_responses_in_sequence(self) -> None:
        mock = MockLLM(responses=["first", "second", "third"])
        r1 = await mock.complete(model="m", messages=[])
        r2 = await mock.complete(model="m", messages=[])
        r3 = await mock.complete(model="m", messages=[])

        assert r1.content == "first"
        assert r2.content == "second"
        assert r3.content == "third"

    @pytest.mark.asyncio
    async def test_repeats_last_response_when_exhausted(self) -> None:
        mock = MockLLM(responses=["only"])
        await mock.complete(model="m", messages=[])
        r2 = await mock.complete(model="m", messages=[])
        r3 = await mock.complete(model="m", messages=[])

        assert r2.content == "only"
        assert r3.content == "only"

    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        mock = MockLLM(responses=["a", "b"])
        await mock.complete(model="m", messages=[])
        assert len(mock.calls) == 1

        mock.reset()
        assert len(mock.calls) == 0

        r = await mock.complete(model="m", messages=[])
        assert r.content == "a"  # back to first response

    @pytest.mark.asyncio
    async def test_response_has_correct_structure(self) -> None:
        mock = MockLLM()
        r = await mock.complete(model="test", messages=[])
        assert isinstance(r, MockResponse)
        assert isinstance(r.content, str)
        assert isinstance(r.tool_calls, list)
        assert isinstance(r.input_tokens, int)
        assert isinstance(r.output_tokens, int)
        assert r.model == "test"
        assert r.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_custom_tools_recorded(self) -> None:
        mock = MockLLM()
        tools = [{"name": "t1", "description": "test", "parameters": {}}]
        await mock.complete(model="m", messages=[], tools=tools, temperature=0.7, max_tokens=1024)
        assert mock.calls[0]["tools"] == tools
        assert mock.calls[0]["temperature"] == 0.7
        assert mock.calls[0]["max_tokens"] == 1024
