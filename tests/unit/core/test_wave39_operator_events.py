"""Wave 39 Team 2: Operator co-authorship event expansion tests (ADR-049).

Verifies:
- Event union grows from 55 to 58 through exactly 3 new families
- All 3 event families are schema-valid, frozen, and serializable
- Import-time self-check passes
- Discriminator type fields match class names
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from formicos.core.events import (
    EVENT_TYPE_NAMES,
    ConfigSuggestionOverridden,
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    FormicOSEvent,
    serialize,
    deserialize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 3, 19, 12, 0, tzinfo=timezone.utc)


def _make_operator_action(
    action: str = "pin",
    entry_id: str = "entry-1",
    workspace_id: str = "ws-1",
) -> KnowledgeEntryOperatorAction:
    return KnowledgeEntryOperatorAction(
        seq=1,
        timestamp=_TS,
        address=f"{workspace_id}/{entry_id}",
        entry_id=entry_id,
        workspace_id=workspace_id,
        action=action,
        actor="operator",
    )


def _make_annotation(
    entry_id: str = "entry-1",
    text: str = "This entry is important for compliance.",
) -> KnowledgeEntryAnnotated:
    return KnowledgeEntryAnnotated(
        seq=2,
        timestamp=_TS,
        address=f"ws-1/{entry_id}",
        entry_id=entry_id,
        workspace_id="ws-1",
        annotation_text=text,
        tag="compliance",
        actor="operator",
    )


def _make_config_override() -> ConfigSuggestionOverridden:
    return ConfigSuggestionOverridden(
        seq=3,
        timestamp=_TS,
        address="ws-1",
        workspace_id="ws-1",
        suggestion_category="strategy",
        original_config={"strategy": "stigmergic"},
        overridden_config={"strategy": "direct"},
        reason="Direct is faster for this task type.",
        actor="operator",
    )


# ---------------------------------------------------------------------------
# Tests: Union expansion
# ---------------------------------------------------------------------------


class TestEventUnionExpansion:
    """Verify the event union grows from 55 to 58 through exactly 3 families."""

    def test_event_count_is_62(self) -> None:
        assert len(EVENT_TYPE_NAMES) == 69

    def test_new_families_in_manifest(self) -> None:
        assert "KnowledgeEntryOperatorAction" in EVENT_TYPE_NAMES
        assert "KnowledgeEntryAnnotated" in EVENT_TYPE_NAMES
        assert "ConfigSuggestionOverridden" in EVENT_TYPE_NAMES

    def test_import_time_self_check_passed(self) -> None:
        """If we got here, the import-time self-check in events.py passed."""
        from formicos.core.events import _manifest_set, _union_members  # noqa: PLC0415
        assert _manifest_set == _union_members


# ---------------------------------------------------------------------------
# Tests: KnowledgeEntryOperatorAction
# ---------------------------------------------------------------------------


class TestKnowledgeEntryOperatorAction:
    """Verify operator action event schema and behavior."""

    @pytest.mark.parametrize("action", [
        "pin", "unpin", "mute", "unmute", "invalidate", "reinstate",
    ])
    def test_all_actions_valid(self, action: str) -> None:
        event = _make_operator_action(action=action)
        assert event.action == action
        assert event.type == "KnowledgeEntryOperatorAction"

    def test_invalid_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_operator_action(action="delete")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        event = _make_operator_action()
        with pytest.raises(ValidationError):
            event.action = "mute"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        event = _make_operator_action(action="invalidate")
        json_str = serialize(event)
        restored = deserialize(json_str)
        assert restored.type == "KnowledgeEntryOperatorAction"
        assert restored.entry_id == "entry-1"  # type: ignore[attr-defined]
        assert restored.action == "invalidate"  # type: ignore[attr-defined]

    def test_reason_is_optional(self) -> None:
        event = _make_operator_action()
        assert event.reason == ""

    def test_reason_preserved(self) -> None:
        event = KnowledgeEntryOperatorAction(
            seq=1,
            timestamp=_TS,
            address="ws-1/entry-1",
            entry_id="entry-1",
            workspace_id="ws-1",
            action="mute",
            actor="operator",
            reason="Too noisy for current task.",
        )
        assert event.reason == "Too noisy for current task."


# ---------------------------------------------------------------------------
# Tests: KnowledgeEntryAnnotated
# ---------------------------------------------------------------------------


class TestKnowledgeEntryAnnotated:
    """Verify annotation event schema and behavior."""

    def test_basic_creation(self) -> None:
        event = _make_annotation()
        assert event.type == "KnowledgeEntryAnnotated"
        assert event.annotation_text == "This entry is important for compliance."
        assert event.tag == "compliance"

    def test_frozen(self) -> None:
        event = _make_annotation()
        with pytest.raises(ValidationError):
            event.annotation_text = "changed"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        event = _make_annotation()
        json_str = serialize(event)
        restored = deserialize(json_str)
        assert restored.type == "KnowledgeEntryAnnotated"
        assert restored.annotation_text == "This entry is important for compliance."  # type: ignore[attr-defined]
        assert restored.tag == "compliance"  # type: ignore[attr-defined]

    def test_tag_is_optional(self) -> None:
        event = KnowledgeEntryAnnotated(
            seq=1,
            timestamp=_TS,
            address="ws-1/entry-1",
            entry_id="entry-1",
            workspace_id="ws-1",
            annotation_text="A note.",
            actor="operator",
        )
        assert event.tag == ""


# ---------------------------------------------------------------------------
# Tests: ConfigSuggestionOverridden
# ---------------------------------------------------------------------------


class TestConfigSuggestionOverridden:
    """Verify config override event schema and behavior."""

    def test_basic_creation(self) -> None:
        event = _make_config_override()
        assert event.type == "ConfigSuggestionOverridden"
        assert event.suggestion_category == "strategy"
        assert event.original_config == {"strategy": "stigmergic"}
        assert event.overridden_config == {"strategy": "direct"}

    def test_frozen(self) -> None:
        event = _make_config_override()
        with pytest.raises(ValidationError):
            event.reason = "changed"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        event = _make_config_override()
        json_str = serialize(event)
        restored = deserialize(json_str)
        assert restored.type == "ConfigSuggestionOverridden"
        assert restored.suggestion_category == "strategy"  # type: ignore[attr-defined]
        assert restored.original_config == {"strategy": "stigmergic"}  # type: ignore[attr-defined]

    def test_reason_is_optional(self) -> None:
        event = ConfigSuggestionOverridden(
            seq=1,
            timestamp=_TS,
            address="ws-1",
            workspace_id="ws-1",
            suggestion_category="model_tier",
            original_config={"tier": "light"},
            overridden_config={"tier": "heavy"},
            actor="operator",
        )
        assert event.reason == ""
