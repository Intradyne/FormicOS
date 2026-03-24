"""Unit tests for KnowledgeGraphAdapter — CRUD, entity resolution, BFS."""

from __future__ import annotations

import pytest

from formicos.adapters.knowledge_graph import (
    KnowledgeGraphAdapter,
    _cosine_similarity,
    _normalize,
)
from formicos.engine.runner import _extract_kg_tuples

WS = "test-workspace"


@pytest.fixture
async def kg(tmp_path):
    """Create a KnowledgeGraphAdapter backed by a temp SQLite file."""
    adapter = KnowledgeGraphAdapter(db_path=tmp_path / "test.db")
    yield adapter
    await adapter.close()


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalize_underscores():
    assert _normalize("FastAPI_router") == "fastapi router"


def test_normalize_whitespace():
    assert _normalize("  hello   world  ") == "hello world"


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entity(kg):
    eid = await kg._create_entity("FastAPI", "MODULE", WS)
    assert isinstance(eid, str) and len(eid) > 0


@pytest.mark.asyncio
async def test_find_by_name_exact(kg):
    eid = await kg._create_entity("fastapi_router", "MODULE", WS)
    found = await kg._find_by_name("fastapi router", WS)
    assert found == eid


@pytest.mark.asyncio
async def test_find_by_name_miss(kg):
    await kg._create_entity("fastapi_router", "MODULE", WS)
    found = await kg._find_by_name("django_view", WS)
    assert found is None


@pytest.mark.asyncio
async def test_resolve_entity_dedup(kg):
    """resolve_entity should return the same ID for normalized-equivalent names."""
    id1 = await kg.resolve_entity("FastAPI_router", "MODULE", WS)
    id2 = await kg.resolve_entity("fastapi router", "MODULE", WS)
    assert id1 == id2


@pytest.mark.asyncio
async def test_resolve_entity_different_workspace(kg):
    """Different workspaces get different entities."""
    id1 = await kg.resolve_entity("FastAPI", "MODULE", "ws1")
    id2 = await kg.resolve_entity("FastAPI", "MODULE", "ws2")
    assert id1 != id2


# ---------------------------------------------------------------------------
# Entity resolution with embeddings
# ---------------------------------------------------------------------------


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Produce embeddings where similar names get similar vectors."""
    results = []
    for t in texts:
        normalized = t.lower().replace("_", " ").strip()
        # Crude: hash-based 4-dim vectors
        h = hash(normalized)
        vec = [(h >> i & 0xFF) / 255.0 for i in range(0, 32, 8)]
        norm = sum(x * x for x in vec) ** 0.5
        results.append([x / norm for x in vec] if norm > 0 else vec)
    return results


@pytest.fixture
async def kg_embed(tmp_path):
    adapter = KnowledgeGraphAdapter(
        db_path=tmp_path / "test_embed.db",
        embed_fn=_fake_embed,
        similarity_threshold=0.85,
    )
    yield adapter
    await adapter.close()


@pytest.mark.asyncio
async def test_resolve_with_embedding_exact_still_works(kg_embed):
    """Even with embed_fn, exact match takes precedence."""
    id1 = await kg_embed.resolve_entity("Router", "MODULE", WS)
    id2 = await kg_embed.resolve_entity("router", "MODULE", WS)
    assert id1 == id2


# ---------------------------------------------------------------------------
# Edge CRUD (bi-temporal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_edge(kg):
    n1 = await kg._create_entity("ModuleA", "MODULE", WS)
    n2 = await kg._create_entity("ModuleB", "MODULE", WS)
    edge_id = await kg.add_edge(n1, n2, "DEPENDS_ON", WS)
    assert isinstance(edge_id, str) and len(edge_id) > 0


@pytest.mark.asyncio
async def test_edge_invalidation_on_update(kg):
    """Adding a new edge with the same triple invalidates the old one."""
    n1 = await kg._create_entity("A", "MODULE", WS)
    n2 = await kg._create_entity("B", "MODULE", WS)

    e1 = await kg.add_edge(n1, n2, "DEPENDS_ON", WS, confidence=0.5)
    e2 = await kg.add_edge(n1, n2, "DEPENDS_ON", WS, confidence=0.9)

    # Only the new edge should appear in neighbors
    neighbors = await kg.get_neighbors(n1, workspace_id=WS)
    edge_ids = [n["id"] for n in neighbors]
    assert e2 in edge_ids
    assert e1 not in edge_ids


@pytest.mark.asyncio
async def test_invalidate_edge(kg):
    n1 = await kg._create_entity("X", "CONCEPT", WS)
    n2 = await kg._create_entity("Y", "CONCEPT", WS)
    edge_id = await kg.add_edge(n1, n2, "ENABLES", WS)

    await kg.invalidate_edge(edge_id)
    neighbors = await kg.get_neighbors(n1, workspace_id=WS)
    assert len(neighbors) == 0


# ---------------------------------------------------------------------------
# BFS / get_neighbors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_neighbors_basic(kg):
    n1 = await kg._create_entity("Auth", "MODULE", WS)
    n2 = await kg._create_entity("Session", "CONCEPT", WS)
    n3 = await kg._create_entity("Token", "CONCEPT", WS)

    await kg.add_edge(n1, n2, "IMPLEMENTS", WS)
    await kg.add_edge(n1, n3, "DEPENDS_ON", WS)

    neighbors = await kg.get_neighbors(n1, workspace_id=WS)
    assert len(neighbors) == 2
    predicates = {n["predicate"] for n in neighbors}
    assert predicates == {"IMPLEMENTS", "DEPENDS_ON"}


@pytest.mark.asyncio
async def test_get_neighbors_bidirectional(kg):
    """get_neighbors returns edges where entity is either from or to."""
    n1 = await kg._create_entity("A", "MODULE", WS)
    n2 = await kg._create_entity("B", "MODULE", WS)

    await kg.add_edge(n1, n2, "ENABLES", WS)

    # Query from the "to" side
    neighbors = await kg.get_neighbors(n2, workspace_id=WS)
    assert len(neighbors) == 1
    assert neighbors[0]["subject"] == "A"
    assert neighbors[0]["object"] == "B"


@pytest.mark.asyncio
async def test_get_neighbors_workspace_filter(kg):
    n1 = await kg._create_entity("A", "MODULE", "ws1")
    n2 = await kg._create_entity("B", "MODULE", "ws1")
    n3 = await kg._create_entity("C", "MODULE", "ws2")

    await kg.add_edge(n1, n2, "DEPENDS_ON", "ws1")
    # Create in ws2 separately
    n4 = await kg._create_entity("A", "MODULE", "ws2")
    await kg.add_edge(n4, n3, "DEPENDS_ON", "ws2")

    ws1_neighbors = await kg.get_neighbors(n1, workspace_id="ws1")
    assert len(ws1_neighbors) == 1


# ---------------------------------------------------------------------------
# search_entities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_entities(kg):
    await kg._create_entity("FastAPI", "MODULE", WS)
    await kg._create_entity("SQLAlchemy", "MODULE", WS)

    results = await kg.search_entities("I need to fix the FastAPI router", WS)
    assert len(results) == 1
    assert results[0]["name"] == "FastAPI"


@pytest.mark.asyncio
async def test_search_entities_no_match(kg):
    await kg._create_entity("FastAPI", "MODULE", WS)
    results = await kg.search_entities("Django views are broken", WS)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Tuple ingestion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_tuples(kg):
    tuples = [
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
            "object": "FeatureX",
            "subject_type": "MODULE",
            "object_type": "CONCEPT",
        },
    ]
    count = await kg.ingest_tuples(tuples, WS, source_colony="c1", source_round=1)
    assert count == 2

    stats = await kg.stats(WS)
    assert stats["nodes"] == 3  # ModuleA, ModuleB, FeatureX
    assert stats["edges"] == 2


@pytest.mark.asyncio
async def test_ingest_tuples_skips_unknown_predicate(kg):
    tuples = [
        {
            "subject": "A",
            "predicate": "UNKNOWN_PRED",
            "object": "B",
        },
    ]
    count = await kg.ingest_tuples(tuples, WS)
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_tuples_dedup_entities(kg):
    """Ingesting tuples with the same entity name should not create duplicates."""
    tuples = [
        {"subject": "FastAPI", "predicate": "DEPENDS_ON", "object": "Starlette",
         "subject_type": "MODULE", "object_type": "MODULE"},
        {"subject": "fastapi", "predicate": "ENABLES", "object": "REST API",
         "subject_type": "MODULE", "object_type": "CONCEPT"},
    ]
    count = await kg.ingest_tuples(tuples, WS)
    assert count == 2

    stats = await kg.stats(WS)
    # "FastAPI" and "fastapi" should resolve to the same entity
    assert stats["nodes"] == 3  # FastAPI, Starlette, REST API


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_empty(kg):
    stats = await kg.stats(WS)
    assert stats == {"nodes": 0, "edges": 0}


@pytest.mark.asyncio
async def test_stats_global(kg):
    await kg._create_entity("A", "MODULE", "ws1")
    await kg._create_entity("B", "MODULE", "ws2")
    stats = await kg.stats()
    assert stats["nodes"] == 2


# ---------------------------------------------------------------------------
# KG tuple extraction (runner helper)
# ---------------------------------------------------------------------------


def test_extract_tuples_json_array():
    text = '[{"subject": "A", "predicate": "DEPENDS_ON", "object": "B"}]'
    result = _extract_kg_tuples(text)
    assert len(result) == 1
    assert result[0]["subject"] == "A"
    assert result[0]["predicate"] == "DEPENDS_ON"
    assert result[0]["object"] == "B"


def test_extract_tuples_with_types():
    text = '[{"subject": "Router", "predicate": "IMPLEMENTS", "object": "API", "subject_type": "MODULE", "object_type": "CONCEPT"}]'
    result = _extract_kg_tuples(text)
    assert result[0]["subject_type"] == "MODULE"
    assert result[0]["object_type"] == "CONCEPT"


def test_extract_tuples_embedded_in_prose():
    text = 'Here are the relationships: {"subject": "Auth", "predicate": "ENABLES", "object": "Login"} and more text.'
    result = _extract_kg_tuples(text)
    assert len(result) == 1
    assert result[0]["subject"] == "Auth"


def test_extract_tuples_empty():
    assert _extract_kg_tuples("No tuples here") == []


def test_extract_tuples_defaults_type():
    text = '[{"subject": "X", "predicate": "VALIDATES", "object": "Y"}]'
    result = _extract_kg_tuples(text)
    assert result[0]["subject_type"] == "CONCEPT"
    assert result[0]["object_type"] == "CONCEPT"


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical():
    assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector():
    assert _cosine_similarity([0, 0], [1, 1]) == 0.0
