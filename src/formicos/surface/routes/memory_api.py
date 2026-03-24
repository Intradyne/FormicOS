"""Institutional memory REST API (Wave 26 B5).

**DEPRECATED (Wave 51):** Use ``/api/v1/knowledge`` endpoints instead.
These endpoints emit ``Sunset`` headers and log usage for evidence-based
removal planning.

- ``GET /api/v1/memory`` -- list entries with filters
- ``GET /api/v1/memory/search`` -- hybrid retrieval search
- ``GET /api/v1/memory/{entry_id}`` -- full entry detail with provenance
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.surface.memory_store import MemoryStore
    from formicos.surface.projections import ProjectionStore

_log = structlog.get_logger(__name__)

# RFC 8594 Sunset header — signals this API will be removed.
_SUNSET_HEADERS = {
    "Sunset": "Sat, 30 Aug 2026 00:00:00 GMT",
    "Deprecation": "true",
    "Link": '</api/v1/knowledge>; rel="successor-version"',
}


def routes(
    *,
    projections: ProjectionStore,
    memory_store: MemoryStore | None = None,
    **_unused: Any,
) -> list[Route]:
    """Build institutional memory API routes."""

    def _log_deprecated(endpoint: str, request: Request) -> None:
        """Log usage of deprecated endpoint for removal evidence."""
        _log.info(
            "deprecated_api_used",
            endpoint=endpoint,
            method=request.method,
            user_agent=request.headers.get("user-agent", ""),
            query_params=dict(request.query_params),
        )

    async def list_entries(request: Request) -> JSONResponse:
        """List memory entries from projection state with optional filters."""
        _log_deprecated("/api/v1/memory", request)
        entry_type = request.query_params.get("type", "")
        status = request.query_params.get("status", "")
        workspace = request.query_params.get("workspace", "")
        domain = request.query_params.get("domain", "")
        try:
            limit = max(1, min(200, int(request.query_params.get("limit", "50"))))
        except ValueError:
            return JSONResponse(
                {"error": "limit must be an integer"}, status_code=400,
                headers=_SUNSET_HEADERS,
            )

        memory_entries: dict[str, dict[str, Any]] = getattr(
            projections, "memory_entries", {},
        )
        entries = list(memory_entries.values())

        if entry_type:
            entries = [e for e in entries if e.get("entry_type") == entry_type]
        if status:
            entries = [e for e in entries if e.get("status") == status]
        if workspace:
            entries = [e for e in entries if e.get("workspace_id") == workspace]
        if domain:
            entries = [e for e in entries if domain in e.get("domains", [])]

        # Sort: newest first
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        total = len(entries)
        return JSONResponse(
            {
                "_deprecated": (
                    "This endpoint is deprecated. "
                    "Use /api/v1/knowledge and /api/v1/knowledge/search instead."
                ),
                "entries": entries[:limit],
                "total": total,
            },
            headers=_SUNSET_HEADERS,
        )

    async def get_entry(request: Request) -> JSONResponse:
        """Get full detail for a single memory entry."""
        _log_deprecated("/api/v1/memory/{entry_id}", request)
        entry_id = request.path_params["entry_id"]
        memory_entries: dict[str, dict[str, Any]] = getattr(
            projections, "memory_entries", {},
        )
        entry = memory_entries.get(entry_id)
        if entry is None:
            return JSONResponse(
                {"error": "entry not found"}, status_code=404,
                headers=_SUNSET_HEADERS,
            )
        return JSONResponse(
            {
                "_deprecated": (
                    "This endpoint is deprecated. "
                    "Use /api/v1/knowledge/{id} instead."
                ),
                **entry,
            },
            headers=_SUNSET_HEADERS,
        )

    async def search_entries(request: Request) -> JSONResponse:
        """Search institutional memory with hybrid retrieval."""
        _log_deprecated("/api/v1/memory/search", request)
        if memory_store is None:
            return JSONResponse(
                {"error": "memory store not available"}, status_code=503,
                headers=_SUNSET_HEADERS,
            )

        query = request.query_params.get("q", "")
        if not query:
            return JSONResponse(
                {"error": "query parameter 'q' is required"}, status_code=400,
                headers=_SUNSET_HEADERS,
            )

        entry_type = request.query_params.get("type", "")
        workspace = request.query_params.get("workspace", "")
        try:
            limit = max(1, min(50, int(request.query_params.get("limit", "10"))))
        except ValueError:
            return JSONResponse(
                {"error": "limit must be an integer"}, status_code=400,
                headers=_SUNSET_HEADERS,
            )

        results = await memory_store.search(
            query=query,
            entry_type=entry_type,
            workspace_id=workspace,
            top_k=limit,
        )
        return JSONResponse(
            {
                "_deprecated": (
                    "This endpoint is deprecated. "
                    "Use /api/v1/knowledge/search instead."
                ),
                "results": results,
                "total": len(results),
            },
            headers=_SUNSET_HEADERS,
        )

    return [
        Route("/api/v1/memory", list_entries, methods=["GET"]),
        Route("/api/v1/memory/search", search_entries, methods=["GET"]),
        Route("/api/v1/memory/{entry_id:str}", get_entry, methods=["GET"]),
    ]
