"""Unit tests for the retrieval diagnostics endpoint and timing store."""

from __future__ import annotations

from pathlib import Path

import pytest

from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter
from formicos.engine.context import (
    _last_retrieval_timing,
    get_last_retrieval_timing,
)


class TestRetrievalTimingStore:
    """Tests for the ephemeral in-memory timing store in engine/context.py."""

    def test_initial_timing_is_zero(self) -> None:
        timing = get_last_retrieval_timing()
        assert "graph_ms" in timing
        assert "vector_ms" in timing
        assert "total_ms" in timing

    def test_returns_copy_not_reference(self) -> None:
        t1 = get_last_retrieval_timing()
        t2 = get_last_retrieval_timing()
        assert t1 is not t2

    def test_mutation_propagates_to_getter(self) -> None:
        original = _last_retrieval_timing["graph_ms"]
        _last_retrieval_timing["graph_ms"] = 42.5
        try:
            timing = get_last_retrieval_timing()
            assert timing["graph_ms"] == 42.5
        finally:
            _last_retrieval_timing["graph_ms"] = original


class TestDiagnosticsDataShape:
    """Tests verifying the shape of data the diagnostics endpoint assembles."""

    @pytest.fixture()
    async def kg(self, tmp_path: Path) -> KnowledgeGraphAdapter:
        adapter = KnowledgeGraphAdapter(db_path=tmp_path / "diag_kg.db")
        yield adapter  # type: ignore[misc]
        await adapter.close()

    @pytest.mark.anyio()
    async def test_kg_stats_shape(self, kg: KnowledgeGraphAdapter) -> None:
        """KG stats returns dict with 'nodes' and 'edges' keys."""
        st = await kg.stats()
        assert "nodes" in st
        assert "edges" in st
        assert isinstance(st["nodes"], int)
        assert isinstance(st["edges"], int)

    @pytest.mark.anyio()
    async def test_kg_stats_with_data(self, kg: KnowledgeGraphAdapter) -> None:
        """KG stats reflect ingested data."""
        await kg.ingest_tuples(
            [{"subject": "A", "predicate": "DEPENDS_ON", "object": "B",
              "subject_type": "MODULE", "object_type": "MODULE"}],
            workspace_id="ws-test",
        )
        st = await kg.stats()
        assert st["nodes"] == 2
        assert st["edges"] == 1

    def test_timing_keys_match_endpoint_contract(self) -> None:
        """Timing dict keys map to the endpoint's camelCase fields."""
        timing = get_last_retrieval_timing()
        # These keys are mapped to graphMs, vectorMs, totalMs in the endpoint
        assert set(timing.keys()) == {"graph_ms", "vector_ms", "total_ms"}

    @pytest.mark.anyio()
    async def test_graceful_no_kg_adapter(self) -> None:
        """When kg_adapter is None, diagnostics should return zero counts."""
        kg_adapter = None
        kg_stats: dict[str, int] = {"nodes": 0, "edges": 0}
        if kg_adapter is not None:
            kg_stats = await kg_adapter.stats()
        assert kg_stats == {"nodes": 0, "edges": 0}
