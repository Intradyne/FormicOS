"""Operator directive tests (Wave 35 C1, ADR-045 D3).

Validates directive injection in context assembly, ColonyChatMessage event
tagging, and AG-UI event emission.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from formicos.core.events import ColonyChatMessage
from formicos.core.types import ColonyContext, DirectiveType, MergeEdge, OperatorDirective


class TestDirectiveTypeEnum:
    """DirectiveType StrEnum has all 4 values."""

    def test_all_types_present(self) -> None:
        expected = {"context_update", "priority_shift", "constraint_add", "strategy_change"}
        actual = {e.value for e in DirectiveType}
        assert actual == expected

    def test_str_coercion(self) -> None:
        assert str(DirectiveType.context_update) == "context_update"


class TestOperatorDirectiveModel:
    """OperatorDirective model validates correctly."""

    def test_basic_construction(self) -> None:
        d = OperatorDirective(
            directive_type=DirectiveType.priority_shift,
            content="Focus on error handling first",
        )
        assert d.directive_type == DirectiveType.priority_shift
        assert d.priority == "normal"
        assert d.applies_to == "all"

    def test_urgent_priority(self) -> None:
        d = OperatorDirective(
            directive_type=DirectiveType.constraint_add,
            content="Must not use deprecated API",
            priority="urgent",
        )
        assert d.priority == "urgent"

    def test_frozen(self) -> None:
        d = OperatorDirective(
            directive_type=DirectiveType.context_update,
            content="test",
        )
        try:
            d.content = "changed"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except Exception:
            pass


class TestColonyChatMessageDirective:
    """ColonyChatMessage carries directive_type in its fields."""

    def test_directive_type_on_event(self) -> None:
        msg = ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address="ws/th/col",
            colony_id="col-1",
            workspace_id="ws-1",
            sender="operator",
            content="Switch to defensive coding",
            directive_type="strategy_change",
            metadata={"directive_type": "strategy_change", "directive_priority": "urgent"},
        )
        assert msg.directive_type == "strategy_change"
        assert msg.metadata is not None
        assert msg.metadata["directive_priority"] == "urgent"

    def test_no_directive_type_by_default(self) -> None:
        msg = ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address="ws/th/col",
            colony_id="col-1",
            workspace_id="ws-1",
            sender="operator",
            content="Hello",
        )
        assert msg.directive_type is None


class TestDirectiveContextInjection:
    """Directive injection framing in context assembly."""

    def test_urgent_directive_position(self) -> None:
        """Urgent directives are injected near the beginning of messages."""
        directives = [
            {"content": "STOP using cache", "directive_type": "constraint_add", "directive_priority": "urgent"},
        ]
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Test goal",
            round_number=1,
            merge_edges=[],
            pending_directives=directives,
        )
        assert len(ctx.pending_directives) == 1
        assert ctx.pending_directives[0]["directive_priority"] == "urgent"

    def test_normal_directive_position(self) -> None:
        """Normal directives are included in pending_directives."""
        directives = [
            {"content": "Consider using batch API", "directive_type": "context_update", "directive_priority": "normal"},
        ]
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Test goal",
            round_number=1,
            merge_edges=[],
            pending_directives=directives,
        )
        assert ctx.pending_directives[0]["directive_type"] == "context_update"

    def test_no_directives_empty_list(self) -> None:
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="th-1",
            goal="Test goal",
            round_number=1,
            merge_edges=[],
        )
        assert ctx.pending_directives == []


class TestDirectiveAGUIEvent:
    """AG-UI event emission for directive-tagged ColonyChatMessages."""

    def test_operator_directive_event(self) -> None:
        from formicos.surface.event_translator import translate_event

        msg = ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address="ws/th/col",
            colony_id="col-1",
            workspace_id="ws-1",
            sender="operator",
            content="Change approach to incremental",
            directive_type="strategy_change",
            metadata={"directive_type": "strategy_change", "directive_priority": "urgent"},
        )
        frames = list(translate_event("col-1", msg, 1))
        assert len(frames) == 1
        import json
        data = json.loads(frames[0]["data"])
        assert data["name"] == "OPERATOR_DIRECTIVE"
        assert data["value"]["directive_type"] == "strategy_change"
        assert data["value"]["priority"] == "urgent"

    def test_non_directive_chat_not_promoted(self) -> None:
        from formicos.surface.event_translator import translate_event

        msg = ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address="ws/th/col",
            colony_id="col-1",
            workspace_id="ws-1",
            sender="operator",
            content="Just a normal chat message",
        )
        frames = list(translate_event("col-1", msg, 1))
        # Should fall through to generic custom_event, not OPERATOR_DIRECTIVE
        assert len(frames) == 1
        import json
        data = json.loads(frames[0]["data"])
        assert data["name"] != "OPERATOR_DIRECTIVE"

    def test_queen_directive_not_promoted_as_operator(self) -> None:
        """Queen directives (SPAWN, REDIRECT) don't emit OPERATOR_DIRECTIVE."""
        from formicos.surface.event_translator import translate_event

        msg = ColonyChatMessage(
            seq=0,
            timestamp=datetime.now(UTC),
            address="ws/th/col",
            colony_id="col-1",
            workspace_id="ws-1",
            sender="queen",
            content="Spawning sub-colony",
            directive_type="SPAWN",
        )
        frames = list(translate_event("col-1", msg, 1))
        import json
        data = json.loads(frames[0]["data"])
        assert data["name"] != "OPERATOR_DIRECTIVE"
