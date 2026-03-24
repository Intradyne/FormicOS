"""Unit tests for QdrantVectorPort adapter (ADR-013).

Uses a mock AsyncQdrantClient to test adapter behavior without a live Qdrant.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.adapters.vector_qdrant import QdrantVectorPort
from formicos.core.types import VectorDocument, VectorSearchHit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deterministic_embed(texts: list[str]) -> list[list[float]]:
    """Return a deterministic 8-dim unit vector derived from each text's hash."""
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode()).digest()
        raw = list(struct.unpack("<8f", digest[:32]))
        mag = max(sum(x * x for x in raw) ** 0.5, 1e-9)
        vectors.append([x / mag for x in raw])
    return vectors


def _doc(id_: str, content: str, **meta: Any) -> VectorDocument:
    return VectorDocument(
        id=id_, content=content,
        metadata={"source": "test", **meta},
    )


def _mock_scored_point(
    id_: str, content: str, score: float = 0.1,
    metadata: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock ScoredPoint like Qdrant returns."""
    point = MagicMock()
    point.id = id_
    point.score = score
    payload = {"text": content}
    if metadata:
        payload.update(metadata)
    point.payload = payload
    return point


def _mock_query_result(points: list[MagicMock]) -> MagicMock:
    """Create a mock QueryResponse."""
    result = MagicMock()
    result.points = points
    return result


# ---------------------------------------------------------------------------
# Tests — Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """QdrantVectorPort construction and config."""

    def test_default_construction(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        assert port._dimensions == 384
        assert port._default_collection == "skill_bank"

    def test_custom_dimensions(self) -> None:
        port = QdrantVectorPort(
            embed_fn=_deterministic_embed,
            vector_dimensions=1024,
        )
        assert port._dimensions == 1024


# ---------------------------------------------------------------------------
# Tests — ensure_collection
# ---------------------------------------------------------------------------


class TestEnsureCollection:
    """Collection creation and idempotency."""

    @pytest.mark.anyio()
    async def test_ensure_collection_creates_new(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("test_col")

        port._client.create_collection.assert_awaited_once()
        assert "test_col" in port._collections_ensured

    @pytest.mark.anyio()
    async def test_ensure_collection_idempotent(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=True)
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("test_col")
        await port.ensure_collection("test_col")  # second call should skip

        # create_collection should NOT be called (collection already exists)
        port._client.create_collection.assert_not_awaited()

    @pytest.mark.anyio()
    async def test_ensure_collection_creates_payload_indexes(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(return_value=False)
        port._client.create_collection = AsyncMock()
        port._client.create_payload_index = AsyncMock()

        await port.ensure_collection("test_col")

        # Should create 6 payload indexes
        assert port._client.create_payload_index.await_count == 6


# ---------------------------------------------------------------------------
# Tests — search
# ---------------------------------------------------------------------------


class TestSearch:
    """VectorPort.search() implementation."""

    @pytest.mark.anyio()
    async def test_search_returns_hits(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("test_col")  # skip ensure_collection
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(return_value=_mock_query_result([
            _mock_scored_point("d1", "hello world", 0.1),
            _mock_scored_point("d2", "goodbye world", 0.3),
        ]))

        hits = await port.search("test_col", "hello", top_k=5)

        assert len(hits) == 2
        assert hits[0].id == "d1"
        assert hits[0].content == "hello world"
        assert hits[0].score == 0.1
        assert hits[1].id == "d2"

    @pytest.mark.anyio()
    async def test_search_empty_collection(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("empty")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(
            return_value=_mock_query_result([]),
        )

        hits = await port.search("empty", "anything")
        assert hits == []

    @pytest.mark.anyio()
    async def test_search_no_embed_fn(self) -> None:
        port = QdrantVectorPort(embed_fn=None)
        port._collections_ensured.add("col")
        port._client = AsyncMock()

        hits = await port.search("col", "query")
        assert hits == []

    @pytest.mark.anyio()
    async def test_search_preserves_metadata(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.query_points = AsyncMock(return_value=_mock_query_result([
            _mock_scored_point(
                "d1", "skill text",
                metadata={"confidence": 0.8, "source_colony": "col-abc"},
            ),
        ]))

        hits = await port.search("col", "query")
        assert hits[0].metadata["confidence"] == 0.8
        assert hits[0].metadata["source_colony"] == "col-abc"


# ---------------------------------------------------------------------------
# Tests — upsert
# ---------------------------------------------------------------------------


class TestUpsert:
    """VectorPort.upsert() implementation."""

    @pytest.mark.anyio()
    async def test_upsert_returns_count(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello"), _doc("d2", "world")]
        count = await port.upsert("col", docs)

        assert count == 2
        port._client.upsert.assert_awaited_once()

    @pytest.mark.anyio()
    async def test_upsert_empty_docs(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()

        count = await port.upsert("col", [])
        assert count == 0

    @pytest.mark.anyio()
    async def test_upsert_no_embed_fn(self) -> None:
        port = QdrantVectorPort(embed_fn=None)
        port._collections_ensured.add("col")
        port._client = AsyncMock()

        count = await port.upsert("col", [_doc("d1", "hello")])
        assert count == 0

    @pytest.mark.anyio()
    async def test_upsert_includes_namespace_in_payload(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello", namespace="ws-1")]
        await port.upsert("col", docs)

        call_args = port._client.upsert.call_args
        points = call_args.kwargs.get("points", call_args[1].get("points", []))
        assert points[0].payload["namespace"] == "ws-1"


# ---------------------------------------------------------------------------
# Tests — delete
# ---------------------------------------------------------------------------


class TestDelete:
    """VectorPort.delete() implementation."""

    @pytest.mark.anyio()
    async def test_delete_returns_count(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("col")
        port._client = AsyncMock()
        port._client.delete = AsyncMock()

        count = await port.delete("col", ["d1", "d2"])
        assert count == 2

    @pytest.mark.anyio()
    async def test_delete_empty_ids(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        count = await port.delete("col", [])
        assert count == 0


# ---------------------------------------------------------------------------
# Tests — Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Qdrant unavailable → empty results, no crash."""

    @pytest.mark.anyio()
    async def test_search_on_connection_failure(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        hits = await port.search("col", "query")
        assert hits == []

    @pytest.mark.anyio()
    async def test_upsert_on_connection_failure(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )
        port._client.upsert = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        count = await port.upsert("col", [_doc("d1", "hello")])
        assert count == 0

    @pytest.mark.anyio()
    async def test_delete_on_connection_failure(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )
        port._client.delete = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        count = await port.delete("col", ["d1"])
        assert count == 0

    @pytest.mark.anyio()
    async def test_ensure_collection_on_failure(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._client = AsyncMock()
        port._client.collection_exists = AsyncMock(
            side_effect=ConnectionError("Qdrant down"),
        )

        # Should not raise
        await port.ensure_collection("col")
        assert "col" not in port._collections_ensured


# ---------------------------------------------------------------------------
# Tests — Namespace isolation
# ---------------------------------------------------------------------------


class TestNamespaceIsolation:
    """Namespace field is set correctly on upsert."""

    @pytest.mark.anyio()
    async def test_default_namespace_is_collection_name(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello")]  # no explicit namespace
        await port.upsert("skill_bank", docs)

        call_args = port._client.upsert.call_args
        points = call_args.kwargs.get("points", call_args[1].get("points", []))
        assert points[0].payload["namespace"] == "skill_bank"

    @pytest.mark.anyio()
    async def test_explicit_namespace_preserved(self) -> None:
        port = QdrantVectorPort(embed_fn=_deterministic_embed)
        port._collections_ensured.add("skill_bank")
        port._client = AsyncMock()
        port._client.upsert = AsyncMock()

        docs = [_doc("d1", "hello", namespace="workspace-42")]
        await port.upsert("skill_bank", docs)

        call_args = port._client.upsert.call_args
        points = call_args.kwargs.get("points", call_args[1].get("points", []))
        assert points[0].payload["namespace"] == "workspace-42"
