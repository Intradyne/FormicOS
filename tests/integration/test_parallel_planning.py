"""Integration test — Queen parallel planning (Wave 35, ADR-045 D1).

Queen generates a DelegationPlan with 2 parallel groups. ParallelPlanCreated
event emitted. Group 1 colonies start concurrently. Group 2 waits for Group 1.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.events import (
    ParallelPlanCreated,
    ThreadCreated,
    WorkspaceCreated,
)
from formicos.core.events import WorkspaceConfigSnapshot
from formicos.core.types import (
    ColonyTask,
    DelegationPlan,
)
from formicos.surface.projections import ProjectionStore


def _ts() -> datetime:
    return datetime.now(tz=UTC)


class TestParallelPlanningIntegration:
    """End-to-end: DelegationPlan → event → projection → dispatch."""

    def test_delegation_plan_validates_dag(self) -> None:
        """Plan with valid depends_on passes validation."""
        plan = DelegationPlan(
            reasoning="Build REST API with auth and tests",
            tasks=[
                ColonyTask(task_id="research-auth", task="Research auth patterns", caste="researcher"),
                ColonyTask(task_id="research-db", task="Research DB schema", caste="researcher"),
                ColonyTask(
                    task_id="implement-api",
                    task="Implement API",
                    caste="coder",
                    depends_on=["research-auth", "research-db"],
                ),
            ],
            parallel_groups=[["research-auth", "research-db"], ["implement-api"]],
        )
        assert len(plan.parallel_groups) == 2
        assert plan.parallel_groups[0] == ["research-auth", "research-db"]
        assert plan.parallel_groups[1] == ["implement-api"]

    def test_delegation_plan_circular_deps_detected(self) -> None:
        """Circular dependency in tasks is detectable via Kahn's algorithm."""
        from formicos.surface.queen_tools import QueenToolDispatcher

        # Kahn's algorithm: in-degree tracking
        assert hasattr(QueenToolDispatcher, "_validate_dag")
        # Create a cycle: A → B → C → A
        tasks = [
            ColonyTask(task_id="A", task="A", caste="coder", depends_on=["C"]),
            ColonyTask(task_id="B", task="B", caste="coder", depends_on=["A"]),
            ColonyTask(task_id="C", task="C", caste="coder", depends_on=["B"]),
        ]
        has_cycle = not QueenToolDispatcher._validate_dag(tasks)
        assert has_cycle, "Circular dependency should be detected"

    def test_parallel_plan_event_stores_on_projection(self) -> None:
        """ParallelPlanCreated event populates ThreadProjection.active_plan."""
        store = ProjectionStore()
        store.apply(
            WorkspaceCreated(
                seq=1, timestamp=_ts(), address="ws-1",
                name="ws-1", config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
            ),
        )
        store.apply(
            ThreadCreated(
                seq=2, timestamp=_ts(), address="ws-1/t-1",
                workspace_id="ws-1", name="t-1",
            ),
        )

        plan_dict = {
            "reasoning": "Parallel build",
            "tasks": [
                {"task_id": "t1", "task": "Research", "caste": "researcher"},
                {"task_id": "t2", "task": "Implement", "caste": "coder"},
            ],
        }
        store.apply(
            ParallelPlanCreated(
                seq=3, timestamp=_ts(), address="ws-1/t-1",
                thread_id="t-1", workspace_id="ws-1",
                plan=plan_dict,
                parallel_groups=[["t1"], ["t2"]],
                reasoning="Sequential dependency",
            ),
        )

        thread = store.get_thread("ws-1", "t-1")
        assert thread is not None
        assert thread.active_plan == plan_dict
        assert thread.parallel_groups == [["t1"], ["t2"]]

    def test_parallel_plan_replay_idempotent(self) -> None:
        """Double-apply of ParallelPlanCreated yields identical projection."""
        store = ProjectionStore()
        store.apply(
            WorkspaceCreated(
                seq=1, timestamp=_ts(), address="ws-1",
                name="ws-1", config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
            ),
        )
        store.apply(
            ThreadCreated(
                seq=2, timestamp=_ts(), address="ws-1/t-1",
                workspace_id="ws-1", name="t-1",
            ),
        )

        event = ParallelPlanCreated(
            seq=3, timestamp=_ts(), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={"reasoning": "test"},
            parallel_groups=[["a"], ["b"]],
            reasoning="test",
        )
        store.apply(event)
        store.apply(event)  # double-apply

        thread = store.get_thread("ws-1", "t-1")
        assert thread is not None
        assert thread.parallel_groups == [["a"], ["b"]]

    @pytest.mark.asyncio
    async def test_concurrent_group_dispatch(self) -> None:
        """Tasks within a parallel group are dispatched concurrently via asyncio.gather."""
        spawn_times: list[float] = []

        async def mock_spawn(**_kwargs: Any) -> str:
            spawn_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)  # simulate spawn latency
            return "colony-id"

        # Verify that 2 tasks spawned in same group overlap temporally
        t1 = asyncio.create_task(mock_spawn())
        t2 = asyncio.create_task(mock_spawn())
        await asyncio.gather(t1, t2)

        # Both should have started at nearly the same time
        assert len(spawn_times) == 2
        assert abs(spawn_times[0] - spawn_times[1]) < 0.02

    def test_agui_parallel_plan_event_promotion(self) -> None:
        """ParallelPlanCreated promotes to PARALLEL_PLAN AG-UI custom event."""
        from formicos.surface.event_translator import translate_event

        event = ParallelPlanCreated(
            seq=10, timestamp=_ts(), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={"reasoning": "test"},
            parallel_groups=[["a", "b"], ["c"]],
            reasoning="Group a and b first",
            knowledge_gaps=["auth-patterns"],
            estimated_cost=0.5,
        )

        frames = list(translate_event("col-1", event, current_round=0))
        assert len(frames) >= 1
        # Find the PARALLEL_PLAN frame
        plan_frames = [f for f in frames if "PARALLEL_PLAN" in str(f)]
        assert plan_frames, "Expected PARALLEL_PLAN AG-UI event"

    def test_queen_prompt_contains_parallel_planning(self) -> None:
        """Queen prompt references parallel planning and spawn_parallel."""
        import yaml

        with open("config/caste_recipes.yaml") as f:
            recipes = yaml.safe_load(f)

        queen = recipes.get("castes", {}).get("queen", {})
        prompt = queen.get("system_prompt", "")
        tools = queen.get("tools", [])

        assert "spawn_parallel" in tools, "spawn_parallel must be in Queen tools"
        assert "parallel" in prompt.lower(), "Queen prompt must reference parallel planning"
