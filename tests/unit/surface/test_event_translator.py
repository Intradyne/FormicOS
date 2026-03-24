"""Tests for surface/event_translator.py (Wave 32.5 Team 3).

Covers ApprovalRequested promotion and generic custom_event fallthrough.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from formicos.core.events import ApprovalRequested
from formicos.core.types import ApprovalType
from formicos.surface.event_translator import translate_event

_NOW = datetime(2026, 3, 18, tzinfo=timezone.utc)


def _make_approval_requested(
    colony_id: str = "colony-1",
    request_id: str = "req-123",
    approval_type: ApprovalType = ApprovalType.budget_increase,
    detail: str = "Budget increase from $5 to $10",
) -> ApprovalRequested:
    return ApprovalRequested(
        seq=1,
        timestamp=_NOW,
        address=f"ws-1/{colony_id}",
        request_id=request_id,
        approval_type=approval_type,
        detail=detail,
        colony_id=colony_id,
    )


class TestApprovalRequestedPromotion:
    """translate_event promotes ApprovalRequested to APPROVAL_NEEDED custom frame."""

    def test_yields_custom_frame(self) -> None:
        event = _make_approval_requested()
        frames = list(translate_event("colony-1", event, current_round=1))
        assert len(frames) == 1
        frame = frames[0]
        assert frame["event"] == "CUSTOM"

    def test_frame_name_is_approval_needed(self) -> None:
        event = _make_approval_requested()
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["name"] == "APPROVAL_NEEDED"

    def test_frame_type_is_custom(self) -> None:
        event = _make_approval_requested()
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["type"] == "CUSTOM"

    def test_run_id_matches_colony_id(self) -> None:
        event = _make_approval_requested(colony_id="colony-abc")
        frames = list(translate_event("colony-abc", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["runId"] == "colony-abc"

    def test_requires_human_is_true(self) -> None:
        event = _make_approval_requested()
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["value"]["requires_human"] is True

    def test_suggested_action_present(self) -> None:
        event = _make_approval_requested()
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert "suggested_action" in data["value"]
        assert "approve" in data["value"]["suggested_action"].lower()

    def test_approval_type_in_value(self) -> None:
        event = _make_approval_requested(approval_type=ApprovalType.budget_increase)
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["value"]["approval_type"] == "budget_increase"

    def test_detail_in_value(self) -> None:
        event = _make_approval_requested(detail="Need more budget")
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["value"]["detail"] == "Need more budget"

    def test_request_id_in_value(self) -> None:
        event = _make_approval_requested(request_id="req-xyz")
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["value"]["request_id"] == "req-xyz"

    @pytest.mark.parametrize("approval_type", list(ApprovalType))
    def test_all_approval_types_translated(self, approval_type: ApprovalType) -> None:
        event = _make_approval_requested(approval_type=approval_type)
        frames = list(translate_event("colony-1", event, current_round=1))
        data = json.loads(frames[0]["data"])
        assert data["value"]["approval_type"] == approval_type.value


class TestGenericFallthrough:
    """Non-promoted events fall through to generic custom_event."""

    def test_unhandled_event_falls_through_to_custom(self) -> None:
        """An unhandled event type falls to custom_event with a non-APPROVAL_NEEDED name."""
        from formicos.core.events import WorkspaceConfigSnapshot, WorkspaceCreated

        event = WorkspaceCreated(
            seq=1, timestamp=_NOW, address="ws-1",
            name="ws-1",
            config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
        )
        frames = list(translate_event("colony-1", event, current_round=1))
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        # Falls to generic custom_event — name is the event type, not APPROVAL_NEEDED
        assert data["name"] != "APPROVAL_NEEDED"
        assert data["type"] == "CUSTOM"
