"""Tests for AG-UI event promotions (Wave 33 B8)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from formicos.surface.event_translator import translate_event


def _ts() -> datetime:
    return datetime(2026, 3, 18, tzinfo=UTC)


class TestKnowledgeExtractedPromotion:
    """MemoryEntryCreated → KNOWLEDGE_EXTRACTED."""

    def test_emits_knowledge_extracted(self) -> None:
        from formicos.core.events import MemoryEntryCreated

        event = MemoryEntryCreated(
            seq=1,
            timestamp=_ts(),
            address="default/main/colony-1",
            entry={"id": "e1", "entry_type": "skill", "domains": ["python"], "scan_status": "safe"},
            workspace_id="default",
        )
        frames = list(translate_event("colony-1", event, 1))
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["name"] == "KNOWLEDGE_EXTRACTED"
        assert data["value"]["entry_id"] == "e1"
        assert data["value"]["domains"] == ["python"]


class TestConfidenceUpdatedPromotion:
    """MemoryConfidenceUpdated → CONFIDENCE_UPDATED."""

    def test_emits_confidence_updated(self) -> None:
        from formicos.core.events import MemoryConfidenceUpdated

        event = MemoryConfidenceUpdated(
            seq=2,
            timestamp=_ts(),
            address="default/main",
            entry_id="e1",
            colony_id="colony-1",
            colony_succeeded=True,
            old_alpha=5.0,
            old_beta=5.0,
            new_alpha=6.0,
            new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id="default",
            thread_id="main",
            reason="observation",
        )
        frames = list(translate_event("colony-1", event, 1))
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["name"] == "CONFIDENCE_UPDATED"
        assert data["value"]["entry_id"] == "e1"
        assert abs(data["value"]["old_confidence"] - 0.5) < 0.01


class TestKnowledgeAccessedPromotion:
    """KnowledgeAccessRecorded → KNOWLEDGE_ACCESSED."""

    def test_emits_knowledge_accessed(self) -> None:
        from formicos.core.events import KnowledgeAccessRecorded

        event = KnowledgeAccessRecorded(
            seq=3,
            timestamp=_ts(),
            address="default/main/colony-1",
            colony_id="colony-1",
            round_number=1,
            access_mode="tool_search",
            items=[
                {"id": "e1", "source_system": "institutional_memory", "canonical_type": "skill"},
                {"id": "e2", "source_system": "institutional_memory", "canonical_type": "experience"},
            ],
            workspace_id="default",
        )
        frames = list(translate_event("colony-1", event, 1))
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["name"] == "KNOWLEDGE_ACCESSED"
        assert data["value"]["item_count"] == 2


class TestStepCompletedPromotion:
    """WorkflowStepCompleted → STEP_COMPLETED."""

    def test_emits_step_completed(self) -> None:
        from formicos.core.events import WorkflowStepCompleted

        event = WorkflowStepCompleted(
            seq=4,
            timestamp=_ts(),
            address="default/main",
            thread_id="main",
            step_index=0,
            colony_id="colony-1",
            success=True,
            workspace_id="default",
        )
        frames = list(translate_event("colony-1", event, 1))
        assert len(frames) == 1
        data = json.loads(frames[0]["data"])
        assert data["name"] == "STEP_COMPLETED"
        assert data["value"]["step_index"] == 0
        assert data["value"]["success"] is True
