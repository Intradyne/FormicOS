"""Tests for Wave 67.5 — Two-Pass Retrieval with Personalized PageRank (ADR-050)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.adapters.knowledge_graph import KnowledgeGraphAdapter
from formicos.surface.knowledge_catalog import KnowledgeCatalog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INSERT_NODE = (
    "INSERT INTO kg_nodes"
    " (id, name, entity_type, summary, workspace_id)"
    " VALUES (?, ?, ?, ?, ?)"
)
_INSERT_NODE_SHORT = (
    "INSERT INTO kg_nodes"
    " (id, name, entity_type, workspace_id)"
    " VALUES (?, ?, ?, ?)"
)
_INSERT_EDGE = (
    "INSERT INTO kg_edges"
    " (id, from_node, to_node, predicate, workspace_id)"
    " VALUES (?, ?, ?, ?, ?)"
)


def _make_kg_adapter(
    *,
    entities: list[dict[str, Any]] | None = None,
    edges: dict[str, list[dict[str, Any]]] | None = None,
) -> MagicMock:
    """Build a mock KnowledgeGraphAdapter with controllable behavior."""
    adapter = MagicMock(spec=KnowledgeGraphAdapter)
    _edges = edges or {}

    async def _match(
        query: str, workspace_id: str, *, limit: int = 5,
    ) -> list[dict[str, Any]]:
        return (entities or [])[:limit]

    adapter.match_entities_by_embedding = AsyncMock(side_effect=_match)

    async def _get_neighbors(
        entity_id: str, depth: int = 1,
        workspace_id: str | None = None,
        *, include_invalidated: bool = False,
        valid_before: str | None = None,
    ) -> list[dict[str, Any]]:
        return _edges.get(entity_id, [])

    adapter.get_neighbors = AsyncMock(side_effect=_get_neighbors)

    async def _ppr(
        seed_ids: list[str], workspace_id: str,
        *, damping: float = 0.5, iterations: int = 20,
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for sid in seed_ids:
            result[sid] = 1.0
            for nbr in _edges.get(sid, []):
                other = (
                    nbr["to_node"]
                    if nbr["from_node"] == sid
                    else nbr["from_node"]
                )
                result.setdefault(other, 0.5)
        max_s = max(result.values()) if result else 1.0
        if max_s > 0:
            result = {k: v / max_s for k, v in result.items()}
        return result

    adapter.personalized_pagerank = AsyncMock(side_effect=_ppr)
    return adapter


def _make_projections(
    *,
    entries: dict[str, dict[str, Any]] | None = None,
    entry_kg_nodes: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock ProjectionStore."""
    proj = MagicMock()
    proj.memory_entries = entries or {}
    proj.entry_kg_nodes = entry_kg_nodes or {}
    proj.cooccurrence_weights = {}
    proj.workspace_configs = {}
    return proj


def _make_memory_store(
    results: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock MemoryStore."""
    store = MagicMock()

    async def _search(**kwargs: Any) -> list[dict[str, Any]]:
        return results or []

    store.search = AsyncMock(side_effect=_search)
    return store


def _make_catalog(
    *,
    memory_results: list[dict[str, Any]] | None = None,
    kg_entities: list[dict[str, Any]] | None = None,
    kg_edges: dict[str, list[dict[str, Any]]] | None = None,
    entries: dict[str, dict[str, Any]] | None = None,
    entry_kg_nodes: dict[str, str] | None = None,
) -> KnowledgeCatalog:
    """Build a KnowledgeCatalog with mocked dependencies."""
    ms = _make_memory_store(memory_results)
    proj = _make_projections(
        entries=entries, entry_kg_nodes=entry_kg_nodes,
    )
    kg = _make_kg_adapter(entities=kg_entities, edges=kg_edges)
    return KnowledgeCatalog(
        memory_store=ms,
        vector_port=None,
        skill_collection="test",
        projections=proj,
        kg_adapter=kg,
    )


def _mock_institutional(
    mem_results: list[dict[str, Any]],
) -> AsyncMock:
    """Return an AsyncMock for _search_institutional."""
    from formicos.surface.knowledge_catalog import (  # noqa: PLC0415
        _normalize_institutional,
    )

    async def _impl(
        *args: Any, **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return [
            _normalize_institutional(r, score=float(r.get("score", 0)))
            for r in mem_results
        ]

    return AsyncMock(side_effect=_impl)


# ---------------------------------------------------------------------------
# Step 1: match_entities_by_embedding
# ---------------------------------------------------------------------------


class TestMatchEntitiesByEmbedding:
    """ADR-050 D2: entity matching for PPR seeding."""

    @pytest.mark.asyncio
    async def test_returns_semantically_relevant(
        self, tmp_path: Any,
    ) -> None:
        """Embedding path sorts by cosine similarity."""
        db_path = tmp_path / "test.db"

        def sync_embed(texts: list[str]) -> list[list[float]]:
            vecs = []
            for t in texts:
                if "auth" in t.lower():
                    vecs.append([0.9, 0.44])
                elif "logging" in t.lower():
                    vecs.append([0.1, 0.99])
                else:
                    vecs.append([1.0, 0.0])
            return vecs

        kg = KnowledgeGraphAdapter(db_path, embed_fn=sync_embed)
        await kg._ensure_db()
        db = kg._db
        assert db is not None
        await db.execute(
            _INSERT_NODE,
            ["e1", "AuthMiddleware", "MODULE", "auth handler", "ws1"],
        )
        await db.execute(
            _INSERT_NODE,
            ["e2", "LoggingService", "MODULE", "logging infra", "ws1"],
        )
        await db.commit()

        results = await kg.match_entities_by_embedding(
            "auth validation", "ws1",
        )
        assert len(results) == 2
        assert results[0]["id"] == "e1"
        assert results[0]["score"] > results[1]["score"]
        await kg.close()

    @pytest.mark.asyncio
    async def test_falls_back_to_substring(
        self, tmp_path: Any,
    ) -> None:
        """Without embedding function, falls back to substring match."""
        db_path = tmp_path / "test.db"
        kg = KnowledgeGraphAdapter(db_path)
        await kg._ensure_db()
        db = kg._db
        assert db is not None
        await db.execute(
            _INSERT_NODE,
            ["e1", "auth", "CONCEPT", "authentication", "ws1"],
        )
        await db.execute(
            _INSERT_NODE,
            ["e2", "logging", "CONCEPT", "log system", "ws1"],
        )
        await db.commit()

        results = await kg.match_entities_by_embedding(
            "check auth handler", "ws1",
        )
        assert len(results) == 1
        assert results[0]["id"] == "e1"
        await kg.close()


# ---------------------------------------------------------------------------
# Step 2: Personalized PageRank
# ---------------------------------------------------------------------------


class TestPersonalizedPageRank:
    """ADR-050 D1: PPR replaces BFS with hop-decay."""

    @pytest.mark.asyncio
    async def test_seed_nodes_highest(self, tmp_path: Any) -> None:
        """Seed nodes should have the highest PPR score."""
        db_path = tmp_path / "test.db"
        kg = KnowledgeGraphAdapter(db_path)
        await kg._ensure_db()
        db = kg._db
        assert db is not None

        for eid, name in [("e1", "A"), ("e2", "B"), ("e3", "C")]:
            await db.execute(
                _INSERT_NODE_SHORT, [eid, name, "CONCEPT", "ws1"],
            )
        await db.execute(
            _INSERT_EDGE,
            ["edge1", "e1", "e2", "RELATED_TO", "ws1"],
        )
        await db.execute(
            _INSERT_EDGE,
            ["edge2", "e2", "e3", "RELATED_TO", "ws1"],
        )
        await db.commit()

        scores = await kg.personalized_pagerank(["e1"], "ws1")
        assert scores.get("e1", 0.0) == pytest.approx(1.0)
        assert scores.get("e2", 0.0) > scores.get("e3", 0.0)
        for v in scores.values():
            assert 0.0 <= v <= 1.0
        await kg.close()

    @pytest.mark.asyncio
    async def test_empty_seeds_returns_empty(
        self, tmp_path: Any,
    ) -> None:
        db_path = tmp_path / "test.db"
        kg = KnowledgeGraphAdapter(db_path)
        scores = await kg.personalized_pagerank([], "ws1")
        assert scores == {}
        await kg.close()


# ---------------------------------------------------------------------------
# Step 4: _search_vector populates graph proximity
# ---------------------------------------------------------------------------


class TestSearchVectorGraphProximity:
    """Wave 67.5: standard retrieval path gets real graph proximity."""

    @pytest.mark.asyncio
    async def test_populates_graph_proximity(self) -> None:
        """Non-thread results carry non-zero _graph_proximity."""
        mem_results = [
            {
                "id": "entry1", "entry_type": "skill",
                "status": "verified", "confidence": 0.8,
                "title": "Auth patterns", "summary": "JWT auth",
                "content": "...", "source_colony_id": "c1",
                "domains": ["auth"],
                "created_at": "2026-01-01T00:00:00+00:00",
                "conf_alpha": 10.0, "conf_beta": 2.0, "score": 0.9,
            },
        ]
        catalog = _make_catalog(
            memory_results=mem_results,
            kg_entities=[{
                "id": "kg1", "name": "AuthMiddleware",
                "entity_type": "MODULE", "score": 0.95,
            }],
            entry_kg_nodes={"entry1": "kg1"},
        )
        catalog._search_institutional = _mock_institutional(mem_results)  # type: ignore[method-assign]

        async def _mock_gs(
            query: str, workspace_id: str,
        ) -> dict[str, float]:
            return {"entry1": 0.85}

        catalog._compute_graph_scores = AsyncMock(side_effect=_mock_gs)  # type: ignore[method-assign]

        results = await catalog.search(
            "auth validation", workspace_id="ws1",
        )
        assert len(results) > 0
        assert results[0].get("_graph_proximity", 0.0) == pytest.approx(
            0.85,
        )

    @pytest.mark.asyncio
    async def test_emits_score_breakdown_parity(self) -> None:
        """Standard path results include _score_breakdown."""
        mem_results = [
            {
                "id": "entry1", "entry_type": "skill",
                "status": "verified", "confidence": 0.8,
                "title": "Test", "summary": "test", "content": "...",
                "source_colony_id": "c1", "domains": [],
                "created_at": "2026-01-01T00:00:00+00:00",
                "conf_alpha": 10.0, "conf_beta": 2.0, "score": 0.9,
            },
        ]
        catalog = _make_catalog(memory_results=mem_results)
        catalog._search_institutional = _mock_institutional(mem_results)  # type: ignore[method-assign]

        async def _mock_gs(
            query: str, workspace_id: str,
        ) -> dict[str, float]:
            return {"entry1": 0.42}

        catalog._compute_graph_scores = AsyncMock(side_effect=_mock_gs)  # type: ignore[method-assign]

        results = await catalog.search("test query", workspace_id="ws1")
        assert len(results) > 0
        breakdown = results[0].get("_score_breakdown")
        assert breakdown is not None
        assert breakdown["graph_proximity"] == pytest.approx(0.42)
        assert "semantic" in breakdown
        assert "thompson" in breakdown
        assert "weights" in breakdown


# ---------------------------------------------------------------------------
# Step 5: thread-boosted uses shared graph enrichment
# ---------------------------------------------------------------------------


class TestSearchThreadBoostedSharedHelper:
    """Wave 67.5: thread path uses shared _enrich_with_graph_scores."""

    @pytest.mark.asyncio
    async def test_uses_shared_graph_enrichment(self) -> None:
        """Thread retrieval calls _enrich_with_graph_scores."""
        mem_results = [
            {
                "id": "entry1", "entry_type": "skill",
                "status": "verified", "confidence": 0.8,
                "title": "Auth", "summary": "auth patterns",
                "content": "...", "source_colony_id": "c1",
                "domains": ["auth"],
                "created_at": "2026-01-01T00:00:00+00:00",
                "conf_alpha": 10.0, "conf_beta": 2.0, "score": 0.9,
            },
        ]
        catalog = _make_catalog(
            memory_results=mem_results,
            entry_kg_nodes={"entry1": "kg1"},
            entries={"entry1": mem_results[0]},
        )
        catalog._search_institutional = _mock_institutional(mem_results)  # type: ignore[method-assign]

        original_enrich = catalog._enrich_with_graph_scores
        catalog._enrich_with_graph_scores = AsyncMock(  # type: ignore[method-assign]
            side_effect=original_enrich,
        )

        await catalog.search(
            "auth validation",
            workspace_id="ws1",
            thread_id="thread1",
        )

        catalog._enrich_with_graph_scores.assert_awaited()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Graph scoring degrades gracefully when KG adapter is unavailable."""

    @pytest.mark.asyncio
    async def test_no_kg_adapter_returns_empty(self) -> None:
        """Without KG adapter, _compute_graph_scores returns {}."""
        catalog = KnowledgeCatalog(
            memory_store=None,
            vector_port=None,
            skill_collection="test",
            projections=None,
            kg_adapter=None,
        )
        scores = await catalog._compute_graph_scores("test query", "ws1")
        assert scores == {}

    @pytest.mark.asyncio
    async def test_enrich_with_no_seeds_returns_empty(self) -> None:
        """_enrich_with_graph_scores with empty seeds returns {}."""
        catalog = _make_catalog()
        scores = await catalog._enrich_with_graph_scores([], "ws1")
        assert scores == {}
