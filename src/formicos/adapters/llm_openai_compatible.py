"""OpenAI-compatible API adapter — implements LLMPort via httpx.

Works with any endpoint exposing the OpenAI /chat/completions format
(e.g. Ollama, vLLM, LiteLLM, OpenAI itself).
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Sequence
from urllib.parse import urlparse

import httpx
import structlog

from formicos.adapters.parse_defensive import parse_tool_calls_defensive
from formicos.core.types import LLMChunk, LLMMessage, LLMResponse, LLMToolSpec


def _parse_args_defensive(raw: object) -> dict[str, object]:
    """Parse tool-call arguments defensively. Handles string or dict."""
    if isinstance(raw, dict):
        return raw  # type: ignore[return-value]
    if isinstance(raw, str) and raw.strip():
        # Try stage 1: json.loads
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed  # type: ignore[return-value]
        except (json.JSONDecodeError, TypeError):
            pass
        # Try stage 2: json_repair
        try:
            import json_repair
            parsed = json_repair.loads(raw)  # pyright: ignore[reportUnknownMemberAccess]
            if isinstance(parsed, dict):
                return parsed  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            pass
        return {"_raw": raw}
    return {}

logger = structlog.get_logger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5


def _local_concurrency_limit() -> int:
    """Derive local concurrency limit from LLM_SLOTS env var.

    Matches the ``-np`` flag in docker-compose.yml so the adapter
    queues requests at the same limit as the server's slot count.
    """
    try:
        return max(1, int(os.environ.get("LLM_SLOTS", "2")))
    except (ValueError, TypeError):
        return 2

_LOCAL_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",  # noqa: S104
    "host.docker.internal",
    "llm",
    "ollama",
})


def _is_local_url(url: str) -> bool:
    """Return True if *url* points to a loopback or Docker-local endpoint."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return False
    return host in _LOCAL_HOSTS


def _strip_prefix(model: str) -> str:
    """Remove provider prefix: 'ollama/llama3.3' -> 'llama3.3'."""
    return model.split("/", 1)[-1]


def _build_tools(tools: Sequence[LLMToolSpec]) -> list[dict[str, object]]:
    """Convert LLMToolSpec list to OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


def _is_retryable(status: int, *, is_local: bool) -> bool:
    """Decide whether an HTTP status code should trigger a retry.

    429 (rate-limit) is always retryable.
    400 is retryable only for local endpoints — llama.cpp returns 400 when all
    inference slots are busy, which is a transient condition.
    """
    if status == 429:
        return True
    return status == 400 and is_local


class OpenAICompatibleLLMAdapter:
    """OpenAI-compatible chat completions adapter satisfying LLMPort."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._is_local = _is_local_url(base_url)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s),
        )
        # Limit concurrent requests to local LLM servers (e.g. llama.cpp with
        # limited inference slots).  Cloud endpoints are not throttled.
        # Reads LLM_SLOTS from the environment to match the server's -np flag.
        self._semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(_local_concurrency_limit())
            if self._is_local else None
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _post_with_retry(
        self,
        path: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        """POST with exponential-backoff retry on retryable status codes.

        Acquires the local-concurrency semaphore (if applicable) before the
        first attempt so that at most ``LLM_SLOTS`` requests are in-flight
        to a local server at any time.
        """
        if self._semaphore is not None:
            await self._semaphore.acquire()

        try:
            return await self._do_post(path, payload, stream=stream)
        except BaseException:
            if self._semaphore is not None:
                self._semaphore.release()
            raise

    async def _do_post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        stream: bool = False,
    ) -> httpx.Response:
        """Inner retry loop.  Caller is responsible for semaphore lifecycle."""
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

            if not _is_retryable(response.status_code, is_local=self._is_local):
                response.raise_for_status()
                return response

            # Retryable status — close stream if needed and back off.
            body_excerpt = ""
            if stream:
                await response.aclose()
            else:
                body_excerpt = response.text[:200]

            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
            wait = _BACKOFF_BASE * (2**attempt)
            logger.warning(
                "openai_retry",
                status=response.status_code,
                attempt=attempt + 1,
                wait=wait,
                local=self._is_local,
                body_excerpt=body_excerpt or None,
            )
            await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def _release_semaphore(self) -> None:
        """Release the concurrency semaphore if one is active."""
        if self._semaphore is not None:
            self._semaphore.release()

    # --- LLMPort.complete ---

    async def complete(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: object | None = None,  # Wave 54: reactive escalation
    ) -> LLMResponse:
        """Return a single structured completion from an OpenAI-compatible endpoint."""
        payload: dict[str, object] = {
            "model": _strip_prefix(model),
            "messages": [dict(m) for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = _build_tools(tools)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        resp = await self._post_with_retry("/chat/completions", payload)
        try:
            data = resp.json()

            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content") or ""

            tool_calls: list[dict[str, object]] = []
            for tc in message.get("tool_calls") or []:  # pyright: ignore[reportUnknownVariableType]
                func: dict[str, object] = tc["function"]  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                args = _parse_args_defensive(func.get("arguments", "{}"))  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                tool_calls.append(
                    {"name": func["name"], "id": tc["id"], "arguments": args}  # pyright: ignore[reportUnknownMemberType]
                )
            if not tool_calls and tools and isinstance(content, str):
                known_tools = {t["name"] for t in tools}
                recovered = parse_tool_calls_defensive(content, known_tools=known_tools)
                for idx, call in enumerate(recovered):
                    tool_calls.append({
                        "name": call.name,
                        "id": f"parsed_{idx}",
                        "arguments": call.arguments,
                    })

            usage = data.get("usage", {})
            _cd = usage.get("completion_tokens_details") or {}
            reasoning_tokens = _cd.get("reasoning_tokens", 0) if isinstance(_cd, dict) else 0
            _pd = usage.get("prompt_tokens_details") or {}
            cache_read_tokens = _pd.get("cached_tokens", 0) if isinstance(_pd, dict) else 0
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,  # type: ignore[arg-type]
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                reasoning_tokens=reasoning_tokens,
                cache_read_tokens=cache_read_tokens,
                model=data.get("model", _strip_prefix(model)),
                stop_reason=choice.get("finish_reason", "unknown"),
            )
        finally:
            self._release_semaphore()

    # --- LLMPort.stream ---

    async def stream(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        """Yield incremental LLMChunk objects from an OpenAI-compatible SSE stream."""
        payload: dict[str, object] = {
            "model": _strip_prefix(model),
            "messages": [dict(m) for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = _build_tools(tools)

        resp = await self._post_with_retry("/chat/completions", payload, stream=True)
        try:
            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):]
                if data_str == "[DONE]":
                    yield LLMChunk(content="", is_final=True)
                    return
                event = json.loads(data_str)
                choices = event.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    yield LLMChunk(content=text, is_final=False)
        finally:
            await resp.aclose()
            self._release_semaphore()

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
