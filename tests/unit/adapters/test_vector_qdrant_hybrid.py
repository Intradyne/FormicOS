"""Tests for QdrantVectorPort hybrid search (Wave 13, ADR-019).

Verifies hybrid mode behavior: named vectors, two-branch prefetch + RRF fusion,
and fallback to dense-only when embed_client is absent.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import models

from formicos.adapters.vector_qdrant import QdrantVectorPort
from formicos.core.types import VectorDocument, VectorSearchHit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deterministic_embed(texts: list[str]) -> list[list[float]]:
    """Sync embed_fn: deterministic 8-dim vectors from text hash."""
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode()).digest()
        raw = list(struct.unpack("<8f", digest[:32]))
        mag = max(sum(x * x for x in raw) ** 0.5, 1e-9)
        vectors.append([x / mag for x in raw])
    return vectors


def _mock_embed_client() -> AsyncMock:
    """Create a mock Qwen3Embedder that returns 4-dim vectors."""
    client = AsyncMock()
    client.embed = AsyncMock(
        side_effect=lambda texts, is_query=False: [
            [0.1, 0.2, 0.3, 0.4] for _ in texts
        ],
    )
    return client


def _doc(id_: str, content: str, **meta: Any) -> VectorDocument:
    return VectorDocument(id=id_, content=content, metadata={"source": "test", **meta})


def _mock_scored_point(
    id_: str, content: str, score: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> MagicMock:
    point = MagicMock()
    point.id = id_
    point.score = score
    payload = {"text": content}
    if metadata:
        payload.update(metadata)
    point.payload = payload
    return point


def _mock_query_result(points: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.points = points
    return result


# ---------------------------------------------------------------------------
# Tests — Hybrid mode detection
# ---------------------------------------------------------------------------


class TestHybridModeDetection:
    """_hybrid_enabled property behavior."""

    def test_hybrid_enabled_with_embed_client(self) -> None:
        port = QdrantVectorPort(embed_client=_mock_embed_client())
        assert port._hybrid_enabled is True

    def test_hybrid_disabled_without_embed_client(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        assert port._hybrid_enabled is False

    def test_hybrid_enabled_when_both_provided(self) -> None:
        port = QdrantVectorPort(
            embed_fn=_deterministic_embed,
            embed_client=_mock_embed_client(),
        )
        assert port._hybrid_enabled is True


# ---------------------------------------------------------------------------
# Tests — Hybrid collection creation
# ---------------------------------------------------------------------------


class TestHybridCollectionCreation:
    """ensure_collection with hybrid mode creates named vector config."""

    @pytest.mark.anyio()
    async def test_creates_named_vectors_config(self) -> None:
        port = QdrantVectorPort(
            embed_client=_mock_embed_client(),
            vector_dimensions=1024,
        )
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("hybrid_col")

        call_kwargs = port._client.create_collection.call_args.kwargs
        # Named dense vector config
        assert "dense" in call_kwargs["vectors_config"]
        dense_cfg = call_kwargs["vectors_config"]["dense"]
        assert dense_cfg.size == 1024
        assert dense_cfg.distance == models.Distance.COSINE

    @pytest.mark.anyio()
    async def test_creates_sparse_vector_config(self) -> None:
        port = QdrantVectorPort(embed_client=_mock_embed_client())
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("hybrid_col")

        call_kwargs = port._client.create_collection.call_args.kwargs
        assert "sparse" in call_kwargs["sparse_vectors_config"]
        sparse_cfg = call_kwargs["sparse_vectors_config"]["sparse"]
        assert isinstance(sparse_cfg, models.SparseVectorParams)
        assert sparse_cfg.modifier == models.Modifier.IDF

    @pytest.mark.anyio()
    async def test_legacy_creates_unnamed_vector_config(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("legacy_col")

        call_kwargs = port._client.create_collection.call_args.kwargs
        # Unnamed vector config — VectorParams directly, not a dict
        assert isinstance(call_kwargs["vectors_config"], models.VectorParams)


# ---------------------------------------------------------------------------
# Tests — Hybrid upsert
# ---------------------------------------------------------------------------


class TestHybridUpsert:
    """Upsert with hybrid mode writes named vectors."""

    @pytest.mark.anyio()
    async def test_upsert_writes_named_vectors(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello hybrid")]
        count = await port.upsert("col", docs)

        assert count == 1
        call_kwargs = port._client.upsert.call_args.kwargs
        points = call_kwargs.get("points", [])
        vec = points[0].vector

        # Named vector: dense list + sparse Document
        assert "dense" in vec
        assert vec["dense"] == [0.1, 0.2, 0.3, 0.4]
        assert "sparse" in vec
        assert isinstance(vec["sparse"], models.Document)
        assert vec["sparse"].text == "hello hybrid"
        assert vec["sparse"].model == "Qdrant/bm25"

    @pytest.mark.anyio()
    async def test_upsert_legacy_writes_unnamed_vector(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello legacy")]
        await port.upsert("col", docs)

        call_kwargs = port._client.upsert.call_args.kwargs
        points = call_kwargs.get("points", [])
        vec = points[0].vector

        # Unnamed vector: plain list of floats
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)

    @pytest.mark.anyio()
    async def test_hybrid_upsert_embed_client_called_as_document(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "skill A"), _doc("d2", "skill B")]
        await port.upsert("col", docs)

        embed_client.embed.assert_awaited_once_with(
            ["skill A", "skill B"], is_query=False,
        )


# ---------------------------------------------------------------------------
# Tests — Hybrid search
# ---------------------------------------------------------------------------


class TestHybridSearch:
    """Hybrid search uses two-branch prefetch + RRF fusion."""

    @pytest.mark.anyio()
    async def test_hybrid_search_calls_query_points_with_prefetch(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([
                _mock_scored_point("d1", "result", 0.9),
            ]),
        )

        hits = await port.search("col", "find something", top_k=5)

        assert len(hits) == 1
        assert hits[0].id == "d1"

        # Verify query_points was called with prefetch branches
        call_kwargs = port._client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "col"
        assert call_kwargs["limit"] == 5
        assert call_kwargs["with_payload"] is True

        # Two prefetch branches
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 2

        # Dense branch
        dense_pf = prefetch[0]
        assert dense_pf.using == "dense"
        assert dense_pf.query == [0.1, 0.2, 0.3, 0.4]

        # Sparse BM25 branch
        sparse_pf = prefetch[1]
        assert sparse_pf.using == "sparse"
        assert isinstance(sparse_pf.query, models.Document)
        assert sparse_pf.query.text == "find something"
        assert sparse_pf.query.model == "Qdrant/bm25"

    @pytest.mark.anyio()
    async def test_hybrid_search_uses_rrf_fusion(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([]),
        )

        await port.search("col", "query", top_k=3)

        call_kwargs = port._client.query_points.call_args.kwargs
        fusion_query = call_kwargs["query"]
        assert isinstance(fusion_query, models.FusionQuery)
        assert fusion_query.fusion == models.Fusion.RRF

    @pytest.mark.anyio()
    async def test_hybrid_search_overfetches(self) -> None:
        """Prefetch branches should overfetch (top_k * 4) for fusion quality."""
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([]),
        )

        await port.search("col", "query", top_k=5)

        call_kwargs = port._client.query_points.call_args.kwargs
        for pf in call_kwargs["prefetch"]:
            assert pf.limit == 20  # 5 * 4

    @pytest.mark.anyio()
    async def test_hybrid_search_embed_client_called_as_query(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([]),
        )

        await port.search("col", "my query")

        embed_client.embed.assert_awaited_once_with(
            ["my query"], is_query=True,
        )

    @pytest.mark.anyio()
    async def test_legacy_search_no_prefetch(self) -> None:
        """Dense-only search should NOT use prefetch or fusion."""
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([
                _mock_scored_point("d1", "result", 0.8),
            ]),
        )

        hits = await port.search("col", "query", top_k=3)

        assert len(hits) == 1
        call_kwargs = port._client.query_points.call_args.kwargs
        # No prefetch in legacy mode
        assert "prefetch" not in call_kwargs
        # Query is a plain vector, not a FusionQuery
        assert isinstance(call_kwargs["query"], list)


# ---------------------------------------------------------------------------
# Tests — Hybrid graceful degradation
# ---------------------------------------------------------------------------


class TestHybridGracefulDegradation:
    """Hybrid mode degrades gracefully on failures."""

    @pytest.mark.anyio()
    async def test_search_with_empty_embed_result(self) -> None:
        embed_client = AsyncMock()
        embed_client.embed = AsyncMock(return_value=[])
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()

        hits = await port.search("col", "query")
        assert hits == []

    @pytest.mark.anyio()
    async def test_no_embed_fn_no_embed_client(self) -> None:
        port = QdrantVectorPort()  # neither provided
        port._collections_ensured.add("col")
        port._client = AsyncMock()

        hits = await port.search("col", "query")
        assert hits == []

        count = await port.upsert("col", [_doc("d1", "hello")])
        assert count == 0

    @pytest.mark.anyio()
    async def test_hybrid_search_qdrant_error(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        hits = await port.search("col", "query")
        assert hits == []

    @pytest.mark.anyio()
    async def test_hybrid_upsert_qdrant_error(self) -> None:
        embed_client = _mock_embed_client()
        port = QdrantVectorPort(embed_client=embed_client)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        count = await port.upsert("col", [_doc("d1", "hello")])
        assert count == 0


# ---------------------------------------------------------------------------
# Tests — embed_client takes precedence
# ---------------------------------------------------------------------------


class TestEmbedClientPrecedence:
    """When both embed_fn and embed_client are provided, embed_client wins."""

    @pytest.mark.anyio()
    async def test_embed_client_used_over_embed_fn(self) -> None:
        sync_called = False

        def sync_embed(texts: list[str]) -> list[list[float]]:
            nonlocal sync_called
            sync_called = True
            return [[0.0] * 4 for _ in texts]

        embed_client = _mock_embed_client()
        port = QdrantVectorPort(
            embed_fn=sync_embed,
            embed_client=embed_client,
        )
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([]),
        )

        await port.search("col", "query")

        assert sync_called is False
        embed_client.embed.assert_awaited_once()
