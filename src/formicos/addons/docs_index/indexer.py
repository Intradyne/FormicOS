"""Documentation indexer — walks workspace, chunks doc files, embeds, upserts to Qdrant.

Chunking strategy: split on structural boundaries per format —
headings for Markdown/RST, ``<h1>``–``<h3>`` for HTML, blank lines for plain text.
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
_DOC_EXTENSIONS = frozenset({".md", ".rst", ".txt", ".html"})

# Directories to skip
_SKIP_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
})

COLLECTION_NAME = "docs_index"

# Regex patterns for structural splitting
_MD_HEADING_RE = re.compile(r"^(#{1,3})\s+", re.MULTILINE)
_RST_UNDERLINE_RE = re.compile(r"^[=\-~^\"]{3,}\s*$", re.MULTILINE)
_HTML_HEADING_RE = re.compile(r"<h[1-3][^>]*>", re.IGNORECASE)


@dataclass
class DocChunk:
    """A chunk of documentation with location metadata."""

    id: str
    text: str
    path: str
    section: str
    line_start: int
    line_end: int


def _is_doc_file(path: Path) -> bool:
    """Check if a file should be indexed."""
    return path.suffix.lower() in _DOC_EXTENSIONS and path.stat().st_size < 500_000


def _make_chunk_id(file_path: str, line_start: int) -> str:
    """Deterministic chunk ID from path and start line."""
    return hashlib.sha256(f"{file_path}:{line_start}".encode()).hexdigest()[:16]


def _flush_section(
    lines: list[str],
    file_path: str,
    section: str,
    line_start: int,
    chunks: list[DocChunk],
) -> None:
    """Flush accumulated lines into a DocChunk if non-empty."""
    text = "".join(lines).strip()
    if text:
        chunks.append(DocChunk(
            id=_make_chunk_id(file_path, line_start),
            text=text,
            path=file_path,
            section=section,
            line_start=line_start,
            line_end=line_start + len(lines) - 1,
        ))


def _chunk_markdown(content: str, file_path: str) -> list[DocChunk]:
    """Split Markdown on # / ## / ### headings."""
    lines = content.splitlines(keepends=True)
    chunks: list[DocChunk] = []
    current_section = "(intro)"
    current_lines: list[str] = []
    section_start = 1

    for i, line in enumerate(lines, start=1):
        if _MD_HEADING_RE.match(line):
            _flush_section(current_lines, file_path, current_section, section_start, chunks)
            current_section = line.lstrip("#").strip() or "(heading)"
            current_lines = [line]
            section_start = i
        else:
            current_lines.append(line)

    _flush_section(current_lines, file_path, current_section, section_start, chunks)
    return chunks


def _chunk_rst(content: str, file_path: str) -> list[DocChunk]:
    """Split RST on heading underlines."""
    lines = content.splitlines(keepends=True)
    chunks: list[DocChunk] = []
    current_section = "(intro)"
    current_lines: list[str] = []
    section_start = 1

    for i, line in enumerate(lines, start=1):
        stripped = line.rstrip("\n\r")
        if _RST_UNDERLINE_RE.match(stripped) and current_lines:
            # The previous line is the heading title
            title_line = current_lines.pop()
            # Flush everything before the title as previous section
            if current_lines:
                _flush_section(current_lines, file_path, current_section, section_start, chunks)
            current_section = title_line.strip() or "(heading)"
            current_lines = [title_line, line]
            section_start = i - 1
        else:
            current_lines.append(line)

    _flush_section(current_lines, file_path, current_section, section_start, chunks)
    return chunks


def _chunk_html(content: str, file_path: str) -> list[DocChunk]:
    """Split HTML on <h1>, <h2>, <h3> tags."""
    lines = content.splitlines(keepends=True)
    chunks: list[DocChunk] = []
    current_section = "(intro)"
    current_lines: list[str] = []
    section_start = 1

    for i, line in enumerate(lines, start=1):
        if _HTML_HEADING_RE.search(line):
            _flush_section(current_lines, file_path, current_section, section_start, chunks)
            # Extract heading text (strip tags naively)
            heading_text = re.sub(r"<[^>]+>", "", line).strip()
            current_section = heading_text or "(heading)"
            current_lines = [line]
            section_start = i
        else:
            current_lines.append(line)

    _flush_section(current_lines, file_path, current_section, section_start, chunks)
    return chunks


def _chunk_text(content: str, file_path: str) -> list[DocChunk]:
    """Split plain text on blank-line-delimited sections."""
    lines = content.splitlines(keepends=True)
    chunks: list[DocChunk] = []
    current_lines: list[str] = []
    section_start = 1
    section_idx = 0

    for i, line in enumerate(lines, start=1):
        if not line.strip() and current_lines:
            section_idx += 1
            _flush_section(
                current_lines, file_path, f"(section {section_idx})",
                section_start, chunks,
            )
            current_lines = []
            section_start = i + 1
        else:
            current_lines.append(line)

    if current_lines:
        section_idx += 1
        _flush_section(
            current_lines, file_path, f"(section {section_idx})",
            section_start, chunks,
        )
    return chunks


def chunk_document(content: str, file_path: str) -> list[DocChunk]:
    """Route to the appropriate chunker based on file extension."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext == "md":
        return _chunk_markdown(content, file_path)
    if ext == "rst":
        return _chunk_rst(content, file_path)
    if ext in ("htm", "html"):
        return _chunk_html(content, file_path)
    return _chunk_text(content, file_path)


def _chunks_to_docs(chunks: Sequence[DocChunk]) -> list[VectorDocument]:
    """Convert doc chunks to VectorDocuments for the VectorPort."""
    return [
        VectorDocument(
            id=chunk.id,
            content=chunk.text,
            metadata={
                "path": chunk.path,
                "section": chunk.section,
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
    """Walk workspace, chunk doc files, upsert to vector store.

    Returns summary dict with file_count, chunk_count, errors.
    """
    file_count = 0
    chunk_count = 0
    errors = 0

    for path in sorted(workspace_path.rglob("*")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or not _is_doc_file(path):
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(path.relative_to(workspace_path))
            chunks = chunk_document(content, rel_path)
            file_count += 1

            docs = _chunks_to_docs(chunks)
            if docs:
                await vector_port.upsert(COLLECTION_NAME, docs)
                chunk_count += len(docs)
        except Exception:  # noqa: BLE001
            errors += 1
            log.warning(
                "docs_index.file_error",
                path=str(path), exc_info=True,
            )

    log.info(
        "docs_index.reindex_complete",
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
        if not path.is_file() or not _is_doc_file(path):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            chunks = chunk_document(content, rel_path)
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
