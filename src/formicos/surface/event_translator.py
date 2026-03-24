"""Shared AG-UI-shaped event translation for SSE streams (Wave 24 B2).

Extracted from agui_endpoint.py so that both AG-UI and A2A attach can
reuse the same FormicOS-to-AG-UI event translation without drift.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ApprovalRequested,
    ColonyChatMessage,
    ColonyCompleted,
    ColonyFailed,
    ColonyKilled,
    KnowledgeAccessRecorded,
    KnowledgeDistilled,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    ParallelPlanCreated,
    RoundCompleted,
    RoundStarted,
    WorkflowStepCompleted,
)

if TYPE_CHECKING:
    from formicos.core.events import FormicOSEvent

TERMINAL_EVENTS = (ColonyCompleted, ColonyFailed, ColonyKilled)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sse_frame(event_type: str, data: dict[str, Any]) -> dict[str, str]:
    """Format a single SSE frame."""
    return {"event": event_type, "data": json.dumps(data)}


def run_started(colony_id: str) -> dict[str, str]:
    return sse_frame("RUN_STARTED", {
        "type": "RUN_STARTED",
        "runId": colony_id,
        "timestamp": _now_iso(),
    })


def run_finished(
    colony_id: str, event: FormicOSEvent, *, timed_out: bool = False,
) -> dict[str, str]:
    status = "timeout" if timed_out else "completed"
    if isinstance(event, ColonyFailed):
        status = "failed"
    elif isinstance(event, ColonyKilled):
        status = "killed"
    return sse_frame("RUN_FINISHED", {
        "type": "RUN_FINISHED",
        "runId": colony_id,
        "status": status,
        "timestamp": _now_iso(),
    })


def step_started(colony_id: str, round_number: int) -> dict[str, str]:
    return sse_frame("STEP_STARTED", {
        "type": "STEP_STARTED",
        "runId": colony_id,
        "stepId": f"{colony_id}-r{round_number}",
        "step": round_number,
        "timestamp": _now_iso(),
    })


def step_finished(colony_id: str, round_number: int) -> dict[str, str]:
    return sse_frame("STEP_FINISHED", {
        "type": "STEP_FINISHED",
        "runId": colony_id,
        "stepId": f"{colony_id}-r{round_number}",
        "step": round_number,
        "timestamp": _now_iso(),
    })


def text_message_start(
    colony_id: str, event: AgentTurnStarted, round_number: int,
) -> dict[str, str]:
    return sse_frame("TEXT_MESSAGE_START", {
        "type": "TEXT_MESSAGE_START",
        "messageId": f"{colony_id}-{event.agent_id}-r{round_number}",
        "role": event.caste,
        "timestamp": _now_iso(),
    })


def text_message_content(
    colony_id: str, event: AgentTurnCompleted, round_number: int,
) -> dict[str, str]:
    return sse_frame("TEXT_MESSAGE_CONTENT", {
        "type": "TEXT_MESSAGE_CONTENT",
        "messageId": f"{colony_id}-{event.agent_id}-r{round_number}",
        "content": event.output_summary,
        "contentType": "summary",
    })


def text_message_end(
    colony_id: str, event: AgentTurnCompleted, round_number: int,
) -> dict[str, str]:
    return sse_frame("TEXT_MESSAGE_END", {
        "type": "TEXT_MESSAGE_END",
        "messageId": f"{colony_id}-{event.agent_id}-r{round_number}",
        "timestamp": _now_iso(),
    })


def state_snapshot(colony_id: str, colony: Any) -> dict[str, str]:
    """Build STATE_SNAPSHOT from colony projection."""
    try:
        from formicos.surface.transcript import build_transcript
        snapshot = build_transcript(colony)
    except ImportError:
        snapshot = {
            "colony_id": colony.id,
            "status": colony.status,
            "round": colony.round_number,
            "cost": colony.cost,
            "convergence": colony.convergence,
        }
    return sse_frame("STATE_SNAPSHOT", {
        "type": "STATE_SNAPSHOT",
        "snapshot": snapshot,
    })


def custom_event(colony_id: str, event: FormicOSEvent) -> dict[str, str]:
    """Passthrough for FormicOS events not mapped to AG-UI standard events."""
    event_type: str = getattr(event, "type", event.__class__.__name__)
    try:
        payload = json.loads(event.model_dump_json())  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:  # noqa: BLE001
        payload = {"event_type": event_type}
    return sse_frame("CUSTOM", {
        "type": "CUSTOM",
        "name": event_type,
        "runId": colony_id,
        "value": payload,
    })


def translate_event(
    colony_id: str,
    event: FormicOSEvent,
    current_round: int,
) -> Iterator[dict[str, str]]:
    """Translate a single FormicOS event into AG-UI-shaped SSE frames.

    Yields zero or more SSE frames. Updates to ``current_round`` must be
    tracked by the caller based on RoundStarted events.
    """
    if isinstance(event, RoundStarted):
        yield step_started(colony_id, event.round_number)
    elif isinstance(event, AgentTurnStarted):
        yield text_message_start(colony_id, event, current_round)
    elif isinstance(event, AgentTurnCompleted):
        yield text_message_content(colony_id, event, current_round)
        yield text_message_end(colony_id, event, current_round)
    elif isinstance(event, RoundCompleted):
        yield step_finished(colony_id, current_round)
    elif isinstance(event, TERMINAL_EVENTS):
        yield run_finished(colony_id, event)
    elif isinstance(event, ApprovalRequested):
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "APPROVAL_NEEDED",
            "runId": colony_id,
            "value": {
                "request_id": event.request_id,
                "approval_type": (
                    event.approval_type.value
                    if hasattr(event.approval_type, "value")
                    else str(event.approval_type)
                ),
                "detail": event.detail,
                "requires_human": True,
                "suggested_action": "approve or deny via MCP approve/deny tools",
            },
        })
    # Wave 33 B8: promoted AG-UI events (4 new)
    elif isinstance(event, MemoryEntryCreated):
        entry: dict[str, Any] = getattr(event, "entry", {})
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "KNOWLEDGE_EXTRACTED",
            "runId": colony_id,
            "value": {
                "entry_id": entry.get("id", ""),
                "entry_type": entry.get("entry_type", ""),
                "domains": entry.get("domains", []),
                "scan_status": entry.get("scan_status", "pending"),
            },
        })
    elif isinstance(event, MemoryConfidenceUpdated):
        old_total = event.old_alpha + event.old_beta
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "CONFIDENCE_UPDATED",
            "runId": colony_id,
            "value": {
                "entry_id": event.entry_id,
                "old_confidence": round(event.old_alpha / old_total, 4) if old_total > 0 else 0.5,
                "new_confidence": event.new_confidence,
                "reason": event.reason,
            },
        })
    elif isinstance(event, KnowledgeAccessRecorded):
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "KNOWLEDGE_ACCESSED",
            "runId": colony_id,
            "value": {
                "colony_id": event.colony_id,
                "access_mode": event.access_mode,
                "item_count": len(event.items),
            },
        })
    elif isinstance(event, WorkflowStepCompleted):
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "STEP_COMPLETED",
            "runId": colony_id,
            "value": {
                "step_index": event.step_index,
                "colony_id": event.colony_id,
                "success": event.success,
            },
        })
    # Wave 35: knowledge distillation
    elif isinstance(event, KnowledgeDistilled):
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "KNOWLEDGE_DISTILLED",
            "runId": colony_id,
            "value": {
                "distilled_entry_id": event.distilled_entry_id,
                "source_count": len(event.source_entry_ids),
                "cluster_avg_weight": event.cluster_avg_weight,
            },
        })
    # Wave 35: parallel plan DAG visualization
    elif isinstance(event, ParallelPlanCreated):
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "PARALLEL_PLAN",
            "runId": colony_id,
            "value": {
                "thread_id": event.thread_id,
                "parallel_groups": event.parallel_groups,
                "reasoning": event.reasoning,
                "knowledge_gaps": event.knowledge_gaps,
                "estimated_cost": event.estimated_cost,
            },
        })
    # Wave 35 C1: operator directive AG-UI event (ADR-045 D3)
    elif (
        isinstance(event, ColonyChatMessage)
        and event.directive_type
        and event.sender == "operator"
    ):
        metadata = event.metadata or {}
        yield sse_frame("CUSTOM", {
            "type": "CUSTOM",
            "name": "OPERATOR_DIRECTIVE",
            "runId": colony_id,
            "value": {
                "directive_type": event.directive_type,
                "priority": metadata.get("directive_priority", "normal"),
                "content": event.content,
            },
        })
    else:
        yield custom_event(colony_id, event)


def maintenance_colony_spawned(
    colony_id: str,
    insight_category: str,
    insight_title: str,
    estimated_cost: float,
) -> dict[str, str]:
    """AG-UI custom event for maintenance colony dispatch (Wave 35)."""
    return sse_frame("CUSTOM", {
        "type": "CUSTOM",
        "name": "MAINTENANCE_COLONY_SPAWNED",
        "runId": colony_id,
        "value": {
            "colony_id": colony_id,
            "insight_category": insight_category,
            "insight_title": insight_title,
            "estimated_cost": estimated_cost,
        },
    })


__all__ = [
    "TERMINAL_EVENTS",
    "custom_event",
    "maintenance_colony_spawned",
    "run_finished",
    "run_started",
    "sse_frame",
    "state_snapshot",
    "step_finished",
    "step_started",
    "text_message_content",
    "text_message_end",
    "text_message_start",
    "translate_event",
]
