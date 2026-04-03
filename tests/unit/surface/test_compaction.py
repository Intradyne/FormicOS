"""Tests for Queen thread compaction (Wave 79 Track 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from formicos.surface.queen_runtime import _compact_thread_history, _RECENT_WINDOW


@dataclass
class FakeMsg:
    role: str
    content: str
    render: str | None = None
    meta: dict[str, Any] | None = None
    intent: str | None = None


def _make_long_thread(
    *,
    operator_msgs: list[str] | None = None,
    queen_msgs: list[str] | None = None,
    extra: list[FakeMsg] | None = None,
) -> list[FakeMsg]:
    """Build a thread long enough to trigger compaction.

    Specific messages are placed early so they land in the compactable
    region (before the recent window). Padding fills the middle.
    """
    msgs: list[FakeMsg] = []
    # Place test-specific messages first (compactable region).
    for text in (operator_msgs or []):
        msgs.append(FakeMsg(role="operator", content=text))
    for text in (queen_msgs or []):
        msgs.append(FakeMsg(role="queen", content=text))
    msgs.extend(extra or [])
    # Pad the compactable region so total tokens exceed budget.
    while len(msgs) < _RECENT_WINDOW + 15:
        msgs.append(FakeMsg(role="operator", content="padding " * 200))
    # Recent tail — always kept raw, never compacted.
    for i in range(_RECENT_WINDOW):
        msgs.append(FakeMsg(role="queen", content=f"recent {i}"))
    return msgs


def _get_system_block(result: list[dict[str, str]]) -> str:
    """Extract the compacted system block content."""
    for msg in result:
        if msg["role"] == "system":
            return msg["content"]
    return ""


class TestGoalSection:
    def test_first_operator_message_becomes_goal(self) -> None:
        msgs = _make_long_thread(
            operator_msgs=["Fix the authentication bug in login.py"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "## Goal" in block
        assert "authentication bug" in block


class TestProgressSection:
    def test_result_card_in_done(self) -> None:
        msgs = _make_long_thread(extra=[
            FakeMsg(
                role="queen", content="Colony completed",
                render="result_card",
                meta={"task": "Fix auth", "status": "completed", "cost": 0.5},
            ),
        ])
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "### Done" in block
        assert "Fix auth" in block
        assert "$0.5000" in block

    def test_preview_card_is_pinned_not_compacted(self) -> None:
        msgs = _make_long_thread(extra=[
            FakeMsg(
                role="queen", content="Preview: Refactor DB layer",
                render="preview_card",
                meta={"task": "Refactor DB layer"},
            ),
        ])
        result = _compact_thread_history(msgs)
        # preview_card is pinned — kept raw as assistant message, not compacted
        raw_msgs = [m for m in result if m["role"] == "assistant" and "Refactor DB layer" in m["content"]]
        assert len(raw_msgs) >= 1

    def test_failed_result_card_in_blocked(self) -> None:
        msgs = _make_long_thread(extra=[
            FakeMsg(
                role="queen", content="Colony failed",
                render="result_card",
                meta={"task": "Deploy service", "status": "failed", "cost": 1.2},
            ),
        ])
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "### Blocked" in block
        assert "Deploy service" in block


class TestBlockedSection:
    def test_error_message_classified_as_blocked(self) -> None:
        msgs = _make_long_thread(
            queen_msgs=["Error: connection timeout when accessing database"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "### Blocked" in block or "## Critical Context" in block
        assert "timeout" in block.lower()


class TestDecisionsSection:
    def test_config_change_in_decisions(self) -> None:
        msgs = _make_long_thread(
            queen_msgs=["Changed strategy to stigmergic for better coordination"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "## Key Decisions" in block
        assert "strategy" in block.lower()


class TestRelevantFiles:
    def test_file_paths_extracted(self) -> None:
        msgs = _make_long_thread(
            queen_msgs=["Modified src/formicos/surface/app.py and tests/unit/test_app.py"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "## Relevant Files" in block
        assert "src/formicos/surface/app.py" in block
        assert "tests/unit/test_app.py" in block


class TestNextSteps:
    def test_queen_suggestion_in_next_steps(self) -> None:
        msgs = _make_long_thread(
            operator_msgs=["Start the auth refactor"],
            queen_msgs=["I suggest we first write integration tests before changing the handler"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "## Next Steps" in block
        assert "integration tests" in block


class TestCriticalContext:
    def test_error_details_in_critical(self) -> None:
        msgs = _make_long_thread(
            queen_msgs=["Exception: KeyError 'user_id' in auth_handler.py line 42"],
        )
        result = _compact_thread_history(msgs)
        block = _get_system_block(result)
        assert "## Critical Context" in block
        assert "KeyError" in block


class TestShortThreadBypass:
    def test_short_thread_not_compacted(self) -> None:
        msgs = [
            FakeMsg(role="operator", content="hello"),
            FakeMsg(role="queen", content="hi there"),
        ]
        result = _compact_thread_history(msgs)
        # No system block — all messages kept raw
        assert all(m["role"] != "system" for m in result)
        assert len(result) == 2


class TestRecentWindowPreserved:
    def test_recent_messages_always_raw(self) -> None:
        msgs = _make_long_thread()
        result = _compact_thread_history(msgs)
        # Last _RECENT_WINDOW messages should be raw (not system)
        recent = result[-_RECENT_WINDOW:]
        assert all(m["role"] in ("user", "assistant") for m in recent)
