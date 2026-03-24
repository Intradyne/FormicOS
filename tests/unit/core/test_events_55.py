"""ParallelPlanCreated event — deserialization, replay, round-trip (Wave 35 ADR-045)."""

from __future__ import annotations

from datetime import UTC, datetime

from formicos.core.events import (
    EVENT_TYPE_NAMES,
    ParallelPlanCreated,
    deserialize,
    serialize,
)


_NOW = datetime(2027, 3, 18, tzinfo=UTC)


class TestParallelPlanCreatedRoundTrip:
    """ParallelPlanCreated deserializes correctly."""

    def test_serialize_deserialize(self) -> None:
        event = ParallelPlanCreated(
            seq=42,
            timestamp=_NOW,
            address="ws-1/thread-1",
            thread_id="thread-1",
            workspace_id="ws-1",
            plan={
                "reasoning": "Split research and coding",
                "tasks": [
                    {"task_id": "t1", "task": "Research API", "caste": "researcher"},
                    {"task_id": "t2", "task": "Implement API", "caste": "coder"},
                ],
                "parallel_groups": [["t1"], ["t2"]],
                "estimated_total_cost": 2.5,
                "knowledge_gaps": ["api-design"],
            },
            parallel_groups=[["t1"], ["t2"]],
            reasoning="Split research and coding",
            knowledge_gaps=["api-design"],
            estimated_cost=2.5,
        )
        blob = serialize(event)
        restored = deserialize(blob)
        assert isinstance(restored, ParallelPlanCreated)
        assert restored.thread_id == "thread-1"
        assert restored.workspace_id == "ws-1"
        assert restored.parallel_groups == [["t1"], ["t2"]]
        assert restored.reasoning == "Split research and coding"
        assert restored.knowledge_gaps == ["api-design"]
        assert restored.estimated_cost == 2.5
        assert restored.plan["tasks"][0]["task_id"] == "t1"

    def test_replay_produces_identical_state(self) -> None:
        """Double-apply produces same result (idempotent via seq tracking)."""
        event = ParallelPlanCreated(
            seq=10,
            timestamp=_NOW,
            address="ws-1/thread-1",
            thread_id="thread-1",
            workspace_id="ws-1",
            plan={"reasoning": "test", "tasks": [], "parallel_groups": []},
            parallel_groups=[["a", "b"], ["c"]],
            reasoning="test",
        )
        blob = serialize(event)
        r1 = deserialize(blob)
        r2 = deserialize(blob)
        assert r1 == r2

    def test_in_event_type_names(self) -> None:
        assert "ParallelPlanCreated" in EVENT_TYPE_NAMES

    def test_default_fields(self) -> None:
        event = ParallelPlanCreated(
            seq=1,
            timestamp=_NOW,
            address="ws-1/t-1",
            thread_id="t-1",
            workspace_id="ws-1",
            plan={},
            parallel_groups=[],
            reasoning="minimal",
        )
        assert event.knowledge_gaps == []
        assert event.estimated_cost == 0.0
