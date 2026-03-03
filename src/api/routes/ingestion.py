"""
FormicOS v0.8.0 -- V1 Ingestion Routes

Routes:
  POST /ingestion/queue          — queue a document for async ingestion
  GET  /ingestion/status/{id}    — poll task status
  GET  /ingestion/tasks          — list all ingestion tasks
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from src.api.helpers import api_error_v1
from src.auth import ClientAPIKey, get_current_client

router = APIRouter()


@router.post("/ingestion/queue")
async def v1_queue_ingestion(
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """Queue a document for async ingestion.

    Body
    ----
    file_path : str (required)
        Absolute or workspace-relative path to the document.
    collection : str (required)
        Qdrant collection to ingest into.
    colony_id : str (optional)
        Colony context for metadata tagging.
    """
    body = await request.json()
    file_path = body.get("file_path", "").strip()
    collection = body.get("collection", "").strip()
    colony_id = body.get("colony_id")

    if not file_path:
        return api_error_v1(400, "VALIDATION_ERROR", "file_path is required")
    if not collection:
        return api_error_v1(400, "VALIDATION_ERROR", "collection is required")

    ingestor = getattr(request.app.state, "ingestor", None)
    if ingestor is None:
        return api_error_v1(
            503, "SERVICE_UNAVAILABLE",
            "Document ingestor not initialised",
        )

    try:
        task_id = await ingestor.queue_document(
            file_path=file_path,
            collection=collection,
            colony_id=colony_id,
        )
    except FileNotFoundError:
        return api_error_v1(
            404, "INGESTION_FILE_NOT_FOUND",
            f"File not found: {file_path}",
        )
    except ValueError as exc:
        return api_error_v1(
            400, "INGESTION_UNSUPPORTED_FORMAT", str(exc),
        )

    return {"task_id": task_id, "status": "queued"}


@router.get("/ingestion/status/{task_id}")
async def v1_ingestion_status(
    request: Request,
    task_id: str,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """Poll the status of an ingestion task."""
    ingestor = getattr(request.app.state, "ingestor", None)
    if ingestor is None:
        return api_error_v1(
            503, "SERVICE_UNAVAILABLE",
            "Document ingestor not initialised",
        )

    task = ingestor.get_task(task_id)
    if task is None:
        return api_error_v1(
            404, "INGESTION_TASK_NOT_FOUND",
            f"No ingestion task with id '{task_id}'",
        )

    return task.to_dict()


@router.get("/ingestion/tasks")
async def v1_list_ingestion_tasks(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    """List ingestion tasks with pagination."""
    ingestor = getattr(request.app.state, "ingestor", None)
    if ingestor is None:
        return api_error_v1(
            503, "SERVICE_UNAVAILABLE",
            "Document ingestor not initialised",
        )

    tasks = ingestor.list_tasks(limit=limit, offset=offset)
    return {
        "items": [t.to_dict() for t in tasks],
        "total": ingestor.total_tasks,
        "limit": limit,
        "offset": offset,
    }
