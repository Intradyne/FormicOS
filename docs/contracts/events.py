"""FormicOS event vocabulary contract.

DO NOT MODIFY without operator approval. This file freezes the complete
event union. Adding an event extends every consumer and every adapter that
matches on `type`, so the union is intentionally closed.

Wave 19: +1 event (ColonyRedirected) and ColonySpawned extension
(`input_sources`). Union: 36 -> 37.
Wave 26: +3 events (MemoryEntryCreated, MemoryEntryStatusChanged,
MemoryExtractionCompleted). Union: 37 -> 40.
Wave 28: +1 event (KnowledgeAccessRecorded). Union: 40 -> 41.
Wave 29: +4 events (ThreadGoalSet, ThreadStatusChanged, MemoryEntryScopeChanged,
DeterministicServiceRegistered) and ThreadCreated extension (`goal`, `expected_outputs`).
Union: 41 -> 45.
Wave 30: +3 events (MemoryConfidenceUpdated, WorkflowStepDefined,
WorkflowStepCompleted) and ColonySpawned extension (`step_index`).
Union: 45 -> 48.
Wave 33: +5 events (CRDTCounterIncremented, CRDTTimestampUpdated,
CRDTSetElementAdded, CRDTRegisterAssigned, MemoryEntryMerged).
Union: 48 -> 53.
Wave 50: No new events. Additive fields on ColonySpawned (`spawn_source`),
ColonyTemplateCreated (`learned`, `task_category`, `max_rounds`,
`budget_limit`, `fast_path`, `target_files_pattern`), and
MemoryEntryScopeChanged (`new_workspace_id`). Union stays at 62.
Wave 51: +2 events (ColonyEscalated, QueenNoteSaved). Replay safety
for escalation (previously runtime-only) and Queen notes (previously
YAML-only). Union: 62 -> 64.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from formicos.core.types import (
    AccessMode,
    ApprovalType,
    MergeReason,
    RedirectTrigger,
    ServicePriority,
)

FrozenConfig = ConfigDict(frozen=True, extra="forbid")

CoordinationStrategyName = Literal["stigmergic", "sequential"]
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


class CasteSlot(BaseModel):
    """Typed slot describing one caste role in a colony."""
    model_config = FrozenConfig
    caste: str = Field(..., description="Caste name.")
    tier: str = Field(default="standard", description="Routing tier override.")
    count: int = Field(default=1, description="Number of agents to spawn.")


class InputSource(BaseModel):
    """Resolved source of seed context for colony chaining."""

    model_config = FrozenConfig

    type: Literal["colony"] = Field(
        ...,
        description="Wave 19 supports completed-colony sources only.",
    )
    colony_id: str = Field(..., description="Completed source colony identifier.")
    summary: str = Field(
        default="",
        description="Resolved compressed summary injected into the new colony.",
    )


class WorkflowStep(BaseModel):
    """Declarative workflow step attached to a thread (Wave 30)."""

    model_config = FrozenConfig

    step_index: int = Field(..., description="Zero-based position in the workflow.")
    description: str = Field(..., description="What this step should accomplish.")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Artifact types this step should produce.",
    )
    template_id: str = Field(default="", description="Optional colony template.")
    strategy: str = Field(default="stigmergic", description="Coordination strategy.")
    status: str = Field(default="pending", description="pending | running | completed | failed | skipped.")
    colony_id: str = Field(default="", description="Colony assigned to this step.")
    input_from_step: int = Field(
        default=-1,
        description="Step index whose output seeds this step (-1 = none).",
    )


class ColonySpawned(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonySpawned"] = "ColonySpawned"
    thread_id: str = Field(..., description="Parent thread identifier.")
    task: str = Field(..., description="Operator or Queen task for the colony.")
    castes: list[CasteSlot] = Field(
        ...,
        description="Ordered caste slots included in the colony.",
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
    template_id: str = Field(default="", description="Template used to spawn, if any.")
    input_sources: list[InputSource] = Field(
        default_factory=list,
        description="Resolved input sources for colony chaining.",
    )
    step_index: int = Field(
        default=-1,
        description="Workflow step this colony fulfils (-1 = none). Wave 30.",
    )
    target_files: list[str] = Field(
        default_factory=list,
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
        default_factory=list,
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
        default=0, ge=0,
        description="Reasoning/thinking tokens (subset of output).",
    )
    cache_read_tokens: int = Field(
        default=0, ge=0,
        description="Input tokens served from cache.",
    )


class ColonyTemplateCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyTemplateCreated"] = "ColonyTemplateCreated"
    template_id: str = Field(..., description="Stable template identifier.")
    name: str = Field(..., description="Human-readable template name.")
    description: str = Field(..., description="Template description.")
    castes: list[CasteSlot] = Field(..., description="Caste slots included in the template.")
    strategy: CoordinationStrategyName = Field(..., description="Coordination strategy.")
    source_colony_id: str | None = Field(default=None, description="Colony this was saved from.")
    # Wave 50: additive fields for learned templates
    learned: bool = Field(default=False, description="True for replay-derived learned templates.")
    task_category: str = Field(default="", description="Category from classify_task() for v1 matching.")
    max_rounds: int = Field(default=25, description="Default rounds when reusing this template.")
    budget_limit: float = Field(default=1.0, description="Default budget when reusing this template.")
    fast_path: bool = Field(default=False, description="Whether the learned template prefers fast_path.")
    target_files_pattern: str = Field(default="", description="Optional compact target-files pattern.")


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


class SkillConfidenceUpdated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["SkillConfidenceUpdated"] = "SkillConfidenceUpdated"
    colony_id: str = Field(..., description="Colony whose completion triggered updates.")
    skills_updated: int = Field(..., ge=0, description="Count of skills with changed confidence.")
    colony_succeeded: bool = Field(..., description="Whether the colony succeeded or failed.")


class SkillMerged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["SkillMerged"] = "SkillMerged"
    surviving_skill_id: str = Field(..., description="Skill that absorbed the other.")
    merged_skill_id: str = Field(..., description="Skill that was absorbed.")
    merge_reason: MergeReason = Field(..., description="Why merged: 'llm_dedup'.")


# Wave 14 events


class ColonyChatMessage(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyChatMessage"] = "ColonyChatMessage"
    colony_id: str = Field(..., description="Colony identifier.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    sender: str = Field(..., description="ChatSender value.")
    content: str = Field(..., description="Message content.")
    agent_id: str | None = Field(default=None, description="Agent that sent the message.")
    caste: str | None = Field(default=None, description="Caste of the sending agent.")
    event_kind: str | None = Field(default=None, description="Optional event kind tag.")
    directive_type: str | None = Field(default=None, description="Optional directive type.")
    source_colony: str | None = Field(default=None, description="Source colony for merge messages.")
    metadata: dict[str, Any] | None = Field(
        default=None, description="Arbitrary extra data.",
    )


class CodeExecuted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["CodeExecuted"] = "CodeExecuted"
    colony_id: str = Field(..., description="Colony that ran the code.")
    agent_id: str = Field(..., description="Agent that executed the code.")
    code_preview: str = Field(..., description="Truncated code snippet.")
    trust_tier: str = Field(..., description="Sandbox trust tier.")
    exit_code: int = Field(..., description="Process exit code.")
    stdout_preview: str = Field(default="", description="Truncated stdout.")
    stderr_preview: str = Field(default="", description="Truncated stderr.")
    duration_ms: float = Field(..., description="Wall-clock execution time.")
    peak_memory_mb: float = Field(
        default=0.0, description="Peak memory usage in MB.",
    )
    blocked: bool = Field(default=False, description="Whether execution was blocked by policy.")


class ServiceQuerySent(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ServiceQuerySent"] = "ServiceQuerySent"
    request_id: str = Field(..., description="Unique request identifier.")
    service_type: str = Field(..., description="Service type being queried.")
    target_colony_id: str = Field(..., description="Target service colony.")
    sender_colony_id: str | None = Field(default=None, description="Sending colony.")
    query_preview: str = Field(
        ..., description="First 200 chars of the query text.",
    )
    priority: ServicePriority = Field(
        default=ServicePriority.normal, description="normal or high.",
    )


class ServiceQueryResolved(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ServiceQueryResolved"] = "ServiceQueryResolved"
    request_id: str = Field(..., description="Matching request identifier.")
    service_type: str = Field(..., description="Service type that responded.")
    source_colony_id: str = Field(..., description="Colony that provided the response.")
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
    colony_id: str = Field(..., description="Colony activated as a service.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    service_type: str = Field(..., description="Service type registered.")
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
    entity_id: str = Field(..., description="Unique entity identifier.")
    name: str = Field(..., description="Entity name.")
    entity_type: str = Field(..., description="Entity type.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    source_colony_id: str | None = Field(default=None, description="Source colony.")


class KnowledgeEdgeCreated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["KnowledgeEdgeCreated"] = "KnowledgeEdgeCreated"
    edge_id: str = Field(..., description="Unique edge identifier.")
    from_entity_id: str = Field(..., description="Source entity.")
    to_entity_id: str = Field(..., description="Target entity.")
    predicate: str = Field(..., description="Relationship predicate.")
    confidence: float = Field(..., description="Edge confidence score.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    source_colony_id: str | None = Field(default=None, description="Source colony.")
    source_round: int | None = Field(default=None, description="Round that produced the edge.")


class KnowledgeEntityMerged(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["KnowledgeEntityMerged"] = "KnowledgeEntityMerged"
    survivor_id: str = Field(..., description="Entity that absorbed the other.")
    merged_id: str = Field(..., description="Entity that was absorbed.")
    similarity_score: float = Field(..., description="Cosine similarity that triggered merge.")
    merge_method: str = Field(..., description="Merge method used.")
    workspace_id: str = Field(..., description="Workspace identifier.")


class ColonyRedirected(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["ColonyRedirected"] = "ColonyRedirected"
    colony_id: str = Field(..., description="Colony being redirected.")
    redirect_index: int = Field(..., ge=0, description="0-based redirect counter.")
    original_goal: str = Field(..., description="Immutable original task from spawn.")
    new_goal: str = Field(..., description="New active goal.")
    reason: str = Field(..., description="Queen rationale for the redirect.")
    trigger: RedirectTrigger = Field(
        ...,
        description="Trigger source such as queen_inspection, governance_alert, or operator_request.",
    )
    round_at_redirect: int = Field(..., ge=0, description="Round number at redirect time.")


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

    Durable receipt that extraction ran to completion (Wave 26).
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


class KnowledgeAccessItem(BaseModel):
    """Single knowledge item accessed during a colony round (Wave 28)."""

    model_config = FrozenConfig

    id: str = Field(description="Knowledge item ID (mem-* for institutional, UUID for legacy)")
    source_system: str = Field(description="legacy_skill_bank | institutional_memory")
    canonical_type: str = Field(description="skill | experience")
    title: str = Field(default="")
    confidence: float = Field(default=0.5)
    score: float = Field(default=0.0, description="Query relevance score from retrieval")


class KnowledgeAccessRecorded(EventEnvelope):
    """Knowledge items accessed during a colony round (Wave 28)."""

    model_config = FrozenConfig

    type: Literal["KnowledgeAccessRecorded"] = "KnowledgeAccessRecorded"
    colony_id: str = Field(..., description="Colony that accessed knowledge.")
    round_number: int = Field(..., ge=1, description="Round number.")
    workspace_id: str = Field(..., description="Workspace scope.")
    access_mode: AccessMode = Field(
        default=AccessMode.context_injection,
        description="context_injection | tool_search | tool_detail | tool_transcript. Wave 28+ tool tracing.",
    )
    items: list[KnowledgeAccessItem] = Field(
        default_factory=list,
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
    """Two knowledge entries merged, with full provenance trail (ADR-042 D2)."""

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


class ParallelPlanCreated(EventEnvelope):
    """Queen generated a validated DelegationPlan for parallel colony dispatch (Wave 35 ADR-045)."""

    model_config = FrozenConfig

    type: Literal["ParallelPlanCreated"] = "ParallelPlanCreated"
    thread_id: str = Field(...)
    workspace_id: str = Field(...)
    plan: dict[str, Any] = Field(...)
    parallel_groups: list[list[str]] = Field(...)
    reasoning: str = Field(...)
    knowledge_gaps: list[str] = Field(default_factory=list)
    estimated_cost: float = Field(default=0.0)


class KnowledgeDistilled(EventEnvelope):
    """Archivist colony synthesized a knowledge cluster into a higher-order entry (Wave 35 ADR-045)."""

    model_config = FrozenConfig

    type: Literal["KnowledgeDistilled"] = "KnowledgeDistilled"
    distilled_entry_id: str = Field(...)
    source_entry_ids: list[str] = Field(...)
    workspace_id: str = Field(...)
    cluster_avg_weight: float = Field(...)
    distillation_strategy: str = Field(default="archivist_synthesis")


# ---------------------------------------------------------------------------
# Wave 39 — Operator co-authorship (ADR-049)
# ---------------------------------------------------------------------------

OperatorActionName = Literal[
    "pin", "unpin", "mute", "unmute", "invalidate", "reinstate",
]


class KnowledgeEntryOperatorAction(EventEnvelope):
    """Operator editorial overlay on a knowledge entry (ADR-049)."""

    model_config = FrozenConfig

    type: Literal["KnowledgeEntryOperatorAction"] = "KnowledgeEntryOperatorAction"
    entry_id: str = Field(...)
    workspace_id: str = Field(...)
    action: OperatorActionName = Field(...)
    actor: str = Field(...)
    reason: str = Field(default="")


class KnowledgeEntryAnnotated(EventEnvelope):
    """Operator annotation on a knowledge entry (ADR-049)."""

    model_config = FrozenConfig

    type: Literal["KnowledgeEntryAnnotated"] = "KnowledgeEntryAnnotated"
    entry_id: str = Field(...)
    workspace_id: str = Field(...)
    annotation_text: str = Field(...)
    tag: str = Field(default="")
    actor: str = Field(...)


class ConfigSuggestionOverridden(EventEnvelope):
    """Operator edited a recommendation before execution (ADR-049)."""

    model_config = FrozenConfig

    type: Literal["ConfigSuggestionOverridden"] = "ConfigSuggestionOverridden"
    workspace_id: str = Field(...)
    suggestion_category: str = Field(...)
    original_config: dict[str, Any] = Field(...)
    overridden_config: dict[str, Any] = Field(...)
    reason: str = Field(default="")
    actor: str = Field(...)


# ---------------------------------------------------------------------------
# Wave 44 — Forager events (4 new types)
# ---------------------------------------------------------------------------

ForageModeName = Literal["reactive", "proactive", "operator"]
DomainOverrideAction = Literal["trust", "distrust", "reset"]


class ForageRequested(EventEnvelope):
    """The system decided to forage for external knowledge (Wave 44)."""

    model_config = FrozenConfig

    type: Literal["ForageRequested"] = "ForageRequested"
    workspace_id: str = Field(...)
    thread_id: str = Field(default="")
    colony_id: str = Field(default="")
    mode: ForageModeName = Field(...)
    reason: str = Field(...)
    gap_domain: str = Field(default="")
    gap_query: str = Field(default="")
    max_results: int = Field(default=5, ge=1, le=20)


class ForageCycleCompleted(EventEnvelope):
    """A forage cycle finished (Wave 44)."""

    model_config = FrozenConfig

    type: Literal["ForageCycleCompleted"] = "ForageCycleCompleted"
    workspace_id: str = Field(...)
    forage_request_seq: int = Field(...)
    queries_issued: int = Field(default=0, ge=0)
    pages_fetched: int = Field(default=0, ge=0)
    pages_rejected: int = Field(default=0, ge=0)
    entries_admitted: int = Field(default=0, ge=0)
    entries_deduplicated: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    error: str = Field(default="")


class DomainStrategyUpdated(EventEnvelope):
    """Forager learned a fetch-level preference for a domain (Wave 44)."""

    model_config = FrozenConfig

    type: Literal["DomainStrategyUpdated"] = "DomainStrategyUpdated"
    workspace_id: str = Field(...)
    domain: str = Field(...)
    preferred_level: int = Field(..., ge=1, le=3)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    reason: str = Field(default="")


class ForagerDomainOverride(EventEnvelope):
    """Operator domain-level trust override for forager (Wave 44)."""

    model_config = FrozenConfig

    type: Literal["ForagerDomainOverride"] = "ForagerDomainOverride"
    workspace_id: str = Field(...)
    domain: str = Field(...)
    action: DomainOverrideAction = Field(...)
    actor: str = Field(...)
    reason: str = Field(default="")


# ---------------------------------------------------------------------------
# Wave 51 — Replay safety (2 new types)
# ---------------------------------------------------------------------------


class ColonyEscalated(EventEnvelope):
    """Colony routing tier was escalated by the Queen (Wave 51)."""

    model_config = FrozenConfig

    type: Literal["ColonyEscalated"] = "ColonyEscalated"
    colony_id: str = Field(...)
    tier: str = Field(...)
    reason: str = Field(...)
    set_at_round: int = Field(..., ge=0)


class QueenNoteSaved(EventEnvelope):
    """Queen saved a private thread-scoped note (Wave 51).

    Private working context — NOT visible in operator chat.
    """

    model_config = FrozenConfig

    type: Literal["QueenNoteSaved"] = "QueenNoteSaved"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    content: str = Field(...)


class MemoryEntryRefined(EventEnvelope):
    """In-place content improvement of a knowledge entry (Wave 59, ADR-048)."""

    model_config = FrozenConfig

    type: Literal["MemoryEntryRefined"] = "MemoryEntryRefined"
    entry_id: str = Field(..., description="Entry being refined.")
    workspace_id: str = Field(default="")
    old_content: str = Field(..., description="Content before refinement (audit trail).")
    new_content: str = Field(..., description="Improved content.")
    new_title: str = Field(default="", description="Updated title. Empty string = keep existing.")
    refinement_source: Literal["extraction", "maintenance", "operator"] = Field(
        ..., description="What triggered the refinement.",
    )
    source_colony_id: str = Field(
        default="",
        description="Colony whose output informed the refinement. "
        "Empty for maintenance-triggered refinements.",
    )


FormicOSEvent: TypeAlias = Annotated[
    Union[
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
        MemoryEntryCreated,
        MemoryEntryStatusChanged,
        MemoryExtractionCompleted,
        KnowledgeAccessRecorded,
        ThreadGoalSet,
        ThreadStatusChanged,
        MemoryEntryScopeChanged,
        DeterministicServiceRegistered,
        MemoryConfidenceUpdated,         # Wave 30
        WorkflowStepDefined,             # Wave 30 (Track B)
        WorkflowStepCompleted,           # Wave 30 (Track B)
        CRDTCounterIncremented,          # Wave 33 (ADR-042)
        CRDTTimestampUpdated,            # Wave 33 (ADR-042)
        CRDTSetElementAdded,             # Wave 33 (ADR-042)
        CRDTRegisterAssigned,            # Wave 33 (ADR-042)
        MemoryEntryMerged,               # Wave 33 (ADR-042)
        ParallelPlanCreated,             # Wave 35 (ADR-045)
        KnowledgeDistilled,              # Wave 35 (ADR-045)
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
        MemoryConfidenceUpdated, WorkflowStepDefined, WorkflowStepCompleted,
        CRDTCounterIncremented, CRDTTimestampUpdated, CRDTSetElementAdded,
        CRDTRegisterAssigned, MemoryEntryMerged,
        ParallelPlanCreated, KnowledgeDistilled,
        KnowledgeEntryOperatorAction, KnowledgeEntryAnnotated,
        ConfigSuggestionOverridden,
        ForageRequested, ForageCycleCompleted,
        DomainStrategyUpdated, ForagerDomainOverride,
        ColonyEscalated, QueenNoteSaved,
        MemoryEntryRefined,
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
        return _EVENT_ADAPTER.validate_python(dict(value))
    return _EVENT_ADAPTER.validate_json(value)


__all__ = [
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
    "MemoryEntryStatusChanged",
    "MemoryExtractionCompleted",
    "MergeCreated",
    "MergePruned",
    "ModelAssignmentChanged",
    "ModelRegistered",
    "ParallelPlanCreated",
    "PhaseEntered",
    "PhaseName",
    "QueenMessage",
    "QueenNoteSaved",
    "QueenRoleName",
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
    "WorkspaceConfigChanged",
    "WorkspaceConfigSnapshot",
    "WorkspaceCreated",
]
