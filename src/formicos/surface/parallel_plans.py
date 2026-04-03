"""Wave 81 Track B: Parallel plan lifecycle management.

Manages deferred-group dispatch, honest aggregation, and restart-time
reconstruction for multi-group parallel plans.

The key invariant: a plan is not "complete" until ALL planned groups
have reached terminal state. Partial dispatch is surfaced as partial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class TaskState(Enum):
    """State of a single planned task."""

    pending = "pending"
    running = "running"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"


class GroupState(Enum):
    """State of a parallel group."""

    pending = "pending"
    running = "running"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"


@dataclass
class PlannedTask:
    """A task within a tracked parallel plan."""

    task_id: str
    colony_id: str
    group_idx: int
    state: TaskState = TaskState.pending
    result_meta: dict[str, Any] | None = None


@dataclass
class TrackedPlan:
    """Full lifecycle state for a parallel plan."""

    plan_id: str
    workspace_id: str
    thread_id: str
    tasks: list[PlannedTask] = field(default_factory=list)
    group_count: int = 0
    current_group: int = 0  # next group to dispatch


class ParallelPlanTracker:
    """Tracks parallel plan state for honest aggregation and deferred dispatch.

    Used by queen_tools.py (spawn_parallel) and queen_runtime.py (aggregation).
    """

    def __init__(self) -> None:
        self._plans: dict[str, TrackedPlan] = {}

    def register_plan(
        self,
        plan_id: str,
        workspace_id: str,
        thread_id: str,
        tasks: list[PlannedTask],
        group_count: int,
    ) -> None:
        """Register a new plan with all its pre-allocated tasks."""
        self._plans[plan_id] = TrackedPlan(
            plan_id=plan_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            tasks=list(tasks),
            group_count=group_count,
            current_group=0,
        )

    def get_plan(self, plan_id: str) -> TrackedPlan | None:
        return self._plans.get(plan_id)

    def find_plan_for_colony(self, colony_id: str) -> tuple[str, PlannedTask] | None:
        """Find the plan and task entry for a given colony ID."""
        for plan_id, plan in self._plans.items():
            for task in plan.tasks:
                if task.colony_id == colony_id:
                    return (plan_id, task)
        return None

    def mark_task_state(
        self, colony_id: str, state: TaskState,
        result_meta: dict[str, Any] | None = None,
    ) -> str | None:
        """Update a task's state. Returns plan_id if the plan is now fully terminal."""
        found = self.find_plan_for_colony(colony_id)
        if found is None:
            return None
        plan_id, task = found
        task.state = state
        if result_meta is not None:
            task.result_meta = result_meta
        if self.is_plan_terminal(plan_id):
            return plan_id
        return None

    def mark_group_dispatched(self, plan_id: str, group_idx: int) -> None:
        """Mark all tasks in a group as running."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return
        for task in plan.tasks:
            if task.group_idx == group_idx and task.state == TaskState.pending:
                task.state = TaskState.running
        plan.current_group = max(plan.current_group, group_idx + 1)

    def next_runnable_group(self, plan_id: str) -> int | None:
        """Return the index of the next group eligible for dispatch, or None.

        A group is runnable when all prior groups are terminal (completed/failed).
        """
        plan = self._plans.get(plan_id)
        if plan is None:
            return None

        for g in range(plan.current_group, plan.group_count):
            # Check if all tasks in prior groups are terminal
            prior_terminal = all(
                t.state in (TaskState.completed, TaskState.failed)
                for t in plan.tasks
                if t.group_idx < g
            )
            if not prior_terminal:
                return None  # blocked
            # Check if this group has pending tasks
            group_tasks = [t for t in plan.tasks if t.group_idx == g]
            if any(t.state == TaskState.pending for t in group_tasks):
                return g
        return None

    def is_plan_terminal(self, plan_id: str) -> bool:
        """True when every task in the plan is completed or failed."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return True
        return all(
            t.state in (TaskState.completed, TaskState.failed)
            for t in plan.tasks
        )

    def get_plan_summary(self, plan_id: str) -> dict[str, Any]:
        """Build an honest aggregation summary for a plan."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return {"error": "plan not found"}

        by_state: dict[str, int] = {}
        for task in plan.tasks:
            by_state[task.state.value] = by_state.get(task.state.value, 0) + 1

        total = len(plan.tasks)
        completed = by_state.get("completed", 0)
        failed = by_state.get("failed", 0)
        pending = by_state.get("pending", 0)
        running = by_state.get("running", 0)
        blocked = by_state.get("blocked", 0)

        return {
            "plan_id": plan_id,
            "total_tasks": total,
            "group_count": plan.group_count,
            "current_group": plan.current_group,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "running": running,
            "blocked": blocked,
            "is_terminal": self.is_plan_terminal(plan_id),
            "task_results": [
                {
                    "task_id": t.task_id,
                    "colony_id": t.colony_id,
                    "group": t.group_idx,
                    "state": t.state.value,
                }
                for t in plan.tasks
            ],
        }

    def get_colony_ids_for_plan(self, plan_id: str) -> list[str]:
        """All colony IDs in a plan (for aggregation registration)."""
        plan = self._plans.get(plan_id)
        if plan is None:
            return []
        return [t.colony_id for t in plan.tasks]

    def reconstruct_from_projections(
        self,
        plan_id: str,
        workspace_id: str,
        thread_id: str,
        planned_tasks: list[dict[str, Any]],
        group_count: int,
        colony_statuses: dict[str, str],
    ) -> None:
        """Reconstruct plan state from persisted data after restart.

        *planned_tasks* are the serialized ColonyTask dicts from the plan.
        *colony_statuses* maps colony_id -> status string from projections.
        """
        tasks: list[PlannedTask] = []
        for i, pt in enumerate(planned_tasks):
            cid = pt.get("colony_id", "")
            tid = pt.get("task_id", f"task-{i}")
            gidx = pt.get("group_idx", 0)
            status = colony_statuses.get(cid, "")
            if status == "completed":
                state = TaskState.completed
            elif status in ("failed", "killed"):
                state = TaskState.failed
            elif status == "running":
                state = TaskState.running
            elif cid and status:
                state = TaskState.running  # spawned but not terminal
            else:
                state = TaskState.pending
            tasks.append(PlannedTask(
                task_id=tid, colony_id=cid, group_idx=gidx, state=state,
            ))

        self.register_plan(plan_id, workspace_id, thread_id, tasks, group_count)

        # Advance current_group to the highest dispatched group
        max_dispatched = -1
        for t in tasks:
            if t.state != TaskState.pending:
                max_dispatched = max(max_dispatched, t.group_idx)
        plan = self._plans[plan_id]
        plan.current_group = max_dispatched + 1 if max_dispatched >= 0 else 0


__all__ = [
    "GroupState",
    "ParallelPlanTracker",
    "PlannedTask",
    "TaskState",
    "TrackedPlan",
]
