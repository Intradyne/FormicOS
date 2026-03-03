"""
Tests for FormicOS v0.6.0 RAG Engine.

Covers:
1.  embed returns correct dimensions
2.  embed batches large input
3.  embed retries with smaller batch on timeout
4.  ingest_document chunks text and upserts
5.  ingest_text stores single chunk
6.  ingest_epoch stores epoch summary
7.  search returns ranked results
8.  search with filters
9.  search_swarm_memory queries correct collection
10. ensure_collection creates collection
11. create_colony_namespace names collection correctly
12. delete_colony_namespace removes collection
13. Qdrant unavailable returns empty results
14. Embedding server down logs warning
15. SearchResult dataclass fields

All external dependencies (httpx, qdrant_client) are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models import EmbeddingConfig, QdrantConfig, QdrantCollectionConfig
from src.rag import (
    CHARS_PER_TOKEN,
    DEFAULT_CHUNK_SIZE,
    SWARM_MEMORY_COLLECTION,
    RAGEngine,
    SearchResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_qdrant_config(**overrides: Any) -> QdrantConfig:
    """Build a QdrantConfig with test-friendly defaults."""
    defaults = dict(
        host="localhost",
        port=6333,
        grpc_port=6334,
        collections={
            "project_docs": QdrantCollectionConfig(
                embedding="bge-m3", dimensions=1024
            ),
            "swarm_memory": QdrantCollectionConfig(
                embedding="bge-m3", dimensions=1024
            ),
        },
    )
    defaults.update(overrides)
    return QdrantConfig(**defaults)


def _make_embedding_config(**overrides: Any) -> EmbeddingConfig:
    """Build an EmbeddingConfig with test-friendly defaults."""
    defaults = dict(
        model="BAAI/bge-m3",
        endpoint="http://localhost:8081/v1",
        dimensions=1024,
        max_tokens=8192,
        batch_size=4,
        routing_model="all-MiniLM-L6-v2",
    )
    defaults.update(overrides)
    return EmbeddingConfig(**defaults)


def _fake_embedding(dims: int = 1024, seed: float = 0.1) -> list[float]:
    """Generate a deterministic fake embedding vector."""
    return [seed + i * 0.001 for i in range(dims)]


def _make_httpx_embedding_response(
    embeddings: list[list[float]],
) -> httpx.Response:
    """Build a mock httpx.Response matching OpenAI embeddings format."""
    data = [
        {"embedding": emb, "index": idx}
        for idx, emb in enumerate(embeddings)
    ]
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {"data": data}
    response.raise_for_status = MagicMock()
    return response


def _make_scored_point(
    point_id: str,
    score: float,
    payload: dict[str, Any],
) -> SimpleNamespace:
    """Create a mock Qdrant scored point."""
    return SimpleNamespace(
        id=point_id,
        score=score,
        payload=dict(payload),  # copy so pop() in RAG doesn't affect original
    )


def _make_query_response(
    points: list[SimpleNamespace],
) -> SimpleNamespace:
    """Create a mock Qdrant query_points() response."""
    return SimpleNamespace(points=points)


def _make_collections_response(
    names: list[str],
) -> SimpleNamespace:
    """Create a mock Qdrant get_collections() response."""
    collections = [SimpleNamespace(name=n) for n in names]
    return SimpleNamespace(collections=collections)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def qdrant_config() -> QdrantConfig:
    return _make_qdrant_config()


@pytest.fixture
def embedding_config() -> EmbeddingConfig:
    return _make_embedding_config()


@pytest.fixture
def engine(qdrant_config, embedding_config) -> RAGEngine:
    """Create a RAGEngine with a mocked Qdrant client."""
    with patch("src.rag.QDRANT_AVAILABLE", True):
        eng = RAGEngine(qdrant_config, embedding_config)
    # Replace the real Qdrant client with a mock
    eng._qdrant = AsyncMock()
    return eng


@pytest.fixture
def engine_no_qdrant(qdrant_config, embedding_config) -> RAGEngine:
    """Create a RAGEngine where Qdrant server is unreachable."""
    with patch("src.rag.QDRANT_AVAILABLE", True):
        eng = RAGEngine(qdrant_config, embedding_config)
    # Simulate Qdrant server being unreachable (client creation failed)
    eng._qdrant = None
    return eng


# ═══════════════════════════════════════════════════════════════════════════
# 1. embed returns correct dimensions
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbedDimensions:
    @pytest.mark.asyncio
    async def test_embed_returns_correct_dimensions(self, engine):
        """embed() returns vectors with the configured dimensionality."""
        dims = engine._embedding_config.dimensions
        fake_emb = _fake_embedding(dims)
        response = _make_httpx_embedding_response([fake_emb])

        engine._http.post = AsyncMock(return_value=response)

        result = await engine.embed(["test text"])
        assert len(result) == 1
        assert len(result[0]) == dims

    @pytest.mark.asyncio
    async def test_embed_empty_input(self, engine):
        """embed() returns empty list for empty input."""
        result = await engine.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self, engine):
        """embed() returns one vector per input text."""
        dims = engine._embedding_config.dimensions
        fake_embs = [_fake_embedding(dims, seed=i * 0.1) for i in range(3)]
        response = _make_httpx_embedding_response(fake_embs)

        engine._http.post = AsyncMock(return_value=response)

        result = await engine.embed(["text1", "text2", "text3"])
        assert len(result) == 3
        for vec in result:
            assert len(vec) == dims


# ═══════════════════════════════════════════════════════════════════════════
# 2. embed batches large input
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbedBatching:
    @pytest.mark.asyncio
    async def test_embed_batches_large_input(self, engine):
        """embed() splits input into batches of batch_size."""
        dims = engine._embedding_config.dimensions
        _batch_size = engine._embedding_config.batch_size  # 4
        num_texts = 10
        texts = [f"text {i}" for i in range(num_texts)]

        call_count = 0
        received_batches: list[int] = []

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            batch_texts = json["input"]
            received_batches.append(len(batch_texts))
            fake_embs = [
                _fake_embedding(dims, seed=i * 0.01)
                for i in range(len(batch_texts))
            ]
            return _make_httpx_embedding_response(fake_embs)

        engine._http.post = mock_post

        result = await engine.embed(texts)
        assert len(result) == num_texts
        # 10 texts with batch_size=4 -> 3 batches: [4, 4, 2]
        assert call_count == 3
        assert received_batches == [4, 4, 2]


# ═══════════════════════════════════════════════════════════════════════════
# 3. embed retries with smaller batch on timeout
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbedRetry:
    @pytest.mark.asyncio
    async def test_embed_retries_on_timeout(self, engine):
        """embed() halves batch size and retries on TimeoutException."""
        dims = engine._embedding_config.dimensions
        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            batch = json["input"]
            # First call (full batch) times out, subsequent succeed
            if len(batch) > 2:
                raise httpx.TimeoutException("read timeout")
            fake_embs = [
                _fake_embedding(dims, seed=i * 0.01)
                for i in range(len(batch))
            ]
            return _make_httpx_embedding_response(fake_embs)

        engine._http.post = mock_post

        result = await engine.embed(["a", "b", "c", "d"])
        assert len(result) == 4
        # First call fails (batch=4), then retries with batch=2 (2 calls)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_embed_retries_on_http_status_error(self, engine):
        """embed() retries with smaller batch on HTTPStatusError."""
        dims = engine._embedding_config.dimensions
        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            batch = json["input"]
            if len(batch) > 1 and call_count == 1:
                resp = MagicMock(spec=httpx.Response)
                resp.status_code = 500
                resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "server error",
                    request=MagicMock(),
                    response=resp,
                )
                return resp
            fake_embs = [
                _fake_embedding(dims) for _ in range(len(batch))
            ]
            return _make_httpx_embedding_response(fake_embs)

        engine._http.post = mock_post

        result = await engine.embed(["a", "b"])
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 4. ingest_document chunks text and upserts
# ═══════════════════════════════════════════════════════════════════════════


class TestIngestDocument:
    @pytest.mark.asyncio
    async def test_ingest_document_chunks_and_upserts(
        self, engine, tmp_path
    ):
        """ingest_document() reads file, chunks, embeds, and upserts."""
        dims = engine._embedding_config.dimensions
        # Create a text file large enough for multiple chunks
        char_chunk = DEFAULT_CHUNK_SIZE * CHARS_PER_TOKEN  # 2048 chars
        text = "A" * (char_chunk * 3)  # 3 chunks worth
        doc = tmp_path / "test.txt"
        doc.write_text(text, encoding="utf-8")

        # Mock embedding
        async def mock_post(url, json=None, **kwargs):
            batch = json["input"]
            embs = [_fake_embedding(dims) for _ in range(len(batch))]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post

        # Mock Qdrant
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()
        engine._qdrant.upsert = AsyncMock()

        count = await engine.ingest_document(doc, "test_collection")
        assert count > 0
        engine._qdrant.upsert.assert_awaited_once()

        # Verify upsert received points with correct metadata
        call_args = engine._qdrant.upsert.call_args
        assert call_args.kwargs["collection_name"] == "test_collection"
        points = call_args.kwargs["points"]
        assert len(points) == count
        for pt in points:
            assert "content" in pt.payload
            assert "source" in pt.payload
            assert "chunk_index" in pt.payload

    @pytest.mark.asyncio
    async def test_ingest_document_missing_file(self, engine, tmp_path):
        """ingest_document() returns 0 for a nonexistent file."""
        count = await engine.ingest_document(
            tmp_path / "no_such_file.txt", "col"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_ingest_document_empty_file(self, engine, tmp_path):
        """ingest_document() returns 0 for an empty file."""
        doc = tmp_path / "empty.txt"
        doc.write_text("", encoding="utf-8")
        count = await engine.ingest_document(doc, "col")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. ingest_text stores single chunk
# ═══════════════════════════════════════════════════════════════════════════


class TestIngestText:
    @pytest.mark.asyncio
    async def test_ingest_text_stores_single_chunk(self, engine):
        """ingest_text() embeds the text and upserts one point."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            batch = json["input"]
            embs = [_fake_embedding(dims) for _ in range(len(batch))]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()
        engine._qdrant.upsert = AsyncMock()

        await engine.ingest_text("hello world", "doc_42", "my_collection")

        engine._qdrant.upsert.assert_awaited_once()
        call_args = engine._qdrant.upsert.call_args
        points = call_args.kwargs["points"]
        assert len(points) == 1
        assert points[0].payload["content"] == "hello world"
        assert points[0].payload["doc_id"] == "doc_42"


# ═══════════════════════════════════════════════════════════════════════════
# 6. ingest_epoch stores epoch summary
# ═══════════════════════════════════════════════════════════════════════════


class TestIngestEpoch:
    @pytest.mark.asyncio
    async def test_ingest_epoch_stores_summary(self, engine):
        """ingest_epoch() stores epoch summary in swarm_memory collection."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            batch = json["input"]
            embs = [_fake_embedding(dims) for _ in range(len(batch))]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()
        engine._qdrant.upsert = AsyncMock()

        await engine.ingest_epoch(3, "Epoch 3 summary text", "session_abc")

        engine._qdrant.upsert.assert_awaited_once()
        call_args = engine._qdrant.upsert.call_args
        assert call_args.kwargs["collection_name"] == SWARM_MEMORY_COLLECTION
        points = call_args.kwargs["points"]
        assert len(points) == 1
        assert points[0].payload["content"] == "Epoch 3 summary text"
        assert points[0].payload["epoch_id"] == 3
        assert points[0].payload["session_id"] == "session_abc"
        assert points[0].payload["type"] == "epoch_summary"


# ═══════════════════════════════════════════════════════════════════════════
# 7. search returns ranked results
# ═══════════════════════════════════════════════════════════════════════════


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_returns_ranked_results(self, engine):
        """search() embeds query and returns results ranked by score."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post

        mock_points = [
            _make_scored_point(
                "p1", 0.95, {"content": "highly relevant", "source": "a.txt"}
            ),
            _make_scored_point(
                "p2", 0.70, {"content": "somewhat relevant", "source": "b.txt"}
            ),
            _make_scored_point(
                "p3", 0.40, {"content": "barely relevant", "source": "c.txt"}
            ),
        ]
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response(mock_points)
        )

        results = await engine.search("test query", "project_docs", top_k=3)
        assert len(results) == 3
        assert results[0].score == 0.95
        assert results[0].content == "highly relevant"
        assert results[1].score == 0.70
        assert results[2].score == 0.40

    @pytest.mark.asyncio
    async def test_search_metadata_excludes_content(self, engine):
        """search() separates content from metadata in SearchResult."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post

        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response(
                [
                    _make_scored_point(
                        "p1",
                        0.9,
                        {"content": "body text", "source": "doc.md", "chunk_index": 2},
                    )
                ]
            )
        )

        results = await engine.search("q", "col")
        assert results[0].content == "body text"
        assert "source" in results[0].metadata
        assert "content" not in results[0].metadata

    @pytest.mark.asyncio
    async def test_search_empty_collection(self, engine):
        """search() returns empty list when collection has no matches."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response([])
        )

        results = await engine.search("q", "empty_col")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. search with filters
# ═══════════════════════════════════════════════════════════════════════════


class TestSearchWithFilters:
    @pytest.mark.asyncio
    async def test_search_passes_filter_to_qdrant(self, engine):
        """search() converts filter dict to Qdrant Filter object."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response([])
        )

        await engine.search(
            "q", "col", filter={"session_id": "s1", "type": "epoch_summary"}
        )

        call_args = engine._qdrant.query_points.call_args
        qdrant_filter = call_args.kwargs["query_filter"]
        assert qdrant_filter is not None
        # Filter should have 2 conditions
        assert len(qdrant_filter.must) == 2

    @pytest.mark.asyncio
    async def test_search_no_filter_passes_none(self, engine):
        """search() passes None filter when no filter dict is provided."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response([])
        )

        await engine.search("q", "col")

        call_args = engine._qdrant.query_points.call_args
        assert call_args.kwargs["query_filter"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 9. search_swarm_memory queries correct collection
# ═══════════════════════════════════════════════════════════════════════════


class TestSearchSwarmMemory:
    @pytest.mark.asyncio
    async def test_search_swarm_memory_correct_collection(self, engine):
        """search_swarm_memory() queries the swarm_memory collection."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response(
                [
                    _make_scored_point(
                        "ep1",
                        0.88,
                        {"content": "epoch summary", "epoch_id": 1},
                    )
                ]
            )
        )

        results = await engine.search_swarm_memory("progress update")
        assert len(results) == 1
        assert results[0].content == "epoch summary"

        call_args = engine._qdrant.query_points.call_args
        assert call_args.kwargs["collection_name"] == SWARM_MEMORY_COLLECTION

    @pytest.mark.asyncio
    async def test_search_swarm_memory_with_session_filter(self, engine):
        """search_swarm_memory() filters by session_id when provided."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response([])
        )

        await engine.search_swarm_memory(
            "query", session_id="sess_42"
        )

        call_args = engine._qdrant.query_points.call_args
        qdrant_filter = call_args.kwargs["query_filter"]
        assert qdrant_filter is not None
        assert len(qdrant_filter.must) == 1

    @pytest.mark.asyncio
    async def test_search_swarm_memory_no_session(self, engine):
        """search_swarm_memory() has no filter when session_id is None."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            return_value=_make_query_response([])
        )

        await engine.search_swarm_memory("query")

        call_args = engine._qdrant.query_points.call_args
        assert call_args.kwargs["query_filter"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 10. ensure_collection creates collection
# ═══════════════════════════════════════════════════════════════════════════


class TestEnsureCollection:
    @pytest.mark.asyncio
    async def test_ensure_collection_creates_new(self, engine):
        """ensure_collection() creates a collection when it doesn't exist."""
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()

        await engine.ensure_collection("new_col", 1024)

        engine._qdrant.create_collection.assert_awaited_once()
        call_args = engine._qdrant.create_collection.call_args
        assert call_args.kwargs["collection_name"] == "new_col"

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_existing(self, engine):
        """ensure_collection() does not create if collection already exists."""
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response(["existing_col"])
        )
        engine._qdrant.create_collection = AsyncMock()

        await engine.ensure_collection("existing_col", 1024)

        engine._qdrant.create_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ensure_collection_handles_error(self, engine):
        """ensure_collection() logs error but does not crash on failure."""
        engine._qdrant.get_collections = AsyncMock(
            side_effect=ConnectionError("Qdrant down")
        )

        # Should not raise
        await engine.ensure_collection("col", 1024)


# ═══════════════════════════════════════════════════════════════════════════
# 11. create_colony_namespace names collection correctly
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateColonyNamespace:
    @pytest.mark.asyncio
    async def test_create_colony_namespace_name(self, engine):
        """create_colony_namespace() creates collection with correct name."""
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()

        await engine.create_colony_namespace("alpha_01")

        call_args = engine._qdrant.create_collection.call_args
        assert call_args.kwargs["collection_name"] == "colony_alpha_01_docs"

    @pytest.mark.asyncio
    async def test_create_colony_namespace_uses_configured_dims(self, engine):
        """create_colony_namespace() uses embedding_config.dimensions."""
        engine._qdrant.get_collections = AsyncMock(
            return_value=_make_collections_response([])
        )
        engine._qdrant.create_collection = AsyncMock()

        await engine.create_colony_namespace("test")

        call_args = engine._qdrant.create_collection.call_args
        vectors_config = call_args.kwargs["vectors_config"]
        assert vectors_config.size == engine._embedding_config.dimensions


# ═══════════════════════════════════════════════════════════════════════════
# 12. delete_colony_namespace removes collection
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteColonyNamespace:
    @pytest.mark.asyncio
    async def test_delete_colony_namespace(self, engine):
        """delete_colony_namespace() deletes the correct collection."""
        engine._qdrant.delete_collection = AsyncMock()

        await engine.delete_colony_namespace("beta_02")

        engine._qdrant.delete_collection.assert_awaited_once_with(
            collection_name="colony_beta_02_docs"
        )

    @pytest.mark.asyncio
    async def test_delete_colony_namespace_handles_error(self, engine):
        """delete_colony_namespace() logs error but does not crash."""
        engine._qdrant.delete_collection = AsyncMock(
            side_effect=Exception("collection not found")
        )

        # Should not raise
        await engine.delete_colony_namespace("missing")


# ═══════════════════════════════════════════════════════════════════════════
# 13. Qdrant unavailable returns empty results
# ═══════════════════════════════════════════════════════════════════════════


class TestQdrantUnavailable:
    @pytest.mark.asyncio
    async def test_search_returns_empty_when_qdrant_unavailable(
        self, engine_no_qdrant
    ):
        """search() returns empty list when Qdrant client is None."""
        results = await engine_no_qdrant.search("test", "col")
        assert results == []

    @pytest.mark.asyncio
    async def test_ensure_collection_noop_when_unavailable(
        self, engine_no_qdrant
    ):
        """ensure_collection() is a no-op when Qdrant is unavailable."""
        # Should not raise
        await engine_no_qdrant.ensure_collection("col", 1024)

    @pytest.mark.asyncio
    async def test_delete_namespace_noop_when_unavailable(
        self, engine_no_qdrant
    ):
        """delete_colony_namespace() is a no-op when Qdrant unavailable."""
        # Should not raise
        await engine_no_qdrant.delete_colony_namespace("test")

    @pytest.mark.asyncio
    async def test_ingest_text_noop_when_unavailable(self, engine_no_qdrant):
        """ingest_text() embeds but cannot upsert without Qdrant."""
        dims = engine_no_qdrant._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            batch = json["input"]
            embs = [_fake_embedding(dims) for _ in range(len(batch))]
            return _make_httpx_embedding_response(embs)

        engine_no_qdrant._http.post = mock_post

        # Should not raise even though Qdrant is None
        await engine_no_qdrant.ingest_text("data", "doc1", "col")

    @pytest.mark.asyncio
    async def test_search_swarm_memory_empty_when_unavailable(
        self, engine_no_qdrant
    ):
        """search_swarm_memory() returns empty list without Qdrant."""
        results = await engine_no_qdrant.search_swarm_memory("q")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# 14. Embedding server down logs warning
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbeddingServerDown:
    @pytest.mark.asyncio
    async def test_connect_error_falls_back_to_local(self, engine):
        """embed() falls back to local model on ConnectError."""
        engine._http.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        # Mock local embedder
        import numpy as np

        mock_embedder = MagicMock()
        dims = engine._embedding_config.dimensions
        mock_embedder.encode.return_value = np.zeros((1, dims))
        engine._local_embedder = mock_embedder

        result = await engine.embed(["test"])
        assert len(result) == 1
        assert len(result[0]) == dims
        mock_embedder.encode.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_timeout_falls_back(self, engine):
        """embed() falls back to local model on ConnectTimeout."""
        engine._http.post = AsyncMock(
            side_effect=httpx.ConnectTimeout("connect timeout")
        )

        import numpy as np

        mock_embedder = MagicMock()
        dims = engine._embedding_config.dimensions
        mock_embedder.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), dims))
        engine._local_embedder = mock_embedder

        result = await engine.embed(["a", "b"])
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_fallback_without_sentence_transformers(self, engine):
        """embed() returns zero vectors when local model also unavailable."""
        engine._http.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        engine._local_embedder = None

        with patch(
            "src.rag.RAGEngine._embed_local"
        ) as mock_local:
            dims = engine._embedding_config.dimensions
            mock_local.return_value = [[0.0] * dims]
            result = await engine.embed(["test"])
            assert len(result) == 1
            assert all(v == 0.0 for v in result[0])

    @pytest.mark.asyncio
    async def test_using_fallback_flag(self, engine):
        """embed() sets _using_fallback flag on first fallback use."""
        engine._http.post = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )

        import numpy as np

        mock_embedder = MagicMock()
        dims = engine._embedding_config.dimensions
        mock_embedder.encode.return_value = np.zeros((1, dims))
        engine._local_embedder = mock_embedder

        assert engine._using_fallback is False
        await engine.embed(["test"])
        assert engine._using_fallback is True

    @pytest.mark.asyncio
    async def test_qdrant_search_error_returns_empty(self, engine):
        """search() returns empty list when Qdrant query_points raises."""
        dims = engine._embedding_config.dimensions

        async def mock_post(url, json=None, **kwargs):
            embs = [_fake_embedding(dims)]
            return _make_httpx_embedding_response(embs)

        engine._http.post = mock_post
        engine._qdrant.query_points = AsyncMock(
            side_effect=ConnectionError("Qdrant down")
        )

        results = await engine.search("query", "col")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# 15. SearchResult dataclass fields
# ═══════════════════════════════════════════════════════════════════════════


class TestSearchResultDataclass:
    def test_fields(self):
        """SearchResult has score, content, and metadata fields."""
        sr = SearchResult(
            score=0.95,
            content="test content",
            metadata={"source": "doc.md", "chunk_index": 0},
        )
        assert sr.score == 0.95
        assert sr.content == "test content"
        assert sr.metadata == {"source": "doc.md", "chunk_index": 0}

    def test_default_metadata(self):
        """SearchResult metadata defaults to empty dict."""
        sr = SearchResult(score=0.5, content="text")
        assert sr.metadata == {}

    def test_equality(self):
        """Two SearchResults with same values are equal."""
        sr1 = SearchResult(score=0.9, content="x", metadata={"a": 1})
        sr2 = SearchResult(score=0.9, content="x", metadata={"a": 1})
        assert sr1 == sr2

    def test_repr(self):
        """SearchResult has a readable repr."""
        sr = SearchResult(score=0.8, content="hello")
        r = repr(sr)
        assert "0.8" in r
        assert "hello" in r


# ═══════════════════════════════════════════════════════════════════════════
# Chunking internals
# ═══════════════════════════════════════════════════════════════════════════


class TestChunking:
    def test_chunk_text_basic(self):
        """_chunk_text() splits text into approximately sized chunks."""
        text = "X" * 4096  # 1024 tokens at 4 chars/token
        chunks = RAGEngine._chunk_text(text, chunk_size=512, overlap=50)
        assert len(chunks) > 1
        # Each chunk should be approximately 512*4 = 2048 chars
        for chunk in chunks:
            assert len(chunk) <= 512 * CHARS_PER_TOKEN + 10

    def test_chunk_text_empty(self):
        """_chunk_text() returns empty list for whitespace-only text."""
        assert RAGEngine._chunk_text("") == []
        assert RAGEngine._chunk_text("   ") == []

    def test_chunk_text_short(self):
        """_chunk_text() returns single chunk for short text."""
        chunks = RAGEngine._chunk_text("short text")
        assert len(chunks) == 1
        assert chunks[0] == "short text"

    def test_chunk_text_overlap(self):
        """Consecutive chunks overlap by approximately overlap tokens."""
        _char_chunk = 100 * CHARS_PER_TOKEN  # 400 chars
        char_overlap = 20 * CHARS_PER_TOKEN  # 80 chars
        # Create unique text so overlap is verifiable
        text = "".join(f"{i:04d}" for i in range(200))  # 800 chars

        chunks = RAGEngine._chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2

        # Verify the end of chunk 0 overlaps with the beginning of chunk 1
        if len(chunks) >= 2:
            end_of_first = chunks[0][-char_overlap:]
            start_of_second = chunks[1][:char_overlap]
            assert end_of_first == start_of_second


# ═══════════════════════════════════════════════════════════════════════════
# Close / cleanup
# ═══════════════════════════════════════════════════════════════════════════


class TestClose:
    @pytest.mark.asyncio
    async def test_close_releases_resources(self, engine):
        """close() closes HTTP client and Qdrant client."""
        engine._http = AsyncMock()
        engine._qdrant = AsyncMock()

        await engine.close()

        engine._http.aclose.assert_awaited_once()
        engine._qdrant.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_handles_qdrant_error(self, engine):
        """close() does not raise when Qdrant close fails."""
        engine._http = AsyncMock()
        engine._qdrant = AsyncMock()
        engine._qdrant.close = AsyncMock(
            side_effect=RuntimeError("already closed")
        )

        # Should not raise
        await engine.close()

    @pytest.mark.asyncio
    async def test_close_without_qdrant(self, engine_no_qdrant):
        """close() works when Qdrant was never connected."""
        engine_no_qdrant._http = AsyncMock()

        # Should not raise
        await engine_no_qdrant.close()
