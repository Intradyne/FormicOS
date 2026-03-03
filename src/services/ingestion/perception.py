"""
FormicOS v0.8.0 -- Async Document Ingestor (Topological Perception Layer)

Asynchronous ingestion queue that converts documents (PDF, DOCX, HTML, etc.)
into topology-preserving Markdown via ``docling``, chunks with HybridChunker
aligned to BGE-M3's 512-token window, embeds via RAGEngine, and upserts to
Qdrant — all without blocking the colony orchestration loop.

Key design choices:
  - ``docling.DocumentConverter.convert()`` is synchronous and NOT thread-safe.
    Each conversion creates a fresh DocumentConverter instance inside
    ``asyncio.to_thread()`` to avoid GIL contention and shared-state corruption.
  - An ``asyncio.Semaphore(max_concurrent)`` caps parallel conversions so the
    RTX 5090 is not saturated with embedding work while the orchestrator needs
    it for LLM inference.
  - Task state is held in-memory with a rolling cap (MAX_TASKS) to prevent
    unbounded growth.  Completed/failed tasks are evicted FIFO.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.ingestion import DocklingParser

if TYPE_CHECKING:
    from src.rag import RAGEngine

logger = logging.getLogger(__name__)


# ── Task Model ───────────────────────────────────────────────────────────


class IngestionStatus(str, Enum):
    """Lifecycle states for an ingestion task."""

    QUEUED = "queued"
    CONVERTING = "converting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IngestionTask:
    """Tracks the progress of a single document ingestion."""

    task_id: str
    file_path: str
    collection: str
    colony_id: str | None = None
    status: IngestionStatus = IngestionStatus.QUEUED
    chunks_produced: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "file_path": self.file_path,
            "collection": self.collection,
            "colony_id": self.colony_id,
            "status": self.status.value,
            "chunks_produced": self.chunks_produced,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# ── AsyncDocumentIngestor ────────────────────────────────────────────────


class AsyncDocumentIngestor:
    """Async document ingestion queue with docling conversion + BGE-M3 embedding.

    Parameters
    ----------
    rag_engine : RAGEngine
        The existing RAG engine for embedding and Qdrant upserts.
    max_concurrent : int
        Maximum concurrent document conversions (semaphore cap).
    """

    SUPPORTED_EXTENSIONS = frozenset({
        ".pdf", ".docx", ".html", ".htm", ".md", ".txt", ".pptx",
    })
    MAX_TASKS = 100

    def __init__(
        self,
        rag_engine: RAGEngine,
        max_concurrent: int = 2,
    ) -> None:
        self._rag = rag_engine
        self._parser = DocklingParser()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, IngestionTask] = {}
        self._task_order: list[str] = []

    # ── Public API ────────────────────────────────────────────────

    async def queue_document(
        self,
        file_path: str | Path,
        collection: str,
        colony_id: str | None = None,
    ) -> str:
        """Queue a document for async ingestion.

        Returns the task_id immediately.  The actual conversion, chunking,
        and embedding happen in a background ``asyncio.Task``.

        Raises
        ------
        FileNotFoundError
            If *file_path* does not exist.
        ValueError
            If the file extension is not in SUPPORTED_EXTENSIONS.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format: {path.suffix}. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        task_id = str(uuid.uuid4())
        task = IngestionTask(
            task_id=task_id,
            file_path=str(path),
            collection=collection,
            colony_id=colony_id,
        )
        self._tasks[task_id] = task
        self._task_order.append(task_id)
        self._evict_old_tasks()

        asyncio.create_task(
            self._process(task), name=f"ingest-{task_id[:8]}"
        )
        logger.info(
            "Queued ingestion task %s for %s → %s",
            task_id[:8], path.name, collection,
        )
        return task_id

    def get_task(self, task_id: str) -> IngestionTask | None:
        """Look up an ingestion task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20, offset: int = 0) -> list[IngestionTask]:
        """Return tasks in FIFO order with pagination."""
        ids = self._task_order[offset : offset + limit]
        return [self._tasks[tid] for tid in ids if tid in self._tasks]

    @property
    def total_tasks(self) -> int:
        return len(self._task_order)

    # ── Pipeline ──────────────────────────────────────────────────

    async def _process(self, task: IngestionTask) -> None:
        """Full pipeline: convert → chunk → embed → upsert."""
        async with self._semaphore:
            try:
                # Phase 1: Convert document to Markdown (CPU-bound)
                task.status = IngestionStatus.CONVERTING
                markdown_text = await self._convert_document(task.file_path)

                if not markdown_text or not markdown_text.strip():
                    logger.warning(
                        "Document %s produced empty markdown", task.file_path
                    )
                    task.status = IngestionStatus.COMPLETED
                    task.completed_at = time.time()
                    return

                # Phase 2: Chunk with HybridChunker (CPU-bound)
                task.status = IngestionStatus.CHUNKING
                chunks = await asyncio.to_thread(
                    self._chunk_markdown, markdown_text
                )

                if not chunks:
                    logger.info(
                        "No chunks produced from %s", task.file_path
                    )
                    task.status = IngestionStatus.COMPLETED
                    task.completed_at = time.time()
                    return

                # Phase 3: Embed via RAGEngine
                task.status = IngestionStatus.EMBEDDING
                texts = [c["text"] for c in chunks]
                embeddings = await self._rag.embed(texts)

                # Phase 4: Upsert to Qdrant
                await self._upsert_chunks(task, chunks, embeddings)

                task.chunks_produced = len(chunks)
                task.status = IngestionStatus.COMPLETED
                task.completed_at = time.time()
                logger.info(
                    "Ingestion %s completed: %d chunks from %s → %s",
                    task.task_id[:8],
                    len(chunks),
                    Path(task.file_path).name,
                    task.collection,
                )

            except Exception as exc:
                task.status = IngestionStatus.FAILED
                task.error = str(exc)
                task.completed_at = time.time()
                logger.error(
                    "Ingestion %s failed for %s: %s",
                    task.task_id[:8], task.file_path, exc,
                )

    # ── Convert ───────────────────────────────────────────────────

    async def _convert_document(self, file_path: str) -> str:
        """Convert a document to Markdown using DocklingParser.

        Delegates to ``DocklingParser.convert_to_markdown()`` inside
        ``asyncio.to_thread()`` (converter is NOT thread-safe).
        """
        return await asyncio.to_thread(
            self._parser.convert_to_markdown, file_path
        )

    # ── Chunk ─────────────────────────────────────────────────────

    def _chunk_markdown(self, markdown_text: str) -> list[dict[str, Any]]:
        """Chunk Markdown using DocklingParser's HybridChunker.

        Delegates to ``DocklingParser.chunk_markdown()`` and converts
        ``ChunkResult`` objects back to the dict format expected by
        the embedding pipeline.
        """
        chunks = self._parser.chunk_markdown(markdown_text)
        return [{"text": c.text, "meta": c.meta} for c in chunks]

    # ── Upsert ────────────────────────────────────────────────────

    async def _upsert_chunks(
        self,
        task: IngestionTask,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """Upsert embedded chunks to Qdrant via RAGEngine internals."""
        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            logger.error("qdrant-client not installed — cannot upsert chunks")
            return

        await self._rag.ensure_collection(
            task.collection, self._rag._embedding_config.dimensions
        )

        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            payload: dict[str, Any] = {
                "content": chunk["text"],
                "source": task.file_path,
                "chunk_index": idx,
                "doc_id": Path(task.file_path).stem,
                "ingestion_task_id": task.task_id,
            }
            if task.colony_id:
                payload["colony_id"] = task.colony_id
            payload.update(chunk.get("meta", {}))

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload=payload,
                )
            )

        await self._rag._upsert_points(task.collection, points)

    # ── Housekeeping ──────────────────────────────────────────────

    def _evict_old_tasks(self) -> None:
        """Evict oldest tasks when rolling cap is exceeded."""
        while len(self._task_order) > self.MAX_TASKS:
            old_id = self._task_order.pop(0)
            self._tasks.pop(old_id, None)
