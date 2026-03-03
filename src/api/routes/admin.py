"""
FormicOS v0.7.9 -- V1 Admin Routes

Routes: /admin/rebuild, /admin/diagnostics/{colony_id},
        /queue GET, /queue/{colony_id} DELETE, /webhooks/logs
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from src.api.helpers import api_error_v1, check_colony_ownership
from src.auth import ClientAPIKey, get_current_client
from src.colony_manager import ColonyManager
from src.models import ColonyStatus
from src.worker import WorkerManager

logger = logging.getLogger("formicos.server")

router = APIRouter()


@router.post("/admin/rebuild")
async def v1_admin_rebuild(request: Request):
    """
    v0.7.8: Allows the Cloud Model to autonomously restart FormicOS
    Docker containers after applying a codebase patch.
    Localhost-only for security.
    """
    client_host = request.client.host if request.client else "unknown"
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return api_error_v1(
            403, "LOCALHOST_ONLY",
            f"Rebuild endpoint restricted to localhost, got {client_host}",
        )
    import subprocess as _sp
    _sp.Popen(
        "sleep 2 && docker-compose down && docker-compose up --build -d",
        shell=True,
        cwd=str(Path(__file__).resolve().parent.parent.parent),
        start_new_session=True,
    )
    logger.warning("v0.7.8: Autonomous rebuild initiated by %s", client_host)
    return {
        "status": "REBUILD_INITIATED",
        "estimated_downtime_seconds": 30,
    }


@router.get("/admin/diagnostics/{colony_id}")
async def v1_admin_diagnostics(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """
    v0.7.8: Aggregates system state for Cloud Model autonomous debugging.
    Returns orchestrator traceback, VRAM, decisions, and episodes.
    """
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    client_id = client.client_id if client else None
    # NOTE: Original server.py called _check_colony_ownership(cm, colony_id, client_id)
    # with 3 args -- this is preserved as-is (existing behavior).
    ownership_err = check_colony_ownership(cm, colony_id, client_id)
    if ownership_err:
        return ownership_err

    try:
        diagnostics = await cm.get_diagnostics(colony_id)
    except Exception as exc:
        return api_error_v1(404, "COLONY_NOT_FOUND", str(exc))

    # Add WebSocket connection count
    ws_manager_v1 = app.state.ws_manager_v1
    ws_count = sum(
        1 for _ws, subs in ws_manager_v1.connections.items()
        if colony_id in subs or None in subs
    )
    diagnostics["ws_connections"] = ws_count

    return diagnostics


# -- Queue (v0.7.6) --

@router.get("/queue")
async def v1_get_queue(
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """Return the compute queue state: active locks + queued."""
    wm: WorkerManager = request.app.state.worker_manager
    active = wm.get_active_colonies()
    queued = wm.get_queue_snapshot()

    # Filter by client_id if authenticated
    if client is not None:
        active = [
            a for a in active
            if a.get("client_id") == client.client_id
        ]
        queued = [
            q for q in queued
            if q.get("client_id") == client.client_id
        ]

    return {
        "active_compute_locks": active,
        "queued": queued,
    }


@router.delete("/queue/{colony_id}")
async def v1_remove_from_queue(
    colony_id: str,
    request: Request,
    fire_webhook: bool = Query(False),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """Remove a colony from the compute queue."""
    app = request.app
    cm: ColonyManager = app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err

    wm: WorkerManager = app.state.worker_manager
    entry = wm.dequeue(colony_id)
    if entry is None:
        return api_error_v1(
            404, "QUEUE_COLONY_NOT_FOUND",
            f"Colony '{colony_id}' is not in the compute queue",
        )

    # Transition colony status to FAILED (aborted)
    try:
        async with cm._lock:
            state = cm._colonies.get(colony_id)
            if (
                state
                and state.info.status
                == ColonyStatus.QUEUED_PENDING_COMPUTE
            ):
                cm._set_status(state, ColonyStatus.FAILED)
                cm._persist_registry_sync()
    except Exception as exc:
        logger.warning(
            "Failed to update status for dequeued '%s': %s",
            colony_id, exc,
        )

    # Optionally fire ABORTED webhook
    if fire_webhook:
        wd = getattr(app.state, "webhook_dispatcher", None)
        webhook_url = None
        try:
            info = cm.get_info(colony_id)
            webhook_url = info.webhook_url
        except Exception:
            pass
        if wd and webhook_url:
            await wd.dispatch(
                url=webhook_url,
                payload={
                    "type": "colony.aborted",
                    "colony_id": colony_id,
                    "client_id": entry.client_id,
                    "status": "ABORTED_BY_SYSTEM",
                    "timestamp": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(),
                    ),
                },
                colony_id=colony_id,
            )

    return {
        "status": "removed",
        "colony_id": colony_id,
        "was_queued": True,
        "webhook_fired": fire_webhook,
    }


# -- Webhooks --

@router.get("/webhooks/logs")
async def v1_webhook_logs(
    request: Request,
    colony_id: str | None = Query(None),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    dispatcher = getattr(request.app.state, "webhook_dispatcher", None)
    if dispatcher is None:
        return {"logs": [], "note": "Webhook dispatcher not initialized"}
    logs = dispatcher.get_logs(colony_id=colony_id)
    if client is not None:
        logs = [
            entry for entry in logs
            if entry.get("payload", {}).get("client_id") == client.client_id
        ]
    return {"logs": logs}
