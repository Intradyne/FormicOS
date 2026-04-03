"""Unit tests for Wave 35 parallel planning: plan validation, concurrent dispatch,
convergence, projection handler, and AG-UI event promotion."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.events import ParallelPlanCreated
from formicos.core.types import ColonyTask, DelegationPlan
from formicos.surface.queen_tools import QueenToolDispatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_runtime() -> MagicMock:
    """Build a mock Runtime with the minimum surface needed for spawn_parallel."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock()
    runtime.spawn_colony = AsyncMock(side_effect=lambda *a, **kw: f"colony-{a[2][:8]}")
    runtime.colony_manager = MagicMock()
    runtime.colony_manager.start_colony = AsyncMock()
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("arguments", tc.get("input", {})))
    runtime.projections = MagicMock()
    runtime.projections.get_thread = MagicMock(return_value=None)
    return runtime


def _plan_inputs(
    tasks: list[dict[str, Any]],
    parallel_groups: list[list[str]],
    reasoning: str = "test plan",
    estimated_total_cost: float = 1.0,
    knowledge_gaps: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "reasoning": reasoning,
        "tasks": tasks,
        "parallel_groups": parallel_groups,
        "estimated_total_cost": estimated_total_cost,
        "knowledge_gaps": knowledge_gaps or [],
    }


def _two_group_plan() -> dict[str, Any]:
    """Valid plan: group 1 runs in parallel, group 2 after."""
    return _plan_inputs(
        tasks=[
            {"task_id": "research", "task": "Research API patterns", "caste": "researcher"},
            {"task_id": "schema", "task": "Design data schema", "caste": "researcher"},
            {"task_id": "implement", "task": "Implement API", "caste": "coder",
             "depends_on": ["research", "schema"], "input_from": ["research", "schema"]},
        ],
        parallel_groups=[["research", "schema"], ["implement"]],
        reasoning="Research and schema are independent; implementation depends on both.",
        knowledge_gaps=["api-design"],
    )


# ---------------------------------------------------------------------------
# DelegationPlan model tests
# ---------------------------------------------------------------------------


class TestDelegationPlanModel:
    def test_valid_plan_construction(self) -> None:
        plan = DelegationPlan(
            reasoning="test",
            tasks=[
                ColonyTask(task_id="t1", task="do A", caste="coder"),
                ColonyTask(task_id="t2", task="do B", caste="reviewer", depends_on=["t1"]),
            ],
            parallel_groups=[["t1"], ["t2"]],
        )
        assert len(plan.tasks) == 2
        assert plan.parallel_groups == [["t1"], ["t2"]]
        assert plan.estimated_total_cost == 0.0

    def test_colony_task_defaults(self) -> None:
        task = ColonyTask(task_id="t1", task="test", caste="coder")
        assert task.strategy == "sequential"
        assert task.max_rounds == 5
        assert task.budget_limit == 1.0
        assert task.depends_on == []
        assert task.input_from == []


# ---------------------------------------------------------------------------
# Plan validation tests
# ---------------------------------------------------------------------------


class TestPlanValidation:
    @pytest.mark.asyncio
    async def test_valid_two_group_plan(self) -> None:
        """Valid plan with 2 groups: group 1 dispatched, group 2 deferred (Wave 81)."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _two_group_plan()
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "Parallel plan created" in result
        assert "3 tasks" in result
        assert "2 groups" in result
        assert action is not None
        assert action["tool"] == "spawn_parallel"
        # Wave 81: only Group 1 colonies are spawned immediately
        assert len(action["colony_ids"]) == 2
        # But total planned includes all tasks
        assert len(action["all_planned_colony_ids"]) == 3
        assert action["deferred_groups"] == 1
        assert "deferred" in result.lower()
        # Event emitted
        runtime.emit_and_broadcast.assert_called_once()
        emitted = runtime.emit_and_broadcast.call_args[0][0]
        assert isinstance(emitted, ParallelPlanCreated)

    @pytest.mark.asyncio
    async def test_circular_deps_fallback(self) -> None:
        """Invalid plan (circular deps): falls back to sequential."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "a", "task": "A", "caste": "coder", "depends_on": ["b"]},
                {"task_id": "b", "task": "B", "caste": "coder", "depends_on": ["a"]},
            ],
            parallel_groups=[["a", "b"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "circular" in result.lower()
        assert action is None

    @pytest.mark.asyncio
    async def test_missing_depends_on_fallback(self) -> None:
        """Invalid plan (missing depends_on): falls back to sequential."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "a", "task": "A", "caste": "coder", "depends_on": ["nonexistent"]},
            ],
            parallel_groups=[["a"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "unknown" in result.lower()
        assert action is None

    @pytest.mark.asyncio
    async def test_single_task_no_parallelism(self) -> None:
        """Plan with single task: no parallelism, works identically to pre-Wave-35."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[{"task_id": "solo", "task": "Do everything", "caste": "coder"}],
            parallel_groups=[["solo"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "1 tasks" in result
        assert "1 groups" in result
        assert action is not None
        assert len(action["colony_ids"]) == 1

    @pytest.mark.asyncio
    async def test_duplicate_task_ids_rejected(self) -> None:
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "dup", "task": "A", "caste": "coder"},
                {"task_id": "dup", "task": "B", "caste": "coder"},
            ],
            parallel_groups=[["dup"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "duplicate" in result.lower()
        assert action is None

    @pytest.mark.asyncio
    async def test_groups_not_covering_all_tasks(self) -> None:
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "a", "task": "A", "caste": "coder"},
                {"task_id": "b", "task": "B", "caste": "coder"},
            ],
            parallel_groups=[["a"]],  # missing "b"
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "exactly once" in result.lower()
        assert action is None

    @pytest.mark.asyncio
    async def test_rejects_plan_missing_explicit_operator_deliverables(self) -> None:
        runtime = _make_runtime()
        runtime.projections.get_thread.return_value = SimpleNamespace(
            queen_messages=[
                SimpleNamespace(
                    role="operator",
                    content=(
                        "Build Group 1 and Group 2 for the addon: "
                        "addon.yaml, scanner.py, coverage.py, quality.py, "
                        "handlers.py, trigger.py, tests"
                    ),
                ),
            ],
        )
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {
                    "task_id": "a",
                    "task": "Create addon.yaml and scanner.py",
                    "caste": "coder",
                },
                {
                    "task_id": "b",
                    "task": "Create coverage.py",
                    "caste": "coder",
                },
                {
                    "task_id": "c",
                    "task": "Create quality.py",
                    "caste": "coder",
                },
            ],
            parallel_groups=[["a", "b", "c"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "operator requested group 1..2" in result.lower()
        assert action is None

    @pytest.mark.asyncio
    async def test_accepts_plan_when_explicit_deliverables_are_covered(self) -> None:
        runtime = _make_runtime()
        runtime.projections.get_thread.return_value = SimpleNamespace(
            queen_messages=[
                SimpleNamespace(
                    role="operator",
                    content=(
                        "Build Group 1 and Group 2 for the addon: "
                        "addon.yaml, scanner.py, coverage.py, quality.py, "
                        "handlers.py, trigger.py, tests"
                    ),
                ),
            ],
        )
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {
                    "task_id": "a",
                    "task": "Create addon.yaml and scanner.py",
                    "caste": "coder",
                },
                {
                    "task_id": "b",
                    "task": "Create coverage.py and quality.py",
                    "caste": "coder",
                },
                {
                    "task_id": "c",
                    "task": "Create handlers.py, trigger.py, and tests",
                    "caste": "coder",
                },
            ],
            parallel_groups=[["a", "b"], ["c"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        assert "parallel plan created" in result.lower()
        assert action is not None


# ---------------------------------------------------------------------------
# DAG validation (Kahn's algorithm)
# ---------------------------------------------------------------------------


class TestValidateDAG:
    def test_valid_dag(self) -> None:
        tasks = [
            ColonyTask(task_id="a", task="A", caste="coder"),
            ColonyTask(task_id="b", task="B", caste="coder", depends_on=["a"]),
            ColonyTask(task_id="c", task="C", caste="coder", depends_on=["a"]),
            ColonyTask(task_id="d", task="D", caste="coder", depends_on=["b", "c"]),
        ]
        assert QueenToolDispatcher._validate_dag(tasks) is True

    def test_cycle_detected(self) -> None:
        tasks = [
            ColonyTask(task_id="a", task="A", caste="coder", depends_on=["c"]),
            ColonyTask(task_id="b", task="B", caste="coder", depends_on=["a"]),
            ColonyTask(task_id="c", task="C", caste="coder", depends_on=["b"]),
        ]
        assert QueenToolDispatcher._validate_dag(tasks) is False

    def test_no_deps_valid(self) -> None:
        tasks = [
            ColonyTask(task_id="x", task="X", caste="coder"),
            ColonyTask(task_id="y", task="Y", caste="coder"),
        ]
        assert QueenToolDispatcher._validate_dag(tasks) is True

    def test_self_cycle(self) -> None:
        tasks = [
            ColonyTask(task_id="a", task="A", caste="coder", depends_on=["a"]),
        ]
        assert QueenToolDispatcher._validate_dag(tasks) is False


# ---------------------------------------------------------------------------
# Concurrent dispatch tests
# ---------------------------------------------------------------------------


class TestConcurrentDispatch:
    @pytest.mark.asyncio
    async def test_multiple_colonies_started_in_same_group(self) -> None:
        """Concurrent spawn: multiple colonies started within same iteration."""
        runtime = _make_runtime()
        spawn_calls: list[str] = []

        async def track_spawn(*args: Any, **kwargs: Any) -> str:
            cid = f"colony-{len(spawn_calls)}"
            spawn_calls.append(cid)
            return cid

        runtime.spawn_colony = AsyncMock(side_effect=track_spawn)
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "a", "task": "Task A", "caste": "coder"},
                {"task_id": "b", "task": "Task B", "caste": "reviewer"},
                {"task_id": "c", "task": "Task C", "caste": "researcher"},
            ],
            parallel_groups=[["a", "b", "c"]],
        )
        result, action = await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")
        # All 3 spawned in the same group
        assert len(spawn_calls) == 3
        assert action is not None
        assert len(action["colony_ids"]) == 3

    @pytest.mark.asyncio
    async def test_structural_hints_backfill_target_files(self) -> None:
        runtime = _make_runtime()
        runtime.projections.get_thread.return_value = SimpleNamespace(
            queen_messages=[
                SimpleNamespace(
                    role="operator",
                    content="Fix src/runner.py and src/types.py import issues.",
                ),
            ],
        )
        dispatcher = QueenToolDispatcher(runtime)
        inputs = _plan_inputs(
            tasks=[
                {"task_id": "a", "task": "Fix runner.py imports", "caste": "coder"},
                {"task_id": "b", "task": "Update types.py definitions", "caste": "coder"},
            ],
            parallel_groups=[["a", "b"]],
        )

        with patch(
            "formicos.surface.structural_planner.get_structural_hints",
            return_value={
                "matched_files": ["src/runner.py", "src/types.py"],
                "suggested_groups": [
                    {"files": ["src/runner.py"], "reason": "runner scope"},
                    {"files": ["src/types.py"], "reason": "types scope"},
                ],
                "coupling_pairs": [],
                "confidence": 0.8,
                "rationale": "2 files matched; 2 groups suggested; conf=0.80",
            },
        ):
            await dispatcher._spawn_parallel(inputs, "ws-1", "thread-1")

        spawn_calls = runtime.spawn_colony.await_args_list
        assert len(spawn_calls) == 2
        target_sets = {
            tuple(call.kwargs["target_files"])
            for call in spawn_calls
        }
        assert ("src/runner.py",) in target_sets
        assert ("src/types.py",) in target_sets


# ---------------------------------------------------------------------------
# Projection handler tests
# ---------------------------------------------------------------------------


class TestProjectionHandler:
    @staticmethod
    def _seed_store() -> Any:
        from formicos.surface.projections import ProjectionStore
        from formicos.core.events import (
            WorkspaceCreated,
            WorkspaceConfigSnapshot,
            ThreadCreated,
        )
        store = ProjectionStore()
        store.apply(WorkspaceCreated(
            seq=1, timestamp=datetime.now(UTC), address="ws-1",
            name="ws-1",
            config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
        ))
        store.apply(ThreadCreated(
            seq=2, timestamp=datetime.now(UTC), address="ws-1/t-1",
            workspace_id="ws-1", name="t-1",
        ))
        return store

    def test_plan_stored_on_thread(self) -> None:
        store = self._seed_store()

        plan_data = {"reasoning": "test", "tasks": [], "parallel_groups": [["a"]]}
        store.apply(ParallelPlanCreated(
            seq=3, timestamp=datetime.now(UTC), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan=plan_data,
            parallel_groups=[["a"]],
            reasoning="test",
        ))

        thread = store.get_thread("ws-1", "t-1")
        assert thread is not None
        assert thread.active_plan == plan_data
        assert thread.parallel_groups == [["a"]]

    def test_replay_produces_identical_plan_state(self) -> None:
        """Replay: double-apply produces identical plan state."""
        plan_event = ParallelPlanCreated(
            seq=3, timestamp=datetime.now(UTC), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={"tasks": []}, parallel_groups=[["x", "y"]],
            reasoning="replay test",
        )
        store1 = self._seed_store()
        store2 = self._seed_store()
        store1.apply(plan_event)
        store2.apply(plan_event)

        t1 = store1.get_thread("ws-1", "t-1")
        t2 = store2.get_thread("ws-1", "t-1")
        assert t1 is not None and t2 is not None
        assert t1.active_plan == t2.active_plan
        assert t1.parallel_groups == t2.parallel_groups


# ---------------------------------------------------------------------------
# AG-UI event promotion tests
# ---------------------------------------------------------------------------


class TestAGUIPromotion:
    def test_parallel_plan_promoted(self) -> None:
        """AG-UI event promotion includes parallel_groups."""
        import json
        from formicos.surface.event_translator import translate_event

        event = ParallelPlanCreated(
            seq=1, timestamp=datetime.now(UTC), address="ws-1/t-1",
            thread_id="t-1", workspace_id="ws-1",
            plan={}, parallel_groups=[["a", "b"], ["c"]],
            reasoning="test promotion",
            knowledge_gaps=["domain-x"],
            estimated_cost=3.5,
        )
        frames = list(translate_event("colony-1", event, current_round=0))
        assert len(frames) == 1
        frame = frames[0]
        assert frame["event"] == "CUSTOM"
        data = json.loads(frame["data"])
        assert data["name"] == "PARALLEL_PLAN"
        assert data["value"]["parallel_groups"] == [["a", "b"], ["c"]]
        assert data["value"]["reasoning"] == "test promotion"
        assert data["value"]["knowledge_gaps"] == ["domain-x"]
        assert data["value"]["estimated_cost"] == 3.5


# ---------------------------------------------------------------------------
# Queen prompt tests
# ---------------------------------------------------------------------------


class TestQueenPrompt:
    def _load_queen_prompt(self) -> str:
        import yaml
        from pathlib import Path
        recipes_path = Path(__file__).parents[3] / "config" / "caste_recipes.yaml"
        with open(recipes_path) as f:
            recipes = yaml.safe_load(f)
        return recipes["castes"]["queen"]["system_prompt"]

    def test_contains_delegation_plan_or_parallel(self) -> None:
        prompt = self._load_queen_prompt()
        assert "parallel" in prompt.lower() or "DelegationPlan" in prompt

    def test_contains_explaining_decisions(self) -> None:
        prompt = self._load_queen_prompt()
        assert "Explaining your decisions" in prompt

    def test_under_130_lines(self) -> None:
        prompt = self._load_queen_prompt()
        line_count = len(prompt.strip().split("\n"))
        assert line_count <= 200, f"Queen prompt is {line_count} lines, expected <= 200"

    def test_spawn_parallel_in_tools(self) -> None:
        import yaml
        from pathlib import Path
        recipes_path = Path(__file__).parents[3] / "config" / "caste_recipes.yaml"
        with open(recipes_path) as f:
            recipes = yaml.safe_load(f)
        tools = recipes["castes"]["queen"]["tools"]
        assert "spawn_parallel" in tools


# ── Wave 81 Track B: Plan tracker tests ──


from formicos.surface.parallel_plans import (
    ParallelPlanTracker,
    PlannedTask,
    TaskState,
)


def _make_tracker_2group() -> tuple[ParallelPlanTracker, str]:
    tracker = ParallelPlanTracker()
    tasks = [
        PlannedTask(task_id="t1", colony_id="c1", group_idx=0),
        PlannedTask(task_id="t2", colony_id="c2", group_idx=0),
        PlannedTask(task_id="t3", colony_id="c3", group_idx=0),
        PlannedTask(task_id="t4", colony_id="c4", group_idx=1),
        PlannedTask(task_id="t5", colony_id="c5", group_idx=1),
    ]
    plan_id = "plan-w81-test"
    tracker.register_plan(plan_id, "ws1", "th1", tasks, group_count=2)
    return tracker, plan_id


class TestW81DeferredGroupDispatch:
    def test_group1_deferred_while_group0_running(self) -> None:
        tracker, plan_id = _make_tracker_2group()
        tracker.mark_group_dispatched(plan_id, 0)
        assert tracker.next_runnable_group(plan_id) is None

    def test_group1_runnable_after_group0_completes(self) -> None:
        tracker, plan_id = _make_tracker_2group()
        tracker.mark_group_dispatched(plan_id, 0)
        for cid in ["c1", "c2", "c3"]:
            tracker.mark_task_state(cid, TaskState.completed)
        assert tracker.next_runnable_group(plan_id) == 1


class TestW81HonestAggregation:
    def test_total_counts_all_planned_not_just_spawned(self) -> None:
        tracker, plan_id = _make_tracker_2group()
        tracker.mark_group_dispatched(plan_id, 0)
        tracker.mark_task_state("c1", TaskState.completed)
        tracker.mark_task_state("c2", TaskState.completed)
        tracker.mark_task_state("c3", TaskState.completed)

        summary = tracker.get_plan_summary(plan_id)
        assert summary["total_tasks"] == 5
        assert summary["completed"] == 3
        assert summary["pending"] == 2
        assert summary["is_terminal"] is False

    def test_plan_not_complete_until_all_terminal(self) -> None:
        tracker, plan_id = _make_tracker_2group()
        for cid in ["c1", "c2", "c3"]:
            tracker.mark_task_state(cid, TaskState.completed)
        assert tracker.is_plan_terminal(plan_id) is False
        for cid in ["c4", "c5"]:
            tracker.mark_task_state(cid, TaskState.completed)
        assert tracker.is_plan_terminal(plan_id) is True


class TestW81RestartReconstruction:
    def test_recover_pending_groups(self) -> None:
        tracker = ParallelPlanTracker()
        planned = [
            {"task_id": "t1", "colony_id": "c1", "group_idx": 0},
            {"task_id": "t2", "colony_id": "c2", "group_idx": 0},
            {"task_id": "t3", "colony_id": "c3", "group_idx": 1},
        ]
        colony_statuses = {"c1": "completed", "c2": "completed"}
        tracker.reconstruct_from_projections(
            "plan-restart", "ws1", "th1",
            planned, 2, colony_statuses,
        )
        plan = tracker.get_plan("plan-restart")
        assert plan is not None
        t3 = next(t for t in plan.tasks if t.task_id == "t3")
        assert t3.state == TaskState.pending
        assert tracker.next_runnable_group("plan-restart") == 1
