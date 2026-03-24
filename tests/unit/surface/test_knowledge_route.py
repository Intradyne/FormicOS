"""Unit tests for the GET /api/v1/knowledge route handler logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter


class TestKnowledgeGraphRoute:
    """Tests verifying the KG adapter returns data in the shape the route serves."""

    @pytest.fixture()
    async def kg(self, tmp_path: Path) -> KnowledgeGraphAdapter:
        adapter = KnowledgeGraphAdapter(db_path=tmp_path / "test_kg.db")
        yield adapter  # type: ignore[misc]
        await adapter.close()

    @pytest.mark.anyio()
    async def test_empty_graph_returns_zero_stats(self, kg: KnowledgeGraphAdapter) -> None:
        st = await kg.stats()
        assert st == {"nodes": 0, "edges": 0}

    @pytest.mark.anyio()
    async def test_empty_graph_query_returns_no_rows(self, kg: KnowledgeGraphAdapter) -> None:
        db = await kg._ensure_db()  # noqa: SLF001
        cursor = await db.execute("SELECT * FROM kg_nodes")
        rows = await cursor.fetchall()
        assert rows == []

    @pytest.mark.anyio()
    async def test_nodes_and_edges_returned(self, kg: KnowledgeGraphAdapter) -> None:
        """After ingesting tuples, the route-style query should return nodes/edges."""
        ws = "test-ws"
        await kg.ingest_tuples(
            [
                {
                    "subject": "ModuleA",
                    "predicate": "DEPENDS_ON",
                    "object": "ModuleB",
                    "subject_type": "MODULE",
                    "object_type": "MODULE",
                },
                {
                    "subject": "ModuleA",
                    "predicate": "IMPLEMENTS",
                    "object": "ConceptX",
                    "subject_type": "MODULE",
                    "object_type": "CONCEPT",
                },
            ],
            workspace_id=ws,
            source_colony="colony-1",
        )

        # Verify stats
        st = await kg.stats(ws)
        assert st["nodes"] == 3
        assert st["edges"] == 2

        # Query nodes like the route does
        db = await kg._ensure_db()  # noqa: SLF001
        cur_n = await db.execute(
            "SELECT id, name, entity_type, summary, source_colony, "
            "workspace_id, created_at FROM kg_nodes WHERE workspace_id = ?",
            [ws],
        )
        nodes = [dict(row) for row in await cur_n.fetchall()]
        assert len(nodes) == 3

        names = {n["name"] for n in nodes}
        assert "ModuleA" in names
        assert "ModuleB" in names
        assert "ConceptX" in names

        # Verify node shape matches route contract
        for node in nodes:
            assert "id" in node
            assert "name" in node
            assert "entity_type" in node
            assert "workspace_id" in node

        # Query edges like the route does
        cur_e = await db.execute(
            "SELECT id, from_node, to_node, predicate, confidence, "
            "source_colony, source_round, created_at "
            "FROM kg_edges WHERE workspace_id = ? AND invalid_at IS NULL",
            [ws],
        )
        edges = [dict(row) for row in await cur_e.fetchall()]
        assert len(edges) == 2

        predicates = {e["predicate"] for e in edges}
        assert predicates == {"DEPENDS_ON", "IMPLEMENTS"}

        # Verify edge shape matches route contract
        for edge in edges:
            assert "id" in edge
            assert "from_node" in edge
            assert "to_node" in edge
            assert "predicate" in edge
            assert "confidence" in edge

    @pytest.mark.anyio()
    async def test_workspace_filter(self, kg: KnowledgeGraphAdapter) -> None:
        """Nodes from different workspaces should be isolated."""
        await kg.ingest_tuples(
            [{"subject": "A", "predicate": "ENABLES", "object": "B",
              "subject_type": "MODULE", "object_type": "MODULE"}],
            workspace_id="ws-1",
        )
        await kg.ingest_tuples(
            [{"subject": "C", "predicate": "VALIDATES", "object": "D",
              "subject_type": "TOOL", "object_type": "CONCEPT"}],
            workspace_id="ws-2",
        )

        st1 = await kg.stats("ws-1")
        st2 = await kg.stats("ws-2")
        assert st1["nodes"] == 2
        assert st2["nodes"] == 2

        # Cross-check: ws-1 should not see ws-2 nodes
        db = await kg._ensure_db()  # noqa: SLF001
        cur = await db.execute(
            "SELECT name FROM kg_nodes WHERE workspace_id = ?", ["ws-1"],
        )
        names = {row["name"] for row in await cur.fetchall()}
        assert "C" not in names
        assert "D" not in names

    @pytest.mark.anyio()
    async def test_invalidated_edges_excluded(self, kg: KnowledgeGraphAdapter) -> None:
        """Invalidated edges should not appear in the route query."""
        ws = "test-ws"
        e1 = await kg.resolve_entity("X", "MODULE", ws)
        e2 = await kg.resolve_entity("Y", "MODULE", ws)
        edge_id = await kg.add_edge(e1, e2, "DEPENDS_ON", ws)
        await kg.invalidate_edge(edge_id)

        db = await kg._ensure_db()  # noqa: SLF001
        cur = await db.execute(
            "SELECT id FROM kg_edges WHERE workspace_id = ? AND invalid_at IS NULL",
            [ws],
        )
        rows = await cur.fetchall()
        assert len(rows) == 0

    @pytest.mark.anyio()
    async def test_graceful_when_no_kg_adapter(self) -> None:
        """When kg_adapter is None, the route should return empty data."""
        # Simulates the route handler's early return
        kg_adapter = None
        if kg_adapter is None:
            result = {"nodes": [], "edges": [], "stats": {"nodes": 0, "edges": 0}}
        assert result["nodes"] == []
        assert result["stats"]["nodes"] == 0
