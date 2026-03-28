"""Semantic documentation search handler for the docs-index addon."""

from __future__ import annotations

import fnmatch
from typing import Any

import structlog

from formicos.addons.docs_index.indexer import COLLECTION_NAME

log = structlog.get_logger()


def _format_result(hit: Any) -> str:
    """Format a single search result for display."""
    metadata = getattr(hit, "metadata", {}) or {}
    payload = getattr(hit, "payload", metadata) or {}
    path = payload.get("path", "?")
    section = payload.get("section", "")
    line_start = payload.get("line_start", "?")
    line_end = payload.get("line_end", "?")
    content = payload.get("content", "")
    score = getattr(hit, "score", 0.0)
    # Truncate content for display
    if len(content) > 300:
        content = content[:300] + "..."
    header = f"**{path}:{line_start}-{line_end}**"
    if section:
        header += f" [{section}]"
    header += f" (score: {score:.3f})"
    return f"{header}\n```\n{content}\n```"


async def handle_semantic_search(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Search documentation by semantic meaning using the vector index."""
    query = inputs.get("query", "")
    top_k = inputs.get("top_k", 10)
    file_pattern = inputs.get("file_pattern", "")

    if not query:
        return "Error: query parameter is required."

    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")

    if vector_port is None:
        return (
            "Semantic search unavailable — vector store not configured. "
            "Ensure the Qdrant sidecar is running."
        )

    try:
        hits = await vector_port.search(COLLECTION_NAME, query, top_k)
    except Exception:  # noqa: BLE001
        log.warning("docs_index.search_error", exc_info=True)
        return (
            "Documentation index not found. Build it first with the "
            "'reindex_docs' tool."
        )

    if not hits:
        return (
            f"No results found for '{query}' in documentation index. "
            "The index may be empty — try 'reindex_docs' first."
        )

    # Filter by file pattern if provided
    if file_pattern:
        filtered: list[Any] = []
        for h in hits:
            metadata = getattr(h, "metadata", {}) or {}
            payload = getattr(h, "payload", metadata) or {}
            path = payload.get("path", "")
            if fnmatch.fnmatch(path, file_pattern):
                filtered.append(h)
        hits = filtered

    if not hits:
        return f"No results matching pattern '{file_pattern}' for query '{query}'."

    lines = [f"**Documentation search:** {len(hits)} results for '{query}'\n"]
    for hit in hits:
        lines.append(_format_result(hit))
    return "\n\n".join(lines)


async def handle_reindex(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Trigger incremental or full reindex of workspace documentation."""
    from formicos.addons.docs_index.indexer import incremental_reindex

    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")
    workspace_root_fn = ctx.get("workspace_root_fn")

    if not vector_port or not workspace_root_fn:
        return (
            "Reindex unavailable — missing vector_port "
            "or workspace_root_fn in runtime context."
        )

    workspace_path = workspace_root_fn(workspace_id)
    if not workspace_path.is_dir():
        return f"Workspace path not found: {workspace_path}"

    changed_files = inputs.get("changed_files")
    result = await incremental_reindex(
        workspace_path, vector_port,
        changed_files=changed_files,
    )
    return (
        f"Reindex complete: {result['file_count']} files, "
        f"{result['chunk_count']} chunks indexed, {result['errors']} errors."
    )
