"""Tests for OpenAICompatibleLLMAdapter — uses httpx mock transport."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from formicos.adapters.llm_openai_compatible import (
    OpenAICompatibleLLMAdapter,
    _is_local_url,
    _local_concurrency_limit,
)

if TYPE_CHECKING:
    from formicos.core.types import LLMMessage, LLMToolSpec


class MockTransport(httpx.AsyncBaseTransport):
    """Test transport that delegates to a handler function."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


def _make_adapter(
    handler: Any,
    base_url: str = "http://localhost:11434/v1",
    api_key: str | None = "test-key",
) -> OpenAICompatibleLLMAdapter:
    adapter = OpenAICompatibleLLMAdapter(base_url=base_url, api_key=api_key)
    adapter._client = httpx.AsyncClient(
        transport=MockTransport(handler),
        base_url=base_url,
    )
    return adapter


def _openai_response(
    content: str = "Hello world",
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    model: str = "llama3.3",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "model": model,
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


# --- Basic functionality ---


@pytest.mark.asyncio
async def test_complete_basic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("llama3.3", messages)
        assert result.content == "Hello world"
        assert result.tool_calls == []
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.model == "llama3.3"
        assert result.stop_reason == "stop"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_complete_with_tools() -> None:
    tc = [
        {
            "id": "call_123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
        }
    ]
    body = _openai_response(content="", tool_calls=tc, finish_reason="tool_calls")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Weather?"}]
        tools: list[LLMToolSpec] = [
            {"name": "get_weather", "description": "Get weather", "parameters": {}}
        ]
        result = await adapter.complete("llama3.3", messages, tools=tools)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "get_weather"
        assert result.tool_calls[0]["id"] == "call_123"
        assert result.tool_calls[0]["arguments"] == {"location": "NYC"}
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_complete_recovers_tool_call_from_content() -> None:
    body = _openai_response(
        content=(
            "```json\n"
            '{"name": "spawn_colony", "arguments": {"task": "build auth", "castes": ["coder"]}}'
            "\n```"
        ),
        tool_calls=None,
        finish_reason="stop",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Please help"}]
        tools: list[LLMToolSpec] = [
            {"name": "spawn_colony", "description": "Spawn colony", "parameters": {}},
            {"name": "kill_colony", "description": "Kill colony", "parameters": {}},
        ]
        result = await adapter.complete("llama-cpp/gpt-4", messages, tools=tools)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "spawn_colony"
        assert result.tool_calls[0]["arguments"] == {
            "task": "build auth",
            "castes": ["coder"],
        }
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_complete_no_auth_header() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler, api_key=None)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        await adapter.complete("llama3.3", messages)
        assert "authorization" not in captured_headers
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_stream_basic() -> None:
    chunk1 = {"choices": [{"delta": {"content": "Hello"}}]}
    chunk2 = {"choices": [{"delta": {"content": " world"}}]}
    sse_body = (
        f"data: {json.dumps(chunk1)}\n\n"
        f"data: {json.dumps(chunk2)}\n\n"
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        chunks = []
        async for chunk in adapter.stream("llama3.3", messages):
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


# --- _is_local_url ---


def test_is_local_url_localhost() -> None:
    assert _is_local_url("http://localhost:11434/v1") is True


def test_is_local_url_loopback() -> None:
    assert _is_local_url("http://127.0.0.1:8080/v1") is True


def test_is_local_url_docker_internal() -> None:
    assert _is_local_url("http://host.docker.internal:8080/v1") is True


def test_is_local_url_compose_service() -> None:
    assert _is_local_url("http://llm:8080/v1") is True


def test_is_local_url_cloud() -> None:
    assert _is_local_url("https://api.openai.com/v1") is False


def test_is_local_url_custom_host() -> None:
    assert _is_local_url("http://example.internal:8080/v1") is False


# --- Semaphore / throttling ---


@pytest.mark.asyncio
async def test_local_endpoint_has_semaphore() -> None:
    """Local adapters get a concurrency semaphore."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler, base_url="http://localhost:8080/v1")
    try:
        assert adapter._semaphore is not None
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_cloud_endpoint_no_semaphore() -> None:
    """Cloud adapters do NOT get a concurrency semaphore."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler, base_url="https://api.openai.com/v1")
    try:
        assert adapter._semaphore is None
    finally:
        await adapter.close()


def test_local_concurrency_limit_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """_local_concurrency_limit reads LLM_SLOTS from environment."""
    monkeypatch.setenv("LLM_SLOTS", "4")
    assert _local_concurrency_limit() == 4


def test_local_concurrency_limit_defaults_to_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without LLM_SLOTS, defaults to 2."""
    monkeypatch.delenv("LLM_SLOTS", raising=False)
    assert _local_concurrency_limit() == 2


def test_local_concurrency_limit_invalid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid LLM_SLOTS falls back to 2."""
    monkeypatch.setenv("LLM_SLOTS", "not_a_number")
    assert _local_concurrency_limit() == 2


def test_local_concurrency_limit_minimum_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM_SLOTS=0 is clamped to 1."""
    monkeypatch.setenv("LLM_SLOTS", "0")
    assert _local_concurrency_limit() == 1


@pytest.mark.asyncio
async def test_local_semaphore_limits_concurrency() -> None:
    """Concurrent local requests are limited to 2 at a time."""
    active = 0
    max_active = 0

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return httpx.Response(200, json=_openai_response())

    # Need an async mock transport for this test
    class AsyncMockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return await slow_handler(request)

    adapter = OpenAICompatibleLLMAdapter(base_url="http://localhost:8080/v1")
    adapter._client = httpx.AsyncClient(
        transport=AsyncMockTransport(),
        base_url="http://localhost:8080/v1",
    )

    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        tasks = [adapter.complete("m", messages) for _ in range(4)]
        await asyncio.gather(*tasks)
        assert max_active <= 2
    finally:
        await adapter.close()


# --- Retry behavior ---


@pytest.mark.asyncio
async def test_429_is_retried() -> None:
    """429 responses trigger retry for any endpoint."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("llama3.3", messages)
        assert result.content == "Hello world"
        assert call_count == 3
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_local_400_is_retried() -> None:
    """Local 400 (slot contention) is retried."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(400, text='{"error": "all slots are busy"}')
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler, base_url="http://localhost:8080/v1")
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("llama3.3", messages)
        assert result.content == "Hello world"
        assert call_count == 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_local_service_hostname_400_is_retried() -> None:
    """Compose-local service URLs should get the same retry behavior."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(400, text='{"error": "all slots are busy"}')
        return httpx.Response(200, json=_openai_response())

    adapter = _make_adapter(handler, base_url="http://llm:8080/v1")
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        result = await adapter.complete("llama-cpp/gpt-4", messages)
        assert result.content == "Hello world"
        assert call_count == 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_cloud_400_is_not_retried() -> None:
    """Cloud 400 is NOT retried — it's a real client error."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, text='{"error": "bad request"}')

    adapter = _make_adapter(handler, base_url="https://api.openai.com/v1")
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await adapter.complete("gpt-4", messages)
        assert exc_info.value.response.status_code == 400
        assert call_count == 1
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_retries_exhaust_then_raise() -> None:
    """After max attempts, the adapter raises."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, text="rate limited")

    adapter = _make_adapter(handler)
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.complete("llama3.3", messages)
        assert call_count == 3  # _MAX_ATTEMPTS
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_stream_through_retry_path() -> None:
    """Stream calls also go through retry/semaphore."""
    call_count = 0
    chunk1 = {"choices": [{"delta": {"content": "ok"}}]}
    sse_body = f"data: {json.dumps(chunk1)}\n\ndata: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    adapter = _make_adapter(handler, base_url="http://localhost:8080/v1")
    try:
        messages: list[LLMMessage] = [{"role": "user", "content": "Hi"}]
        chunks = []
        async for chunk in adapter.stream("m", messages):
            chunks.append(chunk)
        assert call_count == 2
        assert any(c.content == "ok" for c in chunks)
    finally:
        await adapter.close()
