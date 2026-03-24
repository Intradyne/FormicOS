"""Unit tests for formicos.surface.view_models."""

from __future__ import annotations

from datetime import UTC, datetime

from formicos.core.events import (
    ApprovalRequested,
    ColonySpawned,
    RoundCompleted,
    RoundStarted,
    ThreadCreated,
    WorkspaceConfigSnapshot,
    WorkspaceCreated,
)
from formicos.core.types import CasteSlot
from formicos.surface.projections import ProjectionStore
from formicos.surface.view_models import (
    approval_queue,
    colony_detail,
    round_history,
    workspace_colonies,
)

NOW = datetime.now(UTC)
ENVELOPE = {"timestamp": NOW}


def _seed_store() -> ProjectionStore:
    """Create a ProjectionStore with a workspace, thread, colony, and round."""
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, address="ws1", name="ws1",
        config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        **ENVELOPE,
    ))
    store.apply(ThreadCreated(
        seq=2, address="ws1/t1", workspace_id="ws1", name="t1", **ENVELOPE,
    ))
    store.apply(ColonySpawned(
        seq=3, address="ws1/t1/c1", thread_id="t1",
        task="test task", castes=[CasteSlot(caste="coder"), CasteSlot(caste="reviewer")],
        model_assignments={"coder": "anthropic/claude-sonnet-4.6"},
        strategy="stigmergic", max_rounds=10, budget_limit=5.0,
        **ENVELOPE,
    ))
    store.apply(RoundStarted(
        seq=4, address="ws1/t1/c1", colony_id="c1", round_number=1, **ENVELOPE,
    ))
    store.apply(RoundCompleted(
        seq=5, address="ws1/t1/c1", colony_id="c1",
        round_number=1, convergence=0.75, cost=0.12, duration_ms=1500,
        **ENVELOPE,
    ))
    return store


class TestColonyDetail:
    def test_returns_none_for_missing_colony(self) -> None:
        store = ProjectionStore()
        assert colony_detail(store, "nonexistent") is None

    def test_returns_colony_fields(self) -> None:
        store = _seed_store()
        detail = colony_detail(store, "c1")
        assert detail is not None
        assert detail["id"] == "c1"
        assert detail["task"] == "test task"
        assert detail["status"] == "running"
        assert detail["maxRounds"] == 10
        assert detail["budgetLimit"] == 5.0
        assert detail["convergence"] == 0.75

    def test_includes_round_records(self) -> None:
        store = _seed_store()
        detail = colony_detail(store, "c1")
        assert detail is not None
        assert len(detail["rounds"]) == 1
        assert detail["rounds"][0]["roundNumber"] == 1
        assert detail["rounds"][0]["convergence"] == 0.75


class TestApprovalQueue:
    def test_empty_when_no_approvals(self) -> None:
        store = ProjectionStore()
        assert approval_queue(store) == []

    def test_returns_pending_approvals(self) -> None:
        store = _seed_store()
        store.apply(ApprovalRequested(
            seq=10, address="ws1/t1/c1",
            request_id="apr-1", approval_type="budget_increase",
            detail="Colony exceeded budget", colony_id="c1",
            **ENVELOPE,
        ))
        queue = approval_queue(store)
        assert len(queue) == 1
        assert queue[0]["id"] == "apr-1"
        assert queue[0]["type"] == "budget_increase"
        assert queue[0]["colonyId"] == "c1"


class TestRoundHistory:
    def test_empty_for_missing_colony(self) -> None:
        store = ProjectionStore()
        assert round_history(store, "nonexistent") == []

    def test_returns_rounds(self) -> None:
        store = _seed_store()
        history = round_history(store, "c1")
        assert len(history) == 1
        assert history[0]["roundNumber"] == 1
        assert history[0]["cost"] == 0.12
        assert history[0]["durationMs"] == 1500


class TestWorkspaceColonies:
    def test_empty_for_unknown_workspace(self) -> None:
        store = ProjectionStore()
        assert workspace_colonies(store, "unknown") == []

    def test_returns_colony_summaries(self) -> None:
        store = _seed_store()
        colonies = workspace_colonies(store, "ws1")
        assert len(colonies) == 1
        assert colonies[0]["id"] == "c1"
        assert colonies[0]["status"] == "running"
