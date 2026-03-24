"""Tests for Wave 28-31 projection handlers (Wave 32 C4).

Covers the 9 untested handlers added in Waves 28-31.
"""

from __future__ import annotations

from datetime import datetime, timezone

from formicos.core.events import (
    DeterministicServiceRegistered,
    KnowledgeAccessRecorded,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryScopeChanged,
    MemoryEntryStatusChanged,
    ThreadCreated,
    ThreadStatusChanged,
    WorkflowStepCompleted,
    WorkflowStepDefined,
    WorkspaceCreated,
)
from formicos.core.events import WorkspaceConfigSnapshot
from formicos.core.types import WorkflowStep
from formicos.surface.projections import ProjectionStore

_NOW = datetime(2026, 3, 18, tzinfo=timezone.utc)
_WS_CONFIG = WorkspaceConfigSnapshot(budget=5.0, strategy="stigmergic")


_WS_NAME = "ws-1"
_TH_NAME = "t-1"


def _seeded_store(
    workspace_name: str = _WS_NAME,
    thread_name: str = _TH_NAME,
) -> ProjectionStore:
    """Build a ProjectionStore with a workspace and thread.

    Note: ProjectionStore keys workspaces and threads by *name*, not by ID.
    """
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, timestamp=_NOW, address=workspace_name,
        name=workspace_name, config=_WS_CONFIG,
    ))
    store.apply(ThreadCreated(
        seq=2, timestamp=_NOW, address=f"{workspace_name}/{thread_name}",
        workspace_id=workspace_name, name=thread_name,
    ))
    return store


def _seed_memory_entry(
    store: ProjectionStore,
    entry_id: str = "mem-1",
    workspace_id: str = "ws-1",
    thread_id: str = "t-1",
) -> None:
    """Add a memory entry to the store."""
    store.apply(MemoryEntryCreated(
        seq=10, timestamp=_NOW, address=f"{workspace_id}/{thread_id}",
        workspace_id=workspace_id,
        entry={
            "id": entry_id,
            "entry_type": "skill",
            "status": "candidate",
            "polarity": "positive",
            "title": "Test Skill",
            "content": "Test content",
            "source_colony_id": "col-1",
            "source_artifact_ids": [],
            "workspace_id": workspace_id,
            "thread_id": thread_id,
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "confidence": 0.5,
        },
    ))


class TestMemoryEntryCreated:
    """_on_memory_entry_created handler."""

    def test_entry_added_to_store(self) -> None:
        store = ProjectionStore()
        _seed_memory_entry(store)
        assert "mem-1" in store.memory_entries
        entry = store.memory_entries["mem-1"]
        assert entry["title"] == "Test Skill"
        assert entry["status"] == "candidate"
        assert entry["conf_alpha"] == 5.0

    def test_empty_id_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(MemoryEntryCreated(
            seq=1, timestamp=_NOW, address="ws-1",
            workspace_id="ws-1",
            entry={"id": "", "title": "No ID"},
        ))
        assert len(store.memory_entries) == 0


class TestMemoryConfidenceUpdated:
    """_on_memory_confidence_updated handler."""

    def test_alpha_beta_updated(self) -> None:
        store = ProjectionStore()
        _seed_memory_entry(store)

        store.apply(MemoryConfidenceUpdated(
            seq=11, timestamp=_NOW, address="ws-1/t-1",
            entry_id="mem-1", colony_id="col-1",
            colony_succeeded=True,
            old_alpha=5.0, old_beta=5.0,
            new_alpha=6.0, new_beta=5.0,
            new_confidence=6.0 / 11.0,
            workspace_id="ws-1",
        ))

        entry = store.memory_entries["mem-1"]
        assert entry["conf_alpha"] == 6.0
        assert entry["conf_beta"] == 5.0
        assert abs(entry["confidence"] - 6.0 / 11.0) < 0.001

    def test_missing_entry_ignored(self) -> None:
        store = ProjectionStore()
        # Should not raise
        store.apply(MemoryConfidenceUpdated(
            seq=1, timestamp=_NOW, address="ws-1",
            entry_id="nonexistent", colony_id="col-1",
            colony_succeeded=True,
            old_alpha=5.0, old_beta=5.0,
            new_alpha=6.0, new_beta=5.0,
            new_confidence=0.545,
            workspace_id="ws-1",
        ))


class TestWorkflowStepDefined:
    """_on_workflow_step_defined handler."""

    def test_step_appended_to_thread(self) -> None:
        store = _seeded_store()
        store.apply(WorkflowStepDefined(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step=WorkflowStep(step_index=0, description="Implement feature X"),
        ))

        thread = store.workspaces["ws-1"].threads["t-1"]
        assert len(thread.workflow_steps) == 1
        assert thread.workflow_steps[0]["description"] == "Implement feature X"
        assert thread.workflow_steps[0]["step_index"] == 0

    def test_missing_workspace_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(WorkflowStepDefined(
            seq=1, timestamp=_NOW, address="ws-missing/t-1",
            workspace_id="ws-missing", thread_id="t-1",
            step=WorkflowStep(step_index=0, description="Test"),
        ))
        # No crash


class TestWorkflowStepCompleted:
    """_on_workflow_step_completed handler."""

    def test_step_marked_completed(self) -> None:
        store = _seeded_store()
        store.apply(WorkflowStepDefined(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step=WorkflowStep(step_index=0, description="Step 1"),
        ))

        store.apply(WorkflowStepCompleted(
            seq=4, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step_index=0, colony_id="col-1", success=True,
        ))

        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.workflow_steps[0]["status"] == "completed"
        assert thread.workflow_steps[0]["colony_id"] == "col-1"

    def test_success_increments_continuation_depth(self) -> None:
        store = _seeded_store()
        store.apply(WorkflowStepDefined(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step=WorkflowStep(step_index=0, description="Step 1"),
        ))

        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.continuation_depth == 0

        store.apply(WorkflowStepCompleted(
            seq=4, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step_index=0, colony_id="col-1", success=True,
        ))
        assert thread.continuation_depth == 1

    def test_failure_does_not_increment_depth(self) -> None:
        store = _seeded_store()
        store.apply(WorkflowStepDefined(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step=WorkflowStep(step_index=0, description="Step 1"),
        ))

        store.apply(WorkflowStepCompleted(
            seq=4, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            step_index=0, colony_id="col-1", success=False,
        ))

        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.workflow_steps[0]["status"] == "failed"
        assert thread.continuation_depth == 0


class TestKnowledgeAccessRecorded:
    """_on_knowledge_access_recorded handler."""

    def test_access_appended_to_colony(self) -> None:
        store = _seeded_store()
        # Need a colony first
        from formicos.core.events import ColonySpawned
        from formicos.core.types import CasteSlot

        store.apply(ColonySpawned(
            seq=5, timestamp=_NOW, address="ws-1/t-1/col-1",
            thread_id="t-1", task="Test",
            castes=[CasteSlot(caste="coder")],
            model_assignments={"coder": "test-model"},
            strategy="stigmergic", max_rounds=5, budget_limit=1.0,
        ))

        store.apply(KnowledgeAccessRecorded(
            seq=6, timestamp=_NOW, address="ws-1/t-1",
            colony_id="col-1", round_number=1,
            workspace_id="ws-1", access_mode="tool_search",
        ))

        colony = store.colonies["col-1"]
        assert len(colony.knowledge_accesses) == 1
        assert colony.knowledge_accesses[0]["access_mode"] == "tool_search"
        assert colony.knowledge_accesses[0]["round"] == 1

    def test_missing_colony_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(KnowledgeAccessRecorded(
            seq=1, timestamp=_NOW, address="ws-1",
            colony_id="nonexistent", round_number=1,
            workspace_id="ws-1",
        ))
        # No crash


class TestMemoryEntryScopeChanged:
    """_on_memory_entry_scope_changed handler."""

    def test_thread_id_updated(self) -> None:
        store = ProjectionStore()
        _seed_memory_entry(store, thread_id="t-1")

        store.apply(MemoryEntryScopeChanged(
            seq=11, timestamp=_NOW, address="ws-1",
            entry_id="mem-1", old_thread_id="t-1",
            new_thread_id="", workspace_id="ws-1",
        ))

        entry = store.memory_entries["mem-1"]
        assert entry["thread_id"] == ""  # promoted to workspace-wide

    def test_missing_entry_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(MemoryEntryScopeChanged(
            seq=1, timestamp=_NOW, address="ws-1",
            entry_id="nonexistent", workspace_id="ws-1",
        ))


class TestThreadStatusChanged:
    """_on_thread_status_changed handler."""

    def test_status_updated(self) -> None:
        store = _seeded_store()
        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.status == "active"

        store.apply(ThreadStatusChanged(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            old_status="active", new_status="completed",
        ))

        assert thread.status == "completed"

    def test_missing_workspace_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(ThreadStatusChanged(
            seq=1, timestamp=_NOW, address="ws-missing/t-1",
            workspace_id="ws-missing", thread_id="t-1",
            old_status="active", new_status="archived",
        ))


class TestDeterministicServiceRegistered:
    """_on_deterministic_service_registered handler — no-op."""

    def test_no_projection_effect(self) -> None:
        store = ProjectionStore()
        store.apply(DeterministicServiceRegistered(
            seq=1, timestamp=_NOW, address="system",
            service_name="service:consolidation:dedup",
            description="Dedup handler",
        ))
        # No crash, no state change
        assert len(store.workspaces) == 0


class TestMemoryEntryStatusChanged:
    """_on_memory_entry_status_changed handler."""

    def test_status_and_reason_updated(self) -> None:
        store = ProjectionStore()
        _seed_memory_entry(store)

        store.apply(MemoryEntryStatusChanged(
            seq=11, timestamp=_NOW, address="ws-1",
            entry_id="mem-1", old_status="candidate",
            new_status="verified", reason="colony succeeded",
            workspace_id="ws-1",
        ))

        entry = store.memory_entries["mem-1"]
        assert entry["status"] == "verified"
        assert entry["last_status_reason"] == "colony succeeded"

    def test_missing_entry_ignored(self) -> None:
        store = ProjectionStore()
        store.apply(MemoryEntryStatusChanged(
            seq=1, timestamp=_NOW, address="ws-1",
            entry_id="nonexistent", old_status="candidate",
            new_status="verified", workspace_id="ws-1",
        ))


class TestColonySpawnedReactivatesThread:
    """Wave 32.5: _on_colony_spawned re-activates completed threads."""

    def test_completed_thread_becomes_active_on_spawn(self) -> None:
        """Spawning a colony into a completed thread re-activates it."""
        from formicos.core.events import ColonySpawned, ThreadStatusChanged
        from formicos.core.types import CasteSlot

        store = _seeded_store()

        # Mark thread as completed
        store.apply(ThreadStatusChanged(
            seq=3, timestamp=_NOW, address="ws-1/t-1",
            workspace_id="ws-1", thread_id="t-1",
            old_status="active", new_status="completed",
        ))
        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.status == "completed"

        # Spawn a new colony into the completed thread
        store.apply(ColonySpawned(
            seq=4, timestamp=_NOW, address="ws-1/t-1/col-1",
            thread_id="t-1", task="Follow-up task",
            castes=[CasteSlot(caste="coder")],
            model_assignments={"coder": "test-model"},
            strategy="stigmergic", max_rounds=5, budget_limit=1.0,
        ))

        # Thread should be re-activated
        assert thread.status == "active"
        assert "col-1" in thread.colonies

    def test_active_thread_status_unchanged_on_spawn(self) -> None:
        """Spawning into an already-active thread does not change its status."""
        from formicos.core.events import ColonySpawned
        from formicos.core.types import CasteSlot

        store = _seeded_store()
        thread = store.workspaces["ws-1"].threads["t-1"]
        assert thread.status == "active"

        store.apply(ColonySpawned(
            seq=3, timestamp=_NOW, address="ws-1/t-1/col-2",
            thread_id="t-1", task="Normal task",
            castes=[CasteSlot(caste="coder")],
            model_assignments={"coder": "test-model"},
            strategy="stigmergic", max_rounds=5, budget_limit=1.0,
        ))

        assert thread.status == "active"
