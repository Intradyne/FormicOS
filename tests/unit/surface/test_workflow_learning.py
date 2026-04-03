"""Tests for workflow_learning — Track 8 (patterns) and Track 9 (procedures)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from formicos.surface.workflow_learning import (
    _MIN_BEHAVIOR_COUNT,
    _MIN_DISTINCT_THREADS,
    _MIN_SUCCESS_COUNT,
    detect_operator_patterns,
    extract_workflow_patterns,
)


@pytest.fixture()
def data_dir(tmp_path: Path) -> str:
    return str(tmp_path)


WS = "ws-test"


def _outcome(
    *,
    succeeded: bool = True,
    strategy: str = "stigmergic",
    castes: dict[str, int] | None = None,
    total_cost: float = 0.01,
    thread_id: str = "",
    colony_id: str = "col-1",
) -> dict[str, Any]:
    return {
        "succeeded": succeeded,
        "strategy": strategy,
        "caste_composition": castes or {"coder": 1},
        "total_cost": total_cost,
        "thread_id": thread_id,
        "colony_id": colony_id,
    }


# ── Track 8: Workflow pattern recognition ──


class TestExtractWorkflowPatterns:
    async def test_no_outcomes_returns_empty(self, data_dir: str) -> None:
        assert await extract_workflow_patterns(data_dir, WS, []) == []

    async def test_below_threshold_returns_empty(self, data_dir: str) -> None:
        outcomes = [
            _outcome(thread_id="t1"),
            _outcome(thread_id="t2"),
        ]
        assert len(outcomes) < _MIN_SUCCESS_COUNT
        assert await extract_workflow_patterns(data_dir, WS, outcomes) == []

    async def test_single_thread_returns_empty(self, data_dir: str) -> None:
        """Even with enough count, need distinct threads."""
        outcomes = [
            _outcome(thread_id="t1") for _ in range(_MIN_SUCCESS_COUNT)
        ]
        assert await extract_workflow_patterns(data_dir, WS, outcomes) == []

    async def test_successful_pattern_proposed(self, data_dir: str) -> None:
        outcomes = []
        for i in range(_MIN_SUCCESS_COUNT):
            tid = f"t{i % _MIN_DISTINCT_THREADS}"
            outcomes.append(_outcome(thread_id=tid, colony_id=f"col-{i}"))

        proposals = await extract_workflow_patterns(data_dir, WS, outcomes)
        assert len(proposals) == 1
        p = proposals[0]
        assert p["kind"] == "workflow_template"
        assert p["payload"]["strategy"] == "stigmergic"
        assert "coder" in p["payload"]["castes"]

    async def test_failed_outcomes_ignored(self, data_dir: str) -> None:
        outcomes = [
            _outcome(succeeded=False, thread_id=f"t{i % 2}", colony_id=f"col-{i}")
            for i in range(_MIN_SUCCESS_COUNT + 1)
        ]
        assert await extract_workflow_patterns(data_dir, WS, outcomes) == []

    async def test_deduplicates_against_existing_templates(self, data_dir: str) -> None:
        outcomes = [
            _outcome(thread_id=f"t{i % _MIN_DISTINCT_THREADS}", colony_id=f"col-{i}")
            for i in range(_MIN_SUCCESS_COUNT)
        ]

        class FakeTemplate:
            strategy = "stigmergic"
            castes = ["coder"]

        templates = [FakeTemplate()]
        proposals = await extract_workflow_patterns(
            data_dir, WS, outcomes, existing_templates=templates,
        )
        assert proposals == []

    async def test_deduplicates_against_pending_actions(self, data_dir: str) -> None:
        # First call creates the proposal
        outcomes = [
            _outcome(thread_id=f"t{i % _MIN_DISTINCT_THREADS}", colony_id=f"col-{i}")
            for i in range(_MIN_SUCCESS_COUNT)
        ]
        first = await extract_workflow_patterns(data_dir, WS, outcomes)
        assert len(first) == 1

        # Second call with same data should not duplicate
        second = await extract_workflow_patterns(data_dir, WS, outcomes)
        assert second == []

    async def test_empty_data_dir_returns_empty(self) -> None:
        assert await extract_workflow_patterns("", WS, [_outcome()]) == []

    async def test_empty_workspace_returns_empty(self, data_dir: str) -> None:
        assert await extract_workflow_patterns(data_dir, "", [_outcome()]) == []

    async def test_multiple_distinct_patterns(self, data_dir: str) -> None:
        outcomes = []
        for i in range(_MIN_SUCCESS_COUNT):
            tid = f"t{i % _MIN_DISTINCT_THREADS}"
            outcomes.append(_outcome(
                strategy="stigmergic", castes={"coder": 1},
                thread_id=tid, colony_id=f"a-{i}",
            ))
            outcomes.append(_outcome(
                strategy="sequential", castes={"researcher": 1},
                thread_id=tid, colony_id=f"b-{i}",
            ))

        proposals = await extract_workflow_patterns(data_dir, WS, outcomes)
        assert len(proposals) == 2
        kinds = {p["payload"]["strategy"] for p in proposals}
        assert kinds == {"stigmergic", "sequential"}


# ── Track 9: Procedure suggestions ──


def _action(
    *,
    kind: str = "maintenance",
    status: str = "rejected",
    source_category: str = "proactive_intelligence",
) -> dict[str, Any]:
    return {
        "action_id": "act-1",
        "kind": kind,
        "status": status,
        "source_category": source_category,
        "payload": {},
    }


class TestDetectOperatorPatterns:
    async def test_no_actions_returns_empty(self, data_dir: str) -> None:
        assert await detect_operator_patterns(data_dir, WS, actions=[]) == []

    async def test_below_threshold_returns_empty(self, data_dir: str) -> None:
        actions = [_action() for _ in range(_MIN_BEHAVIOR_COUNT - 1)]
        assert await detect_operator_patterns(data_dir, WS, actions=actions) == []

    async def test_rejection_pattern_proposed(self, data_dir: str) -> None:
        actions = [
            _action(status="rejected", source_category="health_check")
            for _ in range(_MIN_BEHAVIOR_COUNT)
        ]
        proposals = await detect_operator_patterns(data_dir, WS, actions=actions)
        assert len(proposals) == 1
        p = proposals[0]
        assert p["kind"] == "procedure_suggestion"
        assert p["payload"]["pattern_type"] == "rejection"
        assert p["payload"]["category"] == "health_check"

    async def test_review_pattern_proposed(self, data_dir: str) -> None:
        actions = [
            _action(kind="maintenance", status="approved", source_category="stale_sweep")
            for _ in range(_MIN_BEHAVIOR_COUNT)
        ]
        proposals = await detect_operator_patterns(data_dir, WS, actions=actions)
        assert len(proposals) == 1
        p = proposals[0]
        assert p["kind"] == "procedure_suggestion"
        assert p["payload"]["pattern_type"] == "review"

    async def test_deduplicates_pending_suggestions(self, data_dir: str) -> None:
        actions = [
            _action(status="rejected", source_category="health_check")
            for _ in range(_MIN_BEHAVIOR_COUNT)
        ]
        first = await detect_operator_patterns(data_dir, WS, actions=actions)
        assert len(first) == 1

        # Simulate the pending suggestion by including it in actions
        pending = first[0]
        pending["status"] = "pending_review"
        actions.append(pending)
        second = await detect_operator_patterns(data_dir, WS, actions=actions)
        assert second == []

    async def test_empty_guards(self) -> None:
        assert await detect_operator_patterns("", WS) == []
        assert await detect_operator_patterns("/tmp", "") == []
