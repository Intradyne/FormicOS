"""Configuration mutation helpers (Wave 5).

Surface handlers for workspace config overrides and model assignment changes.
All mutations emit events — no shadow stores (ADR-001).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.events import (
    ModelAssignmentChanged,
    WorkspaceConfigChanged,
)

if TYPE_CHECKING:
    from formicos.core.ports import EventStorePort
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


async def _emit(
    event_store: EventStorePort,
    projections: ProjectionStore,
    event: Any,  # noqa: ANN401
) -> int:
    seq = await event_store.append(event)
    event_with_seq = event.model_copy(update={"seq": seq})
    projections.apply(event_with_seq)
    return seq


async def update_workspace_config(
    workspace_id: str,
    field: str,
    value: str | float | None,
    event_store: EventStorePort,
    projections: ProjectionStore,
) -> dict[str, Any]:
    """Update a single workspace configuration field."""
    ws = projections.workspaces.get(workspace_id)
    if ws is None:
        return {"error": f"workspace '{workspace_id}' not found"}

    old_value = ws.config.get(field)
    old_str = str(old_value) if old_value is not None else None
    new_str = str(value) if value is not None else None

    await _emit(event_store, projections, WorkspaceConfigChanged(
        seq=0, timestamp=_now(), address=workspace_id,
        workspace_id=workspace_id, field=field,
        old_value=old_str, new_value=new_str,
    ))
    return {"status": "updated", "field": field}


async def update_model_assignment(
    scope: str,
    caste: str,
    new_model: str | None,
    event_store: EventStorePort,
    projections: ProjectionStore,
    old_model: str | None = None,
) -> dict[str, Any]:
    """Change the model assignment for a caste at system or workspace scope."""
    await _emit(event_store, projections, ModelAssignmentChanged(
        seq=0, timestamp=_now(), address=scope,
        scope=scope, caste=caste,
        old_model=old_model, new_model=new_model,
    ))
    return {"status": "updated", "scope": scope, "caste": caste}


def get_workspace_config(
    projections: ProjectionStore,
    workspace_id: str,
) -> dict[str, Any] | None:
    """Read the current workspace config from projections."""
    ws = projections.workspaces.get(workspace_id)
    if ws is None:
        return None
    return {
        "id": ws.id,
        "name": ws.name,
        "config": dict(ws.config),
    }


__all__ = [
    "get_workspace_config",
    "update_model_assignment",
    "update_workspace_config",
]
