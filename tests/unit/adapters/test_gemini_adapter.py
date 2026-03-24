"""Tests for the Gemini generateContent adapter."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from formicos.adapters.llm_gemini import GeminiAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    data: dict[str, Any],
    status: int = 200,
) -> httpx.Response:
    """Build a mock httpx.Response with JSON body."""
    return httpx.Response(
        status_code=status,
        json=data,
        request=httpx.Request("POST", "https://example.com"),
    )


def _text_response(
    text: str = "Hello",
    input_tokens: int = 10,
    output_tokens: int = 5,
    finish_reason: str = "STOP",
) -> dict[str, Any]:
    return {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "finishReason": finish_reason,
        }],
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
        },
    }


def _tool_call_response(
    name: str = "search",
    args: dict[str, Any] | None = None,
    thought_sig: str | None = None,
) -> dict[str, Any]:
    part: dict[str, Any] = {"functionCall": {"name": name, "args": args or {}}}
    if thought_sig:
        part["thoughtSignature"] = thought_sig
    return {
        "candidates": [{
            "content": {"parts": [part]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


# ---------------------------------------------------------------------------
# Text completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_completion() -> None:
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("Hello world", input_tokens=15, output_tokens=8)

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hi"},
            ],
        )

    assert result.content == "Hello world"
    assert result.input_tokens == 15
    assert result.output_tokens == 8
    assert result.stop_reason == "stop"
    assert result.model == "gemini-2.5-flash"
    assert result.tool_calls == []


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_detection() -> None:
    """Tool calls detected via functionCall in parts, not finishReason."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _tool_call_response(
        name="search", args={"query": "python async"},
    )

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "Search for async patterns"}],
        )

    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "search"
    assert result.tool_calls[0]["arguments"] == {"query": "python async"}


@pytest.mark.asyncio
async def test_thought_signature_preserved() -> None:
    """thoughtSignature bytes must be preserved on tool call round-trip."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _tool_call_response(
        name="search", args={"q": "test"},
        thought_sig="base64encodeddata==",
    )

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.tool_calls[0].get("thoughtSignature") == "base64encodeddata=="


# ---------------------------------------------------------------------------
# Blocked responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recitation_block() -> None:
    """RECITATION finish reason should surface as blocked."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = {
        "candidates": [{
            "content": {"parts": []},
            "finishReason": "RECITATION",
        }],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 0},
    }

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.stop_reason == "blocked"


@pytest.mark.asyncio
async def test_safety_block() -> None:
    """SAFETY finish reason should surface as blocked."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = {
        "candidates": [{
            "content": {"parts": []},
            "finishReason": "SAFETY",
        }],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 0},
    }

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.stop_reason == "blocked"


@pytest.mark.asyncio
async def test_empty_candidates_blocked() -> None:
    """No candidates at all → blocked."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = {"candidates": []}

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.stop_reason == "blocked"


# ---------------------------------------------------------------------------
# Max tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_tokens_finish() -> None:
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("partial...", finish_reason="MAX_TOKENS")

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.stop_reason == "length"


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_429() -> None:
    """429 should trigger retry, not raise immediately."""
    adapter = GeminiAdapter(api_key="test-key")

    call_count = 0

    async def mock_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(
                status_code=429,
                text="Rate limited",
                request=httpx.Request("POST", url),
            )
        return _make_response(_text_response("OK"))

    with (
        patch.object(adapter._client, "post", side_effect=mock_post),
        patch("formicos.adapters.llm_gemini.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.content == "OK"
    assert call_count == 3


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_yields_chunks() -> None:
    """Stream should yield text chunks and a final marker."""
    adapter = GeminiAdapter(api_key="test-key")

    chunk1 = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}],
    })
    chunk2 = json.dumps({
        "candidates": [{"content": {"parts": [{"text": " world"}]}, "finishReason": "STOP"}],
    })

    async def mock_lines():  # noqa: ANN202
        yield f"data: {chunk1}"
        yield f"data: {chunk2}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = mock_lines
    mock_response.aclose = AsyncMock()

    with (
        patch.object(adapter._client, "build_request", return_value=MagicMock()),
        patch.object(
            adapter._client, "send",
            new_callable=AsyncMock, return_value=mock_response,
        ),
    ):
        chunks = []
        async for chunk in adapter.stream(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

    # Should have text chunks plus final marker
    assert any(c.content == "Hello" for c in chunks)
    assert any(c.content == " world" for c in chunks)
    assert chunks[-1].is_final


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_prompt_extraction() -> None:
    """System messages should go to systemInstruction, not contents."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("OK")

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "Hi"},
            ],
        )

    call_payload = mock_post.call_args[0][1]
    assert "systemInstruction" in call_payload
    assert call_payload["systemInstruction"]["parts"][0]["text"] == "Be helpful"
    # System message should NOT appear in contents
    for content in call_payload["contents"]:
        assert content["role"] != "system"


@pytest.mark.asyncio
async def test_role_mapping() -> None:
    """assistant → model in Gemini format."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("OK")

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
                {"role": "user", "content": "How are you?"},
            ],
        )

    call_payload = mock_post.call_args[0][1]
    roles = [c["role"] for c in call_payload["contents"]]
    assert roles == ["user", "model", "user"]


# ---------------------------------------------------------------------------
# Thinking tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thinking_parts_skipped() -> None:
    """Parts with thought=True should be excluded from content text."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = {
        "candidates": [{
            "content": {"parts": [
                {"thought": True, "text": "internal thinking"},
                {"text": "visible output"},
            ]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        result = await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
        )

    assert result.content == "visible output"
    assert "internal thinking" not in result.content


# ---------------------------------------------------------------------------
# Tool format
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_sent_as_function_declarations() -> None:
    """Tools should be formatted as Gemini functionDeclarations."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("OK")

    tools = [{"name": "search", "description": "Search docs", "parameters": {"type": "object"}}]

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
            tools=tools,  # type: ignore[arg-type]
        )

    call_payload = mock_post.call_args[0][1]
    assert "tools" in call_payload
    func_decls = call_payload["tools"][0]["functionDeclarations"]
    assert func_decls[0]["name"] == "search"


# ---------------------------------------------------------------------------
# Thinking budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thinking_budget_config() -> None:
    """thinking_budget kwarg should be sent in generationConfig."""
    adapter = GeminiAdapter(api_key="test-key")
    resp_data = _text_response("OK")

    with patch.object(adapter, "_post_with_retry", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _make_response(resp_data)
        await adapter.complete(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "test"}],
            thinking_budget=0,
        )

    call_payload = mock_post.call_args[0][1]
    assert call_payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
