"""Root conftest for FormicOS tests."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure src/ is on the path so 'import formicos' works
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# smoke_test.py is a standalone script, not a pytest module
collect_ignore = ["smoke_test.py"]



# ---------------------------------------------------------------------------
# MockLLM — configurable mock satisfying LLMPort by structural subtyping
# ---------------------------------------------------------------------------


@dataclass
class MockResponse:
    """Minimal mock mirroring LLMResponse fields."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 10
    output_tokens: int = 20
    model: str = "mock"
    stop_reason: str = "end_turn"


class MockLLM:
    """Configurable mock for LLM calls. Records all invocations.

    Usage::

        mock = MockLLM(responses=["First response", "Second response"])
        result = await mock.complete(model="test", messages=[...])
        assert mock.calls[0]["model"] == "test"
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = responses or ["Test output"]
        self._call_idx = 0

    async def complete(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        tool_choice: object | None = None,
        extra_body: dict[str, object] | None = None,
    ) -> MockResponse:
        """Record call and return next configured response."""
        self.calls.append({
            "model": model,
            "messages": list(messages),
            "tools": list(tools) if tools is not None else None,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        response_text = self._responses[min(self._call_idx, len(self._responses) - 1)]
        self._call_idx += 1
        return MockResponse(content=response_text, model=model)

    def reset(self) -> None:
        """Clear recorded calls and reset response index."""
        self.calls.clear()
        self._call_idx = 0
