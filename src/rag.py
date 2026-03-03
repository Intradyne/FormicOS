"""
FormicOS v0.6.0 -- RAG Engine

Vector search layer backed by Qdrant. Ingests documents and epoch summaries as
embeddings, provides semantic search for agent context assembly, and manages
per-colony namespace isolation.

Embedding uses BGE-M3 (1024 dims) via an OpenAI-compatible endpoint served by
llama.cpp.  Falls back to a local SentenceTransformers model when the server is
unreachable -- but logs a warning because vectors from different models are
incomparable.

The Qdrant client is optional.  When ``qdrant-client`` is not installed,
ingestion and search methods degrade gracefully (return empty results, log
warnings).  The embed() path still works since it only depends on httpx.

Key invariants:
  - Always use ``query_points()`` -- ``search()`` was removed in qdrant-client v1.15.
  - BGE-M3 context size is 8192 tokens, NOT 16384.
  - Never mix BGE-M3 embeddings with MiniLM-L6-v2 embeddings.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .models import DocumentInject, EmbeddingConfig, QdrantConfig

logger = logging.getLogger(__name__)

# ── Optional Qdrant imports ──────────────────────────────────────────────

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 512  # tokens (approx)
DEFAULT_CHUNK_OVERLAP = 50  # tokens (approx)
CHARS_PER_TOKEN = 4  # rough heuristic: 4 chars ~ 1 token
SWARM_MEMORY_COLLECTION = "swarm_memory"

# SemanticMMU constants (v0.7.7)
DEFAULT_MMU_MAX_CONTEXT_TOKENS = 4000
DEFAULT_MMU_TOP_K = 10


# ── SearchResult ─────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    """A single result from a Qdrant semantic search."""

    score: float
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ── RAGEngine ────────────────────────────────────────────────────────────


class RAGEngine:
    """
    Vector search engine backed by Qdrant with BGE-M3 embeddings.

    Parameters
    ----------
    qdrant_config : QdrantConfig
        Qdrant connection settings (host, port, collections).
    embedding_config : EmbeddingConfig
        Embedding model settings (endpoint, dimensions, batch_size).
    """

    def __init__(
        self,
        qdrant_config: QdrantConfig,
        embedding_config: EmbeddingConfig,
    ) -> None:
        self._qdrant_config = qdrant_config
        self._embedding_config = embedding_config

        # httpx client for embedding API calls
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=60.0)

        # Qdrant async client (optional)
        self._qdrant: AsyncQdrantClient | None = None
        if QDRANT_AVAILABLE:
            try:
                self._qdrant = AsyncQdrantClient(
                    host=qdrant_config.host,
                    port=qdrant_config.port,
                    grpc_port=qdrant_config.grpc_port,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to create Qdrant client: %s", exc
                )

        # Local SentenceTransformers fallback (lazy-loaded)
        self._local_embedder: Any | None = None
        self._using_fallback: bool = False

    # ── Embedding ────────────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts using the configured embedding server.

        Batches requests into groups of ``embedding_config.batch_size``.
        On timeout or server error, retries with halved batch size.
        Falls back to local SentenceTransformers if the server is
        completely unreachable.

        Returns
        -------
        list[list[float]]
            One embedding vector per input text.
        """
        if not texts:
            return []

        batch_size = self._embedding_config.batch_size
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = await self._embed_batch(batch, batch_size=len(batch))
            all_embeddings.extend(result)

        return all_embeddings

    async def _embed_batch(
        self, texts: list[str], batch_size: int
    ) -> list[list[float]]:
        """Embed a single batch, retrying with smaller batches on failure."""
        try:
            return await self._call_embedding_api(texts)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if batch_size <= 1:
                logger.warning(
                    "Embedding server failed for batch of 1, "
                    "falling back to local model: %s",
                    exc,
                )
                return self._embed_local(texts)

            # Halve batch size and retry
            half = max(1, batch_size // 2)
            logger.warning(
                "Embedding batch of %d failed (%s), retrying with batch size %d",
                batch_size,
                exc,
                half,
            )
            results: list[list[float]] = []
            for j in range(0, len(texts), half):
                sub = texts[j : j + half]
                results.extend(
                    await self._embed_batch(sub, batch_size=len(sub))
                )
            return results
        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
            logger.warning(
                "Embedding server unreachable (%s), "
                "falling back to local SentenceTransformers",
                exc,
            )
            return self._embed_local(texts)

    async def _call_embedding_api(
        self, texts: list[str]
    ) -> list[list[float]]:
        """Call the OpenAI-compatible /v1/embeddings endpoint."""
        url = self._embedding_config.endpoint.rstrip("/") + "/embeddings"
        payload = {
            "model": self._embedding_config.model,
            "input": texts,
        }
        resp = await self._http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # OpenAI format: {"data": [{"embedding": [...], "index": 0}, ...]}
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Fallback: embed using local SentenceTransformers.

        Logs a warning because local model vectors are incomparable with
        server-side BGE-M3 vectors.
        """
        if not self._using_fallback:
            logger.warning(
                "Using local SentenceTransformers fallback -- "
                "vectors will be INCOMPARABLE with server-side BGE-M3 embeddings"
            )
            self._using_fallback = True

        if self._local_embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._local_embedder = SentenceTransformer(
                    self._embedding_config.model
                )
            except ImportError:
                logger.error(
                    "sentence-transformers not installed -- "
                    "cannot embed without the server"
                )
                # Return zero vectors as last resort
                dims = self._embedding_config.dimensions
                return [[0.0] * dims for _ in texts]

        vecs = self._local_embedder.encode(texts)
        return [v.tolist() for v in vecs]

    # ── Ingestion ────────────────────────────────────────────────────

    async def ingest_document(
        self, path: str | Path, collection: str
    ) -> int:
        """Read a file, chunk it, embed chunks, and upsert to Qdrant.

        Parameters
        ----------
        path : str | Path
            Path to the document file to ingest.
        collection : str
            Qdrant collection name to store chunks in.

        Returns
        -------
        int
            Number of chunks ingested.
        """
        if not QDRANT_AVAILABLE:
            logger.warning(
                "qdrant-client not installed -- cannot ingest document"
            )
            return 0

        file_path = Path(path)
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to read document %s: %s", path, exc)
            return 0

        chunks = self._chunk_text(text)
        if not chunks:
            return 0

        embeddings = await self.embed(chunks)
        await self.ensure_collection(
            collection, self._embedding_config.dimensions
        )

        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "content": chunk,
                        "source": str(file_path),
                        "chunk_index": idx,
                        "doc_id": file_path.stem,
                    },
                )
            )

        if not await self._upsert_points(collection, points):
            return 0

        logger.info(
            "Ingested %d chunks from %s into %s",
            len(chunks),
            file_path.name,
            collection,
        )
        return len(chunks)

    async def ingest_text(
        self, text: str, doc_id: str, collection: str
    ) -> None:
        """Embed and store a single text block in Qdrant.

        Parameters
        ----------
        text : str
            The text content to store.
        doc_id : str
            A document identifier for metadata.
        collection : str
            Qdrant collection name.
        """
        if not QDRANT_AVAILABLE:
            logger.warning(
                "qdrant-client not installed -- cannot ingest text"
            )
            return

        embeddings = await self.embed([text])
        if not embeddings:
            return

        await self.ensure_collection(
            collection, self._embedding_config.dimensions
        )

        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=embeddings[0],
            payload={
                "content": text,
                "doc_id": doc_id,
            },
        )
        await self._upsert_points(collection, [point])

    async def ingest_document_inject(
        self, doc: DocumentInject, collection: str,
    ) -> int:
        """Chunk and ingest an in-memory DocumentInject into Qdrant.

        Combines the chunking logic of ingest_document() with in-memory
        text input (no file I/O). Used for headless colony creation.

        Returns the number of chunks ingested.
        """
        if not QDRANT_AVAILABLE:
            logger.warning(
                "qdrant-client not installed -- cannot ingest document"
            )
            return 0

        chunks = self._chunk_text(doc.content)
        if not chunks:
            return 0

        embeddings = await self.embed(chunks)
        await self.ensure_collection(
            collection, self._embedding_config.dimensions,
        )

        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "content": chunk,
                    "source": doc.filename,
                    "chunk_index": idx,
                    "doc_id": doc.filename,
                    "mime_type": doc.mime_type,
                },
            ))

        if not await self._upsert_points(collection, points):
            return 0

        logger.info(
            "Ingested %d chunks from inject '%s' into %s",
            len(chunks), doc.filename, collection,
        )
        return len(chunks)

    async def ingest_epoch(
        self, epoch_id: int, summary: str, session_id: str
    ) -> None:
        """Store an epoch summary in the swarm_memory collection.

        Parameters
        ----------
        epoch_id : int
            The epoch identifier.
        summary : str
            The epoch summary text to embed and store.
        session_id : str
            The session this epoch belongs to.
        """
        if not QDRANT_AVAILABLE:
            logger.warning(
                "qdrant-client not installed -- cannot ingest epoch"
            )
            return

        embeddings = await self.embed([summary])
        if not embeddings:
            return

        await self.ensure_collection(
            SWARM_MEMORY_COLLECTION, self._embedding_config.dimensions
        )

        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=embeddings[0],
            payload={
                "content": summary,
                "epoch_id": epoch_id,
                "session_id": session_id,
                "type": "epoch_summary",
            },
        )
        await self._upsert_points(SWARM_MEMORY_COLLECTION, [point])

    # ── Search ───────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        collection: str,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Semantic search over a Qdrant collection.

        Parameters
        ----------
        query : str
            The search query text.
        collection : str
            Qdrant collection to search.
        top_k : int
            Number of results to return.
        filter : dict | None
            Optional metadata filter. Keys are field names, values are
            exact match values.

        Returns
        -------
        list[SearchResult]
            Ranked results with score, content, and metadata.
        """
        if self._qdrant is None:
            logger.warning("Qdrant not available -- returning empty results")
            return []

        embeddings = await self.embed([query])
        if not embeddings:
            return []

        query_vector = embeddings[0]

        # Build optional Qdrant filter
        qdrant_filter = None
        if filter:
            conditions = []
            for key, value in filter.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )
            qdrant_filter = Filter(must=conditions)

        try:
            results = await self._qdrant.query_points(
                collection_name=collection,
                query=query_vector,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
            )

            search_results: list[SearchResult] = []
            for point in results.points:
                payload = point.payload or {}
                content = payload.get("content", "")
                metadata = {k: v for k, v in payload.items() if k != "content"}
                search_results.append(
                    SearchResult(
                        score=point.score,
                        content=content,
                        metadata=metadata,
                    )
                )
            return search_results

        except Exception as exc:
            logger.error(
                "Qdrant search failed on collection '%s': %s",
                collection,
                exc,
            )
            return []

    # ── SemanticMMU (v0.7.7) ─────────────────────────────────────────

    async def page_in_context(
        self,
        query: str,
        collection: str,
        current_token_count: int = 0,
        max_context_tokens: int = DEFAULT_MMU_MAX_CONTEXT_TOKENS,
        top_k: int = DEFAULT_MMU_TOP_K,
    ) -> dict[str, Any]:
        """Semantic MMU: page context blocks into available token budget.

        Retrieves top_k results from the collection, then greedily packs
        them into the remaining token window (max_context_tokens -
        current_token_count).

        Returns dict with keys: pages (list[dict]), total_tokens (int),
        pages_loaded (int), pages_skipped (int).
        """
        available_tokens = max(0, max_context_tokens - current_token_count)
        if available_tokens <= 0:
            return {
                "pages": [], "total_tokens": 0,
                "pages_loaded": 0, "pages_skipped": 0,
            }

        results = await self.search(query, collection, top_k=top_k)
        if not results:
            return {
                "pages": [], "total_tokens": 0,
                "pages_loaded": 0, "pages_skipped": 0,
            }

        # Greedy packing: take results in relevance order until budget exhausted
        pages: list[dict[str, Any]] = []
        tokens_used = 0
        skipped = 0

        for result in results:
            chunk_tokens = len(result.content) // CHARS_PER_TOKEN
            if tokens_used + chunk_tokens > available_tokens:
                skipped += 1
                continue
            pages.append({
                "content": result.content,
                "score": result.score,
                "tokens": chunk_tokens,
                "source": result.metadata.get("source", "unknown"),
                "chunk_index": result.metadata.get("chunk_index", 0),
            })
            tokens_used += chunk_tokens

        return {
            "pages": pages,
            "total_tokens": tokens_used,
            "pages_loaded": len(pages),
            "pages_skipped": skipped,
        }

    async def search_swarm_memory(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Search the swarm_memory collection for relevant epoch summaries.

        Parameters
        ----------
        query : str
            The search query.
        top_k : int
            Number of results.
        session_id : str | None
            If provided, filter results to this session only.

        Returns
        -------
        list[SearchResult]
            Ranked epoch summaries.
        """
        filter_dict: dict[str, Any] | None = None
        if session_id:
            filter_dict = {"session_id": session_id}
        return await self.search(
            query=query,
            collection=SWARM_MEMORY_COLLECTION,
            top_k=top_k,
            filter=filter_dict,
        )

    # ── Collection Management ────────────────────────────────────────

    async def ensure_collection(self, name: str, dims: int) -> None:
        """Create a Qdrant collection if it does not already exist.

        Parameters
        ----------
        name : str
            Collection name.
        dims : int
            Vector dimensionality.
        """
        if self._qdrant is None:
            logger.warning(
                "Qdrant not available -- cannot ensure collection '%s'", name
            )
            return

        try:
            collections = await self._qdrant.get_collections()
            existing = {c.name for c in collections.collections}
            if name in existing:
                return

            await self._qdrant.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=dims,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dims=%d)", name, dims
            )
        except Exception as exc:
            logger.error(
                "Failed to ensure collection '%s': %s", name, exc
            )

    async def create_colony_namespace(self, colony_id: str) -> None:
        """Create a Qdrant collection for a colony.

        Collection name: ``colony_{colony_id}_docs``

        Parameters
        ----------
        colony_id : str
            The colony identifier.
        """
        collection_name = f"colony_{colony_id}_docs"
        await self.ensure_collection(
            collection_name, self._embedding_config.dimensions
        )
        logger.info(
            "Colony namespace created: %s", collection_name
        )

    async def delete_colony_namespace(self, colony_id: str) -> None:
        """Delete a colony's Qdrant collection.

        Parameters
        ----------
        colony_id : str
            The colony identifier.
        """
        if self._qdrant is None:
            logger.warning(
                "Qdrant not available -- cannot delete colony namespace"
            )
            return

        collection_name = f"colony_{colony_id}_docs"
        try:
            await self._qdrant.delete_collection(
                collection_name=collection_name
            )
            logger.info(
                "Colony namespace deleted: %s", collection_name
            )
        except Exception as exc:
            logger.error(
                "Failed to delete colony namespace '%s': %s",
                collection_name,
                exc,
            )

    # ── Cleanup ──────────────────────────────────────────────────────

    async def close(self) -> None:
        """Release resources (HTTP client, Qdrant connection)."""
        await self._http.aclose()
        if self._qdrant is not None:
            try:
                await self._qdrant.close()
            except Exception:
                pass

    # ── Internal Helpers ─────────────────────────────────────────────

    @staticmethod
    def _chunk_text(
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[str]:
        """Split text into chunks by approximate token count.

        Uses a heuristic of 4 characters per token. Each chunk targets
        ``chunk_size`` tokens with ``overlap`` tokens of overlap between
        consecutive chunks.

        Parameters
        ----------
        text : str
            The full text to chunk.
        chunk_size : int
            Target chunk size in tokens.
        overlap : int
            Overlap between consecutive chunks in tokens.

        Returns
        -------
        list[str]
            List of text chunks.
        """
        if not text.strip():
            return []

        char_chunk = chunk_size * CHARS_PER_TOKEN
        char_overlap = overlap * CHARS_PER_TOKEN
        step = max(1, char_chunk - char_overlap)

        chunks: list[str] = []
        pos = 0
        while pos < len(text):
            end = pos + char_chunk
            chunk = text[pos:end].strip()
            if chunk:
                chunks.append(chunk)
            pos += step

        return chunks

    async def _upsert_points(
        self, collection: str, points: list[Any]
    ) -> bool:
        """Upsert points to Qdrant. Returns True on success."""
        if self._qdrant is None:
            logger.warning(
                "Qdrant not available -- cannot upsert to '%s'", collection
            )
            return False

        try:
            await self._qdrant.upsert(
                collection_name=collection,
                points=points,
            )
            return True
        except Exception as exc:
            logger.error(
                "Qdrant upsert failed on '%s': %s", collection, exc
            )
            return False
