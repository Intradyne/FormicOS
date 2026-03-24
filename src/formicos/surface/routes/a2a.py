"""A2A inbound task lifecycle routes (ADR-038).

Tasks are colonies. ``task_id == colony_id``. No second store.
Submit / poll / attach / result lifecycle.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sse_starlette.sse import EventSourceResponse
from starlette.responses import JSONResponse
from starlette.routing import Route

from formicos.core.events import RoundCompleted, RoundStarted
from formicos.core.types import CasteSlot
from formicos.surface.credential_scan import redact_credentials
from formicos.surface.event_translator import (
    TERMINAL_EVENTS,
    run_finished,
    run_started,
    sse_frame,
    state_snapshot,
    translate_event,
)
from formicos.surface.structured_error import KNOWN_ERRORS, to_http_error
from formicos.surface.task_classifier import classify_task
from formicos.surface.template_manager import load_all_templates
from formicos.surface.transcript import build_transcript

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

    from formicos.core.events import FormicOSEvent
    from formicos.surface.colony_manager import ColonyManager
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import Runtime
    from formicos.surface.ws_handler import WebSocketManager

log = structlog.get_logger()

_A2A_THREAD_PREFIX = "a2a-"
_DEFAULT_WORKSPACE = "default"


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn a description into a short thread-name slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "task"


def _select_team(
    description: str,
    templates: list[Any],
) -> tuple[list[CasteSlot], str, int, float, dict[str, Any]]:
    """Deterministic team selection using shared classifier — no LLM call.

    Order: template tag match → shared classifier → safe fallback.
    Returns (castes, strategy, max_rounds, budget_limit, selection_metadata).
    """
    words = set(description.lower().split())

    # 1. Template match by tag overlap
    for tmpl in templates:
        tags = {t.lower() for t in getattr(tmpl, "tags", [])}
        if tags & words:
            return (
                list(tmpl.castes),
                tmpl.strategy,
                tmpl.max_rounds,
                tmpl.budget_limit,
                {
                    "source": "template",
                    "template_id": tmpl.template_id,
                    "template_name": tmpl.name,
                    "learned": getattr(tmpl, "learned", False),
                },
            )

    # 2. Shared classifier
    cat_name, cat = classify_task(description)
    castes = [CasteSlot(caste=c) for c in cat.get("default_castes", ["coder", "reviewer"])]
    return (
        castes,
        cat.get("default_strategy", "stigmergic"),
        cat.get("default_rounds", 10),
        cat.get("default_budget", 2.0),
        {
            "source": "classifier",
            "category": cat_name,
        },
    )


def _build_failure_context(colony: Any) -> dict[str, Any] | None:
    """Build conservative failure context from projection metadata."""
    if colony.status == "failed" and colony.failure_reason is not None:
        return {
            "failure_reason": colony.failure_reason,
            "failed_at_round": colony.failed_at_round,
        }
    if colony.status == "killed" and colony.killed_by is not None:
        return {
            "killed_by": colony.killed_by,
            "killed_at_round": colony.killed_at_round,
        }
    return None


def _terminal_event_for_colony(colony: Any) -> FormicOSEvent:
    """Build a minimal terminal event for SSE finish translation."""
    from formicos.core.events import ColonyCompleted, ColonyFailed, ColonyKilled

    seq: int = 0
    ts: datetime = datetime.now(UTC)
    addr: str = f"{colony.workspace_id}/{colony.thread_id}/{colony.id}"
    cid: str = colony.id
    if colony.status == "failed":
        return ColonyFailed(
            seq=seq, timestamp=ts, address=addr, colony_id=cid,
            reason=getattr(colony, "failure_reason", None) or "unknown",
        )
    if colony.status == "killed":
        return ColonyKilled(
            seq=seq, timestamp=ts, address=addr, colony_id=cid,
            killed_by=getattr(colony, "killed_by", None) or "unknown",
        )
    return ColonyCompleted(
        seq=seq, timestamp=ts, address=addr, colony_id=cid,
        summary="",
        skills_extracted=colony.skills_extracted,
    )


def _redact_transcript(transcript: dict[str, Any]) -> None:
    """In-place redaction of credential-bearing fields in a transcript dict."""
    for round_data in transcript.get("round_summaries", []):
        for agent in round_data.get("agents", []):
            summary = agent.get("output_summary", "")
            if summary:
                agent["output_summary"], _ = redact_credentials(summary)
    final = transcript.get("final_output", "")
    if final:
        transcript["final_output"], _ = redact_credentials(final)


def _colony_status_envelope(colony: Any) -> dict[str, Any]:
    """Build a task-status JSON envelope from a ColonyProjection."""
    # Wave 33 B7: next_actions on A2A status
    if colony.status in ("pending", "running"):
        next_actions = ["poll", "attach", "cancel"]
    elif colony.status == "completed":
        next_actions = ["result"]
    elif colony.status in ("failed", "killed"):
        next_actions = ["result", "retry"]
    else:
        next_actions = []

    envelope: dict[str, Any] = {
        "task_id": colony.id,
        "status": colony.status,
        "progress": {
            "round": colony.round_number,
            "max_rounds": colony.max_rounds,
            "convergence": colony.convergence,
        },
        "cost": colony.cost,
        "quality_score": colony.quality_score,
        "next_actions": next_actions,
    }
    failure_context = _build_failure_context(colony)
    if failure_context is not None:
        envelope["failure_context"] = failure_context
    return envelope


def routes(
    *,
    runtime: Runtime,
    projections: ProjectionStore,
    **_unused: Any,
) -> list[Route]:
    """Build A2A task lifecycle routes."""

    colony_manager: ColonyManager = runtime.colony_manager  # type: ignore[assignment]

    async def _err(err_key: str, **overrides: Any) -> JSONResponse:
        err = KNOWN_ERRORS[err_key]
        if overrides:
            err = err.model_copy(update=overrides)
        status, body, headers = to_http_error(err)
        return JSONResponse(body, status_code=status, headers=headers)

    async def create_task(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return await _err("INVALID_JSON")

        description = body.get("description", "").strip()
        if not description:
            return await _err("DESCRIPTION_REQUIRED")

        templates = await load_all_templates(
            projection_templates=projections.templates,
        )
        castes, strategy, max_rounds, budget_limit, selection = _select_team(
            description, templates,
        )

        # Wave 52 B2: workspace spawn-gate parity
        from formicos.surface.runtime import BudgetEnforcer  # noqa: PLC0415
        enforcer = BudgetEnforcer(projections)
        allowed, reason = enforcer.check_spawn_allowed(_DEFAULT_WORKSPACE)
        if not allowed:
            return await _err("SPAWN_FAILED", details={"reason": f"Budget gate: {reason}"})

        thread_name = _A2A_THREAD_PREFIX + _slugify(description)
        ws = projections.workspaces.get(_DEFAULT_WORKSPACE)
        if ws is None or thread_name not in ws.threads:
            await runtime.create_thread(_DEFAULT_WORKSPACE, thread_name)

        colony_id = await runtime.spawn_colony(
            workspace_id=_DEFAULT_WORKSPACE,
            thread_id=thread_name,
            task=description,
            castes=castes,
            strategy=strategy,
            max_rounds=max_rounds,
            budget_limit=budget_limit,
        )
        asyncio.create_task(colony_manager.start_colony(colony_id))

        log.info(
            "a2a.task_created",
            task_id=colony_id,
            thread=thread_name,
            strategy=strategy,
        )

        return JSONResponse(
            {
                "task_id": colony_id,
                "status": "running",
                "team": [
                    {
                        "caste": c.caste,
                        "tier": c.tier.value,
                        "count": c.count,
                    }
                    for c in castes
                ],
                "strategy": strategy,
                "max_rounds": max_rounds,
                "budget_limit": budget_limit,
                "selection": selection,
            },
            status_code=201,
        )

    async def list_tasks(request: Request) -> JSONResponse:
        status_filter = request.query_params.get("status")
        try:
            limit = max(1, min(100, int(request.query_params.get("limit", "50"))))
        except ValueError:
            return await _err("LIMIT_INVALID")

        all_colonies = projections.workspace_colonies(_DEFAULT_WORKSPACE)
        a2a_colonies = [
            colony for colony in all_colonies
            if colony.thread_id.startswith(_A2A_THREAD_PREFIX)
        ]
        if status_filter:
            a2a_colonies = [
                colony for colony in a2a_colonies if colony.status == status_filter
            ]

        a2a_colonies.sort(key=lambda colony: colony.id, reverse=True)
        a2a_colonies = a2a_colonies[:limit]

        return JSONResponse({"tasks": [_colony_status_envelope(c) for c in a2a_colonies]})

    async def get_task(request: Request) -> JSONResponse:
        task_id = request.path_params["task_id"]
        colony = projections.get_colony(task_id)
        if colony is None:
            return await _err("TASK_NOT_FOUND")
        return JSONResponse(_colony_status_envelope(colony))

    async def get_task_result(request: Request) -> JSONResponse:
        task_id = request.path_params["task_id"]
        colony = projections.get_colony(task_id)
        if colony is None:
            return await _err("TASK_NOT_FOUND")
        if colony.status in ("pending", "running"):
            return await _err("TASK_NOT_TERMINAL")
        transcript = build_transcript(colony)
        # Wave 33 B2: redact credentials from transcript exports
        _redact_transcript(transcript)
        return JSONResponse(
            {
                "task_id": task_id,
                "status": colony.status,
                "output": transcript.get("final_output", ""),
                "transcript": transcript,
                "quality_score": colony.quality_score,
                "skills_extracted": colony.skills_extracted,
                "cost": colony.cost,
            },
        )

    async def cancel_task(request: Request) -> JSONResponse:
        task_id = request.path_params["task_id"]
        colony = projections.get_colony(task_id)
        if colony is None:
            return await _err("TASK_NOT_FOUND")
        if colony.status not in ("pending", "running"):
            return await _err("TASK_ALREADY_TERMINAL")
        await runtime.kill_colony(task_id, killed_by="a2a")
        return JSONResponse({"task_id": task_id, "status": "killed"})

    async def attach_task_events(
        request: Request,
    ) -> EventSourceResponse | JSONResponse:
        """Snapshot-then-live-tail SSE stream for an A2A task."""
        task_id = request.path_params["task_id"]
        colony = projections.get_colony(task_id)
        if colony is None:
            return await _err("TASK_NOT_FOUND")

        ws_manager: WebSocketManager = request.app.state.ws_manager  # type: ignore[attr-defined]

        if colony.status not in ("pending", "running"):

            async def terminal_generator() -> AsyncIterator[dict[str, str]]:
                yield run_started(task_id)
                yield state_snapshot(task_id, colony)
                yield run_finished(task_id, _terminal_event_for_colony(colony))

            return EventSourceResponse(terminal_generator())

        queue = await ws_manager.subscribe_colony(task_id)

        async def live_generator() -> AsyncIterator[dict[str, str]]:
            current_round = colony.round_number
            idle_count = 0
            _MAX_IDLE = 3  # 3 × 300s = 15min max idle before disconnect
            try:
                yield run_started(task_id)
                yield state_snapshot(task_id, colony)

                while True:
                    try:
                        event: FormicOSEvent = await asyncio.wait_for(
                            queue.get(), timeout=300,
                        )
                        idle_count = 0
                    except TimeoutError:
                        # Wave 52 A7: non-terminal idle — check if colony is still running
                        idle_count += 1
                        refreshed = projections.get_colony(task_id)
                        if refreshed is not None and refreshed.status not in ("pending", "running"):
                            yield run_finished(task_id, _terminal_event_for_colony(refreshed))
                            break
                        if idle_count >= _MAX_IDLE:
                            yield sse_frame("CUSTOM", {
                                "type": "CUSTOM",
                                "runId": task_id,
                                "name": "idle_disconnect",
                                "value": {"idle_seconds": 300 * idle_count},
                            })
                            break
                        # Emit keepalive with current state
                        if refreshed is not None:
                            yield state_snapshot(task_id, refreshed)
                        continue

                    if isinstance(event, RoundStarted):
                        current_round = event.round_number

                    for frame in translate_event(task_id, event, current_round):
                        yield frame

                    if isinstance(event, RoundCompleted):
                        updated = projections.get_colony(task_id)
                        if updated is not None:
                            yield state_snapshot(task_id, updated)

                    if isinstance(event, TERMINAL_EVENTS):
                        break
            finally:
                ws_manager.unsubscribe_colony(task_id, queue)

        return EventSourceResponse(live_generator())

    return [
        Route("/a2a/tasks", create_task, methods=["POST"]),
        Route("/a2a/tasks", list_tasks, methods=["GET"]),
        Route("/a2a/tasks/{task_id}", get_task, methods=["GET"]),
        Route("/a2a/tasks/{task_id}/result", get_task_result, methods=["GET"]),
        Route("/a2a/tasks/{task_id}/events", attach_task_events, methods=["GET"]),
        Route("/a2a/tasks/{task_id}", cancel_task, methods=["DELETE"]),
    ]
