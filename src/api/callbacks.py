"""
FormicOS v0.7.9 -- WebSocket Callback Factories

Extracted from server.py.  These build the ``callbacks`` dict that the
Orchestrator uses to push real-time events to WebSocket clients.

- make_ws_callbacks:  Legacy broadcast callbacks
- make_ws_callbacks_v1:  V1 EventEnvelope callbacks (dual-emit to both managers)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from src.api.helpers import event_envelope
from src.api.ws import ConnectionManager, ConnectionManagerV1
from src.colony_manager import ColonyManager
from src.models import EventTrace


def make_ws_callbacks(colony_id: str, manager: ConnectionManager) -> dict:
    """Create orchestrator callback dict that broadcasts events via WS."""

    async def on_round_update(round_num: int, phase: str, data: Any) -> None:
        await manager.broadcast({
            "type": "round_update",
            "colony_id": colony_id,
            "round": round_num,
            "phase": phase,
            "data": data,
        })

    async def on_token(agent_id: str, token: str) -> None:
        await manager.broadcast({
            "type": "token_stream",
            "colony_id": colony_id,
            "agent_id": agent_id,
            "token": token,
        })

    async def on_tool_call(
        agent_id: str, tool: str, args: dict, result: str = ""
    ) -> None:
        await manager.broadcast({
            "type": "tool_call",
            "colony_id": colony_id,
            "agent_id": agent_id,
            "tool": tool,
            "args": args,
            "result": result,
        })

    async def on_approval_request(
        agent_id: str, tool: str, args: dict, request_id: str = ""
    ) -> None:
        await manager.broadcast({
            "type": "approval_request",
            "colony_id": colony_id,
            "agent_id": agent_id,
            "tool": tool,
            "args": args,
            "request_id": request_id,
        })

    async def on_colony_complete(outcome: str) -> None:
        await manager.broadcast({
            "type": "colony_complete",
            "colony_id": colony_id,
            "outcome": outcome,
        })

    async def on_error(message: str) -> None:
        await manager.broadcast({
            "type": "error",
            "colony_id": colony_id,
            "message": message,
        })

    return {
        "on_round_update": on_round_update,
        "on_stream_token": on_token,
        "on_tool_call": on_tool_call,
        "on_approval_request": on_approval_request,
        "on_colony_complete": on_colony_complete,
        "on_error": on_error,
    }


def make_ws_callbacks_v1(colony_id: str, app: FastAPI) -> dict:
    """Create orchestrator callbacks that emit EventEnvelopeV1 events.

    Reads ws_manager and ws_manager_v1 from app.state.
    Dual-emits to both V1 subscription manager and legacy broadcast manager.
    """
    ws_manager: ConnectionManager = app.state.ws_manager
    ws_manager_v1: ConnectionManagerV1 = app.state.ws_manager_v1

    async def on_round_update(round_num: int, phase: str, data: Any) -> None:
        env = event_envelope(
            "colony.round.phase", colony_id,
            {"round": round_num, "phase": phase, "data": data},
            EventTrace(round=round_num),
        )
        await ws_manager_v1.emit(env)
        # Also broadcast on legacy manager for backward compat
        await ws_manager.broadcast({
            "type": "round_update", "colony_id": colony_id,
            "round": round_num, "phase": phase, "data": data,
        })

        # Emit colony.round.advanced on new round start (v0.7.3)
        if phase == "phase_1_goal":
            cm: ColonyManager = app.state.colony_manager
            try:
                info = cm.get_info(colony_id)
                max_rounds = info.max_rounds
            except Exception:
                max_rounds = 0
            adv_env = event_envelope(
                "colony.round.advanced", colony_id,
                {"round": round_num, "max_rounds": max_rounds},
                EventTrace(round=round_num),
            )
            await ws_manager_v1.emit(adv_env)
            await ws_manager.broadcast({
                "type": "colony_round_advanced", "colony_id": colony_id,
                "round": round_num, "max_rounds": max_rounds,
            })

    async def on_token(agent_id: str, token: str) -> None:
        env = event_envelope(
            "agent.token", colony_id,
            {"agent_id": agent_id, "token": token},
        )
        await ws_manager_v1.emit(env)
        await ws_manager.broadcast({
            "type": "token_stream", "colony_id": colony_id,
            "agent_id": agent_id, "token": token,
        })

    async def on_tool_call(
        agent_id: str, tool: str, args: dict, result: str = ""
    ) -> None:
        env = event_envelope(
            "agent.tool.call", colony_id,
            {"agent_id": agent_id, "tool": tool, "args": args, "result": result},
        )
        await ws_manager_v1.emit(env)
        await ws_manager.broadcast({
            "type": "tool_call", "colony_id": colony_id,
            "agent_id": agent_id, "tool": tool, "args": args, "result": result,
        })

    async def on_approval_request(
        agent_id: str, tool: str, args: dict, request_id: str = ""
    ) -> None:
        env = event_envelope(
            "approval.requested", colony_id,
            {"agent_id": agent_id, "tool": tool, "args": args, "request_id": request_id},
        )
        await ws_manager_v1.emit(env)
        await ws_manager.broadcast({
            "type": "approval_request", "colony_id": colony_id,
            "agent_id": agent_id, "tool": tool, "args": args, "request_id": request_id,
        })

    async def on_colony_complete(outcome: str) -> None:
        env = event_envelope(
            "colony.completed", colony_id,
            {"outcome": outcome},
        )
        await ws_manager_v1.emit(env)
        await ws_manager.broadcast({
            "type": "colony_complete", "colony_id": colony_id, "outcome": outcome,
        })

    async def on_error(message: str) -> None:
        env = event_envelope(
            "colony.failed", colony_id,
            {"message": message},
        )
        await ws_manager_v1.emit(env)
        await ws_manager.broadcast({
            "type": "error", "colony_id": colony_id, "message": message,
        })

    def on_metric(name: str, value_ms: float) -> None:
        """Record an SLO metric value."""
        metrics = getattr(app.state, "slo_metrics", None)
        if metrics and name in metrics:
            metrics[name].append(value_ms)
            # Keep only last 1000 samples per metric
            if len(metrics[name]) > 1000:
                metrics[name] = metrics[name][-1000:]

    return {
        "on_round_update": on_round_update,
        "on_stream_token": on_token,
        "on_tool_call": on_tool_call,
        "on_approval_request": on_approval_request,
        "on_colony_complete": on_colony_complete,
        "on_error": on_error,
        "on_metric": on_metric,
    }
