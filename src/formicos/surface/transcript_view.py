# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Canonical colony transcript schema for export and federation exchange (Wave 33 C9)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from formicos.core.types import FrozenConfig


class AgentTurnView(BaseModel):
    """Single agent turn within a round."""

    model_config = FrozenConfig

    agent_id: str
    caste: str
    output_summary: str
    tool_calls: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class RoundView(BaseModel):
    """Single round within a colony transcript."""

    model_config = FrozenConfig

    round_number: int
    agents: list[AgentTurnView] = Field(default_factory=list)
    convergence: float = 0.0
    cost: float = 0.0
    duration_ms: int = 0


class ColonyStats(BaseModel):
    """Aggregate statistics for a colony."""

    model_config = FrozenConfig

    total_rounds: int = 0
    total_cost: float = 0.0
    total_duration_ms: int = 0
    skills_extracted: int = 0


class ArtifactView(BaseModel):
    """Single artifact reference in a transcript."""

    model_config = FrozenConfig

    type: str = "generic"
    content_preview: str = ""


class ColonyTranscriptView(BaseModel):
    """Canonical transcript view for colony export and federation.

    Built from ProjectionStore colony and round data.
    """

    model_config = ConfigDict(frozen=True)

    colony_id: str
    thread_id: str
    workspace_id: str
    task: str
    strategy: str = "stigmergic"
    castes: list[str] = Field(default_factory=list)
    rounds: list[RoundView] = Field(default_factory=list)
    artifacts: list[ArtifactView] = Field(default_factory=list)
    knowledge_used: list[str] = Field(default_factory=list)
    knowledge_produced: list[str] = Field(default_factory=list)
    stats: ColonyStats = Field(default_factory=ColonyStats)


def build_colony_transcript_view(
    colony_proj: Any,
    projections: Any,
) -> ColonyTranscriptView:
    """Build canonical transcript from colony projection.

    Args:
        colony_proj: ColonyProjection instance from ProjectionStore.colonies
        projections: ProjectionStore instance for resolving references
    """
    rounds: list[RoundView] = []
    for rnd in getattr(colony_proj, "rounds", {}).values():
        agents: list[AgentTurnView] = []
        for agent in getattr(rnd, "agents", {}).values():
            agents.append(AgentTurnView(
                agent_id=getattr(agent, "agent_id", ""),
                caste=getattr(agent, "caste", ""),
                output_summary=getattr(agent, "output_summary", ""),
                tool_calls=list(getattr(agent, "tool_calls", [])),
                input_tokens=getattr(agent, "input_tokens", 0),
                output_tokens=getattr(agent, "output_tokens", 0),
            ))
        rounds.append(RoundView(
            round_number=getattr(rnd, "round_number", 0),
            agents=agents,
            convergence=getattr(rnd, "convergence", 0.0),
            cost=getattr(rnd, "cost", 0.0),
            duration_ms=getattr(rnd, "duration_ms", 0),
        ))

    artifacts: list[ArtifactView] = []
    for art in getattr(colony_proj, "artifacts", []):
        artifacts.append(ArtifactView(
            type=art.get("artifact_type", "generic") if isinstance(art, dict) else "generic",
            content_preview=(
                art.get("content", "")[:200] if isinstance(art, dict) else ""
            ),
        ))

    knowledge_used: list[str] = []
    for access in getattr(colony_proj, "knowledge_accesses", []):
        for item in access.get("items", []):
            kid = item.get("id", "")
            if kid and kid not in knowledge_used:
                knowledge_used.append(kid)

    knowledge_produced: list[str] = []
    for eid, entry in projections.memory_entries.items():
        if entry.get("source_colony_id") == getattr(colony_proj, "colony_id", ""):
            knowledge_produced.append(eid)

    total_cost = sum(
        getattr(r, "cost", 0.0)
        for r in getattr(colony_proj, "rounds", {}).values()
    )
    total_duration = sum(
        getattr(r, "duration_ms", 0)
        for r in getattr(colony_proj, "rounds", {}).values()
    )

    return ColonyTranscriptView(
        colony_id=getattr(colony_proj, "colony_id", ""),
        thread_id=getattr(colony_proj, "thread_id", ""),
        workspace_id=getattr(colony_proj, "workspace_id", ""),
        task=getattr(colony_proj, "task", ""),
        strategy=getattr(colony_proj, "strategy", "stigmergic"),
        castes=list(getattr(colony_proj, "castes", [])),
        rounds=rounds,
        artifacts=artifacts,
        knowledge_used=knowledge_used,
        knowledge_produced=knowledge_produced,
        stats=ColonyStats(
            total_rounds=len(rounds),
            total_cost=total_cost,
            total_duration_ms=total_duration,
            skills_extracted=getattr(colony_proj, "skills_extracted", 0),
        ),
    )


def transcript_to_a2a_artifact(view: ColonyTranscriptView) -> dict[str, Any]:
    """Convert to A2A DataPart artifact format."""
    return {
        "type": "data_part",
        "mime_type": "application/json",
        "data": {
            "kind": "colony_transcript",
            "colony_id": view.colony_id,
            "task": view.task,
            "stats": view.stats.model_dump(),
            "rounds": [r.model_dump() for r in view.rounds],
            "knowledge_used": view.knowledge_used,
            "knowledge_produced": view.knowledge_produced,
        },
    }


def transcript_to_mcp_resource(view: ColonyTranscriptView) -> dict[str, Any]:
    """Convert to MCP resource format."""
    return {
        "uri": f"formicos://colony/{view.colony_id}/transcript",
        "name": f"Colony {view.colony_id} transcript",
        "mimeType": "application/json",
        "contents": view.model_dump(),
    }


__all__ = [
    "AgentTurnView",
    "ArtifactView",
    "ColonyStats",
    "ColonyTranscriptView",
    "RoundView",
    "build_colony_transcript_view",
    "transcript_to_a2a_artifact",
    "transcript_to_mcp_resource",
]
