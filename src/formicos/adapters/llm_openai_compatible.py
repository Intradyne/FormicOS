"""OpenAI-compatible API adapter — implements LLMPort via httpx.

Works with any endpoint exposing the OpenAI /chat/completions format
(e.g. Ollama, vLLM, LiteLLM, OpenAI itself).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from formicos.adapters.parse_defensive import parse_tool_calls_defensive
from formicos.core.types import LLMChunk, LLMMessage, LLMResponse, LLMToolSpec

_MAX_ARG_REPAIR_CHARS = 64_000
_TOOL_RECOVERY_TIMEOUT_S = 2.0
_RESPONSE_JSON_TIMEOUT_S = 30.0
_LOCAL_HTTPX_LIMITS = httpx.Limits(
    max_connections=10,
    max_keepalive_connections=5,
)


def _looks_like_json_payload(raw: str) -> bool:
    stripped = raw.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_args_defensive(raw: object) -> dict[str, object]:
    """Parse tool-call arguments defensively. Handles string or dict."""
    if isinstance(raw, dict):
        return raw  # type: ignore[return-value]
    if isinstance(raw, str) and raw.strip():
        stripped = raw.strip()
        # Try stage 1: json.loads
        if _looks_like_json_payload(stripped):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed  # type: ignore[return-value]
            except (json.JSONDecodeError, TypeError):
                pass
            # Try stage 2: json_repair only for bounded JSON-like payloads.
            if len(stripped) <= _MAX_ARG_REPAIR_CHARS:
                try:
                    import json_repair
                    parsed = json_repair.loads(stripped)  # pyright: ignore[reportUnknownMemberAccess]
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
        timeout_s: float = 300.0,
        max_concurrent: int = 0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._is_local = _is_local_url(base_url)

        def _make_client() -> httpx.AsyncClient:
            kwargs: dict[str, object] = {
                "base_url": base_url,
                "timeout": httpx.Timeout(timeout_s),
            }
            if self._is_local:
                kwargs["limits"] = _LOCAL_HTTPX_LIMITS
            return httpx.AsyncClient(**kwargs)

        self._client_factory: Any = _make_client
        self._client = self._client_factory()
        # Wave 64: per-model max_concurrent overrides LLM_SLOTS.
        # If max_concurrent > 0, always use it (local or cloud).
        # Otherwise, local endpoints use LLM_SLOTS, cloud is unthrottled.
        if max_concurrent > 0:
            self._semaphore: asyncio.Semaphore | None = (
                asyncio.Semaphore(max_concurrent)
            )
        elif self._is_local:
            self._semaphore = asyncio.Semaphore(
                _local_concurrency_limit()
            )
        else:
            self._semaphore = None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._is_local:
            # Local inference servers have shown brittle keep-alive behavior
            # after restarts and long-running requests. Prefer fresh sockets.
            headers["connection"] = "close"
        return headers

    async def _reset_client(self) -> None:
        """Drop pooled connections after local transport churn and rebuild."""
        old_client = self._client
        self._client = self._client_factory()
        with contextlib.suppress(Exception):
            await old_client.aclose()

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
            try:
                if stream:
                    request = self._client.build_request(
                        "POST", path, headers=self._headers(), json=payload
                    )
                    response = await self._client.send(request, stream=True)
                else:
                    response = await self._client.post(
                        path, headers=self._headers(), json=payload
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if not self._is_local or attempt >= _MAX_ATTEMPTS - 1:
                    raise
                wait = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "openai_transport_retry",
                    attempt=attempt + 1,
                    wait=wait,
                    local=self._is_local,
                    error=repr(exc),
                )
                await self._reset_client()
                await asyncio.sleep(wait)
                continue

            if not _is_retryable(response.status_code, is_local=self._is_local):
                if response.status_code >= 400:
                    _err_body = response.text[:500] if not stream else "(stream)"
                    _log = structlog.get_logger()
                    _log.warning(
                        "llm_adapter.http_error",
                        status=response.status_code,
                        body=_err_body,
                        url=path,
                    )
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

    async def _recover_tool_calls_from_content(
        self,
        content: str,
        tools: Sequence[LLMToolSpec],
    ) -> list[dict[str, object]]:
        """Bound defensive recovery so malformed content can't stall a colony."""
        known_tools = {t["name"] for t in tools}
        try:
            recovered = await asyncio.wait_for(
                asyncio.to_thread(
                    parse_tool_calls_defensive,
                    content,
                    known_tools=known_tools,
                ),
                timeout=_TOOL_RECOVERY_TIMEOUT_S,
            )
        except TimeoutError:
            logger.warning(
                "llm_adapter.tool_recovery_timeout",
                content_len=len(content),
                tool_count=len(known_tools),
            )
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "llm_adapter.tool_recovery_error",
                error=repr(exc),
                content_len=len(content),
                tool_count=len(known_tools),
            )
            return []

        return [
            {
                "name": call.name,
                "id": f"parsed_{idx}",
                "arguments": call.arguments,
            }
            for idx, call in enumerate(recovered)
        ]

    # --- LLMPort.complete ---

    async def complete(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: object | None = None,  # Wave 54: reactive escalation
        extra_body: dict[str, object] | None = None,  # Wave 77.5: thinking mode
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
            # Wave 81: normalize tool_choice for llama.cpp / OpenAI-compat.
            # Accepts string ("auto", "none", "required") or dict
            # ({"type": "function", "function": {"name": "..."}}).
            # llama.cpp only supports string values; convert dicts to
            # "required" so tool-forcing escalation actually works.
            if isinstance(tool_choice, dict):
                if self._is_local:
                    payload["tool_choice"] = "required"
                else:
                    payload["tool_choice"] = tool_choice
            elif isinstance(tool_choice, str):
                payload["tool_choice"] = tool_choice
            else:
                # Pydantic model or other — try dict conversion
                payload["tool_choice"] = (
                    tool_choice.model_dump()
                    if hasattr(tool_choice, "model_dump")
                    else str(tool_choice)
                )
        if extra_body:
            payload.update(extra_body)

        resp = await self._post_with_retry("/chat/completions", payload)
        try:
            try:
                data = await asyncio.wait_for(
                    asyncio.to_thread(resp.json),
                    timeout=_RESPONSE_JSON_TIMEOUT_S,
                )
            except TimeoutError as exc:
                with contextlib.suppress(Exception):
                    resp.close()
                logger.warning(
                    "llm_adapter.response_json_timeout",
                    timeout_s=_RESPONSE_JSON_TIMEOUT_S,
                    model=_strip_prefix(model),
                    local=self._is_local,
                )
                raise TimeoutError(
                    f"Timed out parsing LLM response JSON after "
                    f"{_RESPONSE_JSON_TIMEOUT_S:.1f}s"
                ) from exc

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
                tool_calls.extend(
                    await self._recover_tool_calls_from_content(content, tools),
                )

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
