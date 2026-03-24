"""Tests for trajectory extraction from successful colonies (Wave 58).

Given: A colony completes successfully with tool-call round records.
When: _hook_trajectory_extraction fires.
Then: MemoryEntryCreated event emitted with sub_type=trajectory and trajectory_data.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.surface import colony_manager as cm_module


def _make_round_record(
    round_number: int,
    tool_calls: dict[str, list[str]] | None = None,
) -> MagicMock:
    """Build a mock RoundProjection."""
    rec = MagicMock()
    rec.round_number = round_number
    rec.tool_calls = tool_calls or {}
    rec.agent_outputs = {}
    return rec


def _make_runtime(
    *,
    round_records: list[Any] | None = None,
    task: str = "Fix the login bug",
) -> MagicMock:
    """Build a mock runtime with colony projection."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.vector_store = MagicMock()
    runtime.fetch_knowledge_for_colony = AsyncMock(return_value=[])
    runtime.make_catalog_search_fn = MagicMock(return_value=None)
    runtime.make_knowledge_detail_fn = MagicMock(return_value=None)
    runtime.make_artifact_inspect_fn = MagicMock(return_value=None)
    runtime.make_transcript_search_fn = MagicMock(return_value=None)
    runtime.queen = None

    projections = MagicMock()
    projections.memory_entries = {}

    colony_proj = MagicMock()
    colony_proj.round_records = round_records or []
    colony_proj.task = task
    colony_proj.thread_id = "t-1"
    colony_proj.workspace_id = "ws-1"
    colony_proj.round_number = len(round_records or [])
    colony_proj.artifacts = []
    colony_proj.summary = ""
    colony_proj.knowledge_accesses = []
    projections.get_colony = MagicMock(return_value=colony_proj)
    projections.get_thread = MagicMock(return_value=None)

    runtime.projections = projections
    return runtime


def _make_colony(
    colony_id: str = "col-1",
    workspace_id: str = "ws-1",
    thread_id: str = "t-1",
) -> MagicMock:
    colony = MagicMock()
    colony.id = colony_id
    colony.workspace_id = workspace_id
    colony.thread_id = thread_id
    colony.task = "Fix the login bug"
    colony.castes = [{"caste": "coder", "tier": "standard", "count": 1}]
    colony.strategy = "sequential"
    return colony


class TestTrajectoryExtraction:
    """Verify trajectory extraction hook behavior."""

    @pytest.mark.asyncio
    async def test_trajectory_extraction_from_successful_colony(self) -> None:
        """Successful colony with good quality/productivity emits trajectory entry."""
        round_records = [
            _make_round_record(1, {
                "coder-1": ["read_workspace_file", "write_workspace_file"],
            }),
            _make_round_record(2, {
                "coder-1": ["code_execute"],
            }),
        ]
        runtime = _make_runtime(round_records=round_records)
        mgr = cm_module.ColonyManager(runtime)

        await mgr._hook_trajectory_extraction(
            colony_id="col-1",
            workspace_id="ws-1",
            quality=0.50,
            productive_calls=8,
            total_calls=10,
        )

        runtime.emit_and_broadcast.assert_called_once()
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.__class__.__name__ == "MemoryEntryCreated"

        entry = event.entry
        assert entry["sub_type"] == "trajectory"
        assert entry["entry_type"] == "skill"
        assert entry["status"] == "verified"
        assert entry["decay_class"] == "stable"
        assert len(entry["trajectory_data"]) == 3
        assert "Successful" in entry["content"]

        # Hard constraint #9: Beta(alpha, beta) posteriors match quality.
        # quality=0.50 → conf_alpha=max(2, 5.0)=5.0, conf_beta=max(2, 5.0)=5.0
        assert entry["conf_alpha"] == pytest.approx(5.0)
        assert entry["conf_beta"] == pytest.approx(5.0)

        # Trajectory data structure: each step has tool, agent_id, round_number.
        for step in entry["trajectory_data"]:
            assert "tool" in step
            assert "agent_id" in step
            assert "round_number" in step

    @pytest.mark.asyncio
    async def test_trajectory_extraction_skips_failed_colony(self) -> None:
        """_post_colony_hooks with succeeded=False should not call trajectory hook."""
        round_records = [
            _make_round_record(1, {"coder-1": ["read_workspace_file", "write_workspace_file"]}),
        ]
        runtime = _make_runtime(round_records=round_records)
        mgr = cm_module.ColonyManager(runtime)
        colony = _make_colony()

        await mgr._post_colony_hooks(
            colony_id="col-1", colony=colony,
            quality=0.0, total_cost=0.01,
            rounds_completed=1, skills_count=0,
            retrieved_skill_ids=set(),
            governance_warnings=0, stall_count=0,
            succeeded=False,
            productive_calls=8, total_calls=10,
        )

        # No MemoryEntryCreated for trajectory (other hooks may emit events)
        for call in runtime.emit_and_broadcast.call_args_list:
            event = call[0][0]
            if hasattr(event, "entry") and isinstance(event.entry, dict):
                assert event.entry.get("sub_type") != "trajectory"

    @pytest.mark.asyncio
    async def test_trajectory_extraction_skips_low_quality(self) -> None:
        """Quality below 0.30 should skip trajectory extraction."""
        round_records = [
            _make_round_record(1, {"coder-1": ["read_workspace_file", "write_workspace_file"]}),
            _make_round_record(2, {"coder-1": ["code_execute"]}),
        ]
        runtime = _make_runtime(round_records=round_records)
        mgr = cm_module.ColonyManager(runtime)

        await mgr._hook_trajectory_extraction(
            colony_id="col-1",
            workspace_id="ws-1",
            quality=0.20,
            productive_calls=8,
            total_calls=10,
        )

        runtime.emit_and_broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_trajectory_extraction_skips_low_productivity(self) -> None:
        """Productivity ratio below 0.60 should skip trajectory extraction."""
        round_records = [
            _make_round_record(1, {"coder-1": ["read_workspace_file", "write_workspace_file"]}),
            _make_round_record(2, {"coder-1": ["code_execute"]}),
        ]
        runtime = _make_runtime(round_records=round_records)
        mgr = cm_module.ColonyManager(runtime)

        await mgr._hook_trajectory_extraction(
            colony_id="col-1",
            workspace_id="ws-1",
            quality=0.50,
            productive_calls=3,
            total_calls=10,
        )

        runtime.emit_and_broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_trajectory_extraction_skips_trivial(self) -> None:
        """Fewer than 2 tool steps should skip trajectory extraction."""
        round_records = [
            _make_round_record(1, {"coder-1": ["read_workspace_file"]}),
        ]
        runtime = _make_runtime(round_records=round_records)
        mgr = cm_module.ColonyManager(runtime)

        await mgr._hook_trajectory_extraction(
            colony_id="col-1",
            workspace_id="ws-1",
            quality=0.50,
            productive_calls=8,
            total_calls=10,
        )

        runtime.emit_and_broadcast.assert_not_called()


class TestTrajectoryMemoryStore:
    """Verify trajectory data flows through memory_store embedding."""

    @pytest.mark.asyncio
    async def test_trajectory_entry_stored_with_embedding(self) -> None:
        """MemoryStore.upsert_entry() includes trajectory in embed text and metadata."""
        from formicos.surface.memory_store import MemoryStore

        mock_vector = AsyncMock()
        mock_vector.upsert = AsyncMock()
        store = MemoryStore(mock_vector)

        entry: dict[str, Any] = {
            "id": "traj-col-1",
            "title": "Trajectory: code_fix (3 steps)",
            "content": "Successful code_fix pattern",
            "summary": "code_fix tool sequence",
            "tool_refs": ["read_workspace_file", "write_workspace_file"],
            "domains": ["code_fix"],
            "entry_type": "skill",
            "sub_type": "trajectory",
            "status": "verified",
            "trajectory_data": [
                {"tool": "read_workspace_file", "agent_id": "coder-1", "round_number": 1},
                {"tool": "write_workspace_file", "agent_id": "coder-1", "round_number": 1},
                {"tool": "code_execute", "agent_id": "coder-1", "round_number": 2},
            ],
        }

        await store.upsert_entry(entry)

        mock_vector.upsert.assert_called_once()
        doc = mock_vector.upsert.call_args[1]["docs"][0]

        # Embedding text should contain trajectory sequence
        assert "trajectory:" in doc.content
        assert "read_workspace_file -> write_workspace_file -> code_execute" in doc.content

        # Metadata should carry trajectory_data and sub_type
        assert doc.metadata["trajectory_data"] == entry["trajectory_data"]
        assert doc.metadata["sub_type"] == "trajectory"


class TestKnowledgeDetailTrajectoryFormat:
    """Verify knowledge_detail formats trajectory entries with structured steps."""

    @pytest.mark.asyncio
    async def test_knowledge_detail_formats_trajectory(self) -> None:
        """Trajectory entries should show grouped tool sequence by round."""
        from formicos.surface.runtime import Runtime

        mock_catalog = MagicMock()
        mock_catalog.get_by_id = AsyncMock(return_value={
            "canonical_type": "skill",
            "source_system": "local",
            "title": "Trajectory: code_fix (5 steps)",
            "content_preview": "Successful code_fix pattern",
            "sub_type": "trajectory",
            "domains": ["code_fix"],
            "tool_refs": ["read_workspace_file", "write_workspace_file", "code_execute", "patch_file"],
            "trajectory_data": [
                {"tool": "read_workspace_file", "agent_id": "coder-1", "round_number": 1},
                {"tool": "write_workspace_file", "agent_id": "coder-1", "round_number": 1},
                {"tool": "code_execute", "agent_id": "coder-1", "round_number": 2},
                {"tool": "patch_file", "agent_id": "coder-1", "round_number": 2},
                {"tool": "code_execute", "agent_id": "coder-1", "round_number": 3},
            ],
        })

        # Build a minimal runtime mock just to access make_knowledge_detail_fn
        runtime = MagicMock(spec=Runtime)
        runtime.knowledge_catalog = mock_catalog

        # Call the factory directly — it's a method on the real class
        fn = Runtime.make_knowledge_detail_fn(runtime)
        assert fn is not None

        result = await fn("traj-col-1")

        assert "[TRAJECTORY," in result
        assert "Tool sequence:" in result
        assert "Round 1: coder-1: read_workspace_file, coder-1: write_workspace_file" in result
        assert "Round 2: coder-1: code_execute, coder-1: patch_file" in result
        assert "Round 3: coder-1: code_execute" in result
        assert "Domains: code_fix" in result
