"""Operator behavior data collection tests (Wave 37, Pillar 4B).

Validates that operator signals are collected honestly from existing events:
- knowledge_feedback from MemoryConfidenceUpdated (colony-driven)
- ColonyKilled events
- directive usage from ColonyChatMessage metadata
- suggestion follow-through inferred from matching colony spawns

Honesty constraint: accepted suggestions are INFERRED from matching
colony spawns. Rejected suggestions are NOT tracked.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formicos.core.events import (
    ColonyChatMessage,
    ColonyCompleted,
    ColonyKilled,
    ColonySpawned,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    RoundCompleted,
    RoundStarted,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import CasteSlot
from formicos.surface.projections import ProjectionStore


def _now() -> datetime:
    return datetime.now(tz=UTC)


_seq = 0


def _next_seq() -> int:
    global _seq
    _seq += 1
    return _seq


def _make_workspace(store: ProjectionStore, ws_id: str = "test-ws") -> str:
    store.apply(WorkspaceCreated(
        seq=_next_seq(), timestamp=_now(), address=ws_id,
        name=ws_id,
        config=WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic"),
    ))
    return ws_id


def _make_entry(
    store: ProjectionStore,
    ws_id: str,
    entry_id: str,
    domains: list[str] | None = None,
    colony_id: str = "col-1",
) -> None:
    store.apply(MemoryEntryCreated(
        seq=_next_seq(), timestamp=_now(), address=ws_id,
        entry={
            "id": entry_id,
            "category": "skill",
            "sub_type": "technique",
            "title": f"Entry {entry_id}",
            "content": f"Content for {entry_id}",
            "domains": domains or ["python"],
            "status": "verified",
            "conf_alpha": 10.0,
            "conf_beta": 3.0,
            "workspace_id": ws_id,
            "source_colony_id": colony_id,
            "polarity": "positive",
            "created_at": _now().isoformat(),
        },
        workspace_id=ws_id,
    ))


def _spawn_colony(
    store: ProjectionStore,
    ws_id: str,
    colony_id: str = "colony-1",
    task: str = "Test task",
) -> str:
    address = f"{ws_id}/main/{colony_id}"
    store.apply(ColonySpawned(
        seq=_next_seq(), timestamp=_now(), address=address,
        thread_id="main", task=task,
        castes=[CasteSlot(caste="coder")],
        model_assignments={}, strategy="stigmergic",
        max_rounds=5, budget_limit=1.0,
    ))
    return colony_id


class TestOperatorFeedbackCollection:
    """Knowledge feedback signals from MemoryConfidenceUpdated events."""

    def test_colony_outcome_positive_feedback_recorded(self) -> None:
        """Positive colony outcome records positive feedback signal."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _make_entry(store, ws_id, "entry-1", domains=["python", "testing"])

        store.apply(MemoryConfidenceUpdated(
            seq=_next_seq(), timestamp=_now(), address=ws_id,
            entry_id="entry-1", colony_id="col-1",
            colony_succeeded=True, reason="colony_outcome",
            old_alpha=10.0, old_beta=3.0,
            new_alpha=11.0, new_beta=3.0, new_confidence=0.786,
            workspace_id=ws_id,
        ))

        ob = store.operator_behavior
        assert len(ob.feedback_records) == 1
        assert ob.feedback_records[0].direction == "positive"
        assert ob.feedback_records[0].entry_id == "entry-1"
        assert ob.feedback_by_domain["python"]["positive"] == 1
        assert ob.feedback_by_domain["testing"]["positive"] == 1

    def test_colony_outcome_negative_feedback_recorded(self) -> None:
        """Failed colony outcome records negative feedback signal."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _make_entry(store, ws_id, "entry-2", domains=["auth"])

        store.apply(MemoryConfidenceUpdated(
            seq=_next_seq(), timestamp=_now(), address=ws_id,
            entry_id="entry-2", colony_id="col-2",
            colony_succeeded=False, reason="colony_outcome",
            old_alpha=10.0, old_beta=3.0,
            new_alpha=10.0, new_beta=4.0, new_confidence=0.714,
            workspace_id=ws_id,
        ))

        ob = store.operator_behavior
        assert len(ob.feedback_records) == 1
        assert ob.feedback_records[0].direction == "negative"
        assert ob.feedback_by_domain["auth"]["negative"] == 1

    def test_archival_decay_not_recorded_as_feedback(self) -> None:
        """Archival decay updates are NOT counted as operator feedback."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _make_entry(store, ws_id, "entry-3")

        store.apply(MemoryConfidenceUpdated(
            seq=_next_seq(), timestamp=_now(), address=ws_id,
            entry_id="entry-3", colony_id="",
            colony_succeeded=True, reason="archival_decay",
            old_alpha=10.0, old_beta=3.0,
            new_alpha=9.8, new_beta=3.0, new_confidence=0.766,
            workspace_id=ws_id,
        ))

        assert len(store.operator_behavior.feedback_records) == 0

    def test_domain_demotion_rate(self) -> None:
        """Demotion rate correctly reflects negative feedback fraction."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _make_entry(store, ws_id, "e1", domains=["python"])
        _make_entry(store, ws_id, "e2", domains=["python"])
        _make_entry(store, ws_id, "e3", domains=["python"])

        # 2 positive, 1 negative
        for i, (entry_id, succeeded) in enumerate([
            ("e1", True), ("e2", True), ("e3", False),
        ]):
            store.apply(MemoryConfidenceUpdated(
                seq=_next_seq(), timestamp=_now(), address=ws_id,
                entry_id=entry_id, colony_id=f"col-{i}",
                colony_succeeded=succeeded, reason="colony_outcome",
                old_alpha=10.0, old_beta=3.0,
                new_alpha=11.0 if succeeded else 10.0,
                new_beta=3.0 if succeeded else 4.0,
                new_confidence=0.75, workspace_id=ws_id,
            ))

        rate = store.operator_behavior.domain_demotion_rate("python")
        assert rate == pytest.approx(1 / 3, abs=0.01)


class TestColonyKillCollection:
    """Colony kill signals from ColonyKilled events."""

    def test_kill_recorded(self) -> None:
        """ColonyKilled events are captured in operator behavior."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _spawn_colony(store, ws_id, "kill-colony", task="Bad task")

        store.apply(ColonyKilled(
            seq=_next_seq(), timestamp=_now(), address="kill-colony",
            colony_id="kill-colony", killed_by="operator",
        ))

        ob = store.operator_behavior
        assert len(ob.kill_records) == 1
        assert ob.kill_records[0].colony_id == "kill-colony"
        assert ob.kill_records[0].killed_by == "operator"
        assert ob.kills_by_strategy["stigmergic"] == 1


class TestDirectiveCollection:
    """Directive usage patterns from ColonyChatMessage events."""

    def test_operator_directive_recorded(self) -> None:
        """Operator directives with metadata are captured."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _spawn_colony(store, ws_id, "dir-colony")

        store.apply(ColonyChatMessage(
            seq=_next_seq(), timestamp=_now(), address="dir-colony",
            colony_id="dir-colony", workspace_id=ws_id,
            sender="operator", content="Focus on security",
            metadata={"directive_type": "priority_shift"},
        ))

        ob = store.operator_behavior
        assert len(ob.directive_records) == 1
        assert ob.directive_records[0].directive_type == "priority_shift"
        assert ob.directives_by_type["priority_shift"] == 1

    def test_non_operator_messages_not_captured(self) -> None:
        """Messages from non-operator senders are not directives."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _spawn_colony(store, ws_id, "msg-colony")

        store.apply(ColonyChatMessage(
            seq=_next_seq(), timestamp=_now(), address="msg-colony",
            colony_id="msg-colony", workspace_id=ws_id,
            sender="queen", content="Starting work",
            metadata={"directive_type": "context_update"},
        ))

        assert len(store.operator_behavior.directive_records) == 0

    def test_operator_message_without_directive_type_not_captured(self) -> None:
        """Operator messages without directive_type metadata are skipped."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)
        _spawn_colony(store, ws_id, "chat-colony")

        store.apply(ColonyChatMessage(
            seq=_next_seq(), timestamp=_now(), address="chat-colony",
            colony_id="chat-colony", workspace_id=ws_id,
            sender="operator", content="Hello colony",
        ))

        assert len(store.operator_behavior.directive_records) == 0


class TestSuggestionFollowThrough:
    """Inferred suggestion acceptance from matching colony spawns."""

    def test_matching_spawn_infers_acceptance(self) -> None:
        """Colony spawn matching a recent suggestion is recorded."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)

        # Simulate a recent suggestion
        store._recent_suggestions.append({
            "task": "Investigate contradiction between JWT and sessions",
            "category": "contradiction",
        })

        # Spawn a colony that matches
        _spawn_colony(
            store, ws_id, "resolve-col",
            task="Investigate contradiction between JWT and sessions auth",
        )

        ob = store.operator_behavior
        assert len(ob.suggestion_follow_throughs) == 1
        assert ob.suggestion_follow_throughs[0].insight_category == "contradiction"
        assert ob.suggestion_categories_acted_on["contradiction"] == 1
        # Suggestion should be consumed
        assert len(store._recent_suggestions) == 0

    def test_non_matching_spawn_does_not_infer(self) -> None:
        """Colony spawn not matching a suggestion is not recorded."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)

        store._recent_suggestions.append({
            "task": "Research Python API patterns coverage gap",
            "category": "coverage",
        })

        _spawn_colony(
            store, ws_id, "unrelated-col",
            task="Build email validator library",
        )

        assert len(store.operator_behavior.suggestion_follow_throughs) == 0
        assert len(store._recent_suggestions) == 1  # Not consumed

    def test_no_rejection_tracking(self) -> None:
        """Rejected suggestions are NOT tracked (honesty constraint)."""
        store = ProjectionStore()
        ob = store.operator_behavior

        # There's no mechanism for tracking rejections
        # This test documents the intentional constraint
        assert not hasattr(ob, "suggestion_rejections")
        assert not hasattr(ob, "rejected_suggestions")


class TestAggregateQueries:
    """Operator behavior projection can answer summary questions."""

    def test_multiple_signals_aggregate_correctly(self) -> None:
        """Multiple feedback signals accumulate per domain."""
        store = ProjectionStore()
        ws_id = _make_workspace(store)

        for i in range(5):
            _make_entry(
                store, ws_id, f"agg-{i}",
                domains=["python"], colony_id=f"col-{i}",
            )

        # 3 positive, 2 negative
        for i in range(5):
            store.apply(MemoryConfidenceUpdated(
                seq=_next_seq(), timestamp=_now(), address=ws_id,
                entry_id=f"agg-{i}", colony_id=f"col-{i}",
                colony_succeeded=i < 3, reason="colony_outcome",
                old_alpha=10.0, old_beta=3.0,
                new_alpha=11.0 if i < 3 else 10.0,
                new_beta=3.0 if i < 3 else 4.0,
                new_confidence=0.75, workspace_id=ws_id,
            ))

        ob = store.operator_behavior
        assert ob.feedback_by_domain["python"]["positive"] == 3
        assert ob.feedback_by_domain["python"]["negative"] == 2
        assert ob.domain_demotion_rate("python") == pytest.approx(0.4, abs=0.01)
        assert ob.domain_demotion_rate("unknown_domain") == 0.0
