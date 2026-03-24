"""AG-UI Tier 1 SSE bridge — honest summary-at-turn-end semantics (ADR-035).

POST /ag-ui/runs spawns a colony and streams AG-UI-formatted events until
completion.  Read-only: spawn + observe, no steering.

Emitted events:
    RUN_STARTED, RUN_FINISHED, STEP_STARTED, STEP_FINISHED,
    TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT, TEXT_MESSAGE_END,
    STATE_SNAPSHOT, CUSTOM

NOT emitted (runner does not produce the required granularity):
    TOOL_CALL_START, TOOL_CALL_END, STATE_DELTA, token streaming
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from sse_starlette.sse import EventSourceResponse
from starlette.responses import JSONResponse

from formicos.core.events import RoundCompleted, RoundStarted
from formicos.surface.event_translator import (
    TERMINAL_EVENTS,
    run_started,
    sse_frame,
    state_snapshot,
    translate_event,
)
from formicos.surface.structured_error import KNOWN_ERRORS, to_http_error

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

    from formicos.core.events import FormicOSEvent

log = structlog.get_logger()

# AG-UI Tier 1 supported event types (9 total).
AGUI_EVENT_TYPES = frozenset({
    "RUN_STARTED",
    "RUN_FINISHED",
    "STEP_STARTED",
    "STEP_FINISHED",
    "TEXT_MESSAGE_START",
    "TEXT_MESSAGE_CONTENT",
    "TEXT_MESSAGE_END",
    "STATE_SNAPSHOT",
    "CUSTOM",
})


async def handle_agui_run(request: Request) -> EventSourceResponse | JSONResponse:
    """POST /ag-ui/runs — spawn a colony and stream AG-UI SSE events."""
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        status, err_body, headers = to_http_error(KNOWN_ERRORS["INVALID_JSON"])
        return JSONResponse(err_body, status_code=status, headers=headers)

    task = body.get("task", "")
    if not task:
        status, err_body, headers = to_http_error(KNOWN_ERRORS["TASK_REQUIRED"])
        return JSONResponse(err_body, status_code=status, headers=headers)

    raw_castes: list[dict[str, Any]] = body.get("castes", [])
    workspace_id = body.get("workspace_id", "default")
    thread_id = body.get("thread_id", "main")
    caller_budget: float | None = body.get("budget_limit")

    runtime = request.app.state.runtime  # type: ignore[attr-defined]
    ws_manager = request.app.state.ws_manager  # type: ignore[attr-defined]

    # Build CasteSlots (Wave 52 B3: classifier-informed defaults when omitted)
    from formicos.core.types import CasteSlot, SubcasteTier  # noqa: PLC0415
    from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

    if not raw_castes:
        cat_name, cat = classify_task(task)
        castes = [
            CasteSlot(caste=c, tier=SubcasteTier.standard)
            for c in cat.get("default_castes", ["coder", "reviewer"])
        ]
        server_strategy = cat.get("default_strategy", "stigmergic")
        server_budget = cat.get("default_budget", 2.0)
    else:
        castes = [CasteSlot(**c) for c in raw_castes]
        server_strategy = body.get("strategy", "stigmergic")
        server_budget = 2.0

    # Wave 52 B2: explicit budget — caller-provided or server-selected
    budget_limit = caller_budget if caller_budget is not None else server_budget
    strategy = body.get("strategy", server_strategy)

    # Wave 52 B2: workspace spawn-gate parity
    from formicos.surface.runtime import BudgetEnforcer  # noqa: PLC0415
    enforcer = BudgetEnforcer(runtime.projections)
    allowed, reason = enforcer.check_spawn_allowed(workspace_id)
    if not allowed:
        status, err_body, headers = to_http_error(KNOWN_ERRORS["SPAWN_FAILED"].model_copy(
            update={"details": {"reason": f"Budget gate: {reason}"}},
        ))
        return JSONResponse(err_body, status_code=status, headers=headers)

    # Spawn colony
    try:
        colony_id = await runtime.spawn_colony(
            workspace_id, thread_id, task, castes,
            strategy=strategy, budget_limit=budget_limit,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("agui.spawn_failed", error=str(exc))
        status, err_body, headers = to_http_error(KNOWN_ERRORS["SPAWN_FAILED"].model_copy(
            update={"details": {"reason": str(exc)}},
        ))
        return JSONResponse(err_body, status_code=status, headers=headers)

    # Start colony execution
    if runtime.colony_manager is not None:
        asyncio.create_task(runtime.colony_manager.start_colony(colony_id))

    # Subscribe to colony events
    queue = await ws_manager.subscribe_colony(colony_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        current_round = 0
        idle_count = 0
        _MAX_IDLE = 3  # 3 × 300s = 15min max idle before disconnect
        try:
            # Emit RUN_STARTED
            yield run_started(colony_id)

            while True:
                try:
                    event: FormicOSEvent = await asyncio.wait_for(
                        queue.get(), timeout=300,
                    )
                    idle_count = 0
                except TimeoutError:
                    # Wave 52 A7: non-terminal idle — check if colony actually finished
                    idle_count += 1
                    refreshed = runtime.projections.get_colony(colony_id)
                    if refreshed is not None and refreshed.status not in ("pending", "running"):
                        yield sse_frame("RUN_FINISHED", {
                            "type": "RUN_FINISHED",
                            "runId": colony_id,
                            "status": refreshed.status,
                            "timestamp": __import__("datetime").datetime.now(
                                __import__("datetime").UTC,
                            ).isoformat(),
                        })
                        break
                    if idle_count >= _MAX_IDLE:
                        yield sse_frame("CUSTOM", {
                            "type": "CUSTOM",
                            "runId": colony_id,
                            "name": "idle_disconnect",
                            "value": {"idle_seconds": 300 * idle_count},
                        })
                        break
                    # Emit keepalive state snapshot
                    if refreshed is not None:
                        yield state_snapshot(colony_id, refreshed)
                    continue

                # Track round number
                if isinstance(event, RoundStarted):
                    current_round = event.round_number

                # Translate and yield
                for frame in translate_event(colony_id, event, current_round):
                    yield frame

                # STATE_SNAPSHOT after each round completion
                if isinstance(event, RoundCompleted):
                    colony = runtime.projections.get_colony(colony_id)
                    if colony is not None:
                        yield state_snapshot(colony_id, colony)

                # Terminal — stop
                if isinstance(event, TERMINAL_EVENTS):
                    break

        finally:
            ws_manager.unsubscribe_colony(colony_id, queue)

    return EventSourceResponse(event_generator())


__all__ = ["AGUI_EVENT_TYPES", "handle_agui_run"]
