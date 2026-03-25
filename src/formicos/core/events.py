"""FormicOS event vocabulary — runtime version.

Mirrors docs/contracts/events.py. 69 event models,
discriminated union, serialize/deserialize helpers.
"""
# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from formicos.core.types import (
    AccessMode,
    ApprovalType,
    CasteSlot,
    CoordinationStrategyName,
    InputSource,
    KnowledgeAccessItem,
    MergeReason,
    RedirectTrigger,
    ServicePriority,
    WorkflowStep,
)

FrozenConfig = ConfigDict(frozen=True, extra="forbid")
PhaseName = Literal["goal", "intent", "route", "execute", "compress"]
ContextOperationName = Literal["set", "delete"]
QueenRoleName = Literal["operator", "queen"]


class WorkspaceConfigSnapshot(BaseModel):
    """Workspace-scoped model overrides and execution policy snapshot."""

    model_config = FrozenConfig

    queen_model: str | None = Field(
        default=None,
        description="Workspace override for the queen model; null means inherit.",
    )
    coder_model: str | None = Field(
        default=None,
        description="Workspace override for the coder model; null means inherit.",
    )
    reviewer_model: str | None = Field(
        default=None,
        description="Workspace override for the reviewer model; null means inherit.",
    )
    researcher_model: str | None = Field(
        default=None,
        description="Workspace override for the researcher model; null means inherit.",
    )
    archivist_model: str | None = Field(
        default=None,
        description="Workspace override for the archivist model; null means inherit.",
    )
    budget: float = Field(
        ...,
        ge=0.0,
        description="Workspace budget limit in USD for newly spawned colonies.",
    )
    strategy: CoordinationStrategyName = Field(
        ...,
        description="Default coordination strategy for colonies in the workspace.",
    )


class EventEnvelope(BaseModel):
    """Common envelope shared by all FormicOS events."""

    model_config = FrozenConfig

    seq: int = Field(
        ...,
        ge=0,
        description="Monotonic event sequence assigned by the event store.",
    )
    type: str = Field(
        ...,
        description="Closed discriminant matching the event class name.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the event was emitted.",
    )
    address: str = Field(
        ...,
        description="Serialized node address such as workspace/thread/colony.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Optional OpenTelemetry correlation identifier.",
    )


class WorkspaceCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["WorkspaceCreated"] = "WorkspaceCreated"
    name: str = Field(..., description="Human-readable workspace name.")
    config: WorkspaceConfigSnapshot = Field(
        ...,
        description="Initial workspace configuration snapshot.",
    )


class ThreadCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ThreadCreated"] = "ThreadCreated"
    workspace_id: str = Field(..., description="Parent workspace identifier.")
    name: str = Field(..., description="Human-readable thread name.")
    goal: str = Field(default="", description="Optional workflow goal (Wave 29).")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Optional expected artifact types (Wave 29).",
    )


class ThreadRenamed(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ThreadRenamed"] = "ThreadRenamed"
    workspace_id: str = Field(..., description="Parent workspace.")
    thread_id: str = Field(..., description="Stable thread identifier.")
    new_name: str = Field(..., description="New display name.")
    renamed_by: str = Field(default="operator", description="Actor.")


class ColonySpawned(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonySpawned"] = "ColonySpawned"
    thread_id: str = Field(..., description="Parent thread identifier.")
    task: str = Field(..., description="Operator or Queen task for the colony.")
    castes: list[CasteSlot] = Field(
        ...,
        description="Ordered caste slots with tier assignments.",
    )
    model_assignments: dict[str, str] = Field(
        ...,
        description="Resolved model address per caste or agent role.",
    )
    strategy: CoordinationStrategyName = Field(
        ...,
        description="Coordination strategy chosen for this colony.",
    )
    max_rounds: int = Field(
        ...,
        ge=1,
        description="Maximum rounds the colony may execute before forced stop.",
    )
    budget_limit: float = Field(
        ...,
        ge=0.0,
        description="USD budget limit allocated to the colony.",
    )
    template_id: str = Field(
        default="",
        description="Template ID used for spawning, empty if custom.",
    )
    input_sources: list[InputSource] = Field(
        default_factory=lambda: [],
        description="Resolved input sources for colony chaining (ADR-033).",
    )
    step_index: int = Field(
        default=-1,
        description="Workflow step this colony fulfils (-1 = none). Wave 30.",
    )
    target_files: list[str] = Field(
        default_factory=lambda: [],
        description="Files the colony should focus on (Wave 41 multi-file).",
    )
    fast_path: bool = Field(
        default=False,
        description="Skip coordination overhead for simple single-agent tasks (Wave 47).",
    )
    spawn_source: str = Field(
        default="",
        description="Who initiated: queen, operator, api, or empty. Wave 50.",
    )


class ColonyCompleted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyCompleted"] = "ColonyCompleted"
    colony_id: str = Field(..., description="Completed colony identifier.")
    summary: str = Field(..., description="Compressed final outcome summary.")
    skills_extracted: int = Field(
        ...,
        ge=0,
        description="Number of skill records extracted from the colony result.",
    )
    artifacts: list[dict[str, Any]] = Field(
        default_factory=lambda: [],
        description="Final typed artifacts produced by the colony (Wave 25 additive field).",
    )


class ColonyFailed(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyFailed"] = "ColonyFailed"
    colony_id: str = Field(..., description="Failed colony identifier.")
    reason: str = Field(..., description="Failure reason recorded by runtime.")


class ColonyKilled(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyKilled"] = "ColonyKilled"
    colony_id: str = Field(..., description="Killed colony identifier.")
    killed_by: str = Field(
        ...,
        description="Actor that killed the colony, typically operator or governance.",
    )


class RoundStarted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["RoundStarted"] = "RoundStarted"
    colony_id: str = Field(..., description="Colony executing the round.")
    round_number: int = Field(..., ge=1, description="1-based round number.")


class PhaseEntered(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["PhaseEntered"] = "PhaseEntered"
    colony_id: str = Field(..., description="Colony executing the phase.")
    round_number: int = Field(..., ge=1, description="1-based round number.")
    phase: PhaseName = Field(..., description="Current execution phase.")


class AgentTurnStarted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["AgentTurnStarted"] = "AgentTurnStarted"
    colony_id: str = Field(..., description="Owning colony identifier.")
    round_number: int = Field(..., ge=1, description="1-based round number.")
    agent_id: str = Field(..., description="Agent identifier within the colony.")
    caste: str = Field(..., description="Caste assigned to the agent.")
    model: str = Field(..., description="Resolved model address for the turn.")


class AgentTurnCompleted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["AgentTurnCompleted"] = "AgentTurnCompleted"
    agent_id: str = Field(..., description="Agent identifier within the colony.")
    output_summary: str = Field(..., description="Compressed turn output summary.")
    input_tokens: int = Field(..., ge=0, description="Input tokens consumed.")
    output_tokens: int = Field(..., ge=0, description="Output tokens consumed.")
    tool_calls: list[str] = Field(
        ...,
        description="Ordered tool names invoked during the turn.",
    )
    duration_ms: int = Field(
        ...,
        ge=0,
        description="Turn duration in milliseconds.",
    )


class RoundCompleted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["RoundCompleted"] = "RoundCompleted"
    colony_id: str = Field(..., description="Colony that completed the round.")
    round_number: int = Field(..., ge=1, description="1-based round number.")
    convergence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Computed convergence score for the round.",
    )
    cost: float = Field(..., ge=0.0, description="Round cost in USD.")
    duration_ms: int = Field(
        ...,
        ge=0,
        description="End-to-end round duration in milliseconds.",
    )
    # Wave 39 1B: task-type validator state (replay-safe)
    validator_task_type: str | None = Field(
        default=None,
        description="Classified task type (code/research/documentation/review/unknown).",
    )
    validator_verdict: str | None = Field(
        default=None,
        description="Validator verdict (pass/fail/inconclusive).",
    )
    validator_reason: str | None = Field(
        default=None,
        description="Machine-readable reason for the verdict.",
    )


class MergeCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["MergeCreated"] = "MergeCreated"
    edge_id: str = Field(..., description="Stable merge edge identifier.")
    from_colony: str = Field(..., description="Source colony identifier.")
    to_colony: str = Field(..., description="Destination colony identifier.")
    created_by: str = Field(
        ...,
        description="Actor that created the merge edge.",
    )


class MergePruned(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["MergePruned"] = "MergePruned"
    edge_id: str = Field(..., description="Stable merge edge identifier.")
    pruned_by: str = Field(..., description="Actor that pruned the edge.")


# FROZEN (Wave 51): Historical artifact with no projection handler.
# Kept in the closed union for replay compatibility with early event logs.
class ContextUpdated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ContextUpdated"] = "ContextUpdated"
    address: str = Field(
        ...,
        description="Node address whose context entry was changed.",
    )
    key: str = Field(..., description="Context key being updated.")
    value: str = Field(..., description="Serialized context value.")
    operation: ContextOperationName = Field(
        ...,
        description="Mutation kind: set or delete.",
    )


class WorkspaceConfigChanged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["WorkspaceConfigChanged"] = "WorkspaceConfigChanged"
    workspace_id: str = Field(..., description="Workspace identifier.")
    field: str = Field(..., description="Field name that changed.")
    old_value: str | None = Field(
        default=None,
        description="Previous serialized value, if any.",
    )
    new_value: str | None = Field(
        default=None,
        description="New serialized value, if any.",
    )


class ModelRegistered(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ModelRegistered"] = "ModelRegistered"
    provider_prefix: str = Field(
        ...,
        description="Provider prefix such as anthropic or ollama.",
    )
    model_name: str = Field(..., description="Provider-local model name.")
    context_window: int = Field(
        ...,
        ge=1,
        description="Advertised maximum context window in tokens.",
    )
    supports_tools: bool = Field(
        ...,
        description="Whether the model supports tool or function calling.",
    )


class ModelAssignmentChanged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ModelAssignmentChanged"] = "ModelAssignmentChanged"
    scope: str = Field(
        ...,
        description="system or workspace identifier receiving the override.",
    )
    caste: str = Field(..., description="Caste whose assignment changed.")
    old_model: str | None = Field(
        default=None,
        description="Previous resolved or overridden model.",
    )
    new_model: str | None = Field(
        default=None,
        description="New resolved or overridden model.",
    )


class ApprovalRequested(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ApprovalRequested"] = "ApprovalRequested"
    request_id: str = Field(..., description="Stable approval request identifier.")
    approval_type: ApprovalType = Field(..., description="Operator-facing approval category.")
    detail: str = Field(..., description="Human-readable approval detail.")
    colony_id: str = Field(..., description="Related colony identifier.")


class ApprovalGranted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ApprovalGranted"] = "ApprovalGranted"
    request_id: str = Field(..., description="Approved request identifier.")


class ApprovalDenied(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ApprovalDenied"] = "ApprovalDenied"
    request_id: str = Field(..., description="Denied request identifier.")


class QueenMessage(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["QueenMessage"] = "QueenMessage"
    thread_id: str = Field(..., description="Thread receiving the message.")
    role: QueenRoleName = Field(..., description="Message author role.")
    content: str = Field(..., description="Message text content.")
    # Wave 49: additive structured metadata for conversational cards.
    # All optional with safe defaults — older logs replay cleanly.
    intent: str | None = Field(
        default=None,
        description="Message intent: 'notify' | 'ask' | null.",
    )
    render: str | None = Field(
        default=None,
        description="Rendering hint: 'text' | 'preview_card' | 'result_card' | null.",
    )
    meta: dict[str, Any] | None = Field(
        default=None,
        description="Structured payload for preview/result cards.",
    )


class TokensConsumed(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["TokensConsumed"] = "TokensConsumed"
    agent_id: str = Field(..., description="Agent that consumed the tokens.")
    model: str = Field(..., description="Model used for the token spend.")
    input_tokens: int = Field(..., ge=0, description="Input token count.")
    output_tokens: int = Field(..., ge=0, description="Output token count.")
    cost: float = Field(..., ge=0.0, description="Estimated or exact USD cost.")
    reasoning_tokens: int = Field(
        default=0, ge=0, description="Reasoning/thinking tokens (subset of output).",
    )
    cache_read_tokens: int = Field(
        default=0, ge=0, description="Input tokens served from cache.",
    )


class ColonyTemplateCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyTemplateCreated"] = "ColonyTemplateCreated"
    template_id: str = Field(..., description="Stable template identifier.")
    name: str = Field(..., description="Human-readable template name.")
    description: str = Field(..., description="Template description.")
    castes: list[CasteSlot] = Field(..., description="Caste slots in the template.")
    strategy: CoordinationStrategyName = Field(..., description="Coordination strategy.")
    source_colony_id: str | None = Field(default=None, description="Colony this was saved from.")
    # Wave 50: additive fields for learned templates
    learned: bool = Field(
        default=False,
        description="True for replay-derived learned templates, false for operator-authored.",
    )
    task_category: str = Field(
        default="",
        description="Category from classify_task() used for v1 matching.",
    )
    max_rounds: int = Field(
        default=25,
        description="Default rounds when reusing this template.",
    )
    budget_limit: float = Field(
        default=1.0,
        description="Default budget when reusing this template.",
    )
    fast_path: bool = Field(
        default=False,
        description="Whether the learned template prefers fast_path.",
    )
    target_files_pattern: str = Field(
        default="",
        description="Optional compact target-files pattern for preview defaults.",
    )


class ColonyTemplateUsed(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyTemplateUsed"] = "ColonyTemplateUsed"
    template_id: str = Field(..., description="Template that was used.")
    colony_id: str = Field(..., description="Colony spawned from the template.")


class ColonyNamed(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyNamed"] = "ColonyNamed"
    colony_id: str = Field(..., description="Colony receiving a display name.")
    display_name: str = Field(..., description="Human-readable name assigned by Queen or operator.")
    named_by: str = Field(..., description="Actor: 'queen' or 'operator'.")


# FROZEN (Wave 51): Legacy pre-Wave-26 skill event. Kept for replay compatibility.
# Superseded by MemoryConfidenceUpdated. Do not emit in new code.
class SkillConfidenceUpdated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["SkillConfidenceUpdated"] = "SkillConfidenceUpdated"
    colony_id: str = Field(..., description="Colony whose completion triggered updates.")
    skills_updated: int = Field(..., ge=0, description="Count of skills with changed confidence.")
    colony_succeeded: bool = Field(..., description="Whether the colony succeeded or failed.")


# FROZEN (Wave 51): Legacy pre-Wave-26 skill event. Kept for replay compatibility.
# Superseded by MemoryEntryMerged. Do not emit in new code.
class SkillMerged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["SkillMerged"] = "SkillMerged"
    surviving_skill_id: str = Field(..., description="Skill that absorbed the other.")
    merged_skill_id: str = Field(..., description="Skill that was absorbed.")
    merge_reason: MergeReason = Field(..., description="Why merged: 'llm_dedup'.")


# ---------------------------------------------------------------------------
# Wave 14 events (ADR-020)
# ---------------------------------------------------------------------------


class ColonyChatMessage(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyChatMessage"] = "ColonyChatMessage"
    colony_id: str = Field(..., description="Colony this message belongs to.")
    workspace_id: str = Field(..., description="Workspace scope.")
    sender: str = Field(
        ...,
        description="ChatSender value: operator, queen, system, agent, service.",
    )
    content: str = Field(..., description="Message text (markdown supported).")
    agent_id: str | None = Field(
        default=None, description="Set when sender is agent.",
    )
    caste: str | None = Field(
        default=None, description="Set when sender is agent.",
    )
    event_kind: str | None = Field(
        default=None,
        description="Set when sender is system: phase, governance, spawn, complete, approval.",
    )
    directive_type: str | None = Field(
        default=None,
        description="Set when sender is queen: SPAWN, REDIRECT, KILL, APOPTOSIS.",
    )
    source_colony: str | None = Field(
        default=None,
        description="Set when sender is service: the responding colony ID.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Arbitrary extra data.",
    )


class CodeExecuted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["CodeExecuted"] = "CodeExecuted"
    colony_id: str = Field(..., description="Colony that ran the code.")
    agent_id: str = Field(..., description="Agent that called code_execute.")
    code_preview: str = Field(
        ..., description="First 200 chars of the submitted code.",
    )
    trust_tier: str = Field(
        ..., description="Sandbox tier: LIGHT, STANDARD, or MAXIMUM.",
    )
    exit_code: int = Field(..., description="Process exit code.")
    stdout_preview: str = Field(
        default="", description="First 500 chars of stdout.",
    )
    stderr_preview: str = Field(
        default="", description="First 500 chars of stderr.",
    )
    duration_ms: float = Field(..., description="Wall-clock execution time.")
    peak_memory_mb: float = Field(
        default=0.0, description="Peak memory usage in MB.",
    )
    blocked: bool = Field(
        default=False, description="True if AST pre-parser rejected the code.",
    )


class ServiceQuerySent(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ServiceQuerySent"] = "ServiceQuerySent"
    request_id: str = Field(..., description="Unique query tracking ID.")
    service_type: str = Field(
        ..., description="ServiceColonyType value: research, monitoring.",
    )
    target_colony_id: str = Field(
        ..., description="Service colony receiving the query.",
    )
    sender_colony_id: str | None = Field(
        default=None, description="Colony that sent the query (null if operator/Queen).",
    )
    query_preview: str = Field(
        ..., description="First 200 chars of the query text.",
    )
    priority: ServicePriority = Field(
        default=ServicePriority.normal, description="normal or high.",
    )


class ServiceQueryResolved(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ServiceQueryResolved"] = "ServiceQueryResolved"
    request_id: str = Field(
        ..., description="Matches the ServiceQuerySent.request_id.",
    )
    service_type: str = Field(..., description="ServiceColonyType value.")
    source_colony_id: str = Field(
        ..., description="Colony that produced the response.",
    )
    response_preview: str = Field(
        ..., description="First 200 chars of response text.",
    )
    latency_ms: float = Field(..., description="End-to-end query latency.")
    artifact_count: int = Field(
        default=0, description="Number of artifacts (skill IDs, URLs) in response.",
    )


class ColonyServiceActivated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyServiceActivated"] = "ColonyServiceActivated"
    colony_id: str = Field(..., description="Colony transitioned to service mode.")
    workspace_id: str = Field(..., description="Workspace scope.")
    service_type: str = Field(..., description="ServiceColonyType value.")
    agent_count: int = Field(..., description="Number of agents now idle.")
    skill_count: int = Field(
        default=0, description="Skills retained by the service colony.",
    )
    kg_entity_count: int = Field(
        default=0, description="KG entities retained.",
    )


class KnowledgeEntityCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["KnowledgeEntityCreated"] = "KnowledgeEntityCreated"
    entity_id: str = Field(..., description="New entity ID.")
    name: str = Field(..., description="Entity name.")
    entity_type: str = Field(
        ..., description="MODULE, CONCEPT, SKILL, TOOL, PERSON, or ORGANIZATION.",
    )
    workspace_id: str = Field(..., description="Workspace scope.")
    source_colony_id: str | None = Field(
        default=None, description="Colony whose Archivist created this entity.",
    )


class KnowledgeEdgeCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["KnowledgeEdgeCreated"] = "KnowledgeEdgeCreated"
    edge_id: str = Field(..., description="New edge ID.")
    from_entity_id: str = Field(..., description="Source entity.")
    to_entity_id: str = Field(..., description="Target entity.")
    predicate: str = Field(
        ..., description="DEPENDS_ON, ENABLES, IMPLEMENTS, VALIDATES, MIGRATED_TO, or FAILED_ON.",
    )
    confidence: float = Field(..., description="Edge confidence score.")
    workspace_id: str = Field(..., description="Workspace scope.")
    source_colony_id: str | None = Field(
        default=None, description="Colony whose Archivist created this edge.",
    )
    source_round: int | None = Field(
        default=None, description="Round number when edge was extracted.",
    )


class KnowledgeEntityMerged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["KnowledgeEntityMerged"] = "KnowledgeEntityMerged"
    survivor_id: str = Field(..., description="Entity that absorbed the duplicate.")
    merged_id: str = Field(..., description="Entity that was absorbed.")
    similarity_score: float = Field(..., description="Cosine similarity that triggered merge.")
    merge_method: str = Field(
        ..., description="auto (cosine >= 0.95) or llm_confirmed.",
    )
    workspace_id: str = Field(..., description="Workspace scope.")


# ---------------------------------------------------------------------------
# Wave 19 events (ADR-032)
# ---------------------------------------------------------------------------


class ColonyRedirected(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyRedirected"] = "ColonyRedirected"
    colony_id: str = Field(..., description="Colony being redirected.")
    redirect_index: int = Field(
        ..., ge=0, description="0-based redirect counter.",
    )
    original_goal: str = Field(
        ..., description="Immutable original task from spawn.",
    )
    new_goal: str = Field(
        ..., description="New goal the colony works toward.",
    )
    reason: str = Field(..., description="Queen's rationale for the redirect.")
    trigger: RedirectTrigger = Field(
        ...,
        description="Trigger source: queen_inspection, governance_alert, or operator_request.",
    )
    round_at_redirect: int = Field(
        ..., ge=0, description="Round number when redirect occurred.",
    )


# ---------------------------------------------------------------------------
# Wave 26 events — Institutional Memory
# ---------------------------------------------------------------------------


class MemoryEntryCreated(EventEnvelope):
    """A new institutional memory entry was extracted and persisted (Wave 26)."""

    model_config = FrozenConfig

    type: Literal["MemoryEntryCreated"] = "MemoryEntryCreated"
    entry: dict[str, Any] = Field(
        ..., description="Serialized MemoryEntry dict. Source of truth for replay.",
    )
    workspace_id: str = Field(..., description="Workspace scope.")


class MemoryEntryStatusChanged(EventEnvelope):
    """An entry's trust status changed (Wave 26)."""

    model_config = FrozenConfig

    type: Literal["MemoryEntryStatusChanged"] = "MemoryEntryStatusChanged"
    entry_id: str = Field(..., description="Memory entry being updated.")
    old_status: str = Field(..., description="Previous status.")
    new_status: str = Field(..., description="New status.")
    reason: str = Field(default="", description="Why the status changed.")
    workspace_id: str = Field(..., description="Workspace scope.")


class MemoryExtractionCompleted(EventEnvelope):
    """Memory extraction finished for a colony (even if zero entries produced).

    Durable receipt that extraction ran to completion. Without this,
    restart recovery cannot distinguish 'extraction crashed' from
    'extraction ran but found nothing to extract.'
    """

    model_config = FrozenConfig

    type: Literal["MemoryExtractionCompleted"] = "MemoryExtractionCompleted"
    colony_id: str = Field(..., description="Colony whose extraction finished.")
    entries_created: int = Field(
        ..., ge=0, description="Number of MemoryEntryCreated events emitted.",
    )
    workspace_id: str = Field(..., description="Workspace scope.")


# ---------------------------------------------------------------------------
# Wave 28 events — Knowledge Access Traces
# ---------------------------------------------------------------------------


class KnowledgeAccessRecorded(EventEnvelope):
    """Knowledge items accessed during a colony round (Wave 28).

    Emitted by colony_manager after each run_round() returns.
    Carries the round's aggregated knowledge_items_used from RoundResult.
    """

    model_config = FrozenConfig

    type: Literal["KnowledgeAccessRecorded"] = "KnowledgeAccessRecorded"
    colony_id: str = Field(..., description="Colony that accessed knowledge.")
    round_number: int = Field(..., ge=1, description="Round number.")
    workspace_id: str = Field(..., description="Workspace scope.")
    access_mode: AccessMode = Field(
        default=AccessMode.context_injection,
        description=(
            "context_injection | tool_search | tool_detail"
            " | tool_transcript. Wave 28+ tool tracing."
        ),
    )
    items: list[KnowledgeAccessItem] = Field(
        default_factory=lambda: [],
        description="Knowledge items that were injected into agent context.",
    )


# ---------------------------------------------------------------------------
# Wave 29 events — Workflow Threads
# ---------------------------------------------------------------------------


class ThreadGoalSet(EventEnvelope):
    """A thread's workflow goal was set or updated (Wave 29)."""
    model_config = FrozenConfig

    type: Literal["ThreadGoalSet"] = "ThreadGoalSet"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    goal: str = Field(..., description="Workflow objective.")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Expected artifact types: code, test, document, etc.",
    )


class ThreadStatusChanged(EventEnvelope):
    """A thread's workflow status changed (Wave 29)."""
    model_config = FrozenConfig

    type: Literal["ThreadStatusChanged"] = "ThreadStatusChanged"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    old_status: str = Field(...)
    new_status: str = Field(..., description="active | completed | archived.")
    reason: str = Field(default="", description="Why the status changed.")


class MemoryEntryScopeChanged(EventEnvelope):
    """A memory entry's thread/workspace scope changed (Wave 29, extended Wave 50)."""
    model_config = FrozenConfig

    type: Literal["MemoryEntryScopeChanged"] = "MemoryEntryScopeChanged"
    entry_id: str = Field(...)
    old_thread_id: str = Field(default="")
    new_thread_id: str = Field(default="", description="Empty = workspace-wide.")
    workspace_id: str = Field(...)
    # Wave 50: workspace-to-global promotion. Empty = global scope.
    new_workspace_id: str = Field(
        default="",
        description="Target workspace. Empty string = global scope. Wave 50.",
    )


class DeterministicServiceRegistered(EventEnvelope):
    """A deterministic service handler was registered (Wave 29).

    Emitted at startup for operator visibility. Dispatch uses
    the in-memory registry on ServiceRouter, not this event.
    """
    model_config = FrozenConfig

    type: Literal["DeterministicServiceRegistered"] = "DeterministicServiceRegistered"
    service_name: str = Field(...)
    description: str = Field(default="")
    workspace_id: str = Field(default="system")


class MemoryConfidenceUpdated(EventEnvelope):
    """Knowledge entry confidence updated from colony outcome or archival decay (Wave 30)."""
    model_config = FrozenConfig

    type: Literal["MemoryConfidenceUpdated"] = "MemoryConfidenceUpdated"
    entry_id: str = Field(..., description="Memory entry being updated.")
    colony_id: str = Field(
        default="",
        description="Colony whose outcome drove the update. Empty for archival decay.",
    )
    colony_succeeded: bool = Field(
        default=True, description="True for archival decay (neutral).",
    )
    old_alpha: float = Field(...)
    old_beta: float = Field(...)
    new_alpha: float = Field(...)
    new_beta: float = Field(...)
    new_confidence: float = Field(
        ..., description="Posterior mean: alpha / (alpha + beta).",
    )
    workspace_id: str = Field(...)
    thread_id: str = Field(default="")
    reason: str = Field(
        default="colony_outcome",
        description="colony_outcome | archival_decay",
    )


class WorkflowStepDefined(EventEnvelope):
    """A workflow step was added to a thread (Wave 30, Track B)."""
    model_config = FrozenConfig

    type: Literal["WorkflowStepDefined"] = "WorkflowStepDefined"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step: WorkflowStep = Field(...)


class WorkflowStepCompleted(EventEnvelope):
    """A workflow step's colony completed (Wave 30, Track B)."""
    model_config = FrozenConfig

    type: Literal["WorkflowStepCompleted"] = "WorkflowStepCompleted"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step_index: int = Field(...)
    colony_id: str = Field(...)
    success: bool = Field(...)
    artifacts_produced: list[str] = Field(
        default_factory=list, description="Artifact type list.",
    )


class WorkflowStepUpdated(EventEnvelope):
    """Operator directly edited a workflow step (Wave 63, ADR-049)."""

    model_config = FrozenConfig

    type: Literal["WorkflowStepUpdated"] = "WorkflowStepUpdated"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step_index: int = Field(..., description="Index of the step being updated.")
    new_description: str = Field(
        default="", description="Updated description. Empty = keep existing.",
    )
    new_status: str = Field(
        default="",
        description="Updated status: pending|skipped|in_progress. Empty = keep existing.",
    )
    new_position: int = Field(
        default=-1, description="New position index. -1 = no reorder.",
    )
    notes: str = Field(default="", description="Operator notes for this step.")


# ---------------------------------------------------------------------------
# Wave 33 events — CRDT Operations + Merge Provenance (ADR-042)
# ---------------------------------------------------------------------------


class CRDTCounterIncremented(EventEnvelope):
    """G-Counter increment for observation tracking."""

    model_config = FrozenConfig

    type: Literal["CRDTCounterIncremented"] = "CRDTCounterIncremented"
    entry_id: str = Field(..., description="Knowledge entry being observed.")
    instance_id: str = Field(
        ..., description="FormicOS instance that recorded the observation.",
    )
    field: Literal["successes", "failures"] = Field(
        ..., description="Which counter: positive or negative observations.",
    )
    delta: int = Field(
        ..., ge=1, description="Increment amount (always positive, G-Counter invariant).",
    )
    workspace_id: str = Field(...)


class CRDTTimestampUpdated(EventEnvelope):
    """LWW Register update for per-instance last-observation time."""

    model_config = FrozenConfig

    type: Literal["CRDTTimestampUpdated"] = "CRDTTimestampUpdated"
    entry_id: str = Field(...)
    instance_id: str = Field(...)
    obs_timestamp: float = Field(
        ..., description="Epoch seconds of the observation.",
    )
    workspace_id: str = Field(...)


class CRDTSetElementAdded(EventEnvelope):
    """G-Set element addition for domains and archival markers."""

    model_config = FrozenConfig

    type: Literal["CRDTSetElementAdded"] = "CRDTSetElementAdded"
    entry_id: str = Field(...)
    field: Literal["domains", "archived_by"] = Field(
        ..., description="Which G-Set: domain tags or archival markers.",
    )
    element: str = Field(
        ..., description="Element being added (domain name or instance_id).",
    )
    workspace_id: str = Field(...)


class CRDTRegisterAssigned(EventEnvelope):
    """LWW Register assignment for content, entry_type, and decay_class."""

    model_config = FrozenConfig

    type: Literal["CRDTRegisterAssigned"] = "CRDTRegisterAssigned"
    entry_id: str = Field(...)
    field: Literal["content", "entry_type", "decay_class"] = Field(
        ..., description="Which register is being updated.",
    )
    value: str = Field(..., description="New register value.")
    lww_timestamp: float = Field(
        ..., description="LWW timestamp. Higher timestamp wins on merge.",
    )
    instance_id: str = Field(
        ..., description="Instance that assigned the value.",
    )
    workspace_id: str = Field(...)


class MemoryEntryMerged(EventEnvelope):
    """Two knowledge entries merged, with full provenance trail (ADR-042 D2).

    Dual-purpose: emitted by the dedup maintenance handler (merge_source="dedup")
    and by the federation conflict resolver (merge_source="federation").
    """

    model_config = FrozenConfig

    type: Literal["MemoryEntryMerged"] = "MemoryEntryMerged"
    target_id: str = Field(..., description="Surviving entry that absorbs the source.")
    source_id: str = Field(
        ..., description="Entry being absorbed. Will be marked rejected.",
    )
    merged_content: str = Field(
        ..., description="Content that survived selection.",
    )
    merged_domains: list[str] = Field(
        ..., description="Union of both entries' domain tags.",
    )
    merged_from: list[str] = Field(
        ..., description="Accumulated provenance: all entry IDs merged into the target.",
    )
    content_strategy: Literal["keep_longer", "keep_target", "llm_selected"] = Field(
        ..., description="How merged_content was selected.",
    )
    similarity: float = Field(..., ge=0.0, le=1.0)
    merge_source: Literal["dedup", "federation", "extraction"] = Field(
        ..., description="Which code path emitted this event.",
    )
    workspace_id: str = Field(...)


# ---------------------------------------------------------------------------
# Wave 35 — Multi-colony parallel planning (ADR-045 D1)
# ---------------------------------------------------------------------------


class ParallelPlanCreated(EventEnvelope):
    """Queen generated a validated DelegationPlan for parallel colony dispatch."""

    model_config = FrozenConfig

    type: Literal["ParallelPlanCreated"] = "ParallelPlanCreated"
    thread_id: str = Field(...)
    workspace_id: str = Field(...)
    plan: dict[str, Any] = Field(
        ..., description="Serialized DelegationPlan.",
    )
    parallel_groups: list[list[str]] = Field(
        ..., description="Task IDs per execution group.",
    )
    reasoning: str = Field(...)
    knowledge_gaps: list[str] = Field(default_factory=list)
    estimated_cost: float = Field(default=0.0)


class KnowledgeDistilled(EventEnvelope):
    """Archivist colony synthesized a knowledge cluster into a higher-order entry (ADR-045 D2)."""

    model_config = FrozenConfig

    type: Literal["KnowledgeDistilled"] = "KnowledgeDistilled"
    distilled_entry_id: str = Field(
        ..., description="ID of the newly created synthesis entry.",
    )
    source_entry_ids: list[str] = Field(
        ..., description="IDs of the source entries that were distilled.",
    )
    workspace_id: str = Field(...)
    cluster_avg_weight: float = Field(
        ..., description="Average co-occurrence weight of the source cluster.",
    )
    distillation_strategy: str = Field(
        default="archivist_synthesis",
        description="Strategy used for distillation.",
    )


# ---------------------------------------------------------------------------
# Wave 39 — Operator co-authorship (ADR-049)
# ---------------------------------------------------------------------------

OperatorActionName = Literal[
    "pin", "unpin", "mute", "unmute", "invalidate", "reinstate",
]


class KnowledgeEntryOperatorAction(EventEnvelope):
    """Operator editorial overlay on a knowledge entry (ADR-049).

    Local-first: does not mutate shared Beta confidence.
    Does not federate by default. Reversible via inverse actions.
    """

    model_config = FrozenConfig

    type: Literal["KnowledgeEntryOperatorAction"] = "KnowledgeEntryOperatorAction"
    entry_id: str = Field(..., description="Knowledge entry being acted on.")
    workspace_id: str = Field(...)
    action: OperatorActionName = Field(
        ..., description="Editorial overlay action.",
    )
    actor: str = Field(
        ..., description="Operator identifier who performed the action.",
    )
    reason: str = Field(
        default="",
        description="Optional reason for the action.",
    )


class KnowledgeEntryAnnotated(EventEnvelope):
    """Operator annotation on a knowledge entry (ADR-049).

    Additive operator truth. Optionally federated by workspace policy.
    """

    model_config = FrozenConfig

    type: Literal["KnowledgeEntryAnnotated"] = "KnowledgeEntryAnnotated"
    entry_id: str = Field(..., description="Knowledge entry being annotated.")
    workspace_id: str = Field(...)
    annotation_text: str = Field(
        ..., description="Operator annotation content.",
    )
    tag: str = Field(
        default="",
        description="Optional classification tag.",
    )
    actor: str = Field(
        ..., description="Operator identifier who wrote the annotation.",
    )


class ConfigSuggestionOverridden(EventEnvelope):
    """Operator edited a recommendation or plan before execution (ADR-049).

    Records what was suggested, what was chosen, and why.
    Local by default.
    """

    model_config = FrozenConfig

    type: Literal["ConfigSuggestionOverridden"] = "ConfigSuggestionOverridden"
    workspace_id: str = Field(...)
    suggestion_category: str = Field(
        ..., description="Category of the suggestion (strategy, caste, round_limit, model_tier).",
    )
    original_config: dict[str, Any] = Field(
        ..., description="The system's original recommendation.",
    )
    overridden_config: dict[str, Any] = Field(
        ..., description="The operator's chosen configuration.",
    )
    reason: str = Field(
        default="",
        description="Operator's reason for the override.",
    )
    actor: str = Field(
        ..., description="Operator identifier.",
    )


# ---------------------------------------------------------------------------
# Wave 44 — Forager events (4 new types)
# ---------------------------------------------------------------------------

ForageModeName = Literal["reactive", "proactive", "operator"]
DomainOverrideAction = Literal["trust", "distrust", "reset"]


class ForageRequested(EventEnvelope):
    """The system decided to forage for external knowledge (Wave 44).

    Replay-critical: records when and why a forage cycle was initiated.
    """

    model_config = FrozenConfig

    type: Literal["ForageRequested"] = "ForageRequested"
    workspace_id: str = Field(..., description="Workspace scope.")
    thread_id: str = Field(default="", description="Thread context, if any.")
    colony_id: str = Field(default="", description="Colony that triggered foraging, if reactive.")
    mode: ForageModeName = Field(
        ...,
        description="Trigger mode: reactive, proactive, or operator.",
    )
    reason: str = Field(..., description="Human-readable reason for the forage request.")
    gap_domain: str = Field(default="", description="Knowledge domain with the detected gap.")
    gap_query: str = Field(default="", description="Original query that exposed the gap.")
    max_results: int = Field(
        default=5, ge=1, le=20, description="Max results to fetch.",
    )


class ForageCycleCompleted(EventEnvelope):
    """A forage cycle finished — summary of what it accomplished (Wave 44).

    Replay-critical: provides the durable record of cycle outcomes.
    Individual search/fetch/rejection details stay log-only in v1.
    """

    model_config = FrozenConfig

    type: Literal["ForageCycleCompleted"] = "ForageCycleCompleted"
    workspace_id: str = Field(..., description="Workspace scope.")
    forage_request_seq: int = Field(
        ..., description="Seq of the ForageRequested event that started this cycle.",
    )
    queries_issued: int = Field(default=0, ge=0, description="Number of search queries executed.")
    pages_fetched: int = Field(default=0, ge=0, description="Number of pages successfully fetched.")
    pages_rejected: int = Field(
        default=0, ge=0, description="Pages rejected by quality/dedup.",
    )
    entries_admitted: int = Field(
        default=0, ge=0, description="Entries admitted via MemoryEntryCreated.",
    )
    entries_deduplicated: int = Field(
        default=0, ge=0, description="Entries rejected as duplicates.",
    )
    duration_ms: int = Field(default=0, ge=0, description="Wall-clock duration of the cycle.")
    error: str = Field(default="", description="Error message if the cycle failed.")


class DomainStrategyUpdated(EventEnvelope):
    """The forager learned a fetch-level preference for a domain (Wave 44).

    Replay-critical: domain strategy is durable state that affects future
    fetch behavior. Without this event, strategy would be lost on restart.
    """

    model_config = FrozenConfig

    type: Literal["DomainStrategyUpdated"] = "DomainStrategyUpdated"
    workspace_id: str = Field(..., description="Workspace scope.")
    domain: str = Field(..., description="Domain (e.g. 'docs.python.org').")
    preferred_level: int = Field(
        ..., ge=1, le=3,
        description="Preferred fetch level: 1=httpx+trafilatura, 2=fallback extractors, 3=browser.",
    )
    success_count: int = Field(default=0, ge=0, description="Cumulative successful fetches.")
    failure_count: int = Field(default=0, ge=0, description="Cumulative failed fetches.")
    reason: str = Field(
        default="", description="Why the strategy was updated.",
    )


class ForagerDomainOverride(EventEnvelope):
    """Operator domain-level trust override for forager behavior (Wave 44).

    Replay-critical: operator co-authorship action that must survive replay.
    Extends the existing overlay model (pin/mute/invalidate) to domain scope.
    """

    model_config = FrozenConfig

    type: Literal["ForagerDomainOverride"] = "ForagerDomainOverride"
    workspace_id: str = Field(..., description="Workspace scope.")
    domain: str = Field(..., description="Domain being overridden (e.g. 'stackoverflow.com').")
    action: DomainOverrideAction = Field(
        ..., description="trust=allow fetching, distrust=block fetching, reset=remove override.",
    )
    actor: str = Field(..., description="Operator identifier.")
    reason: str = Field(default="", description="Optional reason for the override.")


# ---------------------------------------------------------------------------
# Wave 51 — Replay safety (2 new types: escalation + Queen notes)
# ---------------------------------------------------------------------------


class ColonyEscalated(EventEnvelope):
    """Colony routing tier was escalated by the Queen (Wave 51).

    Makes escalation replay-safe. Previously, routing_override was set
    directly on the in-memory projection and lost on restart.
    """

    model_config = FrozenConfig

    type: Literal["ColonyEscalated"] = "ColonyEscalated"
    colony_id: str = Field(..., description="Colony being escalated.")
    tier: str = Field(..., description="Target tier: standard, heavy, or max.")
    reason: str = Field(..., description="Queen's rationale for escalation.")
    set_at_round: int = Field(
        ..., ge=0, description="Round number when escalation was applied.",
    )


class QueenNoteSaved(EventEnvelope):
    """Queen saved a private thread-scoped note (Wave 51).

    Private working context — NOT visible in operator chat.
    Replaces the previous YAML-only persistence path.
    Projection handler rebuilds queen_notes on replay.
    """

    model_config = FrozenConfig

    type: Literal["QueenNoteSaved"] = "QueenNoteSaved"
    workspace_id: str = Field(..., description="Workspace scope.")
    thread_id: str = Field(..., description="Thread scope.")
    content: str = Field(..., description="Note content (max 2000 chars).")


class MemoryEntryRefined(EventEnvelope):
    """In-place content improvement of a knowledge entry (Wave 59, ADR-048).

    Distinct from MemoryEntryMerged (one entry refined, not two merged) and
    from MemoryEntryStatusChanged (content changes, not just status).
    old_content preserved for audit trail.
    """

    model_config = FrozenConfig

    type: Literal["MemoryEntryRefined"] = "MemoryEntryRefined"
    entry_id: str = Field(..., description="Entry being refined.")
    workspace_id: str = Field(default="")
    old_content: str = Field(..., description="Content before refinement (audit trail).")
    new_content: str = Field(..., description="Improved content.")
    new_title: str = Field(
        default="",
        description="Updated title. Empty string = keep existing.",
    )
    refinement_source: Literal["extraction", "maintenance", "operator"] = Field(
        ..., description="What triggered the refinement.",
    )
    source_colony_id: str = Field(
        default="",
        description="Colony whose output informed the refinement. "
        "Empty for maintenance-triggered refinements.",
    )


class AddonLoaded(EventEnvelope):
    """An addon manifest was loaded and its components registered."""

    type: Literal["AddonLoaded"] = "AddonLoaded"
    addon_name: str = Field(..., description="Addon identifier from manifest.")
    version: str = Field(default="", description="Addon version string.")
    tools: list[str] = Field(default_factory=list, description="Registered tool names.")
    handlers: list[str] = Field(default_factory=list, description="Registered event handler names.")
    panels: list[str] = Field(default_factory=list, description="Registered frontend panel IDs.")


class AddonUnloaded(EventEnvelope):
    """An addon was deregistered."""

    type: Literal["AddonUnloaded"] = "AddonUnloaded"
    addon_name: str = Field(..., description="Addon being unloaded.")
    reason: str = Field(default="", description="shutdown | removed | error")


class ServiceTriggerFired(EventEnvelope):
    """A scheduled trigger activated a service colony."""

    type: Literal["ServiceTriggerFired"] = "ServiceTriggerFired"
    addon_name: str = Field(..., description="Addon that owns the trigger.")
    trigger_type: str = Field(default="", description="cron | event | webhook | manual")
    workspace_id: str = Field(default="")
    details: str = Field(default="", description="Human-readable trigger context.")


FormicOSEvent: TypeAlias = Annotated[  # noqa: UP040
    Union[  # noqa: UP007
        WorkspaceCreated,
        ThreadCreated,
        ThreadRenamed,
        ColonySpawned,
        ColonyCompleted,
        ColonyFailed,
        ColonyKilled,
        RoundStarted,
        PhaseEntered,
        AgentTurnStarted,
        AgentTurnCompleted,
        RoundCompleted,
        MergeCreated,
        MergePruned,
        ContextUpdated,
        WorkspaceConfigChanged,
        ModelRegistered,
        ModelAssignmentChanged,
        ApprovalRequested,
        ApprovalGranted,
        ApprovalDenied,
        QueenMessage,
        TokensConsumed,
        ColonyTemplateCreated,
        ColonyTemplateUsed,
        ColonyNamed,
        SkillConfidenceUpdated,
        SkillMerged,
        ColonyChatMessage,
        CodeExecuted,
        ServiceQuerySent,
        ServiceQueryResolved,
        ColonyServiceActivated,
        KnowledgeEntityCreated,
        KnowledgeEdgeCreated,
        KnowledgeEntityMerged,
        ColonyRedirected,
        MemoryEntryCreated,          # Wave 26
        MemoryEntryStatusChanged,    # Wave 26
        MemoryExtractionCompleted,   # Wave 26
        KnowledgeAccessRecorded,     # Wave 28
        ThreadGoalSet,               # Wave 29
        ThreadStatusChanged,         # Wave 29
        MemoryEntryScopeChanged,     # Wave 29
        DeterministicServiceRegistered,  # Wave 29
        MemoryConfidenceUpdated,         # Wave 30
        WorkflowStepDefined,             # Wave 30 (Track B)
        WorkflowStepCompleted,           # Wave 30 (Track B)
        WorkflowStepUpdated,             # Wave 63 (ADR-049)
        CRDTCounterIncremented,          # Wave 33 (ADR-042)
        CRDTTimestampUpdated,            # Wave 33 (ADR-042)
        CRDTSetElementAdded,             # Wave 33 (ADR-042)
        CRDTRegisterAssigned,            # Wave 33 (ADR-042)
        MemoryEntryMerged,               # Wave 33 (ADR-042)
        ParallelPlanCreated,             # Wave 35 (ADR-045)
        KnowledgeDistilled,              # Wave 35 (ADR-045 D2)
        KnowledgeEntryOperatorAction,    # Wave 39 (ADR-049)
        KnowledgeEntryAnnotated,         # Wave 39 (ADR-049)
        ConfigSuggestionOverridden,      # Wave 39 (ADR-049)
        ForageRequested,                 # Wave 44
        ForageCycleCompleted,            # Wave 44
        DomainStrategyUpdated,           # Wave 44
        ForagerDomainOverride,           # Wave 44
        ColonyEscalated,                 # Wave 51
        QueenNoteSaved,                  # Wave 51
        MemoryEntryRefined,              # Wave 59 (ADR-048)
        AddonLoaded,                     # Wave 64 (ADR-050)
        AddonUnloaded,                   # Wave 64 (ADR-050)
        ServiceTriggerFired,             # Wave 64 (ADR-050)
    ],
    Field(discriminator="type"),
]

# ---------------------------------------------------------------------------
# Declared event manifest (ADR-036).  Import-time self-check below.
# ---------------------------------------------------------------------------

EVENT_TYPE_NAMES: list[str] = [
    "WorkspaceCreated",
    "ThreadCreated",
    "ThreadRenamed",
    "ColonySpawned",
    "ColonyCompleted",
    "ColonyFailed",
    "ColonyKilled",
    "RoundStarted",
    "PhaseEntered",
    "AgentTurnStarted",
    "AgentTurnCompleted",
    "RoundCompleted",
    "MergeCreated",
    "MergePruned",
    "ContextUpdated",
    "WorkspaceConfigChanged",
    "ModelRegistered",
    "ModelAssignmentChanged",
    "ApprovalRequested",
    "ApprovalGranted",
    "ApprovalDenied",
    "QueenMessage",
    "TokensConsumed",
    "ColonyTemplateCreated",
    "ColonyTemplateUsed",
    "ColonyNamed",
    "SkillConfidenceUpdated",
    "SkillMerged",
    "ColonyChatMessage",
    "CodeExecuted",
    "ServiceQuerySent",
    "ServiceQueryResolved",
    "ColonyServiceActivated",
    "KnowledgeEntityCreated",
    "KnowledgeEdgeCreated",
    "KnowledgeEntityMerged",
    "ColonyRedirected",
    "MemoryEntryCreated",
    "MemoryEntryStatusChanged",
    "MemoryExtractionCompleted",
    "KnowledgeAccessRecorded",
    "ThreadGoalSet",
    "ThreadStatusChanged",
    "MemoryEntryScopeChanged",
    "DeterministicServiceRegistered",
    "MemoryConfidenceUpdated",
    "WorkflowStepDefined",
    "WorkflowStepCompleted",
    "WorkflowStepUpdated",
    "CRDTCounterIncremented",
    "CRDTTimestampUpdated",
    "CRDTSetElementAdded",
    "CRDTRegisterAssigned",
    "MemoryEntryMerged",
    "ParallelPlanCreated",
    "KnowledgeDistilled",
    "KnowledgeEntryOperatorAction",
    "KnowledgeEntryAnnotated",
    "ConfigSuggestionOverridden",
    "ForageRequested",
    "ForageCycleCompleted",
    "DomainStrategyUpdated",
    "ForagerDomainOverride",
    "ColonyEscalated",
    "QueenNoteSaved",
    "MemoryEntryRefined",
    "AddonLoaded",
    "AddonUnloaded",
    "ServiceTriggerFired",
]

# Import-time self-check: manifest must match the closed union members.
_union_members: frozenset[str] = frozenset(
    t.__name__  # pyright: ignore[reportAttributeAccessIssue]
    for t in (
        WorkspaceCreated, ThreadCreated, ThreadRenamed, ColonySpawned,
        ColonyCompleted, ColonyFailed, ColonyKilled, RoundStarted,
        PhaseEntered, AgentTurnStarted, AgentTurnCompleted, RoundCompleted,
        MergeCreated, MergePruned, ContextUpdated, WorkspaceConfigChanged,
        ModelRegistered, ModelAssignmentChanged, ApprovalRequested,
        ApprovalGranted, ApprovalDenied, QueenMessage, TokensConsumed,
        ColonyTemplateCreated, ColonyTemplateUsed, ColonyNamed,
        SkillConfidenceUpdated, SkillMerged, ColonyChatMessage,
        CodeExecuted, ServiceQuerySent, ServiceQueryResolved,
        ColonyServiceActivated, KnowledgeEntityCreated,
        KnowledgeEdgeCreated, KnowledgeEntityMerged, ColonyRedirected,
        MemoryEntryCreated, MemoryEntryStatusChanged, MemoryExtractionCompleted,
        KnowledgeAccessRecorded,
        ThreadGoalSet, ThreadStatusChanged, MemoryEntryScopeChanged,
        DeterministicServiceRegistered,
        MemoryConfidenceUpdated, WorkflowStepDefined, WorkflowStepCompleted, WorkflowStepUpdated,
        CRDTCounterIncremented, CRDTTimestampUpdated, CRDTSetElementAdded,
        CRDTRegisterAssigned, MemoryEntryMerged,
        ParallelPlanCreated,
        KnowledgeDistilled,
        KnowledgeEntryOperatorAction,
        KnowledgeEntryAnnotated,
        ConfigSuggestionOverridden,
        ForageRequested,
        ForageCycleCompleted,
        DomainStrategyUpdated,
        ForagerDomainOverride,
        ColonyEscalated,
        QueenNoteSaved,
        MemoryEntryRefined,
        AddonLoaded,
        AddonUnloaded,
        ServiceTriggerFired,
    )
)
_manifest_set = frozenset(EVENT_TYPE_NAMES)
if _manifest_set != _union_members:
    _missing = _union_members - _manifest_set
    _extra = _manifest_set - _union_members
    raise RuntimeError(
        f"EVENT_TYPE_NAMES manifest drift! "
        f"Missing from manifest: {_missing or 'none'}. "
        f"Extra in manifest: {_extra or 'none'}."
    )


_EVENT_ADAPTER: TypeAdapter[FormicOSEvent] = TypeAdapter(FormicOSEvent)  # pyright: ignore[reportUnknownVariableType]


def serialize(event: FormicOSEvent) -> str:
    """Serialize a frozen event to canonical JSON."""

    return event.model_dump_json()


def deserialize(value: str | bytes | bytearray | Mapping[str, Any]) -> FormicOSEvent:
    """Deserialize JSON or a Python mapping into the closed event union."""

    if isinstance(value, Mapping):
        return _EVENT_ADAPTER.validate_python(dict(value))  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
    return _EVENT_ADAPTER.validate_json(value)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]


__all__ = [
    "AddonLoaded",
    "AddonUnloaded",
    "AgentTurnCompleted",
    "AgentTurnStarted",
    "ApprovalDenied",
    "ApprovalGranted",
    "ApprovalRequested",
    "CRDTCounterIncremented",
    "CRDTRegisterAssigned",
    "CRDTSetElementAdded",
    "CRDTTimestampUpdated",
    "CodeExecuted",
    "ColonyChatMessage",
    "ColonyCompleted",
    "ColonyEscalated",
    "ColonyFailed",
    "ColonyKilled",
    "ColonyNamed",
    "ColonyRedirected",
    "ColonyServiceActivated",
    "ColonySpawned",
    "ColonyTemplateCreated",
    "ColonyTemplateUsed",
    "ConfigSuggestionOverridden",
    "ContextOperationName",
    "ContextUpdated",
    "DeterministicServiceRegistered",
    "DomainOverrideAction",
    "DomainStrategyUpdated",
    "CoordinationStrategyName",
    "deserialize",
    "EVENT_TYPE_NAMES",
    "EventEnvelope",
    "ForageCycleCompleted",
    "ForageModeName",
    "ForageRequested",
    "ForagerDomainOverride",
    "FormicOSEvent",
    "KnowledgeAccessItem",
    "KnowledgeAccessRecorded",
    "KnowledgeDistilled",
    "KnowledgeEdgeCreated",
    "KnowledgeEntryAnnotated",
    "KnowledgeEntryOperatorAction",
    "KnowledgeEntityCreated",
    "KnowledgeEntityMerged",
    "MemoryConfidenceUpdated",
    "MemoryEntryScopeChanged",
    "MemoryEntryCreated",
    "MemoryEntryMerged",
    "MemoryEntryRefined",
    "MemoryEntryStatusChanged",
    "ParallelPlanCreated",
    "MemoryExtractionCompleted",
    "MergeCreated",
    "MergePruned",
    "ModelAssignmentChanged",
    "ModelRegistered",
    "PhaseEntered",
    "PhaseName",
    "QueenMessage",
    "QueenNoteSaved",
    "QueenRoleName",
    "ServiceTriggerFired",
    "RoundCompleted",
    "RoundStarted",
    "serialize",
    "ServiceQueryResolved",
    "ServiceQuerySent",
    "SkillConfidenceUpdated",
    "SkillMerged",
    "ThreadCreated",
    "ThreadGoalSet",
    "ThreadRenamed",
    "ThreadStatusChanged",
    "TokensConsumed",
    "WorkflowStepCompleted",
    "WorkflowStepDefined",
    "WorkflowStepUpdated",
    "WorkspaceConfigChanged",
    "WorkspaceConfigSnapshot",
    "WorkspaceCreated",
]
