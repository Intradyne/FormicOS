"""Anthropic Messages API adapter — implements LLMPort via httpx."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence

import httpx
import structlog

from formicos.core.types import LLMChunk, LLMMessage, LLMResponse, LLMToolSpec

logger = structlog.get_logger(__name__)

_RETRYABLE_CODES = frozenset({429, 529})
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.0
_ANTHROPIC_VERSION = "2023-06-01"


def _strip_prefix(model: str) -> str:
    """Remove provider prefix: 'anthropic/claude-sonnet-4.6' -> 'claude-sonnet-4.6'."""
    return model.split("/", 1)[-1]


def _build_tools(tools: Sequence[LLMToolSpec]) -> list[dict[str, object]]:
    """Convert LLMToolSpec list to Anthropic tool format."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


def _extract_system_and_messages(
    messages: Sequence[LLMMessage],
) -> tuple[str, list[dict[str, str]]]:
    """Extract system messages from the messages list.

    Anthropic's Messages API requires the system prompt as a top-level
    parameter, not as a message with role="system". This helper separates
    them so the adapter can construct the correct payload shape.
    """
    system_parts: list[str] = []
    user_messages: list[dict[str, str]] = []
    for m in messages:
        msg = dict(m)
        if msg.get("role") == "system":
            system_parts.append(str(msg.get("content", "")))
        else:
            user_messages.append({k: str(v) for k, v in msg.items()})
    return "\n".join(system_parts), user_messages


class AnthropicLLMAdapter:
    """Anthropic Messages API adapter satisfying LLMPort by structural subtyping."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(120.0),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def _post_with_retry(
        self,
        path: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        """POST with exponential-backoff retry on retryable status codes."""
        last_exc: httpx.HTTPStatusError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            if stream:
                request = self._client.build_request(
                    "POST", path, headers=self._headers(), json=payload
                )
                response = await self._client.send(request, stream=True)
            else:
                response = await self._client.post(
                    path, headers=self._headers(), json=payload
                )
            if response.status_code not in _RETRYABLE_CODES:
                response.raise_for_status()
                return response
            if not stream:
                _ = response.text
            else:
                await response.aclose()
            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
            wait = _BACKOFF_BASE * (2**attempt)
            logger.warning(
                "anthropic_retry",
                status=response.status_code,
                attempt=attempt + 1,
                wait=wait,
            )
            await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

    # --- LLMPort.complete ---

    async def complete(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: object | None = None,  # Wave 58: accepted for LLMPort compat
        extra_body: dict[str, object] | None = None,  # Wave 77.5: ignored for cloud
    ) -> LLMResponse:
        """Return a single structured completion from Anthropic."""
        # FIX BUG 4: Anthropic requires system as top-level param, not in messages
        system_content, user_messages = _extract_system_and_messages(messages)

        payload: dict[str, object] = {
            "model": _strip_prefix(model),
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_content.strip():
            payload["system"] = system_content.strip()
        if tools:
            payload["tools"] = _build_tools(tools)

        resp = await self._post_with_retry("/v1/messages", payload)
        data = resp.json()

        content_parts: list[str] = []
        tool_calls: list[dict[str, object]] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                raw_input = block.get("input", {})
                # Defensive: handle truncated tool_use (args as string or missing)
                if isinstance(raw_input, str):
                    try:
                        raw_input = json.loads(raw_input)
                    except (json.JSONDecodeError, TypeError):
                        try:
                            import json_repair
                            raw_input = json_repair.loads(raw_input)  # pyright: ignore[reportUnknownMemberAccess]
                        except Exception:  # noqa: BLE001
                            raw_input = {}
                if not isinstance(raw_input, dict):
                    raw_input = {}
                tool_calls.append(
                    {"name": block["name"], "id": block["id"], "input": raw_input}
                )

        usage = data.get("usage", {})
        cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,  # type: ignore[arg-type]
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=cache_read_tokens,
            model=data.get("model", _strip_prefix(model)),
            stop_reason=data.get("stop_reason", "unknown"),
        )

    # --- LLMPort.stream ---

    async def stream(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        """Yield incremental LLMChunk objects from an Anthropic SSE stream."""
        # FIX BUG 4: Same system extraction for streaming
        system_content, user_messages = _extract_system_and_messages(messages)

        payload: dict[str, object] = {
            "model": _strip_prefix(model),
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_content.strip():
            payload["system"] = system_content.strip()
        if tools:
            payload["tools"] = _build_tools(tools)

        resp = await self._post_with_retry("/v1/messages", payload, stream=True)
        try:
            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):]
                if not data_str:
                    continue
                event = json.loads(data_str)
                etype = event.get("type", "")
                if etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield LLMChunk(content=delta.get("text", ""), is_final=False)
                elif etype == "message_stop":
                    yield LLMChunk(content="", is_final=True)
        finally:
            await resp.aclose()

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
