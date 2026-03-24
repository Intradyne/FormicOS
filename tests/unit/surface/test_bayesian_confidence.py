"""Tests for Bayesian confidence update end-to-end (Wave 31 B3).

Given: Colony completes with knowledge access traces.
When: _post_colony_hooks processes the traces.
Then: MemoryConfidenceUpdated events are emitted with correct alpha/beta.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface import colony_manager as cm_module


def _make_runtime(
    *, memory_entries: dict[str, Any] | None = None,
    knowledge_accesses: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock runtime with projections and colony knowledge accesses."""
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
    projections.memory_entries = memory_entries or {}

    # Colony projection with knowledge_accesses
    colony_proj = MagicMock()
    colony_proj.knowledge_accesses = knowledge_accesses or []
    colony_proj.artifacts = []
    colony_proj.summary = ""
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
    colony.task = "Test task"
    colony.castes = [{"caste": "coder", "tier": "standard", "count": 1}]
    colony.strategy = "sequential"
    return colony


class TestBayesianConfidenceUpdate:
    """Verify Bayesian confidence update from colony outcomes."""

    @pytest.mark.asyncio
    async def test_success_increments_alpha(self) -> None:
        """Colony success should increase alpha by quality-aware delta (Wave 37 1B)."""
        runtime = _make_runtime(
            memory_entries={
                "mem-abc-1": {
                    "id": "mem-abc-1",
                    "workspace_id": "ws-1",
                    "thread_id": "t-1",
                    "conf_alpha": 5.0,
                    "conf_beta": 5.0,
                    "status": "verified",
                },
            },
            knowledge_accesses=[
                {
                    "round_number": 1,
                    "items": [
                        {"id": "mem-abc-1", "source_system": "institutional_memory"},
                    ],
                },
            ],
        )

        manager = cm_module.ColonyManager(runtime)
        colony = _make_colony()

        await manager._post_colony_hooks(
            colony_id="col-1",
            colony=colony,
            quality=0.9,
            total_cost=0.5,
            rounds_completed=3,
            skills_count=1,
            retrieved_skill_ids=set(),
            governance_warnings=0,
            stall_count=0,
            succeeded=True,
        )

        confidence_calls = [
            call
            for call in runtime.emit_and_broadcast.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        assert len(confidence_calls) >= 1, "Should emit MemoryConfidenceUpdated"
        event = confidence_calls[0].args[0]
        # Wave 37 1B: delta_alpha = clip(0.5 + quality, 0.5, 1.5)
        # quality=0.9 → delta=1.4 → new_alpha=5.0+1.4=6.4
        assert event.new_alpha == 6.4
        assert event.new_beta == 5.0  # unchanged on success

    @pytest.mark.asyncio
    async def test_failure_increments_beta(self) -> None:
        """Colony failure should increase beta by quality-aware delta (Wave 37 1B)."""
        runtime = _make_runtime(
            memory_entries={
                "mem-abc-1": {
                    "id": "mem-abc-1",
                    "workspace_id": "ws-1",
                    "thread_id": "t-1",
                    "conf_alpha": 5.0,
                    "conf_beta": 5.0,
                    "status": "verified",
                },
            },
            knowledge_accesses=[
                {
                    "round_number": 1,
                    "items": [
                        {"id": "mem-abc-1", "source_system": "institutional_memory"},
                    ],
                },
            ],
        )

        manager = cm_module.ColonyManager(runtime)
        colony = _make_colony()

        await manager._post_colony_hooks(
            colony_id="col-1",
            colony=colony,
            quality=0.2,
            total_cost=0.5,
            rounds_completed=3,
            skills_count=0,
            retrieved_skill_ids=set(),
            governance_warnings=0,
            stall_count=0,
            succeeded=False,
        )

        confidence_calls = [
            call
            for call in runtime.emit_and_broadcast.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        assert len(confidence_calls) >= 1
        event = confidence_calls[0].args[0]
        # Wave 37 1B: delta_beta = clip(0.5 + (1-quality), 0.5, 1.5)
        # quality=0.2, succeeded=False → failure_penalty=0.8
        # delta_beta = clip(0.5 + 0.8, 0.5, 1.5) = 1.3
        assert event.new_alpha == 5.0  # unchanged on failure
        assert event.new_beta == 6.3  # 5.0 + 1.3

    @pytest.mark.asyncio
    async def test_confidence_posterior_mean_correct(self) -> None:
        """new_confidence should equal new_alpha / (new_alpha + new_beta)."""
        runtime = _make_runtime(
            memory_entries={
                "mem-abc-1": {
                    "id": "mem-abc-1",
                    "workspace_id": "ws-1",
                    "thread_id": "t-1",
                    "conf_alpha": 10.0,
                    "conf_beta": 5.0,
                    "status": "verified",
                },
            },
            knowledge_accesses=[
                {
                    "round_number": 1,
                    "items": [
                        {"id": "mem-abc-1", "source_system": "institutional_memory"},
                    ],
                },
            ],
        )

        manager = cm_module.ColonyManager(runtime)
        colony = _make_colony()

        await manager._post_colony_hooks(
            colony_id="col-1",
            colony=colony,
            quality=0.8,
            total_cost=0.5,
            rounds_completed=2,
            skills_count=1,
            retrieved_skill_ids=set(),
            governance_warnings=0,
            stall_count=0,
            succeeded=True,
        )

        confidence_calls = [
            call
            for call in runtime.emit_and_broadcast.call_args_list
            if hasattr(call.args[0], "type")
            and call.args[0].type == "MemoryConfidenceUpdated"
        ]
        if confidence_calls:
            event = confidence_calls[0].args[0]
            expected_conf = event.new_alpha / (event.new_alpha + event.new_beta)
            assert abs(event.new_confidence - expected_conf) < 0.001
