"""Wave 86 Track B: Knowledge graph bridge tests.

Tests for:
- Post-reindex graph reflection wiring
- Conservative entry-to-module bridging
- MODULE node seeding in graph proximity scoring
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Post-reindex graph reflection ──


class TestPostReindexReflection:
    @pytest.mark.asyncio
    async def test_full_reindex_calls_graph_reflection(self) -> None:
        """full_reindex should call _post_reindex_graph_reflection."""
        from formicos.addons.codebase_index.indexer import (
            _post_reindex_graph_reflection,
        )

        runtime = MagicMock()
        runtime_context = {"runtime": runtime}

        with patch(
            "formicos.surface.structural_planner.reflect_structure_to_graph",
            new_callable=AsyncMock,
            return_value=5,
        ) as mock_reflect:
            await _post_reindex_graph_reflection(runtime_context, "ws1")
            mock_reflect.assert_called_once_with(runtime, "ws1")

    @pytest.mark.asyncio
    async def test_reflection_failure_is_best_effort(self) -> None:
        """Graph reflection failure should not propagate."""
        from formicos.addons.codebase_index.indexer import (
            _post_reindex_graph_reflection,
        )

        runtime = MagicMock()
        runtime_context = {"runtime": runtime}

        with patch(
            "formicos.surface.structural_planner.reflect_structure_to_graph",
            new_callable=AsyncMock,
            side_effect=RuntimeError("KG unavailable"),
        ):
            # Should not raise
            await _post_reindex_graph_reflection(runtime_context, "ws1")

    @pytest.mark.asyncio
    async def test_reflection_skips_without_runtime(self) -> None:
        """Reflection should skip gracefully with no runtime context."""
        from formicos.addons.codebase_index.indexer import (
            _post_reindex_graph_reflection,
        )

        # No runtime in context
        await _post_reindex_graph_reflection({}, "ws1")
        # None context
        await _post_reindex_graph_reflection(None, "ws1")


# ── Conservative entry-to-module bridging ──


class TestEntryToModuleBridge:
    """Test _bridge_entry_to_modules via the unbound Runtime method."""

    def _make_runtime(self) -> MagicMock:
        runtime = MagicMock()
        runtime.kg_adapter = AsyncMock()
        runtime.kg_adapter.resolve_entity = AsyncMock(return_value="mod-node-1")
        runtime.kg_adapter.add_edge = AsyncMock()
        runtime.projections = MagicMock()
        runtime.projections.get_colony = MagicMock(return_value=None)
        return runtime

    async def _call_bridge(
        self, runtime: MagicMock, entry: Any, entry_id: str,
        node_id: str, ws_id: str,
    ) -> None:
        from formicos.surface.runtime import Runtime

        await Runtime._bridge_entry_to_modules(
            runtime, entry, entry_id, node_id, ws_id,
        )

    @pytest.mark.asyncio
    async def test_bridges_from_title_file_refs(self) -> None:
        """File-path patterns in title should create MODULE edges."""
        runtime = self._make_runtime()
        entry = {
            "title": "Fix bug in src/runner.py",
            "source_colony_id": "",
        }
        await self._call_bridge(runtime, entry, "e1", "node-e1", "ws1")
        runtime.kg_adapter.resolve_entity.assert_called()

    @pytest.mark.asyncio
    async def test_bridges_from_colony_target_files(self) -> None:
        """Colony target_files should create MODULE edges."""
        runtime = self._make_runtime()
        colony = MagicMock()
        colony.target_files = ["src/auth.py", "src/types.py"]
        runtime.projections.get_colony.return_value = colony

        entry = {
            "title": "Auth module work",
            "source_colony_id": "c1",
        }
        await self._call_bridge(runtime, entry, "e1", "node-e1", "ws1")
        assert runtime.kg_adapter.resolve_entity.call_count >= 2

    @pytest.mark.asyncio
    async def test_no_bridge_without_file_refs(self) -> None:
        """Entries with no file references should not create MODULE edges."""
        runtime = self._make_runtime()
        entry = {
            "title": "General observation about caching",
            "source_colony_id": "",
        }
        await self._call_bridge(runtime, entry, "e1", "node-e1", "ws1")
        runtime.kg_adapter.resolve_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_bridge_failure_is_best_effort(self) -> None:
        """Bridge failures should not propagate."""
        runtime = self._make_runtime()
        runtime.kg_adapter.resolve_entity.side_effect = RuntimeError("KG error")
        entry = {
            "title": "Fix src/runner.py",
            "source_colony_id": "",
        }
        await self._call_bridge(runtime, entry, "e1", "node-e1", "ws1")

    @pytest.mark.asyncio
    async def test_bridge_caps_file_refs(self) -> None:
        """Bridge should cap file refs to prevent explosion."""
        runtime = self._make_runtime()
        colony = MagicMock()
        colony.target_files = [f"src/file{i}.py" for i in range(20)]
        runtime.projections.get_colony.return_value = colony

        entry = {
            "title": "Mass refactor",
            "source_colony_id": "c1",
        }
        await self._call_bridge(runtime, entry, "e1", "node-e1", "ws1")
        assert runtime.kg_adapter.resolve_entity.call_count <= 5


# ── MODULE node seeding in graph scoring ──


class TestModuleSeeding:
    @pytest.mark.asyncio
    async def test_resolve_module_seeds_from_file_refs(self) -> None:
        """Queries with file refs should produce MODULE seeds."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        kg = AsyncMock()
        kg.resolve_entity = AsyncMock(return_value="mod-123")
        catalog = KnowledgeCatalog.__new__(KnowledgeCatalog)
        catalog._kg_adapter = kg

        seeds = await catalog._resolve_module_seeds(
            "fix the bug in src/runner.py",
            "ws1",
        )
        assert len(seeds) >= 1
        assert "mod-123" in seeds

    @pytest.mark.asyncio
    async def test_resolve_module_seeds_empty_for_no_refs(self) -> None:
        """Queries without file refs should produce no MODULE seeds."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        kg = AsyncMock()
        catalog = KnowledgeCatalog.__new__(KnowledgeCatalog)
        catalog._kg_adapter = kg

        seeds = await catalog._resolve_module_seeds(
            "what is the status?",
            "ws1",
        )
        assert seeds == []

    @pytest.mark.asyncio
    async def test_resolve_module_seeds_best_effort(self) -> None:
        """MODULE seed resolution failures should return empty."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        kg = AsyncMock()
        kg.resolve_entity = AsyncMock(side_effect=RuntimeError("KG down"))
        catalog = KnowledgeCatalog.__new__(KnowledgeCatalog)
        catalog._kg_adapter = kg

        seeds = await catalog._resolve_module_seeds(
            "fix src/runner.py",
            "ws1",
        )
        assert seeds == []

    @pytest.mark.asyncio
    async def test_resolve_module_seeds_none_adapter(self) -> None:
        """No KG adapter should return empty seeds."""
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        catalog = KnowledgeCatalog.__new__(KnowledgeCatalog)
        catalog._kg_adapter = None

        seeds = await catalog._resolve_module_seeds("fix src/runner.py", "ws1")
        assert seeds == []
