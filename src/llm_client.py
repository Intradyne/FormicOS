"""
FormicOS v0.8.0 -- aiohttp-based OpenAI-compatible LLM Client

Drop-in replacement for ``AsyncOpenAI`` that uses a shared
``aiohttp.ClientSession`` for connection pooling control.  Preserves the
``.chat.completions.create()`` call interface so existing Agent, Archivist,
and execute_raw call sites require only a type annotation change.

SSE Streaming
-------------
The ``/v1/chat/completions`` streaming protocol emits newline-delimited
``data: {json}`` frames terminated by ``data: [DONE]``.  This module
provides ``_iter_sse()`` for parsing that stream into typed chunks.

Protocol
--------
``LLMClient`` is a structural ``Protocol`` satisfied by both ``AsyncOpenAI``
and ``AioLLMClient`` — STRICTURE-003 compliant (no ``typing.Any`` on core
constructors; the Protocol uses ``Any`` only for the nested namespace).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

import aiohttp

logger = logging.getLogger(__name__)


# ━━ Errors ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LLMClientError(Exception):
    """Raised on HTTP errors, timeouts, or malformed LLM responses."""


# ━━ Response Dataclasses ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Mirror the openai SDK attribute structure so that existing code like
# ``response.choices[0].message.content`` works unchanged.


@dataclass(slots=True)
class LLMFunction:
    """Function call details within a tool call."""
    name: str | None = None
    arguments: str | None = None


@dataclass(slots=True)
class LLMToolCall:
    """A single tool call in a completion response."""
    id: str = ""
    index: int = 0
    type: str = "function"
    function: LLMFunction = field(default_factory=LLMFunction)


@dataclass(slots=True)
class LLMUsage:
    """Token usage statistics."""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class LLMMessage:
    """Assistant message in a non-streaming response."""
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[LLMToolCall] | None = None


@dataclass(slots=True)
class LLMDelta:
    """Incremental delta in a streaming chunk."""
    role: str | None = None
    content: str | None = None
    tool_calls: list[LLMToolCall] | None = None


@dataclass(slots=True)
class LLMChoice:
    """A single choice in a completion response."""
    index: int = 0
    message: LLMMessage = field(default_factory=LLMMessage)
    finish_reason: str | None = None


@dataclass(slots=True)
class LLMStreamChoice:
    """A single choice in a streaming chunk."""
    index: int = 0
    delta: LLMDelta = field(default_factory=LLMDelta)
    finish_reason: str | None = None


@dataclass(slots=True)
class LLMChatCompletion:
    """Non-streaming chat completion response."""
    id: str = ""
    choices: list[LLMChoice] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    model: str = ""


@dataclass(slots=True)
class LLMChatCompletionChunk:
    """Single chunk in a streaming chat completion."""
    id: str = ""
    choices: list[LLMStreamChoice] = field(default_factory=list)
    usage: LLMUsage | None = None
    model: str = ""


# ━━ SSE Parser ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _iter_sse(
    response: aiohttp.ClientResponse,
) -> AsyncIterator[dict[str, Any]]:
    """Parse an ``text/event-stream`` response into JSON payloads.

    Handles partial lines, empty ``data:`` fields, and the ``[DONE]``
    sentinel from OpenAI-compatible endpoints.
    """
    buffer = ""
    async for raw_bytes in response.content:
        buffer += raw_bytes.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            if line.startswith("data: "):
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    return
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    logger.debug("SSE: skipping malformed JSON: %s", payload[:120])


# ━━ Response Parsers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _parse_tool_call(raw: dict[str, Any]) -> LLMToolCall:
    """Parse a tool_call dict from JSON into an ``LLMToolCall``."""
    func_raw = raw.get("function") or {}
    return LLMToolCall(
        id=raw.get("id", ""),
        index=raw.get("index", 0),
        type=raw.get("type", "function"),
        function=LLMFunction(
            name=func_raw.get("name"),
            arguments=func_raw.get("arguments"),
        ),
    )


def _parse_completion(data: dict[str, Any]) -> LLMChatCompletion:
    """Parse a full (non-streaming) JSON response into ``LLMChatCompletion``."""
    choices = []
    for c in data.get("choices", []):
        msg_raw = c.get("message", {})
        tool_calls = None
        if msg_raw.get("tool_calls"):
            tool_calls = [_parse_tool_call(tc) for tc in msg_raw["tool_calls"]]
        choices.append(LLMChoice(
            index=c.get("index", 0),
            message=LLMMessage(
                role=msg_raw.get("role", "assistant"),
                content=msg_raw.get("content"),
                tool_calls=tool_calls,
            ),
            finish_reason=c.get("finish_reason"),
        ))

    usage_raw = data.get("usage") or {}
    return LLMChatCompletion(
        id=data.get("id", ""),
        choices=choices,
        usage=LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        ),
        model=data.get("model", ""),
    )


def _parse_chunk(data: dict[str, Any]) -> LLMChatCompletionChunk:
    """Parse a single SSE frame into ``LLMChatCompletionChunk``."""
    choices = []
    for c in data.get("choices", []):
        delta_raw = c.get("delta", {})
        tool_calls = None
        if delta_raw.get("tool_calls"):
            tool_calls = [_parse_tool_call(tc) for tc in delta_raw["tool_calls"]]
        choices.append(LLMStreamChoice(
            index=c.get("index", 0),
            delta=LLMDelta(
                role=delta_raw.get("role"),
                content=delta_raw.get("content"),
                tool_calls=tool_calls,
            ),
            finish_reason=c.get("finish_reason"),
        ))

    usage = None
    usage_raw = data.get("usage")
    if usage_raw:
        usage = LLMUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
        )

    return LLMChatCompletionChunk(
        id=data.get("id", ""),
        choices=choices,
        usage=usage,
        model=data.get("model", ""),
    )


# ━━ Async Stream Wrapper ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _AsyncChunkStream:
    """Async-iterable wrapper over an aiohttp SSE response.

    Allows ``async for chunk in response:`` — the same pattern used by
    the openai SDK's streaming interface.
    """

    def __init__(self, response: aiohttp.ClientResponse) -> None:
        self._response = response
        self._iter: AsyncIterator[dict[str, Any]] | None = None

    def __aiter__(self) -> _AsyncChunkStream:
        self._iter = _iter_sse(self._response)
        return self

    async def __anext__(self) -> LLMChatCompletionChunk:
        if self._iter is None:
            self._iter = _iter_sse(self._response)
        try:
            data = await self._iter.__anext__()
        except StopAsyncIteration:
            raise
        return _parse_chunk(data)


# ━━ Client Namespaces ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _CompletionsNamespace:
    """Implements ``client.chat.completions.create()``.

    Mirrors the openai SDK's nested namespace so call sites like
    ``await self.model_client.chat.completions.create(...)`` work without
    modification.
    """

    def __init__(self, client: AioLLMClient) -> None:
        self._client = client

    async def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 1.0,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        seed: int | None = None,
        **kwargs: Any,
    ) -> LLMChatCompletion | _AsyncChunkStream:
        """Send a chat completion request.

        Parameters mirror the OpenAI ``/v1/chat/completions`` API.
        Returns ``LLMChatCompletion`` for non-streaming, or an async-iterable
        ``_AsyncChunkStream`` for streaming.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if tools is not None:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if seed is not None:
            body["seed"] = seed
        body.update(kwargs)

        url = f"{self._client._base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._client._api_key}",
        }

        try:
            resp = await self._client._session.post(
                url, json=body, headers=headers,
                timeout=self._client._timeout,
            )
        except aiohttp.ClientError as exc:
            raise LLMClientError(f"Connection error: {exc}") from exc
        except TimeoutError as exc:
            raise LLMClientError(f"Request timed out: {exc}") from exc

        if stream:
            if resp.status >= 400:
                text = await resp.text()
                resp.release()
                raise LLMClientError(
                    f"HTTP {resp.status} from {url}: {text[:500]}"
                )
            return _AsyncChunkStream(resp)

        # Non-streaming
        if resp.status >= 400:
            text = await resp.text()
            raise LLMClientError(
                f"HTTP {resp.status} from {url}: {text[:500]}"
            )

        try:
            data = await resp.json()
        except (json.JSONDecodeError, aiohttp.ContentTypeError) as exc:
            raise LLMClientError(f"Malformed JSON response: {exc}") from exc

        return _parse_completion(data)


class _ChatNamespace:
    """Implements ``client.chat.completions``."""

    def __init__(self, client: AioLLMClient) -> None:
        self.completions = _CompletionsNamespace(client)


# ━━ Main Client ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AioLLMClient:
    """aiohttp-based OpenAI-compatible LLM client.

    Uses a shared ``aiohttp.ClientSession`` for connection pooling.
    Exposes the same ``.chat.completions.create()`` interface as
    ``AsyncOpenAI`` for drop-in compatibility.

    Parameters
    ----------
    session : aiohttp.ClientSession
        Shared session (typically one per server process).
    base_url : str
        Base URL of the OpenAI-compatible endpoint (e.g. ``http://localhost:8080``).
        Must NOT include a trailing ``/v1``.
    api_key : str
        API key.  Defaults to ``"not-needed"`` for local llama.cpp.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str = "not-needed",
        timeout: float = 120.0,
    ) -> None:
        # Strip trailing /v1 if caller includes it (normalize)
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        if base_url.endswith("/"):
            base_url = base_url.rstrip("/")

        self._session = session
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self.chat = _ChatNamespace(self)


# ━━ Protocol ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LLMClient(Protocol):
    """Structural protocol satisfied by both ``AsyncOpenAI`` and ``AioLLMClient``.

    Used for type annotations in Agent, Archivist, and other consumers.
    """

    chat: Any  # has .completions.create()
