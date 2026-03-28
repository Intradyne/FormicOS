"""Qdrant-backed vector store adapter (ADR-013, Wave 13 hybrid search).

Implements ``VectorPort`` via qdrant-client v1.16+ async API.
Uses ``query_points()`` for search (NOT the removed ``search()`` method).

Wave 13 upgrade (ADR-019): hybrid search is adapter-internal.
  - Upsert writes **named vectors**: ``dense`` (1024-dim) + ``sparse`` (BM25
    via ``models.Document``).
  - Search uses **two-branch prefetch** (dense + BM25) fused with
    ``RrfQuery(rrf=Rrf(k=60))``.
  - ``VectorPort.search()`` signature is **unchanged**.

Falls back to dense-only when:
  - ``embed_client`` is not injected (legacy sync ``embed_fn`` path), or
  - the collection lacks named vectors (pre-migration ``skill_bank`` data).

Graceful degradation: Qdrant down → empty results / warnings, no crash.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

import structlog
from qdrant_client import AsyncQdrantClient, models

from formicos.core.types import VectorDocument, VectorSearchHit

# Namespace UUID for deterministic string→UUID5 conversion.
# Qdrant requires UUID or integer point IDs; FormicOS uses arbitrary strings.
_QDRANT_NS = uuid.UUID("a3f1b2c4-d5e6-7890-abcd-ef1234567890")


def _to_point_id(string_id: str) -> str:
    """Convert an arbitrary string ID to a deterministic UUID5 string."""
    return str(uuid.uuid5(_QDRANT_NS, string_id))

_T = TypeVar("_T")
_TRANSIENT = (ConnectionError, TimeoutError, OSError)

if TYPE_CHECKING:
    from formicos.adapters.embedding_qwen3 import Qwen3Embedder

logger = structlog.get_logger(__name__)


class QdrantVectorPort:
    """VectorPort implementation backed by Qdrant.

    Supports two embedding modes:

    1. **Legacy (sync):** ``embed_fn`` callable — dense-only search, unnamed
       vectors.  Used by existing tests and the sentence-transformers path.
    2. **Hybrid (async):** ``embed_client`` (``Qwen3Embedder``) — writes both
       dense and BM25 sparse vectors via named vector config, searches with
       two-branch prefetch + RRF fusion.

    When *both* are provided, ``embed_client`` takes precedence for all
    embedding operations.
    """

    def __init__(
        self,
        url: str = "http://qdrant:6333",
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        embed_client: Qwen3Embedder | None = None,
        prefer_grpc: bool = True,
        default_collection: str = "skill_bank",
        vector_dimensions: int = 384,
    ) -> None:
        self._client = AsyncQdrantClient(url=url, prefer_grpc=prefer_grpc, timeout=30)
        self._embed_fn = embed_fn
        self._embed_client = embed_client
        self._default_collection = default_collection
        self._dimensions = vector_dimensions
        self._collections_ensured: set[str] = set()

    @property
    def _hybrid_enabled(self) -> bool:
        """True when the async embedding client is available for hybrid search."""
        return self._embed_client is not None

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    async def _embed_texts(
        self, texts: list[str], *, is_query: bool = False,
    ) -> list[list[float]]:
        """Embed texts using the best available method.

        Prefers ``embed_client`` (async Qwen3) over ``embed_fn`` (sync).
        """
        if self._embed_client is not None:
            return await self._embed_client.embed(texts, is_query=is_query)
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        return []

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def ensure_collection(self, name: str | None = None) -> None:
        """Create collection + payload indexes if they don't exist. Idempotent."""
        collection = name or self._default_collection
        if collection in self._collections_ensured:
            return

        try:
            if not await self._client.collection_exists(collection):
                if self._hybrid_enabled:
                    # Named vector config: dense + sparse (Wave 13)
                    await self._client.create_collection(
                        collection_name=collection,
                        vectors_config={
                            "dense": models.VectorParams(
                                size=self._dimensions,
                                distance=models.Distance.COSINE,
                            ),
                        },
                        sparse_vectors_config={
                            "sparse": models.SparseVectorParams(
                                modifier=models.Modifier.IDF,
                            ),
                        },
                        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                    )
                else:
                    # Legacy unnamed vector config
                    await self._client.create_collection(
                        collection_name=collection,
                        vectors_config=models.VectorParams(
                            size=self._dimensions,
                            distance=models.Distance.COSINE,
                        ),
                        hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                    )
                logger.info(
                    "qdrant.collection_created",
                    collection=collection,
                    dimensions=self._dimensions,
                    hybrid=self._hybrid_enabled,
                )

            # Always ensure indexes (idempotent in Qdrant)
            index_fields: list[tuple[str, models.PayloadSchemaType]] = [
                ("namespace", models.PayloadSchemaType.KEYWORD),
                ("confidence", models.PayloadSchemaType.FLOAT),
                ("algorithm_version", models.PayloadSchemaType.KEYWORD),
                ("extracted_at", models.PayloadSchemaType.DATETIME),
                ("source_colony", models.PayloadSchemaType.KEYWORD),
                ("source_colony_id", models.PayloadSchemaType.KEYWORD),
                ("hierarchy_path", models.PayloadSchemaType.KEYWORD),
            ]
            for field, schema in index_fields:
                try:
                    if field == "namespace":
                        await self._client.create_payload_index(
                            collection, field,
                            field_schema=models.KeywordIndexParams(
                                type="keyword",  # pyright: ignore[reportArgumentType]
                                is_tenant=True,
                            ),
                        )
                    else:
                        await self._client.create_payload_index(
                            collection, field, schema,
                        )
                except Exception:  # noqa: BLE001
                    pass  # Index already exists — Qdrant is idempotent here

            self._collections_ensured.add(collection)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "qdrant.ensure_collection_failed",
                collection=collection, error=str(exc),
            )

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    async def _retry_qdrant(
        self,
        operation: Callable[..., Any],
        *args: Any,
        retries: int = 3,
        **kwargs: Any,
    ) -> Any:  # noqa: ANN401
        """Retry transient Qdrant failures with exponential backoff."""
        for attempt in range(retries):
            try:
                return await operation(*args, **kwargs)
            except _TRANSIENT as exc:
                if attempt == retries - 1:
                    logger.error(
                        "qdrant.transient_failure_exhausted",
                        error=str(exc), attempt=attempt,
                    )
                    return None
                await asyncio.sleep(0.5 * (2 ** attempt))
            except Exception as exc:  # noqa: BLE001
                logger.error("qdrant.permanent_failure", error=str(exc))
                return None
        return None

    # ------------------------------------------------------------------
    # VectorPort interface
    # ------------------------------------------------------------------

    async def upsert(
        self, collection: str, docs: Sequence[VectorDocument],
    ) -> int:
        """Embed documents and upsert to Qdrant.

        When hybrid mode is active, writes **named vectors**:
        - ``dense``: 1024-dim dense embedding from Qwen3-Embedding
        - ``sparse``: BM25 via ``models.Document(text=..., model="Qdrant/bm25")``
        """
        await self.ensure_collection(collection)

        if (self._embed_fn is None and self._embed_client is None) or not docs:
            return 0

        texts = [doc.content for doc in docs]
        vectors = await self._embed_texts(texts, is_query=False)

        if not vectors:
            return 0

        points: list[models.PointStruct] = []
        for doc, vector in zip(docs, vectors, strict=True):
            point_id = _to_point_id(doc.id)
            payload: dict[str, Any] = {
                "text": doc.content,
                "namespace": doc.metadata.get("namespace", collection),
                "_original_id": doc.id,
            }
            for k, v in doc.metadata.items():
                if k != "namespace":
                    payload[k] = v

            if self._hybrid_enabled:
                # Named vectors: dense + BM25 sparse
                point_vector: dict[str, Any] = {
                    "dense": vector,
                    "sparse": models.Document(
                        text=doc.content,
                        model="Qdrant/bm25",
                    ),
                }
                points.append(models.PointStruct(
                    id=point_id,
                    vector=point_vector,
                    payload=payload,
                ))
            else:
                # Legacy unnamed vector
                points.append(models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                ))

        result = await self._retry_qdrant(
            self._client.upsert,
            collection_name=collection,
            points=points,
            wait=True,
        )
        if result is None:
            return 0

        logger.debug(
            "qdrant.upserted",
            collection=collection, count=len(points),
            hybrid=self._hybrid_enabled,
        )
        return len(points)

    async def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
    ) -> list[VectorSearchHit]:
        """Embed query text, then search Qdrant.

        **Hybrid mode** (``embed_client`` present): two-branch prefetch
        (dense + BM25 sparse) fused with RRF(k=60).

        **Legacy mode** (``embed_fn`` only): dense-only query via
        ``query_points()``.

        Port signature unchanged — ADR-019.
        """
        await self.ensure_collection(collection)

        if self._embed_fn is None and self._embed_client is None:
            logger.warning("qdrant.search_no_embed")
            return []

        search_fn = (
            self._search_hybrid if self._hybrid_enabled
            else self._search_dense_only
        )
        result = await self._retry_qdrant(search_fn, collection, query, top_k)
        if result is None:
            return []
        return result  # type: ignore[no-any-return]

    async def delete(
        self, collection: str, ids: Sequence[str],
    ) -> int:
        """Delete documents by identifier."""
        if not ids:
            return 0

        await self.ensure_collection(collection)

        result = await self._retry_qdrant(
            self._client.delete,
            collection_name=collection,
            points_selector=models.PointIdsList(
                points=[_to_point_id(i) for i in ids],
            ),
            wait=True,
        )
        if result is None:
            return 0

        logger.debug(
            "qdrant.deleted",
            collection=collection, count=len(ids),
        )
        return len(ids)

    # ------------------------------------------------------------------
    # Search internals
    # ------------------------------------------------------------------

    async def _search_hybrid(
        self, collection: str, query: str, top_k: int,
    ) -> list[VectorSearchHit]:
        """Two-branch prefetch (dense + BM25) → RRF fusion.

        Algorithm: algorithms.md §3.
        """
        query_vectors = await self._embed_texts([query], is_query=True)
        if not query_vectors or not query_vectors[0]:
            return []

        overfetch = top_k * 4  # overfetch for fusion quality

        result = await self._client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(
                    query=query_vectors[0],
                    using="dense",
                    limit=overfetch,
                ),
                models.Prefetch(
                    query=models.Document(
                        text=query,
                        model="Qdrant/bm25",
                    ),
                    using="sparse",
                    limit=overfetch,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        logger.debug(
            "qdrant.hybrid_search",
            collection=collection,
            hits=len(result.points),
            top_k=top_k,
        )

        return [_to_search_hit(point) for point in result.points]

    async def _search_dense_only(
        self, collection: str, query: str, top_k: int,
    ) -> list[VectorSearchHit]:
        """Legacy dense-only search via sync embed_fn."""
        vectors = await self._embed_texts([query], is_query=True)
        if not vectors or not vectors[0]:
            return []
        query_vector = vectors[0]

        result = await self._client.query_points(
            collection_name=collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )

        return [_to_search_hit(point) for point in result.points]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the Qdrant client connection."""
        await self._client.close()
        logger.info("qdrant.closed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_search_hit(point: Any) -> VectorSearchHit:  # noqa: ANN401
    """Convert a Qdrant ScoredPoint to a VectorSearchHit."""
    payload: dict[str, Any] = dict(point.payload) if point.payload else {}
    content = str(payload.pop("text", ""))
    # Return the original domain ID if stored, else fall back to point UUID
    original_id = str(payload.pop("_original_id", point.id))

    return VectorSearchHit(
        id=original_id,
        content=content,
        score=float(point.score) if point.score is not None else 0.0,
        metadata=payload,
    )


__all__ = ["QdrantVectorPort"]
