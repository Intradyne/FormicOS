"""Tests for prediction error counters (Wave 33 A3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPredictionErrorCounters:
    """Test prediction error detection in _search_thread_boosted."""

    def _make_catalog(
        self,
        *,
        memory_entries: dict[str, dict[str, Any]] | None = None,
    ) -> Any:
        from formicos.surface.knowledge_catalog import KnowledgeCatalog

        projections = MagicMock()
        projections.memory_entries = memory_entries or {}
        projections.cooccurrence_weights = {}

        memory_store = MagicMock()
        memory_store.search = AsyncMock(return_value=[])

        catalog = KnowledgeCatalog(
            memory_store=memory_store,
            vector_port=None,
            skill_collection="skills",
            projections=projections,
        )
        return catalog

    @pytest.mark.asyncio
    async def test_low_semantic_increments_counter(self) -> None:
        entries = {
            "mem-1": {"conf_alpha": 5.0, "conf_beta": 5.0, "created_at": datetime.now(UTC).isoformat()},
        }
        catalog = self._make_catalog(memory_entries=entries)

        # Mock _search_institutional to return a result with low semantic score
        hit = {
            "id": "mem-1",
            "score": 0.2,  # below 0.38 threshold
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "verified",
        }
        catalog._search_institutional = AsyncMock(return_value=[hit])

        await catalog._search_thread_boosted(
            "test query",
            source_system="institutional_memory",
            canonical_type="skill",
            workspace_id="ws-1",
            thread_id="th-1",
            source_colony_id="col-1",
            top_k=5,
        )

        assert entries["mem-1"].get("prediction_error_count", 0) == 1
        assert "test query" in entries["mem-1"].get("prediction_error_queries", [])

    @pytest.mark.asyncio
    async def test_high_semantic_no_increment(self) -> None:
        entries = {
            "mem-1": {"conf_alpha": 5.0, "conf_beta": 5.0, "created_at": datetime.now(UTC).isoformat()},
        }
        catalog = self._make_catalog(memory_entries=entries)

        hit = {
            "id": "mem-1",
            "score": 0.85,  # above 0.38 threshold
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "verified",
        }
        catalog._search_institutional = AsyncMock(return_value=[hit])

        await catalog._search_thread_boosted(
            "test query",
            source_system="institutional_memory",
            canonical_type="skill",
            workspace_id="ws-1",
            thread_id="th-1",
            source_colony_id="col-1",
            top_k=5,
        )

        assert entries["mem-1"].get("prediction_error_count", 0) == 0

    @pytest.mark.asyncio
    async def test_queries_capped_at_3(self) -> None:
        entries = {
            "mem-1": {
                "conf_alpha": 5.0,
                "conf_beta": 5.0,
                "created_at": datetime.now(UTC).isoformat(),
                "prediction_error_count": 4,
                "prediction_error_queries": ["q1", "q2", "q3"],
            },
        }
        catalog = self._make_catalog(memory_entries=entries)

        hit = {
            "id": "mem-1",
            "score": 0.1,
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "verified",
        }
        catalog._search_institutional = AsyncMock(return_value=[hit])

        await catalog._search_thread_boosted(
            "q4 new query",
            source_system="institutional_memory",
            canonical_type="skill",
            workspace_id="ws-1",
            thread_id="th-1",
            source_colony_id="col-1",
            top_k=5,
        )

        queries = entries["mem-1"]["prediction_error_queries"]
        assert len(queries) == 3  # still capped at 3
        assert queries[-1] == "q4 new query"
        assert entries["mem-1"]["prediction_error_count"] == 5


class TestPredictionErrorInStaleSweep:
    @pytest.mark.asyncio
    async def test_high_errors_low_access_triggers_stale(self) -> None:
        from formicos.surface.maintenance import make_stale_handler

        runtime = MagicMock()
        now = datetime.now(UTC)
        # Entry is young (30 days) but has many prediction errors
        entries = {
            "mem-1": {
                "status": "verified",
                "created_at": (now - timedelta(days=30)).isoformat(),
                "workspace_id": "ws-1",
                "prediction_error_count": 7,
            },
        }
        projections = MagicMock()
        projections.memory_entries = entries
        projections.colonies = {}  # no accesses
        runtime.projections = projections
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        handler = make_stale_handler(runtime)
        result = await handler("", {})

        assert "1 entries" in result
        # Verify the event was emitted with prediction error reason
        call_args = runtime.emit_and_broadcast.call_args
        event = call_args[0][0]
        assert "prediction_error" in event.reason

    @pytest.mark.asyncio
    async def test_high_errors_high_access_no_stale(self) -> None:
        from formicos.surface.maintenance import make_stale_handler

        runtime = MagicMock()
        now = datetime.now(UTC)
        entries = {
            "mem-1": {
                "status": "verified",
                "created_at": (now - timedelta(days=30)).isoformat(),
                "workspace_id": "ws-1",
                "prediction_error_count": 7,
            },
        }
        projections = MagicMock()
        projections.memory_entries = entries
        # Simulate 5 accesses for mem-1
        colony = MagicMock()
        colony.knowledge_accesses = [
            {"items": [{"id": "mem-1"}]},
            {"items": [{"id": "mem-1"}]},
            {"items": [{"id": "mem-1"}]},
        ]
        projections.colonies = {"col-1": colony}
        runtime.projections = projections
        runtime.emit_and_broadcast = AsyncMock(return_value=1)

        handler = make_stale_handler(runtime)
        result = await handler("", {})

        assert "0 entries" in result
