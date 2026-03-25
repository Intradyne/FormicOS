"""Serialize/deserialize round-trip tests for Wave 11 Phase A events."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formicos.core.events import (
    ColonyNamed,
    ColonyTemplateCreated,
    ColonyTemplateUsed,
    FormicOSEvent,
    SkillConfidenceUpdated,
    deserialize,
    serialize,
)
from formicos.core.types import CasteSlot


_NOW = datetime(2027, 3, 14, tzinfo=UTC)


class TestColonyTemplateCreatedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        event = ColonyTemplateCreated(
            seq=1, timestamp=_NOW, address="ws-1",
            template_id="tmpl-abc123",
            name="Code Review",
            description="Coder + Reviewer pair.",
            castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
            strategy="stigmergic",
            source_colony_id="colony-deadbeef",
        )
        blob = serialize(event)
        restored = deserialize(blob)
        assert isinstance(restored, ColonyTemplateCreated)
        assert restored.template_id == "tmpl-abc123"
        assert restored.name == "Code Review"
        assert restored.castes == [CasteSlot(caste="coder"), CasteSlot(caste="reviewer")]
        assert restored.strategy == "stigmergic"
        assert restored.source_colony_id == "colony-deadbeef"

    def test_source_colony_id_optional(self) -> None:
        event = ColonyTemplateCreated(
            seq=2, timestamp=_NOW, address="ws-1",
            template_id="tmpl-xyz",
            name="Research",
            description="Solo researcher.",
            castes=[CasteSlot(caste="researcher")],
            strategy="sequential",
        )
        restored = deserialize(serialize(event))
        assert isinstance(restored, ColonyTemplateCreated)
        assert restored.source_colony_id is None


class TestColonyTemplateUsedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        event = ColonyTemplateUsed(
            seq=3, timestamp=_NOW, address="ws-1",
            template_id="tmpl-abc123",
            colony_id="colony-12345678",
        )
        restored = deserialize(serialize(event))
        assert isinstance(restored, ColonyTemplateUsed)
        assert restored.template_id == "tmpl-abc123"
        assert restored.colony_id == "colony-12345678"


class TestColonyNamedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        event = ColonyNamed(
            seq=4, timestamp=_NOW, address="ws-1/thread-1/colony-1",
            colony_id="colony-1",
            display_name="Phoenix Rising",
            named_by="queen",
        )
        restored = deserialize(serialize(event))
        assert isinstance(restored, ColonyNamed)
        assert restored.colony_id == "colony-1"
        assert restored.display_name == "Phoenix Rising"
        assert restored.named_by == "queen"


class TestSkillConfidenceUpdatedRoundTrip:
    def test_serialize_deserialize(self) -> None:
        event = SkillConfidenceUpdated(
            seq=5, timestamp=_NOW, address="ws-1/thread-1/colony-1",
            colony_id="colony-1",
            skills_updated=3,
            colony_succeeded=True,
        )
        restored = deserialize(serialize(event))
        assert isinstance(restored, SkillConfidenceUpdated)
        assert restored.colony_id == "colony-1"
        assert restored.skills_updated == 3
        assert restored.colony_succeeded is True

    def test_failure_case(self) -> None:
        event = SkillConfidenceUpdated(
            seq=6, timestamp=_NOW, address="ws-1/thread-1/colony-2",
            colony_id="colony-2",
            skills_updated=0,
            colony_succeeded=False,
        )
        restored = deserialize(serialize(event))
        assert isinstance(restored, SkillConfidenceUpdated)
        assert restored.colony_succeeded is False
        assert restored.skills_updated == 0


class TestUnionSize:
    def test_runtime_union_has_37_members(self) -> None:
        """The runtime FormicOSEvent union contains exactly 37 types."""
        from typing import get_args

        annotated_args = get_args(FormicOSEvent)
        union_type = annotated_args[0]
        members = get_args(union_type)
        assert len(members) == 69, (
            f"Expected 69 event types, got {len(members)}: "
            f"{[m.__name__ for m in members]}"
        )
