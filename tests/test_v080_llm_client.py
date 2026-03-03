"""
Tests for FormicOS v0.8.0 AioLLMClient.

Validates:
  - Response dataclass construction and field access
  - SSE stream parsing (_iter_sse)
  - AioLLMClient non-streaming and streaming paths
  - Error handling (HTTP errors, timeouts, malformed JSON)
  - LLMClient Protocol satisfaction
  - AioLLMClient base_url normalization
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm_client import (
    AioLLMClient,
    LLMChatCompletion,
    LLMChatCompletionChunk,
    LLMChoice,
    LLMClientError,
    LLMDelta,
    LLMFunction,
    LLMMessage,
    LLMStreamChoice,
    LLMToolCall,
    LLMUsage,
    _parse_completion,
    _parse_chunk,
    _iter_sse,
)


# ── Response Dataclasses ─────────────────────────────────────────────────


class TestResponseDataclasses:

    def test_llm_message_defaults(self):
        msg = LLMMessage()
        assert msg.role == "assistant"
        assert msg.content is None
        assert msg.tool_calls is None

    def test_llm_choice_field_access(self):
        """Verify .choices[0].message.content pattern works."""
        completion = LLMChatCompletion(
            id="chatcmpl-test",
            choices=[
                LLMChoice(
                    index=0,
                    message=LLMMessage(content="Hello world"),
                    finish_reason="stop",
                )
            ],
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="test-model",
        )
        assert completion.choices[0].message.content == "Hello world"
        assert completion.choices[0].finish_reason == "stop"
        assert completion.usage.total_tokens == 15

    def test_llm_tool_call(self):
        tc = LLMToolCall(
            id="call_123",
            index=0,
            function=LLMFunction(name="file_read", arguments='{"path": "test.py"}'),
        )
        assert tc.function.name == "file_read"
        assert tc.function.arguments == '{"path": "test.py"}'
        assert tc.id == "call_123"

    def test_streaming_chunk_delta(self):
        """Verify .choices[0].delta.content pattern works."""
        chunk = LLMChatCompletionChunk(
            choices=[
                LLMStreamChoice(
                    delta=LLMDelta(content="Hello"),
                    finish_reason=None,
                )
            ],
        )
        assert chunk.choices[0].delta.content == "Hello"
        assert chunk.choices[0].finish_reason is None

    def test_streaming_chunk_tool_calls(self):
        """Verify delta.tool_calls with index and function."""
        tc = LLMToolCall(
            id="call_1",
            index=0,
            function=LLMFunction(name="file_read", arguments='{"pa'),
        )
        chunk = LLMChatCompletionChunk(
            choices=[
                LLMStreamChoice(
                    delta=LLMDelta(tool_calls=[tc]),
                    finish_reason=None,
                )
            ],
        )
        delta_tcs = chunk.choices[0].delta.tool_calls
        assert delta_tcs is not None
        assert len(delta_tcs) == 1
        assert delta_tcs[0].index == 0
        assert delta_tcs[0].function.name == "file_read"

    def test_usage_none_on_chunk(self):
        """Usage can be None on most streaming chunks."""
        chunk = LLMChatCompletionChunk(choices=[])
        assert chunk.usage is None


# ── JSON Parsers ─────────────────────────────────────────────────────────


class TestParsers:

    def test_parse_completion(self):
        data = {
            "id": "chatcmpl-abc",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
            },
            "model": "test-model",
        }
        result = _parse_completion(data)
        assert isinstance(result, LLMChatCompletion)
        assert result.choices[0].message.content == "Hello"
        assert result.usage.total_tokens == 13

    def test_parse_completion_with_tool_calls(self):
        data = {
            "id": "chatcmpl-tc",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "file_read",
                                    "arguments": '{"path": "test.py"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
        result = _parse_completion(data)
        assert result.choices[0].message.tool_calls is not None
        assert len(result.choices[0].message.tool_calls) == 1
        assert result.choices[0].message.tool_calls[0].function.name == "file_read"
        assert result.choices[0].finish_reason == "tool_calls"

    def test_parse_chunk(self):
        data = {
            "id": "chatcmpl-stream",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "Hi"},
                    "finish_reason": None,
                }
            ],
        }
        chunk = _parse_chunk(data)
        assert isinstance(chunk, LLMChatCompletionChunk)
        assert chunk.choices[0].delta.content == "Hi"
        assert chunk.choices[0].finish_reason is None
        assert chunk.usage is None

    def test_parse_chunk_with_usage(self):
        data = {
            "id": "chatcmpl-final",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        chunk = _parse_chunk(data)
        assert chunk.usage is not None
        assert chunk.usage.total_tokens == 8
        assert chunk.choices[0].finish_reason == "stop"

    def test_parse_chunk_with_tool_call_delta(self):
        data = {
            "id": "chatcmpl-tc",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "file_read", "arguments": '{"pa'},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        chunk = _parse_chunk(data)
        tcs = chunk.choices[0].delta.tool_calls
        assert tcs is not None
        assert len(tcs) == 1
        assert tcs[0].index == 0
        assert tcs[0].id == "call_1"
        assert tcs[0].function.name == "file_read"


# ── SSE Parser ───────────────────────────────────────────────────────────


class TestIterSSE:

    @pytest.mark.asyncio
    async def test_basic_sse_parsing(self):
        """Parses standard data: {json} lines."""
        lines = [
            b'data: {"id":"1","choices":[{"delta":{"content":"A"},"index":0}]}\n',
            b'\n',
            b'data: {"id":"2","choices":[{"delta":{"content":"B"},"index":0}]}\n',
            b'\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.content = _async_iter(lines)

        results = []
        async for data in _iter_sse(mock_response):
            results.append(data)

        assert len(results) == 2
        assert results[0]["choices"][0]["delta"]["content"] == "A"
        assert results[1]["choices"][0]["delta"]["content"] == "B"

    @pytest.mark.asyncio
    async def test_sse_ignores_empty_lines(self):
        """Empty lines between events are silently skipped."""
        lines = [
            b'\n',
            b'\n',
            b'data: {"id":"1","choices":[]}\n',
            b'\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.content = _async_iter(lines)

        results = []
        async for data in _iter_sse(mock_response):
            results.append(data)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_sse_skips_malformed_json(self):
        """Malformed JSON after data: is silently skipped."""
        lines = [
            b'data: {invalid json}\n',
            b'data: {"id":"ok","choices":[]}\n',
            b'data: [DONE]\n',
        ]
        mock_response = MagicMock()
        mock_response.content = _async_iter(lines)

        results = []
        async for data in _iter_sse(mock_response):
            results.append(data)

        assert len(results) == 1
        assert results[0]["id"] == "ok"

    @pytest.mark.asyncio
    async def test_sse_handles_no_done_sentinel(self):
        """Stream ends without [DONE] — just exhausts the iterator."""
        lines = [
            b'data: {"id":"1","choices":[]}\n',
        ]
        mock_response = MagicMock()
        mock_response.content = _async_iter(lines)

        results = []
        async for data in _iter_sse(mock_response):
            results.append(data)

        assert len(results) == 1


# ── AioLLMClient Construction ───────────────────────────────────────────


class TestAioLLMClientConstruction:

    def test_base_url_normalization_trailing_v1(self):
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080/v1")
        assert client._base_url == "http://localhost:8080"

    def test_base_url_normalization_trailing_slash(self):
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080/")
        assert client._base_url == "http://localhost:8080"

    def test_base_url_clean(self):
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080")
        assert client._base_url == "http://localhost:8080"

    def test_chat_completions_namespace(self):
        """Client has .chat.completions.create() namespace."""
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080")
        assert hasattr(client, "chat")
        assert hasattr(client.chat, "completions")
        assert hasattr(client.chat.completions, "create")

    def test_default_api_key(self):
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080")
        assert client._api_key == "not-needed"

    def test_custom_api_key(self):
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080", api_key="sk-test")
        assert client._api_key == "sk-test"


# ── AioLLMClient Non-Streaming ───────────────────────────────────────────


class TestNonStreaming:

    @pytest.mark.asyncio
    async def test_non_streaming_success(self):
        """Non-streaming request returns LLMChatCompletion."""
        response_data = {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            "model": "test-model",
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        result = await client.chat.completions.create(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.5,
        )

        assert isinstance(result, LLMChatCompletion)
        assert result.choices[0].message.content == "Hello!"
        assert result.usage.total_tokens == 7

        # Verify correct URL and body
        call_args = mock_session.post.call_args
        assert "/v1/chat/completions" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["model"] == "test"
        assert body["temperature"] == 0.5
        assert body["stream"] is False

    @pytest.mark.asyncio
    async def test_non_streaming_http_error(self):
        """HTTP 4xx/5xx raises LLMClientError."""
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        with pytest.raises(LLMClientError, match="HTTP 500"):
            await client.chat.completions.create(
                model="test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_non_streaming_connection_error(self):
        """Connection error raises LLMClientError."""
        import aiohttp

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(
            side_effect=aiohttp.ClientError("Connection refused")
        )

        client = AioLLMClient(mock_session, "http://localhost:8080")
        with pytest.raises(LLMClientError, match="Connection error"):
            await client.chat.completions.create(
                model="test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_non_streaming_timeout(self):
        """Timeout raises LLMClientError."""
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(side_effect=TimeoutError("timed out"))

        client = AioLLMClient(mock_session, "http://localhost:8080")
        with pytest.raises(LLMClientError, match="timed out"):
            await client.chat.completions.create(
                model="test",
                messages=[{"role": "user", "content": "Hi"}],
            )

    @pytest.mark.asyncio
    async def test_non_streaming_with_tools(self):
        """Tools and tool_choice are passed in request body."""
        response_data = {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=response_data)

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        tools = [{"type": "function", "function": {"name": "test"}}]
        await client.chat.completions.create(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
            tools=tools,
            tool_choice="auto",
        )

        body = mock_session.post.call_args[1]["json"]
        assert body["tools"] == tools
        assert body["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_non_streaming_seed_kwarg(self):
        """Seed is passed through to request body."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "id": "chatcmpl-test",
            "choices": [{"index": 0, "message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 5},
        })

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        await client.chat.completions.create(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
            seed=42,
        )

        body = mock_session.post.call_args[1]["json"]
        assert body["seed"] == 42


# ── AioLLMClient Streaming ──────────────────────────────────────────────


class TestStreaming:

    @pytest.mark.asyncio
    async def test_streaming_returns_async_iterable(self):
        """stream=True returns an async-iterable of chunks."""
        sse_data = [
            b'data: {"id":"1","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}\n',
            b'\n',
            b'data: {"id":"2","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}\n',
            b'\n',
            b'data: [DONE]\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.content = _async_iter(sse_data)
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        result = await client.chat.completions.create(
            model="test",
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )

        chunks = []
        async for chunk in result:
            chunks.append(chunk)

        assert len(chunks) == 2
        assert isinstance(chunks[0], LLMChatCompletionChunk)
        assert chunks[0].choices[0].delta.content == "Hi"
        assert chunks[1].choices[0].finish_reason == "stop"
        assert chunks[1].usage is not None
        assert chunks[1].usage.total_tokens == 4

    @pytest.mark.asyncio
    async def test_streaming_http_error(self):
        """Streaming with HTTP error raises LLMClientError."""
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.text = AsyncMock(return_value="Service Unavailable")
        mock_resp.release = MagicMock()

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_resp)

        client = AioLLMClient(mock_session, "http://localhost:8080")
        with pytest.raises(LLMClientError, match="HTTP 503"):
            await client.chat.completions.create(
                model="test",
                messages=[{"role": "user", "content": "Hi"}],
                stream=True,
            )


# ── Protocol ─────────────────────────────────────────────────────────────


class TestProtocol:

    def test_aio_client_has_chat_attribute(self):
        """AioLLMClient satisfies LLMClient protocol structurally."""
        session = MagicMock()
        client = AioLLMClient(session, "http://localhost:8080")
        # Protocol requires `chat: Any`
        assert hasattr(client, "chat")
        assert hasattr(client.chat, "completions")
        assert callable(getattr(client.chat.completions, "create", None))

    def test_asyncopenai_satisfies_protocol(self):
        """AsyncOpenAI also satisfies LLMClient protocol."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            pytest.skip("openai not installed")

        client = AsyncOpenAI(base_url="http://localhost:8080", api_key="not-needed")
        assert hasattr(client, "chat")
        assert hasattr(client.chat, "completions")


# ── ModelRegistry Integration ────────────────────────────────────────────


class TestModelRegistryIntegration:

    def test_registry_creates_aio_client_when_session_provided(self, mock_config):
        """ModelRegistry._make_client returns AioLLMClient when aio_session is set."""
        import aiohttp
        from src.model_registry import ModelRegistry

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        registry = ModelRegistry(mock_config, aio_session=mock_session)
        client, model_str = registry.get_client("test/model")

        assert isinstance(client, AioLLMClient)

    def test_registry_fallback_to_asyncopenai_without_session(self, mock_config):
        """ModelRegistry._make_client returns AsyncOpenAI when no aio_session."""
        from src.model_registry import ModelRegistry

        registry = ModelRegistry(mock_config)  # no aio_session
        client, model_str = registry.get_client("test/model")

        try:
            from openai import AsyncOpenAI
            assert isinstance(client, AsyncOpenAI)
        except ImportError:
            pytest.skip("openai not installed")

    def test_get_cached_clients(self, mock_config):
        """get_cached_clients returns dict of model_id → client."""
        import aiohttp
        from src.model_registry import ModelRegistry

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        registry = ModelRegistry(mock_config, aio_session=mock_session)

        # Before any get_client call, cache is empty
        assert registry.get_cached_clients() == {}

        # After get_client, cache is populated
        registry.get_client("test/model")
        cached = registry.get_cached_clients()
        assert "test/model" in cached
        assert isinstance(cached["test/model"], AioLLMClient)


# ── Helpers ──────────────────────────────────────────────────────────────


class _AsyncIterator:
    """Helper to create an async iterator from a list of bytes."""

    def __init__(self, items: list[bytes]):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


def _async_iter(items: list[bytes]) -> _AsyncIterator:
    return _AsyncIterator(items)
