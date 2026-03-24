"""Tests for AnthropicLLMAdapter — uses httpx mock transport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from formicos.adapters.llm_anthropic import AnthropicLLMAdapter
from formicos.core.types import LLMMessage, LLMToolSpec


class MockTransport(httpx.AsyncBaseTransport):
    """Test transport that delegates to a handler function."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


def _make_adapter(handler: Any) -> AnthropicLLMAdapter:
    adapter = AnthropicLLMAdapter(api_key="test-key", base_url="https://api.anthropic.com")
    adapter._client = httpx.AsyncClient(
        transport=MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    return adapter


def _anthropic_response(
    content_blocks: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
    model: str = "claude-sonnet-4.6",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> dict[str, Any]:
    if content_blocks is None:
        content_blocks = [{"type": "text", "text": "Hello world"}]
    return {
        "content": content_blocks,
        "stop_reason": stop_reason,
        "model": model,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


# --- Tests ---


@pytest.mark.asyncio
async def test_complete_basic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_anthropic_response())

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("claude-sonnet-4.6", messages)
        assert result.content == "Hello world"
        assert result.tool_calls == []
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.model == "claude-sonnet-4.6"
        assert result.stop_reason == "end_turn"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_complete_with_tools() -> None:
    tool_block = {
        "type": "tool_use",
        "id": "tool_abc",
        "name": "get_weather",
        "input": {"location": "NYC"},
    }
    body = _anthropic_response(
        content_blocks=[{"type": "text", "text": "Let me check"}, tool_block],
        stop_reason="tool_use",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Weather?"}]
        tools: list[LLMToolSpec] = [
            {"name": "get_weather", "description": "Get weather", "parameters": {}}
        ]
        result = await adapter.complete("claude-sonnet-4.6", messages, tools=tools)
        assert result.content == "Let me check"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "get_weather"
        assert result.tool_calls[0]["id"] == "tool_abc"
        assert result.tool_calls[0]["input"] == {"location": "NYC"}
        assert result.stop_reason == "tool_use"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_complete_retry_on_429() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_anthropic_response())

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("claude-sonnet-4.6", messages)
        assert result.content == "Hello world"
        assert call_count == 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_stream_basic() -> None:
    sse_body = (
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}\n\n'
        'data: {"type":"message_stop"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        chunks = []
        async for chunk in adapter.stream("claude-sonnet-4.6", messages):
            chunks.append(chunk)
        assert len(chunks) == 3
        assert chunks[0].content == "Hello"
        assert chunks[0].is_final is False
        assert chunks[1].content == " world"
        assert chunks[1].is_final is False
        assert chunks[2].content == ""
        assert chunks[2].is_final is True
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_model_prefix_stripped() -> None:
    captured_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json=_anthropic_response())

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        await adapter.complete("anthropic/claude-sonnet-4.6", messages)
        assert captured_body["model"] == "claude-sonnet-4.6"
    finally:
        await adapter.close()
