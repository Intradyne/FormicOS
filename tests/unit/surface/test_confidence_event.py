"""Tests for SkillConfidenceUpdated — disabled as of Wave 28 (C2).

Legacy confidence updates and SkillConfidenceUpdated emission were removed.
These tests verify the removal is complete.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface import colony_manager as cm_module


class TestSkillConfidenceDisabled:
    """Verify legacy confidence machinery is fully removed."""

    def test_no_has_confidence_event_flag(self) -> None:
        """_HAS_CONFIDENCE_EVENT flag should no longer exist."""
        assert not hasattr(cm_module, "_HAS_CONFIDENCE_EVENT")

    def test_no_skill_confidence_updated_import(self) -> None:
        """SkillConfidenceUpdated should not be importable from colony_manager."""
        assert not hasattr(cm_module, "SkillConfidenceUpdated")

    @pytest.mark.asyncio
    async def test_no_confidence_event_emitted(self) -> None:
        """_post_colony_hooks must not emit SkillConfidenceUpdated."""
        runtime = MagicMock()
        runtime.vector_store = MagicMock()
        runtime.emit_and_broadcast = AsyncMock(return_value=1)
        runtime.fetch_knowledge_for_colony = AsyncMock(return_value=[])
        runtime.make_catalog_search_fn = MagicMock(return_value=None)
        runtime.make_knowledge_detail_fn = MagicMock(return_value=None)
        runtime.make_artifact_inspect_fn = MagicMock(return_value=None)

        colony = MagicMock()
        colony.id = "col-1"
        colony.workspace_id = "ws-1"
        colony.thread_id = "t-1"
        colony.task = "Test"
        colony.castes = [{"caste": "coder", "tier": "standard", "count": 1}]
        colony.strategy = "sequential"

        manager = cm_module.ColonyManager(runtime)
        await manager._post_colony_hooks(
            colony_id="col-1",
            colony=colony,
            quality=0.9,
            total_cost=0.5,
            rounds_completed=5,
            skills_count=3,
            retrieved_skill_ids={"skill-1"},
            governance_warnings=0,
            stall_count=0,
            succeeded=True,
        )

        # No events should have been emitted (confidence path disabled)
        runtime.emit_and_broadcast.assert_not_called()
