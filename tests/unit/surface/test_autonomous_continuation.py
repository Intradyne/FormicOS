"""Tests for Wave 72 Team B: Autonomous continuation engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from formicos.surface.action_queue import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_PENDING_REVIEW,
    append_action,
    create_action,
    read_actions,
)
from formicos.surface.continuation import (
    build_warm_start_cue,
    execute_idle_continuations,
    queue_continuation_proposals,
)

WS_ID = "ws-cont-test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dispatcher(
    *,
    autonomy_level: str = "suggest",
    daily_budget: float = 5.0,
    daily_spend: float = 0.0,
) -> MagicMock:
    """Build a mock MaintenanceDispatcher with configurable policy."""
    dispatcher = MagicMock()
    dispatcher._daily_spend = {WS_ID: daily_spend}
    dispatcher._runtime = MagicMock()
    dispatcher._runtime.spawn_colony = AsyncMock(return_value="colony-test-1")

    from formicos.core.types import AutonomyLevel, MaintenancePolicy

    policy = MaintenancePolicy(
        autonomy_level=AutonomyLevel(autonomy_level),
        daily_maintenance_budget=daily_budget,
    )
    dispatcher._get_policy = MagicMock(return_value=policy)
    return dispatcher


def _make_projections() -> MagicMock:
    return MagicMock()


def _make_summary(
    *,
    operator_active: bool = False,
    idle_for_minutes: int | None = 120,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "workspace_id": WS_ID,
        "pending_review_count": 0,
        "active_milestone_count": 0,
        "stalled_thread_count": 0,
        "last_operator_activity_at": None,
        "idle_for_minutes": idle_for_minutes,
        "operator_active": operator_active,
        "continuation_candidates": candidates or [],
        "sync_issues": [],
        "recent_progress": [],
    }


def _make_blast_radius(score: float = 0.2) -> Any:
    from formicos.surface.self_maintenance import BlastRadiusEstimate

    level = "low" if score < 0.3 else ("medium" if score < 0.6 else "high")
    rec = "proceed" if score < 0.3 else ("notify" if score < 0.6 else "escalate")
    return BlastRadiusEstimate(
        score=score, level=level, factors=[], recommendation=rec,
    )


# ---------------------------------------------------------------------------
# Test 1: queue_continuation_proposals
# ---------------------------------------------------------------------------


class TestQueueContinuationProposals:
    @pytest.mark.asyncio
    async def test_queues_proposals_for_candidates(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        projections = _make_projections()
        dispatcher = _make_dispatcher()
        candidates = [
            {
                "thread_id": "thread-abc",
                "description": "Thread abc: 2/5 steps done",
                "ready_for_autonomy": True,
                "blocked_reason": "",
                "priority": "high",
            },
        ]
        summary = _make_summary(candidates=candidates)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.15),
            ),
        ):
            count = await queue_continuation_proposals(
                data_dir, WS_ID, projections, dispatcher,
            )

        assert count == 1
        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 1
        assert actions[0]["kind"] == "continuation"
        assert actions[0]["thread_id"] == "thread-abc"
        assert actions[0]["status"] == STATUS_PENDING_REVIEW
        assert "suggested_colony" in actions[0]["payload"]

    @pytest.mark.asyncio
    async def test_skips_when_operator_active(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        summary = _make_summary(operator_active=True, candidates=[
            {"thread_id": "t1", "description": "x", "priority": "high",
             "ready_for_autonomy": True, "blocked_reason": ""},
        ])
        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            count = await queue_continuation_proposals(
                data_dir, WS_ID, _make_projections(), _make_dispatcher(),
            )
        assert count == 0
        assert read_actions(data_dir, WS_ID) == []

    @pytest.mark.asyncio
    async def test_deduplicates_by_thread_id(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        # Pre-seed a pending continuation for thread-abc
        existing = create_action(
            kind="continuation", title="Existing",
            thread_id="thread-abc",
        )
        append_action(data_dir, WS_ID, existing)

        candidates = [
            {"thread_id": "thread-abc", "description": "dup",
             "ready_for_autonomy": True, "blocked_reason": "", "priority": "high"},
            {"thread_id": "thread-xyz", "description": "new",
             "ready_for_autonomy": True, "blocked_reason": "", "priority": "medium"},
        ]
        summary = _make_summary(candidates=candidates)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.1),
            ),
        ):
            count = await queue_continuation_proposals(
                data_dir, WS_ID, _make_projections(), _make_dispatcher(),
            )

        assert count == 1  # Only thread-xyz queued
        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 2
        thread_ids = {a["thread_id"] for a in actions}
        assert thread_ids == {"thread-abc", "thread-xyz"}

    @pytest.mark.asyncio
    async def test_empty_data_dir_returns_zero(self) -> None:
        count = await queue_continuation_proposals(
            "", WS_ID, _make_projections(), _make_dispatcher(),
        )
        assert count == 0


# ---------------------------------------------------------------------------
# Test 2: execute_idle_continuations
# ---------------------------------------------------------------------------


class TestExecuteIdleContinuations:
    @pytest.mark.asyncio
    async def test_executes_approved_continuation(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(
            autonomy_level="autonomous", daily_budget=5.0,
        )

        # Create an approved continuation action
        action = create_action(
            kind="continuation",
            title="Continue thread work",
            thread_id="thread-exec",
            payload={
                "suggested_colony": {
                    "task": "Continue work",
                    "caste": "coder",
                    "strategy": "sequential",
                    "max_rounds": 3,
                },
            },
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=120)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.2),
            ),
            patch(
                "formicos.surface.continuation.append_journal_entry",
            ) as mock_journal,
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )

        assert executed == 1
        actions = read_actions(data_dir, WS_ID)
        assert actions[0]["status"] == STATUS_EXECUTED
        assert actions[0]["executed_at"] != ""
        dispatcher._runtime.spawn_colony.assert_called_once()
        mock_journal.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_when_not_autonomous(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="auto_notify")

        action = create_action(
            kind="continuation", title="X",
            payload={"suggested_colony": {"task": "X", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        executed = await execute_idle_continuations(
            data_dir, WS_ID, _make_projections(), dispatcher,
        )
        assert executed == 0

    @pytest.mark.asyncio
    async def test_blocks_when_operator_not_idle_enough(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="autonomous")

        action = create_action(
            kind="continuation", title="X",
            payload={"suggested_colony": {"task": "X", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=10)  # Below threshold

        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )
        assert executed == 0

    @pytest.mark.asyncio
    async def test_blocks_when_pending_review_exists(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="autonomous")

        # An approved continuation
        approved = create_action(
            kind="continuation", title="Ready",
            payload={"suggested_colony": {"task": "X", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        approved["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, approved)

        # A pending review action (different kind)
        pending = create_action(kind="maintenance", title="Needs review")
        append_action(data_dir, WS_ID, pending)

        summary = _make_summary(idle_for_minutes=120)

        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )
        assert executed == 0

    @pytest.mark.asyncio
    async def test_blocks_high_blast_radius(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="autonomous")

        action = create_action(
            kind="continuation", title="Risky",
            payload={"suggested_colony": {"task": "Risky", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=120)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.7),
            ),
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )
        assert executed == 0

    @pytest.mark.asyncio
    async def test_blocks_when_budget_exhausted(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(
            autonomy_level="autonomous", daily_budget=0.10, daily_spend=0.10,
        )

        action = create_action(
            kind="continuation", title="Costly",
            estimated_cost=0.36,
            payload={"suggested_colony": {"task": "X", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=120)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.1),
            ),
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )
        assert executed == 0

    @pytest.mark.asyncio
    async def test_journals_autonomous_continuation(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="autonomous")

        action = create_action(
            kind="continuation", title="Journal test",
            thread_id="t-journal",
            payload={"suggested_colony": {"task": "Work", "caste": "coder",
                                           "strategy": "sequential", "max_rounds": 3}},
        )
        action["status"] = STATUS_APPROVED
        append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=120)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.1),
            ),
            patch(
                "formicos.surface.continuation.append_journal_entry",
            ) as mock_journal,
        ):
            await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
            )

        mock_journal.assert_called_once()
        call_kwargs = mock_journal.call_args
        assert call_kwargs[1]["source"] == "continuation"
        assert "Auto-executed" in call_kwargs[1]["message"]

    @pytest.mark.asyncio
    async def test_max_per_sweep_limits_execution(self, tmp_path: Path) -> None:
        data_dir = str(tmp_path)
        dispatcher = _make_dispatcher(autonomy_level="autonomous")

        # Create 3 approved continuations
        for i in range(3):
            action = create_action(
                kind="continuation", title=f"Work {i}",
                thread_id=f"t-{i}",
                payload={"suggested_colony": {"task": f"Work {i}", "caste": "coder",
                                               "strategy": "sequential", "max_rounds": 3}},
            )
            action["status"] = STATUS_APPROVED
            append_action(data_dir, WS_ID, action)

        summary = _make_summary(idle_for_minutes=120)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.1),
            ),
            patch(
                "formicos.surface.continuation.append_journal_entry",
            ),
        ):
            executed = await execute_idle_continuations(
                data_dir, WS_ID, _make_projections(), dispatcher,
                max_per_sweep=1,
            )
        assert executed == 1  # Only 1 despite 3 available


# ---------------------------------------------------------------------------
# Test 3: build_warm_start_cue
# ---------------------------------------------------------------------------


class TestBuildWarmStartCue:
    def test_builds_cue_from_candidates(self, tmp_path: Path) -> None:
        projections = _make_projections()
        candidates = [
            {"thread_id": "t1", "description": "Thread t1: 2/5 done",
             "ready_for_autonomy": True, "blocked_reason": "", "priority": "high"},
            {"thread_id": "t2", "description": "Thread t2: 1 failed",
             "ready_for_autonomy": False, "blocked_reason": "prior failures",
             "priority": "medium"},
        ]
        summary = _make_summary(candidates=candidates)

        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            cue = build_warm_start_cue(
                str(tmp_path), WS_ID, projections,
            )

        assert "Continuation Opportunities" in cue
        assert "[READY]" in cue
        assert "[BLOCKED: prior failures]" in cue
        assert "Thread t1" in cue

    def test_empty_when_no_candidates(self, tmp_path: Path) -> None:
        summary = _make_summary(candidates=[])
        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            cue = build_warm_start_cue(
                str(tmp_path), WS_ID, _make_projections(),
            )
        assert cue == ""

    def test_empty_when_no_data_dir(self) -> None:
        cue = build_warm_start_cue("", WS_ID, _make_projections())
        assert cue == ""

    def test_caps_candidates(self, tmp_path: Path) -> None:
        candidates = [
            {"thread_id": f"t{i}", "description": f"Thread {i}",
             "ready_for_autonomy": True, "blocked_reason": "", "priority": "medium"}
            for i in range(10)
        ]
        summary = _make_summary(candidates=candidates)

        with patch(
            "formicos.surface.continuation.build_operations_summary",
            return_value=summary,
        ):
            cue = build_warm_start_cue(
                str(tmp_path), WS_ID, _make_projections(),
                max_candidates=3,
            )

        assert "+7 more" in cue


# ---------------------------------------------------------------------------
# Test 4: Integration — proposal flows through approve_action contract
# ---------------------------------------------------------------------------


class TestProposalApprovalIntegration:
    @pytest.mark.asyncio
    async def test_proposal_has_suggested_colony_for_approve_action(
        self, tmp_path: Path,
    ) -> None:
        """Verify that queued continuation actions carry suggested_colony
        so that approve_action() can dispatch them without a second mechanism.
        """
        data_dir = str(tmp_path)
        candidates = [
            {"thread_id": "t-int", "description": "Integration test thread",
             "ready_for_autonomy": True, "blocked_reason": "", "priority": "high"},
        ]
        summary = _make_summary(candidates=candidates)

        with (
            patch(
                "formicos.surface.continuation.build_operations_summary",
                return_value=summary,
            ),
            patch(
                "formicos.surface.continuation.estimate_blast_radius",
                return_value=_make_blast_radius(0.15),
            ),
        ):
            await queue_continuation_proposals(
                data_dir, WS_ID, _make_projections(), _make_dispatcher(),
            )

        actions = read_actions(data_dir, WS_ID)
        assert len(actions) == 1
        sc = actions[0]["payload"]["suggested_colony"]
        assert sc["caste"] == "coder"
        assert sc["strategy"] == "sequential"
        assert sc["max_rounds"] == 3
        assert sc["task"] == "Integration test thread"


# ---------------------------------------------------------------------------
# Test 5: Scheduler consolidation — proactive dispatch not in maintenance
# ---------------------------------------------------------------------------


class TestSchedulerConsolidation:
    """Verify app.py structural assertions via source inspection."""

    def test_maintenance_loop_does_not_call_proactive_dispatch(self) -> None:
        """Maintenance loop should only run consolidation services."""
        import inspect

        from formicos.surface import app

        source = inspect.getsource(app)
        # Find the maintenance loop function
        maint_start = source.find("async def _maintenance_loop")
        assert maint_start != -1, "_maintenance_loop not found"
        # Find the next function after it
        maint_end = source.find("_maint_task = asyncio.create_task", maint_start)
        assert maint_end != -1
        maint_body = source[maint_start:maint_end]
        assert "run_proactive_dispatch" not in maint_body, (
            "Proactive dispatch should not be in _maintenance_loop (Wave 72)"
        )

    def test_ops_sweep_calls_proactive_dispatch(self) -> None:
        """Operational sweep should include proactive dispatch."""
        import inspect

        from formicos.surface import app

        source = inspect.getsource(app)
        ops_start = source.find("async def _operational_sweep_loop")
        assert ops_start != -1
        ops_end = source.find("_ops_sweep_task = asyncio.create_task", ops_start)
        assert ops_end != -1
        ops_body = source[ops_start:ops_end]
        assert "run_proactive_dispatch" in ops_body
        assert "queue_continuation_proposals" in ops_body
        assert "execute_idle_continuations" in ops_body
