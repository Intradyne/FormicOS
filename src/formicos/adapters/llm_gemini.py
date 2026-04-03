"""Gemini generateContent API adapter — implements LLMPort via httpx.

Uses raw httpx, no Google SDK. Handles role mapping (assistant→model),
tool-call detection via functionCall parts, thoughtSignature preservation,
and RECITATION/SAFETY block surfacing.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import structlog

from formicos.core.types import LLMChunk, LLMMessage, LLMResponse, LLMToolSpec

logger = structlog.get_logger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_RETRYABLE_CODES = frozenset({429, 500, 503})
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.0

_TOOL_RESULT_RE = re.compile(r"^\[Tool result: (\w+)\]\n(.+)", re.DOTALL)

# Safety settings: permissive for code workloads
_SAFETY_SETTINGS = [
    {"category": c, "threshold": "BLOCK_ONLY_HIGH"}
    for c in [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
]


def _strip_prefix(model: str) -> str:
    """Remove provider prefix: 'gemini/gemini-2.5-flash' -> 'gemini-2.5-flash'."""
    return model.split("/", 1)[-1]


def _build_tools(tools: Sequence[LLMToolSpec]) -> list[dict[str, object]]:
    """Convert LLMToolSpec list to Gemini tool format."""
    declarations: list[dict[str, object]] = []
    for t in tools:
        declarations.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        })
    return [{"functionDeclarations": declarations}]


def _convert_messages(
    messages: Sequence[LLMMessage],
) -> tuple[str, list[dict[str, object]]]:
    """Split system prompt and convert messages to Gemini format.

    Returns (system_instruction_text, contents_list).
    """
    system_parts: list[str] = []
    contents: list[dict[str, object]] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            system_parts.append(content)
            continue

        gemini_role = "model" if role == "assistant" else "user"
        parts: list[dict[str, object]] = []

        # Detect tool result pattern
        if role == "user" and (m := _TOOL_RESULT_RE.match(content)):
            tool_name, result_text = m.group(1), m.group(2)
            parts.append({"functionResponse": {
                "name": tool_name,
                "response": {"result": result_text},
            }})
        else:
            if content:
                parts.append({"text": content})

        if parts:
            contents.append({"role": gemini_role, "parts": parts})

    return "\n".join(system_parts), contents


class GeminiAdapter:
    """Gemini generateContent adapter satisfying LLMPort by structural subtyping."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

    async def _post_with_retry(
        self,
        url: str,
        payload: dict[str, object],
    ) -> httpx.Response:
        """POST with exponential-backoff retry on 429/500/503."""
        last_exc: httpx.HTTPStatusError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            response = await self._client.post(
                url, headers=self._headers(), json=payload,
            )
            if response.status_code not in _RETRYABLE_CODES:
                response.raise_for_status()
                return response
            _ = response.text  # consume body
            last_exc = httpx.HTTPStatusError(
                f"HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
            wait = _BACKOFF_BASE * (2**attempt)
            logger.warning(
                "gemini_retry",
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
        thinking_budget: int | None = None,
        tool_choice: object | None = None,  # Wave 58: accepted for LLMPort compat
        extra_body: dict[str, object] | None = None,  # Wave 77.5: ignored for cloud
    ) -> LLMResponse:
        """Return a single structured completion from Gemini."""
        model_name = _strip_prefix(model)
        system_text, contents = _convert_messages(messages)

        payload: dict[str, object] = {"contents": contents}

        if system_text.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_text.strip()}],
            }

        gen_config: dict[str, object] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if thinking_budget is not None:
            gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}
        payload["generationConfig"] = gen_config
        payload["safetySettings"] = _SAFETY_SETTINGS

        if tools:
            payload["tools"] = _build_tools(tools)

        url = f"{self._base_url}/models/{model_name}:generateContent"
        resp = await self._post_with_retry(url, payload)
        data = resp.json()

        return self._parse_response(data, model_name)

    def _parse_response(  # noqa: C901
        self, data: Any, model_name: str,  # noqa: ANN401
    ) -> LLMResponse:
        """Parse Gemini generateContent response into normalized LLMResponse."""
        candidates = data.get("candidates")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if not candidates or not isinstance(candidates, list) or len(candidates) == 0:  # pyright: ignore[reportUnknownArgumentType]
            return LLMResponse(
                content="", tool_calls=[], input_tokens=0,
                output_tokens=0, model=model_name, stop_reason="blocked",
            )

        candidate = candidates[0]  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(candidate, dict):
            return LLMResponse(
                content="", tool_calls=[], input_tokens=0,
                output_tokens=0, model=model_name, stop_reason="blocked",
            )

        parts: list[Any] = []
        content_obj = candidate.get("content")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if isinstance(content_obj, dict):
            raw_parts = content_obj.get("parts")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            if isinstance(raw_parts, list):
                parts = raw_parts  # pyright: ignore[reportUnknownVariableType]

        finish_reason_raw = candidate.get("finishReason", "STOP")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
        if not isinstance(finish_reason_raw, str):
            finish_reason_raw = "STOP"

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("thought"):  # pyright: ignore[reportUnknownMemberType]
                continue
            if "functionCall" in part:
                fc = part["functionCall"]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(fc, dict):
                    tc: dict[str, Any] = {
                        "name": fc.get("name", ""),  # pyright: ignore[reportUnknownMemberType]
                        "arguments": fc.get("args", {}),  # pyright: ignore[reportUnknownMemberType]
                    }
                    if "thoughtSignature" in part:
                        tc["thoughtSignature"] = part["thoughtSignature"]
                    tool_calls.append(tc)
            elif "text" in part:
                text_val = part["text"]  # pyright: ignore[reportUnknownVariableType]
                if isinstance(text_val, str):
                    text_parts.append(text_val)

        if tool_calls:
            stop_reason = "tool_use"
        elif finish_reason_raw in ("SAFETY", "RECITATION", "OTHER"):
            stop_reason = "blocked"
        elif finish_reason_raw == "MAX_TOKENS":
            stop_reason = "length"
        else:
            stop_reason = "stop"

        usage = data.get("usageMetadata")  # pyright: ignore[reportUnknownMemberType]
        input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0
        cache_read_tokens = 0
        if isinstance(usage, dict):
            pt = usage.get("promptTokenCount")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            ct = usage.get("candidatesTokenCount")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            input_tokens = pt if isinstance(pt, int) else 0
            output_tokens = ct if isinstance(ct, int) else 0
            tt = usage.get("thoughtsTokenCount")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            reasoning_tokens = tt if isinstance(tt, int) else 0
            ct_cached = usage.get("cachedContentTokenCount")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            cache_read_tokens = ct_cached if isinstance(ct_cached, int) else 0

        return LLMResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,  # type: ignore[arg-type]
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cache_read_tokens=cache_read_tokens,
            model=model_name,
            stop_reason=stop_reason,
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
        """Yield incremental LLMChunk objects from Gemini SSE stream."""
        model_name = _strip_prefix(model)
        system_text, contents = _convert_messages(messages)

        payload: dict[str, object] = {"contents": contents}

        if system_text.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_text.strip()}],
            }

        gen_config: dict[str, object] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        payload["generationConfig"] = gen_config
        payload["safetySettings"] = _SAFETY_SETTINGS

        if tools:
            payload["tools"] = _build_tools(tools)

        url = f"{self._base_url}/models/{model_name}:streamGenerateContent?alt=sse"

        # Streaming uses direct request (no retry on SSE)
        request = self._client.build_request(
            "POST", url, headers=self._headers(), json=payload,
        )
        response = await self._client.send(request, stream=True)
        try:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):]
                if not data_str:
                    continue
                try:
                    chunk_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                cands = chunk_data.get("candidates")
                if not isinstance(cands, list) or not cands:
                    continue
                cand = cands[0]  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(cand, dict):
                    continue
                c_obj = cand.get("content")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                if not isinstance(c_obj, dict):
                    continue
                c_parts = c_obj.get("parts")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                if not isinstance(c_parts, list):
                    continue
                for p in c_parts:  # pyright: ignore[reportUnknownVariableType]
                    if isinstance(p, dict) and "text" in p:
                        t = p["text"]  # pyright: ignore[reportUnknownVariableType]
                        if isinstance(t, str) and t:
                            yield LLMChunk(content=t, is_final=False)

            yield LLMChunk(content="", is_final=True)
        finally:
            await response.aclose()

    # --- Lifecycle ---

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


__all__ = ["GeminiAdapter"]
