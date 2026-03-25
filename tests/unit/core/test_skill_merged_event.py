"""Serialize/deserialize round-trip tests for SkillMerged event."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from formicos.core.events import (
    FormicOSEvent,
    SkillMerged,
    deserialize,
    serialize,
)

_NOW = datetime(2026, 3, 14, tzinfo=UTC)


class TestSkillMergedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        event = SkillMerged(
            seq=1, timestamp=_NOW, address="ws-1",
            surviving_skill_id="skill-abc",
            merged_skill_id="skill-xyz",
            merge_reason="llm_dedup",
        )
        blob = serialize(event)
        restored = deserialize(blob)
        assert isinstance(restored, SkillMerged)
        assert restored.surviving_skill_id == "skill-abc"
        assert restored.merged_skill_id == "skill-xyz"
        assert restored.merge_reason == "llm_dedup"

    def test_type_discriminant(self) -> None:
        event = SkillMerged(
            seq=2, timestamp=_NOW, address="ws-1",
            surviving_skill_id="a",
            merged_skill_id="b",
            merge_reason="llm_dedup",
        )
        assert event.type == "SkillMerged"

    def test_in_union(self) -> None:
        annotated_args = get_args(FormicOSEvent)
        union_type = annotated_args[0]
        members = {cls.__name__ for cls in get_args(union_type)}
        assert "SkillMerged" in members

    def test_union_has_37_members(self) -> None:
        annotated_args = get_args(FormicOSEvent)
        union_type = annotated_args[0]
        members = get_args(union_type)
        assert len(members) == 69
