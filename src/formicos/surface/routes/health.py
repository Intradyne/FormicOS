"""Health and debug routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.surface.projections import ProjectionStore
    from formicos.surface.registry import CapabilityRegistry


def routes(
    *,
    projections: ProjectionStore,
    registry: CapabilityRegistry,
    **_unused: Any,
) -> list[Route]:
    """Build health/debug routes."""

    async def health(_request: Request) -> JSONResponse:
        thread_count = sum(len(ws.threads) for ws in projections.workspaces.values())
        return JSONResponse({
            "status": "ok",
            "last_seq": projections.last_seq,
            "bootstrapped": bool(projections.workspaces),
            "workspaces": len(projections.workspaces),
            "threads": thread_count,
            "colonies": len(projections.colonies),
            "memory_entries": len(projections.memory_entries),
            "memory_extractions": len(projections.memory_extractions_completed),
        })

    async def debug_inventory(_request: Request) -> JSONResponse:
        return JSONResponse(registry.to_dict())

    return [
        Route("/health", health),
        Route("/debug/inventory", debug_inventory, methods=["GET"]),
    ]
