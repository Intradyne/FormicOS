"""WebSocket command handlers — thin wrappers over runtime.

Each handler delegates to runtime operations (ADR-005: same ops for MCP and WS).
No direct event emission — runtime.emit_and_broadcast is the ONE mutation path.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from formicos.surface.structured_error import KNOWN_ERRORS, to_ws_error

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


async def handle_command(
    action: str,
    workspace_id: str,
    payload: dict[str, Any],
    runtime: Runtime,
) -> dict[str, Any]:
    """Dispatch a WS command to the appropriate handler. Returns response dict."""
    handler = _COMMAND_HANDLERS.get(action)
    if handler is None:
        return to_ws_error(KNOWN_ERRORS["UNKNOWN_COMMAND"].model_copy(
            update={"message": f"Unknown command '{action}'"},
        ))
    try:
        return await handler(workspace_id, payload, runtime)
    except KeyError as exc:
        log.warning("ws.command_missing_field", action=action, field=str(exc))
        return to_ws_error(KNOWN_ERRORS["MISSING_FIELD"].model_copy(
            update={"message": f"Missing required field: {exc}"},
        ))
    except Exception:
        log.exception("ws.command_failed", action=action, workspace_id=workspace_id)
        return to_ws_error(KNOWN_ERRORS["INTERNAL_ERROR"])


# ---------------------------------------------------------------------------
# Individual command handlers — thin wrappers over runtime
# ---------------------------------------------------------------------------


async def _handle_spawn_colony(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    # Template resolution (ADR-016): load defaults, allow overrides
    template_id = payload.get("templateId")
    template = None
    if template_id:
        from formicos.surface.template_manager import get_template
        template = await get_template(template_id)
        if template is None:
            return {"error": f"template '{template_id}' not found"}

    # Resolve spawn parameters: explicit payload > template defaults > hardcoded
    from formicos.core.types import CasteSlot

    if template is not None:
        raw_castes = payload.get("castes", payload.get("team",
                     [s.model_dump() for s in template.castes]))
        strategy = payload.get("strategy", template.strategy)
        max_rounds = payload.get("maxRounds", template.max_rounds)
        budget_limit = payload.get("budgetLimit", template.budget_limit)
    else:
        # Accept "team" as alias for "castes" (Wave 49 confirm-from-preview).
        raw_castes = payload.get("castes", payload.get("team"))
        if not raw_castes:
            return {"error": "castes (or team) is required"}
        strategy = payload.get("strategy", "stigmergic")
        max_rounds = payload.get("maxRounds", 25)
        budget_limit = payload.get("budgetLimit", 5.0)

    castes = [CasteSlot(**c) if isinstance(c, dict) else c for c in raw_castes]  # pyright: ignore[reportUnknownArgumentType]

    # Wave 49: forward targetFiles and fastPath from confirm-from-preview.
    raw_target = payload.get("targetFiles", [])
    target_files = list(raw_target) if isinstance(raw_target, list) else []
    fast_path = bool(payload.get("fastPath", False))

    colony_id = await runtime.spawn_colony(
        workspace_id, payload["threadId"], payload["task"],
        castes,
        strategy=strategy,
        max_rounds=max_rounds,
        budget_limit=budget_limit,
        model_assignments=payload.get("modelAssignments"),
        template_id=template_id or "",
        target_files=target_files or None,
        fast_path=fast_path,
    )

    # Emit ColonyTemplateUsed if spawned from template
    if template_id and template is not None:
        from datetime import UTC, datetime

        from formicos.core.events import ColonyTemplateUsed
        address = f"{workspace_id}/{payload['threadId']}/{colony_id}"
        await runtime.emit_and_broadcast(ColonyTemplateUsed(
            seq=0, timestamp=datetime.now(UTC), address=address,
            template_id=template_id,
            colony_id=colony_id,
        ))

    # Start colony round loop
    if runtime.colony_manager is not None:
        asyncio.create_task(runtime.colony_manager.start_colony(colony_id))
    return {"colonyId": colony_id, "templateId": template_id}


async def _handle_kill_colony(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.kill_colony(payload["colonyId"], payload.get("killedBy", "operator"))
    return {"status": "killed"}


async def _handle_send_queen_message(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.send_queen_message(workspace_id, payload["threadId"], payload["content"])
    # Queen responds asynchronously — events stream to UI via WS
    if runtime.queen is not None:
        asyncio.create_task(runtime.queen.respond(workspace_id, payload["threadId"]))
    return {"status": "sent"}


async def _handle_create_merge(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    edge_id = await runtime.create_merge(
        workspace_id, payload["fromColony"], payload["toColony"],
        payload.get("createdBy", "operator"),
    )
    return {"edgeId": edge_id}


async def _handle_prune_merge(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.prune_merge(workspace_id, payload["edgeId"])
    return {"status": "pruned"}


async def _handle_broadcast(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    from_colony = payload.get("fromColony")
    if not from_colony:
        return {"error": "fromColony is required for broadcast — select a colony to broadcast from"}
    thread_id = payload.get("threadId")
    if not thread_id:
        return {"error": "threadId is required for broadcast"}
    edges = await runtime.broadcast(workspace_id, thread_id, from_colony)
    return {"edges": edges}


async def _handle_approve(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.approve(workspace_id, payload["requestId"])
    return {"status": "approved"}


async def _handle_deny(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.deny(workspace_id, payload["requestId"])
    return {"status": "denied"}


async def _handle_update_config(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    await runtime.update_config(workspace_id, payload["field"], payload.get("value"))
    return {"status": "updated"}


async def _handle_chat_colony(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    """Send an operator message to a colony's chat (algorithms.md §8)."""
    colony_id = payload["colonyId"]
    message = payload["message"]

    colony = runtime.projections.get_colony(colony_id)
    if colony is None:
        return {"error": f"colony '{colony_id}' not found"}

    from datetime import UTC, datetime

    from formicos.core.events import ColonyChatMessage
    address = f"{colony.workspace_id}/{colony.thread_id}/{colony_id}"
    await runtime.emit_and_broadcast(ColonyChatMessage(
        seq=0, timestamp=datetime.now(UTC), address=address,
        colony_id=colony_id, workspace_id=colony.workspace_id,
        sender="operator", content=message,
    ))

    # Inject into colony's context for next round
    if runtime.colony_manager is not None:
        await runtime.colony_manager.inject_message(colony_id, message)

    return {"status": "sent"}


async def _handle_activate_service(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    """Activate a completed colony as a service colony."""
    colony_id = payload["colonyId"]
    service_type = payload["serviceType"]

    if runtime.colony_manager is None:
        return {"error": "colony manager not available"}

    try:
        await runtime.colony_manager.activate_service(colony_id, service_type)
    except ValueError as exc:
        return {"error": str(exc)}

    return {"status": "activated", "serviceType": service_type}


async def _handle_create_thread(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    thread_id = await runtime.create_thread(workspace_id, payload["name"])
    return {"threadId": thread_id}


async def _handle_rename_colony(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    colony_id = payload["colonyId"]
    new_name = payload["name"]
    colony = runtime.projections.get_colony(colony_id)
    if colony is None:
        return {"error": f"colony '{colony_id}' not found"}

    from datetime import UTC, datetime

    from formicos.core.events import ColonyNamed
    address = f"{colony.workspace_id}/{colony.thread_id}/{colony.id}"
    await runtime.emit_and_broadcast(ColonyNamed(
        seq=0, timestamp=datetime.now(UTC), address=address,
        colony_id=colony_id, display_name=new_name, named_by="operator",
    ))
    return {"status": "renamed"}


async def _handle_rename_thread(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    thread_id = payload["threadId"]
    new_name = payload["name"]
    await runtime.rename_thread(workspace_id, thread_id, new_name)
    return {"status": "renamed"}


async def _handle_save_queen_note(
    workspace_id: str, payload: dict[str, Any], runtime: Runtime,
) -> dict[str, Any]:
    """Save a Queen message as a thread-scoped preference (Wave 23 B3)."""
    if runtime.queen is None:
        return {"error": "queen unavailable"}
    thread_id = payload["threadId"]
    content = payload["content"]
    if not content:
        return {"error": "content is required"}
    count = await runtime.queen.save_thread_note(workspace_id, thread_id, content)
    return {"status": "saved", "noteCount": count}


_COMMAND_HANDLERS: dict[str, Any] = {
    "create_thread": _handle_create_thread,
    "spawn_colony": _handle_spawn_colony,
    "kill_colony": _handle_kill_colony,
    "send_queen_message": _handle_send_queen_message,
    "create_merge": _handle_create_merge,
    "prune_merge": _handle_prune_merge,
    "broadcast": _handle_broadcast,
    "approve": _handle_approve,
    "deny": _handle_deny,
    "update_config": _handle_update_config,
    "chat_colony": _handle_chat_colony,
    "activate_service": _handle_activate_service,
    "rename_colony": _handle_rename_colony,
    "rename_thread": _handle_rename_thread,
    "save_queen_note": _handle_save_queen_note,
}


__all__ = ["handle_command"]
