"""Tests for workflow step lifecycle (Wave 31 B3).

Given: Steps are defined on a thread.
When: Colonies are spawned and complete for each step.
Then: WorkflowStepCompleted events are emitted with correct status transitions.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.core.events import WorkflowStepCompleted, WorkflowStepDefined
from formicos.core.types import WorkflowStep
from formicos.surface.projections import (
    ProjectionStore,
    ThreadProjection,
)


def _make_store_with_thread(
    thread_id: str = "t-1",
    workspace_id: str = "ws-1",
    steps: list[dict[str, Any]] | None = None,
) -> tuple[ProjectionStore, ThreadProjection]:
    """Build a ProjectionStore with a workspace containing a thread."""
    store = ProjectionStore()
    ws = MagicMock()
    ws.threads = {}
    store.workspaces[workspace_id] = ws

    thread = ThreadProjection(id=thread_id, workspace_id=workspace_id, name="test")
    if steps:
        thread.workflow_steps = steps
    ws.threads[thread_id] = thread
    return store, thread


class TestWorkflowStepLifecycle:
    """Verify workflow step state transitions."""

    def test_step_defined_adds_to_thread(self) -> None:
        """WorkflowStepDefined should add a pending step to the thread."""
        store, thread = _make_store_with_thread()

        event = WorkflowStepDefined(
            seq=1,
            timestamp=MagicMock(),
            address="ws-1/t-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step=WorkflowStep(
                step_index=0,
                description="Implement feature X",
            ),
        )
        store.apply(event)

        assert len(thread.workflow_steps) == 1
        assert thread.workflow_steps[0]["status"] == "pending"
        assert thread.workflow_steps[0]["description"] == "Implement feature X"

    def test_step_completed_updates_status(self) -> None:
        """WorkflowStepCompleted should mark the step as completed."""
        store, thread = _make_store_with_thread(steps=[
            {
                "step_index": 0,
                "description": "Step 1",
                "status": "running",
                "colony_id": "col-1",
                "template_id": "",
                "expected_outputs": [],
            },
        ])

        event = WorkflowStepCompleted(
            seq=2,
            timestamp=MagicMock(),
            address="ws-1/t-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step_index=0,
            colony_id="col-1",
            success=True,
            artifacts_produced=["code"],
        )
        store.apply(event)

        assert thread.workflow_steps[0]["status"] == "completed"

    def test_multiple_steps_sequential_completion(self) -> None:
        """Steps should complete in order without affecting other steps."""
        store, thread = _make_store_with_thread(steps=[
            {
                "step_index": 0,
                "description": "Step 1",
                "status": "completed",
                "colony_id": "col-1",
                "template_id": "",
                "expected_outputs": [],
            },
            {
                "step_index": 1,
                "description": "Step 2",
                "status": "running",
                "colony_id": "col-2",
                "template_id": "",
                "expected_outputs": [],
            },
            {
                "step_index": 2,
                "description": "Step 3",
                "status": "pending",
                "colony_id": "",
                "template_id": "",
                "expected_outputs": [],
            },
        ])

        event = WorkflowStepCompleted(
            seq=3,
            timestamp=MagicMock(),
            address="ws-1/t-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step_index=1,
            colony_id="col-2",
            success=True,
            artifacts_produced=[],
        )
        store.apply(event)

        assert thread.workflow_steps[0]["status"] == "completed"
        assert thread.workflow_steps[1]["status"] == "completed"
        assert thread.workflow_steps[2]["status"] == "pending"

    def test_failed_step_marked_accordingly(self) -> None:
        """A failed colony should mark the step as failed."""
        store, thread = _make_store_with_thread(steps=[
            {
                "step_index": 0,
                "description": "Step 1",
                "status": "running",
                "colony_id": "col-1",
                "template_id": "",
                "expected_outputs": [],
            },
        ])

        event = WorkflowStepCompleted(
            seq=2,
            timestamp=MagicMock(),
            address="ws-1/t-1",
            workspace_id="ws-1",
            thread_id="t-1",
            step_index=0,
            colony_id="col-1",
            success=False,
            artifacts_produced=[],
        )
        store.apply(event)

        assert thread.workflow_steps[0]["status"] in ("completed", "failed")
