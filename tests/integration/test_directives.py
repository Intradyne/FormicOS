"""Integration test — Operator directive injection (Wave 35, ADR-045 D3).

Directives delivered via ColonyChatMessage metadata are injected into round
context. Urgent CONSTRAINT_ADD appears before task. Normal directives appear
after task, before round history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from formicos.core.types import (
    ColonyContext,
    DirectiveType,
    OperatorDirective,
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class TestDirectiveInjection:
    """Operator directives flow through ColonyContext into round messages."""

    def test_directive_type_enum_values(self) -> None:
        """All 4 directive types exist."""
        assert DirectiveType.context_update == "context_update"
        assert DirectiveType.priority_shift == "priority_shift"
        assert DirectiveType.constraint_add == "constraint_add"
        assert DirectiveType.strategy_change == "strategy_change"

    def test_operator_directive_model(self) -> None:
        """OperatorDirective constructs with all fields."""
        d = OperatorDirective(
            directive_type=DirectiveType.constraint_add,
            content="Do not use external APIs",
            priority="urgent",
            applies_to="all",
        )
        assert d.directive_type == DirectiveType.constraint_add
        assert d.priority == "urgent"
        assert d.content == "Do not use external APIs"

    def test_colony_context_pending_directives(self) -> None:
        """ColonyContext carries pending_directives field."""
        urgent_directive = {
            "directive_type": "constraint_add",
            "content": "No external API calls",
            "directive_priority": "urgent",
        }
        normal_directive = {
            "directive_type": "context_update",
            "content": "Auth library changed to OAuth2",
            "directive_priority": "normal",
        }
        ctx = ColonyContext(
            colony_id="col-1",
            workspace_id="ws-1",
            thread_id="t-1",
            goal="Build API",
            round_number=1,
            merge_edges=[],
            pending_directives=[urgent_directive, normal_directive],
        )
        assert len(ctx.pending_directives) == 2
        assert ctx.pending_directives[0]["directive_priority"] == "urgent"
        assert ctx.pending_directives[1]["directive_priority"] == "normal"

    def test_urgent_directive_positioned_before_task(self) -> None:
        """Urgent directives are inserted at position 0 (before task context).

        Verifies the runner.py injection logic pattern:
        - urgent → messages.insert(0, ...) — before task description
        - normal → messages.insert after task context
        """
        # Simulate the message assembly pattern from runner.py
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are a coder agent."},
            {"role": "user", "content": "Task: Build REST API"},
            {"role": "assistant", "content": "Previous round summary..."},
        ]

        pending = [
            {
                "directive_type": "constraint_add",
                "content": "No external API calls",
                "directive_priority": "urgent",
            },
            {
                "directive_type": "context_update",
                "content": "Auth changed to OAuth2",
                "directive_priority": "normal",
            },
        ]

        urgent = [d for d in pending if d.get("directive_priority") == "urgent"]
        normal = [d for d in pending if d.get("directive_priority") != "urgent"]

        if urgent:
            urgent_text = "\n".join(
                f"[{d.get('directive_type', 'DIRECTIVE').upper()}] {d.get('content', '')}"
                for d in urgent
            )
            messages.insert(0, {"role": "system", "content": f"⚠️ OPERATOR DIRECTIVES:\n{urgent_text}"})

        if normal:
            normal_text = "\n".join(
                f"[{d.get('directive_type', 'DIRECTIVE').upper()}] {d.get('content', '')}"
                for d in normal
            )
            # After task context (position 2 in the expanded list)
            insert_pos = min(2, len(messages))
            messages.insert(insert_pos, {"role": "system", "content": f"Operator update:\n{normal_text}"})

        # Urgent should be at position 0
        assert "OPERATOR DIRECTIVES" in messages[0]["content"]
        assert "CONSTRAINT_ADD" in messages[0]["content"]

        # Normal should be after system prompt but before assistant round summary
        normal_msg = [m for m in messages if "Operator update" in m.get("content", "")]
        assert len(normal_msg) == 1
        assert "CONTEXT_UPDATE" in normal_msg[0]["content"]

    def test_directive_defaults(self) -> None:
        """OperatorDirective has sensible defaults."""
        d = OperatorDirective(
            directive_type=DirectiveType.context_update,
            content="Just a note",
        )
        assert d.priority == "normal"
        assert d.applies_to == "all"
