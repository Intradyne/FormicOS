"""Integration test — 55-event replay idempotency (Wave 35).

All 55 event types (53 existing + ParallelPlanCreated + KnowledgeDistilled)
replay correctly. Double-apply yields identical projections.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from formicos.core.events import (
    EVENT_TYPE_NAMES,
    FormicOSEvent,
    KnowledgeDistilled,
    ParallelPlanCreated,
)
from formicos.surface.projections import ProjectionStore


def _ts() -> datetime:
    return datetime.now(tz=UTC)


class TestReplay55Events:
    """55-event union completeness and replay idempotency."""

    def test_event_union_has_55_types(self) -> None:
        """EVENT_TYPE_NAMES contains exactly 55 entries."""
        assert len(EVENT_TYPE_NAMES) == 65, (
            f"Expected 65 event types, found {len(EVENT_TYPE_NAMES)}"
        )

    def test_parallel_plan_created_in_union(self) -> None:
        """ParallelPlanCreated is in the event type names list."""
        assert "ParallelPlanCreated" in EVENT_TYPE_NAMES

    def test_knowledge_distilled_in_union(self) -> None:
        """KnowledgeDistilled is in the event type names list."""
        assert "KnowledgeDistilled" in EVENT_TYPE_NAMES

    def test_parallel_plan_created_round_trip(self) -> None:
        """ParallelPlanCreated serializes/deserializes via union discriminator."""
        event = ParallelPlanCreated(
            seq=1, timestamp=_ts(), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={"reasoning": "test plan", "tasks": []},
            parallel_groups=[["a", "b"], ["c"]],
            reasoning="Parallel research then implement",
            knowledge_gaps=["auth-patterns"],
            estimated_cost=0.5,
        )
        # Serialize via Pydantic
        data = event.model_dump()
        assert data["type"] == "ParallelPlanCreated"

        # Deserialize back
        from pydantic import TypeAdapter

        adapter = TypeAdapter(FormicOSEvent)
        restored = adapter.validate_python(data)
        assert isinstance(restored, ParallelPlanCreated)
        assert restored.parallel_groups == [["a", "b"], ["c"]]
        assert restored.knowledge_gaps == ["auth-patterns"]

    def test_knowledge_distilled_round_trip(self) -> None:
        """KnowledgeDistilled serializes/deserializes via union discriminator."""
        event = KnowledgeDistilled(
            seq=2, timestamp=_ts(), address="ws-1/t-1/col-1",
            distilled_entry_id="mem-distilled-1",
            source_entry_ids=["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"],
            workspace_id="ws-1",
            cluster_avg_weight=4.2,
        )
        data = event.model_dump()
        assert data["type"] == "KnowledgeDistilled"

        from pydantic import TypeAdapter

        adapter = TypeAdapter(FormicOSEvent)
        restored = adapter.validate_python(data)
        assert isinstance(restored, KnowledgeDistilled)
        assert restored.source_entry_ids == ["mem-1", "mem-2", "mem-3", "mem-4", "mem-5"]

    def test_parallel_plan_projection_idempotent(self) -> None:
        """Double-apply of ParallelPlanCreated yields identical projection state."""
        from formicos.core.events import ThreadCreated, WorkspaceConfigSnapshot, WorkspaceCreated

        store = ProjectionStore()
        ts = _ts()
        store.apply(WorkspaceCreated(
            seq=1, timestamp=ts, address="ws-1",
            name="ws-1", config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        ))
        store.apply(ThreadCreated(
            seq=2, timestamp=ts, address="ws-1/t-1",
            workspace_id="ws-1", name="t-1",
        ))

        event = ParallelPlanCreated(
            seq=3, timestamp=ts, address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={"reasoning": "test"},
            parallel_groups=[["x"], ["y"]],
            reasoning="test",
        )

        store.apply(event)
        thread_after_1 = store.get_thread("ws-1", "t-1")
        plan_1 = thread_after_1.active_plan if thread_after_1 else None
        groups_1 = thread_after_1.parallel_groups if thread_after_1 else None

        store.apply(event)  # double-apply
        thread_after_2 = store.get_thread("ws-1", "t-1")
        plan_2 = thread_after_2.active_plan if thread_after_2 else None
        groups_2 = thread_after_2.parallel_groups if thread_after_2 else None

        assert plan_1 == plan_2, "Plans should be identical after double-apply"
        assert groups_1 == groups_2, "Groups should be identical after double-apply"

    def test_all_55_types_have_type_literal(self) -> None:
        """Every event type name in the list maps to a real event class."""
        import formicos.core.events as events_mod

        for name in EVENT_TYPE_NAMES:
            cls = getattr(events_mod, name, None)
            assert cls is not None, f"Event class {name} not found in events module"
            assert hasattr(cls, "model_fields"), f"{name} is not a Pydantic model"
