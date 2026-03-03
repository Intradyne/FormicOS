"""
FormicOS v0.8.0 -- Topology-Preserving Document Parser

Stateless parser that converts documents (PDF, DOCX, HTML, etc.) to Markdown
via ``docling.DocumentConverter`` and produces topology-preserving chunks via
``HybridChunker``.  Tables, lists, and structural elements survive chunking
intact — no Euclidean shredding.

All methods are synchronous.  Callers (e.g. ``AsyncDocumentIngestor``) wrap
calls in ``asyncio.to_thread()`` to avoid blocking the event loop.

Key design choices:
  - A fresh ``DocumentConverter`` is created per ``convert_to_markdown()``
    call because the converter is NOT thread-safe.
  - ``HybridChunker`` uses a ``HuggingFaceTokenizer`` aligned to BGE-M3's
    512-token window so each chunk fits a single embedding call.
  - ``merge_peers=True`` keeps sibling structural nodes (e.g. adjacent list
    items, table rows) together whenever they fit the token budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("formicos.dockling_parser")


# ── Result Model ─────────────────────────────────────────────────────────


@dataclass
class ChunkResult:
    """A single topology-preserving chunk produced by the parser."""

    text: str
    """Markdown chunk content."""

    meta: dict[str, Any] = field(default_factory=dict)
    """Docling structural metadata (heading path, doc-item type, etc.)."""

    chunk_index: int = 0
    """Position of this chunk within the source document."""


# ── Parser ───────────────────────────────────────────────────────────────


class DocklingParser:
    """Stateless document-to-chunks parser using docling + HybridChunker.

    Parameters
    ----------
    tokenizer_model:
        HuggingFace model ID for the tokenizer (default: BGE-M3).
    max_tokens:
        Maximum tokens per chunk — aligned to the embedding model's window.
    merge_peers:
        Whether HybridChunker should merge sibling structural nodes.
    """

    def __init__(
        self,
        tokenizer_model: str = "BAAI/bge-m3",
        max_tokens: int = 512,
        merge_peers: bool = True,
    ) -> None:
        self._tokenizer_model = tokenizer_model
        self._max_tokens = max_tokens
        self._merge_peers = merge_peers

    # ── Convert ──────────────────────────────────────────────────

    def convert_to_markdown(self, file_path: str | Path) -> str:
        """Convert a document to Markdown using docling's DocumentConverter.

        Creates a fresh converter per call (NOT thread-safe).
        """
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        return result.document.export_to_markdown()

    # ── Chunk ────────────────────────────────────────────────────

    def chunk_markdown(self, markdown: str) -> list[ChunkResult]:
        """Split Markdown into topology-preserving chunks.

        Uses ``HybridChunker`` with ``merge_peers=True`` so that tables,
        lists, and heading-scoped blocks stay intact whenever they fit
        within the token budget.

        Returns an empty list for blank input.
        """
        if not markdown or not markdown.strip():
            return []

        from docling.chunking import HybridChunker
        from docling_core.transforms.chunker.tokenizer import (
            HuggingFaceTokenizer,
        )
        from docling_core.types.doc import DoclingDocument

        tokenizer = HuggingFaceTokenizer(
            tokenizer=self._tokenizer_model,
            max_tokens=self._max_tokens,
        )
        chunker = HybridChunker(
            tokenizer=tokenizer, merge_peers=self._merge_peers,
        )

        doc = DoclingDocument.from_markdown(markdown)
        raw_chunks = list(chunker.chunk(doc))

        results: list[ChunkResult] = []
        for idx, chunk in enumerate(raw_chunks):
            meta: dict[str, Any] = {}
            if hasattr(chunk, "meta") and chunk.meta:
                try:
                    meta = chunk.meta.export_json_dict()
                except Exception:
                    pass
            results.append(
                ChunkResult(text=chunk.text, meta=meta, chunk_index=idx)
            )

        return results

    # ── End-to-End ───────────────────────────────────────────────

    def parse(self, file_path: str | Path) -> list[ChunkResult]:
        """Convert a document and chunk it in one call.

        Equivalent to ``chunk_markdown(convert_to_markdown(file_path))``.
        """
        markdown = self.convert_to_markdown(file_path)
        return self.chunk_markdown(markdown)

    # ── Qdrant Handoff ───────────────────────────────────────────

    @staticmethod
    def to_qdrant_payloads(
        chunks: list[ChunkResult],
        source: str,
        doc_id: str,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Format chunks as Qdrant-ready payload dicts.

        Each payload contains::

            {"content": ..., "source": ..., "doc_id": ...,
             "chunk_index": ..., **meta, **extra}

        Ready for ``PointStruct(id=uuid, vector=embedding, payload=payload)``.
        """
        payloads: list[dict[str, Any]] = []
        for chunk in chunks:
            payload: dict[str, Any] = {
                "content": chunk.text,
                "source": source,
                "doc_id": doc_id,
                "chunk_index": chunk.chunk_index,
            }
            payload.update(chunk.meta)
            if extra:
                payload.update(extra)
            payloads.append(payload)
        return payloads
