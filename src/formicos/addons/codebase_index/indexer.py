"""Codebase indexer — walks workspace, chunks code files, embeds, upserts to Qdrant.

Chunking strategy: split on function/class boundaries where detectable
(simple regex for ``def``/``class`` in Python, ``function``/``class`` in JS/TS),
fall back to sliding-window chunks.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.types import VectorDocument

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

log = structlog.get_logger()

# File extensions worth indexing
_CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".sh", ".yaml", ".yml",
    ".toml", ".json", ".md", ".sql", ".html", ".css",
})

# Directories to skip
_SKIP_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
})

# Regex for Python/JS/TS structural boundaries
_BOUNDARY_RE = re.compile(
    r"^(?:def |class |async def |function |export (?:default )?(?:function |class ))",
    re.MULTILINE,
)

COLLECTION_NAME = "code_index"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 100


@dataclass
class CodeChunk:
    """A chunk of code with location metadata."""

    id: str
    text: str
    path: str
    line_start: int
    line_end: int


def _is_code_file(path: Path) -> bool:
    """Check if a file should be indexed."""
    return path.suffix.lower() in _CODE_EXTENSIONS and path.stat().st_size < 500_000


def chunk_code(
    content: str,
    file_path: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[CodeChunk]:
    """Split code content into chunks, preferring structural boundaries."""
    lines = content.splitlines(keepends=True)
    if not lines:
        return []

    # Find structural boundaries (function/class definitions)
    boundaries: list[int] = [0]
    for i, line in enumerate(lines):
        if _BOUNDARY_RE.match(line) and i > 0:
            boundaries.append(i)

    chunks: list[CodeChunk] = []
    current_chars = 0
    current_start = 0

    for i, line in enumerate(lines):
        current_chars += len(line)
        # Split when we exceed chunk_size at a boundary or at hard limit (2x)
        at_boundary = (i + 1) in boundaries
        at_hard_limit = current_chars > chunk_size * 2
        at_soft_limit = current_chars > chunk_size and at_boundary

        if at_soft_limit or at_hard_limit or i == len(lines) - 1:
            chunk_text = "".join(lines[current_start:i + 1])
            if chunk_text.strip():
                chunk_id = hashlib.sha256(
                    f"{file_path}:{current_start}".encode()
                ).hexdigest()[:16]
                chunks.append(CodeChunk(
                    id=chunk_id,
                    text=chunk_text,
                    path=file_path,
                    line_start=current_start + 1,  # 1-indexed
                    line_end=i + 1,
                ))
            # Start next chunk with overlap
            overlap_start = max(current_start, i + 1 - (overlap // max(1, len(line))))
            current_start = i + 1 if not at_boundary else i
            if current_start <= overlap_start:
                current_start = overlap_start
            current_chars = sum(len(lines[j]) for j in range(current_start, i + 1))

    return chunks


def _chunks_to_docs(chunks: Sequence[CodeChunk]) -> list[VectorDocument]:
    """Convert code chunks to VectorDocuments for the VectorPort."""
    return [
        VectorDocument(
            id=chunk.id,
            content=chunk.text,
            metadata={
                "path": chunk.path,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "content": chunk.text,
            },
        )
        for chunk in chunks
    ]


async def full_reindex(
    workspace_path: Path,
    vector_port: Any,
) -> dict[str, Any]:
    """Walk workspace, chunk files, upsert to vector store.

    The VectorPort handles embedding internally — no embed_fn needed.
    Returns summary dict with file_count, chunk_count, errors.
    """
    file_count = 0
    chunk_count = 0
    errors = 0

    for path in sorted(workspace_path.rglob("*")):
        # Skip excluded directories
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or not _is_code_file(path):
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(path.relative_to(workspace_path))
            chunks = chunk_code(content, rel_path)
            file_count += 1

            docs = _chunks_to_docs(chunks)
            if docs:
                await vector_port.upsert(COLLECTION_NAME, docs)
                chunk_count += len(docs)
        except Exception:  # noqa: BLE001
            errors += 1
            log.warning(
                "codebase_index.file_error",
                path=str(path), exc_info=True,
            )

    log.info(
        "codebase_index.reindex_complete",
        files=file_count,
        chunks=chunk_count,
        errors=errors,
    )
    return {
        "file_count": file_count,
        "chunk_count": chunk_count,
        "errors": errors,
    }


async def incremental_reindex(
    workspace_path: Path,
    vector_port: Any,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Re-index only changed files.

    If ``changed_files`` is None, falls back to full reindex.
    """
    if changed_files is None:
        return await full_reindex(workspace_path, vector_port)

    chunk_count = 0
    errors = 0

    for rel_path in changed_files:
        path = workspace_path / rel_path
        if not path.is_file() or not _is_code_file(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            chunks = chunk_code(content, rel_path)
            docs = _chunks_to_docs(chunks)
            if docs:
                await vector_port.upsert(COLLECTION_NAME, docs)
                chunk_count += len(docs)
        except Exception:  # noqa: BLE001
            errors += 1

    return {
        "file_count": len(changed_files),
        "chunk_count": chunk_count,
        "errors": errors,
    }


async def on_scheduled_reindex(
    *,
    runtime_context: dict[str, Any] | None = None,
) -> None:
    """Cron trigger wrapper: extract deps from runtime_context and run full_reindex."""
    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")
    workspace_root_fn = ctx.get("workspace_root_fn")

    if not vector_port or not workspace_root_fn:
        log.warning(
            "codebase_index.cron_skip",
            reason="missing vector_port or workspace_root_fn",
        )
        return

    # Reindex all known workspaces
    projections = ctx.get("projections")
    ws_ids = list(
        getattr(projections, "workspaces", {}).keys(),
    ) if projections else []
    for ws_id in ws_ids:
        ws_path = workspace_root_fn(ws_id)
        if ws_path and ws_path.is_dir():
            await full_reindex(ws_path, vector_port)
