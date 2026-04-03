"""Queen thread lifecycle manager — governance, archival, workflow steps.

Extracted from queen_runtime.py (Wave 32 B2). Handles thread-level
operations: governance alerts, archival decay, workflow step definition.
"""
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from formicos.core.events import (
    MemoryConfidenceUpdated,
    ThreadStatusChanged,
    WorkflowStepDefined,
)
from formicos.core.types import WorkflowStep
from formicos.surface.knowledge_constants import (
    ARCHIVAL_EQUIVALENT_DAYS,
    GAMMA_PER_DAY,
    MAX_ELAPSED_DAYS,
    PRIOR_ALPHA,
    PRIOR_BETA,
)

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_projection_timestamp(timestamp: str) -> datetime | None:
    """Best-effort parser for projection timestamps stored as strings."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


class QueenThreadManager:
    """Thread lifecycle operations extracted from QueenAgent."""

    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime

    async def on_governance_alert(
        self,
        colony_id: str,
        workspace_id: str,
        thread_id: str,
        alert_type: str,
        emit_queen_message: Any,  # noqa: ANN401
    ) -> None:
        """React to a governance alert for a Queen-spawned colony.

        Preconditions (all must be true):
        1. Thread has recent operator activity (30 min)
        2. Colony is running and has not exhausted its redirect cap
        """
        thread = self._runtime.projections.get_thread(
            workspace_id, thread_id,
        )
        if thread is None:
            return

        recent_cutoff = _now() - timedelta(minutes=30)
        has_recent = any(
            m.role == "operator"
            and (
                parsed := _parse_projection_timestamp(m.timestamp)
            ) is not None
            and parsed >= recent_cutoff
            for m in thread.queen_messages
        )
        if not has_recent:
            return

        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None or colony.status != "running":
            return

        max_redirects = (
            self._runtime.settings.governance.max_redirects_per_colony
        )
        history = getattr(colony, "redirect_history", [])
        if len(history) >= max_redirects:
            return

        display = getattr(colony, "display_name", None) or colony_id
        await emit_queen_message(
            workspace_id,
            thread_id,
            f"Governance alert on colony **{display}**: "
            f"{alert_type}. Inspecting.",
        )

        log.info(
            "queen.governance_alert",
            colony_id=colony_id,
            alert_type=alert_type,
            workspace_id=workspace_id,
            thread_id=thread_id,
        )

    async def archive_thread(
        self,
        workspace_id: str,
        thread_id: str,
        reason: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Archive a thread and apply confidence decay to its entries."""
        ws = self._runtime.projections.workspaces.get(workspace_id)
        old_status = "completed"
        if ws is not None:
            thread = ws.threads.get(thread_id)
            if thread is not None:
                old_status = thread.status

        await self._runtime.emit_and_broadcast(
            ThreadStatusChanged(
                seq=0, timestamp=_now(),
                address=f"{workspace_id}/{thread_id}",
                workspace_id=workspace_id,
                thread_id=thread_id,
                old_status=old_status,
                new_status="archived",
                reason=reason,
            ),
        )

        # Archival decay: confidence shrink for thread entries
        decayed = 0
        mem_entries = self._runtime.projections.memory_entries
        for entry_id, entry in mem_entries.items():
            if entry.get("thread_id") != thread_id:
                continue
            old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
            old_beta = float(entry.get("conf_beta", PRIOR_BETA))
            # Wave 32 A2: symmetric gamma-burst at 30-day equivalent (ADR-041 D2)
            # Wave 33 A4: defensive cap for future-proofing
            archival_days = min(ARCHIVAL_EQUIVALENT_DAYS, MAX_ELAPSED_DAYS)
            archival_gamma = GAMMA_PER_DAY ** archival_days
            new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
            new_beta = max(archival_gamma * old_beta + (1 - archival_gamma) * PRIOR_BETA, 1.0)
            new_conf = new_alpha / (new_alpha + new_beta)
            await self._runtime.emit_and_broadcast(
                MemoryConfidenceUpdated(
                    seq=0, timestamp=_now(),
                    address=f"{workspace_id}/{thread_id}",
                    entry_id=entry_id,
                    colony_id="",
                    colony_succeeded=True,
                    old_alpha=old_alpha,
                    old_beta=old_beta,
                    new_alpha=new_alpha,
                    new_beta=new_beta,
                    new_confidence=new_conf,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    reason="archival_decay",
                ),
            )
            decayed += 1

        return (
            f"Thread archived: {reason}. "
            f"{decayed} entries decayed.",
            None,
        )

    async def define_workflow_steps(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Define declarative workflow steps for a thread (Wave 30 B6)."""
        from formicos.engine.schema_sanitize import coerce_array_items  # noqa: PLC0415

        raw_steps = coerce_array_items(inputs.get("steps", []))
        if not raw_steps:
            return ("Error: steps array is required.", None)

        defined: list[str] = []
        for idx, raw in enumerate(raw_steps):
            step = WorkflowStep(
                step_index=idx,
                description=str(raw.get("description", "")),
                expected_outputs=raw.get("expected_outputs", []),
                template_id=str(raw.get("template_id", "")),
                strategy=str(raw.get("strategy", "stigmergic")),
                input_from_step=int(raw.get("input_from_step", -1)),
            )
            await self._runtime.emit_and_broadcast(WorkflowStepDefined(
                seq=0,
                timestamp=_now(),
                address=f"{workspace_id}/{thread_id}",
                workspace_id=workspace_id,
                thread_id=thread_id,
                step=step,
            ))
            defined.append(f"[{idx}] {step.description}")

        return (
            f"Defined {len(defined)} workflow step(s):\n"
            + "\n".join(defined),
            None,
        )


__all__ = ["QueenThreadManager"]
