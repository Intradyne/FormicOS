"""Wave 49 Team 1: Queen message metadata and thread compaction tests.

Covers:
- Track A: QueenMessage gains additive intent/render/meta fields
- Track B: Preview metadata persisted on emitted Queen messages
- Track C: Result-card metadata on follow-up messages
- Track D: Ask/notify classification at emit sites
- Track E: Backward compatibility — older events replay with defaults
- Track F: Deterministic Queen thread compaction
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from formicos.core.events import QueenMessage, deserialize, serialize
from formicos.surface.projections import QueenMessageProjection
from formicos.surface.queen_runtime import (
    _RECENT_WINDOW,
    _compact_thread_history,
    _is_pinned,
)

NOW = datetime.now(UTC)
ADDR = "ws-1/th-1"


# ---------------------------------------------------------------------------
# Track A + E: QueenMessage metadata fields and backward compatibility
# ---------------------------------------------------------------------------


class TestQueenMessageMetadata:
    """Verify additive metadata fields on the QueenMessage event."""

    def test_defaults_are_none(self) -> None:
        msg = QueenMessage(
            seq=1, timestamp=NOW, address=ADDR,
            thread_id="th-1", role="queen", content="Hello",
        )
        assert msg.intent is None
        assert msg.render is None
        assert msg.meta is None

    def test_fields_accepted(self) -> None:
        msg = QueenMessage(
            seq=1, timestamp=NOW, address=ADDR,
            thread_id="th-1", role="queen", content="Preview",
            intent="notify", render="preview_card",
            meta={"task": "Fix bug", "estimated_cost": 2.5},
        )
        assert msg.intent == "notify"
        assert msg.render == "preview_card"
        assert msg.meta["task"] == "Fix bug"

    def test_backward_compat_serialization(self) -> None:
        """Older events without metadata fields deserialize cleanly."""
        old_msg = QueenMessage(
            seq=1, timestamp=NOW, address=ADDR,
            thread_id="th-1", role="queen", content="old message",
        )
        raw = serialize(old_msg)
        restored = deserialize(raw)
        assert restored.content == "old message"  # type: ignore[union-attr]
        assert restored.intent is None  # type: ignore[union-attr]
        assert restored.render is None  # type: ignore[union-attr]
        assert restored.meta is None  # type: ignore[union-attr]

    def test_full_round_trip_with_metadata(self) -> None:
        msg = QueenMessage(
            seq=2, timestamp=NOW, address=ADDR,
            thread_id="th-1", role="queen", content="Result",
            intent="notify", render="result_card",
            meta={"colony_id": "col-1", "status": "completed"},
        )
        restored = deserialize(serialize(msg))
        assert restored == msg


# ---------------------------------------------------------------------------
# Track A: Projection handler carries metadata
# ---------------------------------------------------------------------------


class TestProjectionMetadata:
    """Verify QueenMessageProjection carries Wave 49 fields."""

    def test_projection_has_metadata_fields(self) -> None:
        proj = QueenMessageProjection(
            role="queen", content="Hello", timestamp="2026-01-01T00:00:00",
            intent="ask", render="text", meta={"question": "confirm?"},
        )
        assert proj.intent == "ask"
        assert proj.render == "text"
        assert proj.meta == {"question": "confirm?"}

    def test_projection_defaults_none(self) -> None:
        proj = QueenMessageProjection(
            role="queen", content="Hello", timestamp="2026-01-01T00:00:00",
        )
        assert proj.intent is None
        assert proj.render is None
        assert proj.meta is None

    def test_handler_carries_fields(self) -> None:
        """Verify _on_queen_message propagates metadata to projection."""
        from formicos.surface.projections import ProjectionStore, _on_queen_message

        store = ProjectionStore()
        # Create a workspace with a thread
        from formicos.surface.projections import ThreadProjection, WorkspaceProjection
        ws = WorkspaceProjection(id="ws-1", name="test")
        thread = ThreadProjection(id="th-1", workspace_id="ws-1", name="test")
        ws.threads["th-1"] = thread
        store.workspaces["ws-1"] = ws

        event = QueenMessage(
            seq=1, timestamp=NOW, address=ADDR,
            thread_id="th-1", role="queen", content="Preview proposed",
            intent="notify", render="preview_card",
            meta={"task": "Fix bug"},
        )
        _on_queen_message(store, event)

        assert len(thread.queen_messages) == 1
        proj = thread.queen_messages[0]
        assert proj.intent == "notify"
        assert proj.render == "preview_card"
        assert proj.meta == {"task": "Fix bug"}


# ---------------------------------------------------------------------------
# Track F: Deterministic Queen thread compaction
# ---------------------------------------------------------------------------


@dataclass
class FakeMsg:
    """Minimal message stub for compaction tests."""
    role: str
    content: str
    intent: str | None = None
    render: str | None = None
    meta: dict[str, Any] | None = None


class TestCompaction:
    """Verify _compact_thread_history behavior."""

    def test_short_thread_not_compacted(self) -> None:
        msgs = [FakeMsg(role="operator", content=f"msg {i}") for i in range(5)]
        result = _compact_thread_history(msgs)
        assert len(result) == 5
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "msg 0"

    def test_compaction_triggers_on_token_pressure(self) -> None:
        # Create enough messages to exceed token budget
        long_content = "x" * 1000  # ~250 tokens each
        msgs = [
            FakeMsg(
                role="operator" if i % 2 == 0 else "queen",
                content=long_content,
            )
            for i in range(30)
        ]
        result = _compact_thread_history(msgs)
        # Should have compacted block + recent window
        assert len(result) < 30
        # Recent window messages should be raw
        assert result[-1]["content"] == long_content

    def test_recent_window_preserved(self) -> None:
        msgs = [
            FakeMsg(role="operator", content=f"old-{i}")
            for i in range(20)
        ] + [
            FakeMsg(role="queen", content=f"recent-{i}")
            for i in range(_RECENT_WINDOW)
        ]
        # Force token pressure
        msgs[0].content = "x" * 10000
        result = _compact_thread_history(msgs)
        # Last _RECENT_WINDOW entries should be the recent messages
        recent_contents = [r["content"] for r in result[-_RECENT_WINDOW:]]
        for i in range(_RECENT_WINDOW):
            assert f"recent-{i}" in recent_contents

    def test_pinned_ask_preserved(self) -> None:
        """Unresolved ask messages in older region are kept raw."""
        long_content = "x" * 1000
        msgs = [
            FakeMsg(role="operator", content=long_content)
            for _ in range(20)
        ]
        # Put an ask in the older region
        msgs[2] = FakeMsg(
            role="queen", content="Do you want to proceed?",
            intent="ask",
        )
        # Add recent window
        msgs += [FakeMsg(role="queen", content="recent") for _ in range(_RECENT_WINDOW)]
        result = _compact_thread_history(msgs)
        # The ask should be preserved raw somewhere
        ask_entries = [r for r in result if "Do you want to proceed?" in r["content"]]
        assert len(ask_entries) == 1

    def test_pinned_preview_card_preserved(self) -> None:
        """Active preview_card messages in older region are kept raw."""
        long_content = "x" * 1000
        msgs = [
            FakeMsg(role="operator", content=long_content)
            for _ in range(20)
        ]
        msgs[3] = FakeMsg(
            role="queen", content="Here is the plan",
            render="preview_card", meta={"task": "Fix bug"},
        )
        msgs += [FakeMsg(role="queen", content="recent") for _ in range(_RECENT_WINDOW)]
        result = _compact_thread_history(msgs)
        preview_entries = [r for r in result if "Here is the plan" in r["content"]]
        assert len(preview_entries) == 1

    def test_compacted_block_uses_structured_metadata(self) -> None:
        """Result-card messages should appear as structured summaries."""
        long_content = "x" * 2000
        msgs = [FakeMsg(role="operator", content=long_content) for _ in range(20)]
        msgs[1] = FakeMsg(
            role="queen", content="Colony completed",
            render="result_card",
            meta={"task": "Fix auth", "status": "completed", "cost": 0.5},
        )
        msgs += [FakeMsg(role="queen", content="recent") for _ in range(_RECENT_WINDOW)]
        result = _compact_thread_history(msgs)
        # Find the compacted block
        system_blocks = [r for r in result if r["role"] == "system"]
        assert len(system_blocks) >= 1
        compacted = system_blocks[0]["content"]
        # Wave 77.5 A8: structured compression uses section headers
        assert "## Progress" in compacted or "Earlier conversation:" in compacted
        assert "Fix auth" in compacted

    def test_is_pinned_ask(self) -> None:
        msg = FakeMsg(role="queen", content="x", intent="ask")
        assert _is_pinned(msg) is True

    def test_is_pinned_preview(self) -> None:
        msg = FakeMsg(role="queen", content="x", render="preview_card")
        assert _is_pinned(msg) is True

    def test_is_pinned_normal(self) -> None:
        msg = FakeMsg(role="queen", content="x")
        assert _is_pinned(msg) is False

    def test_at_boundary_no_compaction(self) -> None:
        """Exactly _RECENT_WINDOW messages should not compact."""
        msgs = [
            FakeMsg(role="operator", content=f"msg {i}")
            for i in range(_RECENT_WINDOW)
        ]
        result = _compact_thread_history(msgs)
        assert len(result) == _RECENT_WINDOW
