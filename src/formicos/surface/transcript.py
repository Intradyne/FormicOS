"""Colony transcript builder (Wave 20 Track A).

Pure function that reads from ``ColonyProjection`` — no I/O, no HTTP calls.

Consumed by:
- ``GET /api/v1/colonies/{id}/transcript`` (HTTP endpoint)
- AG-UI late-join replay (future Track B)
- Colony chaining resolution (future)
"""

from __future__ import annotations

from typing import Any

from formicos.surface.projections import ColonyProjection


def _build_team(colony: ColonyProjection) -> list[dict[str, Any]]:
    """Return a truthful team summary from caste slots when available."""
    team: list[dict[str, Any]] = []

    if colony.castes:
        for slot in colony.castes:
            if hasattr(slot, "caste"):
                caste = getattr(slot, "caste", "")
                tier = getattr(slot, "tier", "standard")
                count = getattr(slot, "count", 1)
            else:
                slot_dict: dict[str, Any] = slot if isinstance(slot, dict) else {}  # pyright: ignore[reportUnknownVariableType]
                caste = str(slot_dict.get("caste", ""))
                tier: Any = slot_dict.get("tier", "standard")
                count: Any = slot_dict.get("count", 1)
            tier_value: str = tier.value if hasattr(tier, "value") else str(tier)
            model = colony.model_assignments.get(caste, "")
            if not model:
                for agent in colony.agents.values():
                    if agent.caste == caste:
                        model = agent.model
                        break
            team.append({
                "caste": caste,
                "tier": tier_value,
                "count": int(count),  # pyright: ignore[reportUnknownArgumentType]
                "model": model,
            })
        return team

    # Older colonies may not have caste slots populated; fall back to agent inventory.
    grouped: dict[tuple[str, str], int] = {}
    for agent in colony.agents.values():
        key = (agent.caste, agent.model)
        grouped[key] = grouped.get(key, 0) + 1
    for (caste, model), count in sorted(grouped.items()):
        team.append({
            "caste": caste,
            "tier": "standard",
            "count": count,
            "model": model,
        })
    return team


def build_transcript(colony: ColonyProjection) -> dict[str, Any]:
    """Build a structured summary of a colony.

    Works for running, completed, failed, and killed colonies.
    """
    round_summaries: list[dict[str, Any]] = []
    for rec in colony.round_records:
        agents: list[dict[str, Any]] = []
        for agent_id, output in rec.agent_outputs.items():
            agent_proj = colony.agents.get(agent_id)
            agents.append({
                "id": agent_id,
                "caste": agent_proj.caste if agent_proj else "unknown",
                "output_summary": output[:500],
                "tool_calls": rec.tool_calls.get(agent_id, []),
            })
        round_summaries.append({
            "round": rec.round_number,
            "agents": agents,
            "convergence": rec.convergence,
            "cost": rec.cost,
        })

    # Final output: last round's combined agent outputs
    final_output = ""
    if colony.round_records:
        last = colony.round_records[-1]
        final_output = "\n\n".join(
            f"[{aid}] {out[:1000]}"
            for aid, out in last.agent_outputs.items()
        )

    # Build conservative failure context from projection metadata (Wave 24 C2)
    failure_context: dict[str, Any] | None = None
    if colony.status == "failed" and colony.failure_reason is not None:
        failure_context = {
            "failure_reason": colony.failure_reason,
            "failed_at_round": colony.failed_at_round,
        }
    elif colony.status == "killed" and colony.killed_by is not None:
        failure_context = {
            "killed_by": colony.killed_by,
            "killed_at_round": colony.killed_at_round,
        }

    # Wave 25: artifact previews (truncated content for transcript readability)
    artifact_previews: list[dict[str, Any]] = []
    for art in getattr(colony, "artifacts", []):
        preview: dict[str, Any] = {
            "id": art.get("id", ""),
            "name": art.get("name", ""),
            "artifact_type": art.get("artifact_type", "generic"),
            "mime_type": art.get("mime_type", "text/plain"),
            "source_agent_id": art.get("source_agent_id", ""),
            "source_round": art.get("source_round", 0),
            "content_preview": art.get("content", "")[:500],
        }
        artifact_previews.append(preview)

    result: dict[str, Any] = {
        "colony_id": colony.id,
        "display_name": colony.display_name or colony.id,
        "original_task": colony.task,
        "active_goal": colony.active_goal or colony.task,
        "status": colony.status,
        "quality_score": colony.quality_score,
        "skills_extracted": colony.skills_extracted,
        "cost": colony.cost,
        "rounds_completed": colony.round_number,
        "redirect_history": list(colony.redirect_history),
        "input_sources": list(getattr(colony, "input_sources", [])),
        "team": _build_team(colony),
        "round_summaries": round_summaries,
        "final_output": final_output,
        "artifacts": artifact_previews,
    }
    if failure_context is not None:
        result["failure_context"] = failure_context

    # Knowledge access trace (Wave 28)
    if getattr(colony, "knowledge_accesses", None):
        result["knowledge_trace"] = colony.knowledge_accesses

    return result


__all__ = ["build_transcript"]
