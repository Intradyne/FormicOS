"""Surface view-model helpers for operator surfaces (Wave 4).

Projection-derived read models for colony detail, approval queue,
and round history. These are presentation helpers, NOT a second
source of truth — all data comes from ProjectionStore.
"""

from __future__ import annotations

from typing import Any

from formicos.surface.projections import (
    ApprovalProjection,
    ColonyProjection,
    ProjectionStore,
    RoundProjection,
)


def colony_detail(store: ProjectionStore, colony_id: str) -> dict[str, Any] | None:
    """Build a colony detail view matching types.ts ColonyDetail shape."""
    colony = store.get_colony(colony_id)
    if colony is None:
        return None
    return _serialize_colony(colony)


def approval_queue(store: ProjectionStore) -> list[dict[str, Any]]:
    """Build the pending approval queue for the operator."""
    return [_serialize_approval(a) for a in store.pending_approvals()]


def round_history(store: ProjectionStore, colony_id: str) -> list[dict[str, Any]]:
    """Build the round history for a colony."""
    colony = store.get_colony(colony_id)
    if colony is None:
        return []
    return [_serialize_round(r) for r in colony.round_records]


def workspace_colonies(
    store: ProjectionStore, workspace_id: str,
) -> list[dict[str, Any]]:
    """List all colonies in a workspace with summary info."""
    return [
        {
            "id": c.id,
            "threadId": c.thread_id,
            "task": c.task,
            "status": c.status,
            "round": c.round_number,
            "maxRounds": c.max_rounds,
            "convergence": c.convergence,
            "cost": c.cost,
        }
        for c in store.workspace_colonies(workspace_id)
    ]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_colony(colony: ColonyProjection) -> dict[str, Any]:
    return {
        "id": colony.id,
        "threadId": colony.thread_id,
        "workspaceId": colony.workspace_id,
        "task": colony.task,
        "status": colony.status,
        "round": colony.round_number,
        "maxRounds": colony.max_rounds,
        "strategy": colony.strategy,
        "convergence": colony.convergence,
        "cost": colony.cost,
        "budgetLimit": colony.budget_limit,
        "agents": [
            {
                "id": a.id,
                "caste": a.caste,
                "model": a.model,
                "status": a.status,
                "tokens": a.tokens,
            }
            for a in colony.agents.values()
        ],
        "rounds": [_serialize_round(r) for r in colony.round_records],
    }


def _serialize_round(r: RoundProjection) -> dict[str, Any]:
    return {
        "roundNumber": r.round_number,
        "phase": r.current_phase,
        "convergence": r.convergence,
        "cost": r.cost,
        "durationMs": r.duration_ms,
        "agentOutputs": r.agent_outputs,
        "toolCalls": r.tool_calls,
    }


def _serialize_approval(a: ApprovalProjection) -> dict[str, Any]:
    return {
        "id": a.id,
        "type": a.approval_type,
        "detail": a.detail,
        "colonyId": a.colony_id,
    }


__all__ = ["approval_queue", "colony_detail", "round_history", "workspace_colonies"]
