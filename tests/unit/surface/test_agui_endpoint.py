"""Unit tests for formicos.surface.agui_endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ColonyCompleted,
    ColonyFailed,
    ColonyKilled,
    RoundCompleted,
    RoundStarted,
)
from formicos.surface.agui_endpoint import AGUI_EVENT_TYPES
from formicos.surface.event_translator import (
    custom_event as _custom_event,
    run_finished as _run_finished,
    run_started as _run_started,
    state_snapshot as _state_snapshot,
    step_finished as _step_finished,
    step_started as _step_started,
    text_message_content as _text_message_content,
    text_message_end as _text_message_end,
    text_message_start as _text_message_start,
)

NOW = datetime.now(UTC)


class TestAguiEventTypes:
    def test_event_type_count(self) -> None:
        assert len(AGUI_EVENT_TYPES) == 9

    def test_required_types_present(self) -> None:
        expected = {
            "RUN_STARTED", "RUN_FINISHED",
            "STEP_STARTED", "STEP_FINISHED",
            "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
            "STATE_SNAPSHOT", "CUSTOM",
        }
        assert AGUI_EVENT_TYPES == expected


class TestRunStarted:
    def test_shape(self) -> None:
        result = _run_started("colony-1")
        assert result["event"] == "RUN_STARTED"
        data = json.loads(result["data"])
        assert data["type"] == "RUN_STARTED"
        assert data["runId"] == "colony-1"
        assert "timestamp" in data


class TestRunFinished:
    def test_completed(self) -> None:
        event = ColonyCompleted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1",
            summary="done", skills_extracted=0,
        )
        result = _run_finished("c1", event)
        data = json.loads(result["data"])
        assert data["status"] == "completed"

    def test_failed(self) -> None:
        event = ColonyFailed(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1", reason="boom",
        )
        result = _run_finished("c1", event)
        data = json.loads(result["data"])
        assert data["status"] == "failed"

    def test_killed(self) -> None:
        event = ColonyKilled(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1", killed_by="operator",
        )
        result = _run_finished("c1", event)
        data = json.loads(result["data"])
        assert data["status"] == "killed"

    def test_timeout(self) -> None:
        event = ColonyCompleted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1",
            summary="", skills_extracted=0,
        )
        result = _run_finished("c1", event, timed_out=True)
        data = json.loads(result["data"])
        assert data["status"] == "timeout"


class TestStepEvents:
    def test_step_started(self) -> None:
        result = _step_started("c1", 3)
        data = json.loads(result["data"])
        assert data["type"] == "STEP_STARTED"
        assert data["step"] == 3
        assert data["stepId"] == "c1-r3"

    def test_step_finished(self) -> None:
        result = _step_finished("c1", 3)
        data = json.loads(result["data"])
        assert data["type"] == "STEP_FINISHED"
        assert data["step"] == 3


class TestTextMessageEvents:
    def test_message_start(self) -> None:
        event = AgentTurnStarted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1",
            round_number=2, agent_id="a1", caste="coder",
            model="llama/test",
        )
        result = _text_message_start("c1", event, 2)
        data = json.loads(result["data"])
        assert data["type"] == "TEXT_MESSAGE_START"
        assert data["messageId"] == "c1-a1-r2"
        assert data["role"] == "coder"

    def test_message_content_is_summary(self) -> None:
        event = AgentTurnCompleted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", agent_id="a1",
            output_summary="This is a summary.",
            input_tokens=100, output_tokens=50,
            tool_calls=["code_execute"],
            duration_ms=500,
        )
        result = _text_message_content("c1", event, 2)
        data = json.loads(result["data"])
        assert data["type"] == "TEXT_MESSAGE_CONTENT"
        assert data["content"] == "This is a summary."
        assert data["contentType"] == "summary"
        assert data["messageId"] == "c1-a1-r2"

    def test_message_end(self) -> None:
        event = AgentTurnCompleted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", agent_id="a1",
            output_summary="done",
            input_tokens=100, output_tokens=50,
            tool_calls=[],
            duration_ms=500,
        )
        result = _text_message_end("c1", event, 2)
        data = json.loads(result["data"])
        assert data["type"] == "TEXT_MESSAGE_END"
        assert data["messageId"] == "c1-a1-r2"


class TestStateSnapshot:
    def test_snapshot_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Patch build_transcript to avoid needing a real ColonyProjection
        monkeypatch.setattr(
            "formicos.surface.transcript.build_transcript",
            lambda colony: {"colony_id": colony.id, "status": colony.status},
        )
        from types import SimpleNamespace
        colony = SimpleNamespace(id="c1", status="running")
        result = _state_snapshot("c1", colony)
        data = json.loads(result["data"])
        assert data["type"] == "STATE_SNAPSHOT"
        assert "snapshot" in data
        snapshot = data["snapshot"]
        assert snapshot["colony_id"] == "c1"


class TestCustomEvent:
    def test_passthrough_shape(self) -> None:
        event = RoundStarted(
            seq=1, timestamp=NOW,
            address="ws/t/c1", colony_id="c1", round_number=1,
        )
        result = _custom_event("c1", event)
        assert result["event"] == "CUSTOM"
        data = json.loads(result["data"])
        assert data["type"] == "CUSTOM"
        assert data["name"] == "RoundStarted"
        assert data["runId"] == "c1"
        assert "value" in data
