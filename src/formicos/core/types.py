"""FormicOS core types — value objects, configs, and LLM/vector data structures."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict, Field

FrozenConfig = ConfigDict(frozen=True, extra="forbid")

CoordinationStrategyName = Literal["stigmergic", "sequential"]


# ---------------------------------------------------------------------------
# Wave 14 enums and structured caste slot (ADR-020)
# ---------------------------------------------------------------------------


class SubcasteTier(StrEnum):
    light = "light"
    standard = "standard"
    heavy = "heavy"
    flash = "flash"


class ChatSender(StrEnum):
    operator = "operator"
    queen = "queen"
    system = "system"
    agent = "agent"
    service = "service"


class ArtifactType(StrEnum):
    """Typed artifact categories produced by colonies (Wave 25)."""

    code = "code"
    test = "test"
    document = "document"
    schema = "schema"
    data = "data"
    config = "config"
    report = "report"
    generic = "generic"


class ToolCategory(StrEnum):
    """Categories for tool permission enforcement (ADR-023)."""

    read_fs = "read_fs"
    write_fs = "write_fs"
    exec_code = "exec_code"
    search_web = "search_web"
    vector_query = "vector_query"
    llm_call = "llm_call"
    shell_cmd = "shell_cmd"
    network_out = "network_out"
    delegate = "delegate"


class CasteToolPolicy(BaseModel):
    """Per-caste tool permission policy (ADR-023)."""

    model_config = FrozenConfig

    caste: str = Field(..., description="Caste name this policy applies to.")
    allowed_categories: frozenset[ToolCategory] = Field(
        ..., description="Tool categories permitted for this caste.",
    )
    denied_tools: frozenset[str] = Field(
        default=frozenset(), description="Explicit tool deny list (overrides category allow).",
    )
    max_tool_calls_per_iteration: int = Field(
        default=10, description="Max tool calls in a single iteration.",
    )


class CasteSlot(BaseModel):
    """Structured caste slot with tier override and count (ADR-020)."""

    model_config = FrozenConfig

    caste: str = Field(..., description="Caste name.")
    tier: SubcasteTier = Field(
        default=SubcasteTier.standard, description="Routing tier override.",
    )
    count: int = Field(default=1, description="Number of agents to spawn.")


# ---------------------------------------------------------------------------
# Node address
# ---------------------------------------------------------------------------


class NodeType(StrEnum):
    system = "system"
    workspace = "workspace"
    thread = "thread"
    colony = "colony"
    round = "round"
    turn = "turn"


class NodeAddress(BaseModel):
    """Immutable tree address encoded as a tuple of path segments."""

    model_config = FrozenConfig

    segments: tuple[str, ...] = Field(
        ..., description="Ordered path segments from root to leaf."
    )

    @property
    def workspace_id(self) -> str | None:
        """Return the workspace segment if present."""
        return self.segments[0] if len(self.segments) >= 1 else None

    @property
    def thread_id(self) -> str | None:
        """Return the thread segment if present."""
        return self.segments[1] if len(self.segments) >= 2 else None

    @property
    def colony_id(self) -> str | None:
        """Return the colony segment if present."""
        return self.segments[2] if len(self.segments) >= 3 else None

    def parent(self) -> NodeAddress | None:
        """Return the parent address or None if already at root."""
        if len(self.segments) <= 1:
            return None
        return NodeAddress(segments=self.segments[:-1])


# ---------------------------------------------------------------------------
# Merge edge
# ---------------------------------------------------------------------------


class MergeEdge(BaseModel):
    """Immutable inter-colony merge edge."""

    model_config = FrozenConfig

    id: str = Field(..., description="Stable merge edge identifier.")
    from_colony: str = Field(..., description="Source colony identifier.")
    to_colony: str = Field(..., description="Destination colony identifier.")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    created_by: str = Field(..., description="Actor that created the edge.")


# ---------------------------------------------------------------------------
# Caste and model configuration
# ---------------------------------------------------------------------------


class CasteRecipe(BaseModel):
    """Defines an agent caste's behaviour template."""

    name: str = Field(..., description="Caste name.")
    description: str = Field(default="", description="Human-readable caste description.")
    system_prompt: str = Field(..., description="System prompt template.")
    temperature: float = Field(..., description="Sampling temperature.")
    model_override: str | None = Field(
        default=None,
        description="Deprecated — unused by runtime. Use tier_models instead.",
    )
    tools: list[str] = Field(..., description="Tool names available to this caste.")
    max_tokens: int = Field(
        ...,
        description="Legacy output token cap. Superseded by ModelRecord.max_output_tokens.",
    )
    max_iterations: int = Field(default=5, description="Per-caste iteration cap (Wave 14).")
    max_execution_time_s: int = Field(
        default=120, description="Base execution time in seconds (multiplied by model policy).",
    )
    base_tool_calls_per_iteration: int = Field(
        default=10,
        description="Base tool calls per iteration (multiplied by model policy).",
    )
    tier_models: dict[str, str] = Field(
        default_factory=dict,
        description="Per-tier model overrides, e.g. {'light': 'gemini/gemini-2.5-flash'}.",
    )


class ModelRecord(BaseModel):
    """Registry entry for an LLM model endpoint."""

    address: str = Field(..., description="Canonical model address.")
    provider: str = Field(..., description="Provider prefix.")
    endpoint: str | None = Field(default=None, description="Optional endpoint URL.")
    api_key_env: str | None = Field(
        default=None, description="Environment variable name for the API key."
    )
    context_window: int = Field(..., description="Max context window in tokens.")
    supports_tools: bool = Field(..., description="Tool calling support.")
    supports_vision: bool | None = Field(
        default=False, description="Vision support."
    )
    cost_per_input_token: float | None = Field(
        default=None, description="USD cost per input token."
    )
    cost_per_output_token: float | None = Field(
        default=None, description="USD cost per output token."
    )
    status: Literal["available", "unavailable", "no_key", "loaded", "error"] = Field(
        default="available", description="Current model status."
    )
    max_output_tokens: int = Field(
        default=4096, description="Max output tokens for this model.",
    )
    time_multiplier: float = Field(
        default=1.0,
        description="Multiplier over caste base execution time.",
    )
    tool_call_multiplier: float = Field(
        default=1.0,
        description="Multiplier over caste base tool calls per iteration.",
    )
    max_concurrent: int = Field(
        default=0,
        description="Max concurrent requests. 0 = use LLM_SLOTS env var.",
    )


# ---------------------------------------------------------------------------
# Input source for colony chaining (ADR-033)
# ---------------------------------------------------------------------------

InputSourceType: TypeAlias = Literal["colony"]  # noqa: UP040


class InputSource(BaseModel):
    """Source of seed context for a chained colony (ADR-033).

    Wave 19 implements type="colony" only. The discriminator leaves room for
    future source types (file, url, skill_set) without redesign.
    """

    model_config = FrozenConfig

    type: InputSourceType = Field(
        ..., description="Source type discriminator. Wave 19: 'colony' only.",
    )
    colony_id: str = Field(
        ..., description="Source colony identifier (must be completed).",
    )
    summary: str = Field(
        default="", description="Resolved at spawn time — not a lazy reference.",
    )
    artifacts: list[dict[str, Any]] = Field(
        default_factory=lambda: [],
        description="Artifacts from the completed source colony (Wave 25).",
    )


class ApprovalType(StrEnum):
    """Operator-facing approval categories (Wave 32 C3)."""

    budget_increase = "budget_increase"
    cloud_burst = "cloud_burst"
    tool_permission = "tool_permission"
    expense = "expense"


class ServicePriority(StrEnum):
    """Service query priority levels (Wave 32 C3)."""

    normal = "normal"
    high = "high"


class RedirectTrigger(StrEnum):
    """Colony redirect trigger sources (Wave 32 C3)."""

    queen_inspection = "queen_inspection"
    governance_alert = "governance_alert"
    operator_request = "operator_request"


class MergeReason(StrEnum):
    """Skill merge reasons (Wave 32 C3)."""

    llm_dedup = "llm_dedup"


class AccessMode(StrEnum):
    """Knowledge access mode tracking (Wave 32 C3)."""

    context_injection = "context_injection"
    tool_search = "tool_search"
    tool_detail = "tool_detail"
    tool_transcript = "tool_transcript"


class DecayClass(StrEnum):
    """Confidence decay rate classification (Wave 33 A4, ADR-041)."""

    ephemeral = "ephemeral"    # gamma=0.98, half-life ~34 days
    stable = "stable"          # gamma=0.995, half-life ~139 days
    permanent = "permanent"    # gamma=1.0, no decay


class ScanStatus(StrEnum):
    """Security scan result tiers (Wave 32 C3)."""

    pending = "pending"
    safe = "safe"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MemoryEntryType(StrEnum):
    """Discriminator for institutional memory entries (Wave 26)."""

    skill = "skill"
    experience = "experience"


class MemoryEntryStatus(StrEnum):
    """Trust lifecycle for memory entries (Wave 26)."""

    candidate = "candidate"
    verified = "verified"
    rejected = "rejected"
    stale = "stale"


class MemoryEntryPolarity(StrEnum):
    """Outcome signal carried by a memory entry (Wave 26)."""

    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class EntrySubType(StrEnum):
    """Granular sub-type within skill/experience (Wave 34 B3).

    Skills: technique, pattern, anti_pattern, trajectory.
    Experiences: decision, convention, learning, bug.
    """

    # Under "skill"
    technique = "technique"
    pattern = "pattern"
    anti_pattern = "anti_pattern"
    # Under "skill" -- tool-call sequence from successful colony (Wave 58)
    trajectory = "trajectory"
    # Under "experience"
    decision = "decision"
    convention = "convention"
    learning = "learning"
    bug = "bug"


class DirectiveType(StrEnum):
    """Operator directive types for mid-colony steering (Wave 35 C1, ADR-045 D3)."""

    context_update = "context_update"
    priority_shift = "priority_shift"
    constraint_add = "constraint_add"
    strategy_change = "strategy_change"


class OperatorDirective(BaseModel):
    """Typed operator directive delivered via ColonyChatMessage metadata."""

    model_config = FrozenConfig

    directive_type: DirectiveType
    content: str
    priority: str = "normal"  # "normal" | "urgent"
    applies_to: str = "all"  # "all" | specific agent_id


class MemoryEntry(BaseModel):
    """Institutional memory entry -- skill or experience (Wave 26).

    Persisted as dicts on MemoryEntryCreated events for replay safety.
    The model is used for construction and validation.
    """

    model_config = FrozenConfig

    id: str = Field(description="Stable ID: mem-{colony_id}-{type[0]}-{index}")
    entry_type: MemoryEntryType = Field(description="skill or experience")
    status: MemoryEntryStatus = Field(default=MemoryEntryStatus.candidate)
    polarity: MemoryEntryPolarity = Field(default=MemoryEntryPolarity.positive)
    title: str = Field(description="Short descriptive title")
    content: str = Field(description="Full entry content -- the actionable knowledge")
    summary: str = Field(default="", description="One-line summary for search result display")
    source_colony_id: str = Field(description="Colony that produced this entry")
    source_artifact_ids: list[str] = Field(
        ...,
        description="Artifact IDs from which this entry was derived",
    )
    source_round: int = Field(default=0, description="Round number of source material")
    domains: list[str] = Field(default_factory=list, description="Domain tags")
    tool_refs: list[str] = Field(default_factory=list, description="Tool names referenced")
    confidence: float = Field(default=0.5, description="Initial confidence score")
    scan_status: ScanStatus = Field(default=ScanStatus.pending, description="Scanner result tier")
    created_at: str = Field(default="", description="ISO timestamp")
    workspace_id: str = Field(default="", description="Workspace scope")
    thread_id: str = Field(
        default="",
        description="Thread scope. Empty = workspace-wide (Wave 29).",
    )
    conf_alpha: float = Field(
        default=5.0,
        gt=0,
        description="Beta distribution alpha. Prior strength 10 split evenly (Wave 30).",
    )
    conf_beta: float = Field(
        default=5.0,
        gt=0,
        description="Beta distribution beta. Prior strength 10 split evenly (Wave 30).",
    )
    decay_class: DecayClass = Field(
        default=DecayClass.ephemeral,
        description=(
            "Decay rate class. Ephemeral = standard gamma. "
            "Stable = 4x slower. Permanent = no decay."
        ),
    )
    sub_type: EntrySubType | None = Field(
        default=None,
        description="Granular sub-type within skill/experience (Wave 34 B3).",
    )
    playbook_generation: str = Field(
        default="",
        description="Content-hash of playbooks at extraction time (Wave 56.5 C).",
    )
    trajectory_data: list[dict[str, Any]] = Field(
        default_factory=lambda: [],
        description=(
            "Compressed tool-call sequence for trajectory entries (Wave 58). "
            "Each dict: {tool: str, agent_id: str, round_number: int}."
        ),
    )


class WorkflowStepStatus(StrEnum):
    """Lifecycle status for a workflow step (Wave 30)."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class WorkflowStep(BaseModel):
    """Declarative workflow step attached to a thread (Wave 30).

    Steps are Queen scaffolding — the Queen spawns colonies to fulfill them,
    but steps do not auto-execute.
    """

    model_config = FrozenConfig

    step_index: int = Field(..., description="Zero-based position in the workflow.")
    description: str = Field(..., description="What this step should accomplish.")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Artifact types this step should produce.",
    )
    template_id: str = Field(default="", description="Optional colony template.")
    strategy: str = Field(default="stigmergic", description="Coordination strategy.")
    status: WorkflowStepStatus = Field(default=WorkflowStepStatus.pending)
    colony_id: str = Field(default="", description="Colony assigned to this step.")
    input_from_step: int = Field(
        default=-1,
        description="Step index whose output seeds this step (-1 = none).",
    )


class Artifact(BaseModel):
    """Typed colony output artifact (Wave 25).

    Immutable once created. Persisted as plain dicts on ColonyCompleted
    for replay safety; the model is used for construction and validation.
    """

    model_config = FrozenConfig

    id: str = Field(description="Stable ID: art-{colony}-{agent}-r{round}-{n}")
    name: str = Field(description="Human-readable name, e.g. 'email_validator.py'")
    artifact_type: ArtifactType = Field(default=ArtifactType.generic)
    mime_type: str = Field(default="text/plain")
    content: str = Field(description="Artifact content")
    source_colony_id: str = Field(default="")
    source_agent_id: str = Field(default="")
    source_round: int = Field(default=0)
    created_at: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeAccessItem(BaseModel):
    """Single knowledge item accessed during a colony round (Wave 28).

    Used end-to-end: ContextResult -> RoundResult -> KnowledgeAccessRecorded event.
    """

    model_config = FrozenConfig

    id: str = Field(description="Knowledge item ID (mem-* for institutional, UUID for legacy)")
    source_system: str = Field(description="legacy_skill_bank | institutional_memory")
    canonical_type: str = Field(description="skill | experience")
    title: str = Field(default="")
    confidence: float = Field(default=0.5)
    score: float = Field(default=0.0, description="Composite/ranked score from retrieval")
    similarity: float = Field(
        default=0.0,
        description="Raw semantic similarity from vector search (before composite ranking)",
    )


class ColonyConfig(BaseModel):
    """Configuration for spawning a colony."""

    task: str = Field(..., description="Task description for the colony.")
    castes: list[CasteSlot] = Field(
        ..., description="Ordered caste slots with tier/count assignments."
    )
    max_rounds: int = Field(..., description="Maximum rounds.")
    budget_limit: float = Field(..., description="USD budget limit.")
    context_budget_tokens: int | None = Field(
        default=None, description="Optional context budget in tokens."
    )
    strategy: CoordinationStrategyName = Field(
        ..., description="Coordination strategy."
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Files this colony should focus on (Wave 41 B2).",
    )


# ---------------------------------------------------------------------------
# LLM data structures
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    """Frozen structured completion response."""

    model_config = FrozenConfig

    content: str = Field(..., description="Text content of the response.")
    tool_calls: list[dict[str, Any]] = Field(
        ..., description="Tool calls requested by the model."
    )
    input_tokens: int = Field(..., description="Input tokens consumed.")
    output_tokens: int = Field(..., description="Output tokens produced.")
    reasoning_tokens: int = Field(
        default=0, description="Reasoning/thinking tokens (subset of output).",
    )
    cache_read_tokens: int = Field(
        default=0, description="Input tokens served from cache.",
    )
    model: str = Field(..., description="Model that produced the response.")
    stop_reason: str = Field(..., description="Reason the model stopped generating.")


class LLMChunk(BaseModel):
    """Frozen streaming chunk from an LLM."""

    model_config = FrozenConfig

    content: str = Field(..., description="Chunk text content.")
    is_final: bool = Field(..., description="Whether this is the final chunk.")


class LLMMessage(TypedDict):
    """Single message in an LLM conversation."""

    role: str
    content: str


class LLMToolSpec(TypedDict):
    """Tool schema passed to an LLM for function calling."""

    name: str
    description: str
    parameters: dict[str, Any]


# ---------------------------------------------------------------------------
# Agent and colony context
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Frozen agent identity and configuration."""

    model_config = FrozenConfig

    id: str = Field(..., description="Unique agent identifier.")
    name: str = Field(..., description="Human-readable agent name.")
    caste: str = Field(..., description="Caste assignment.")
    model: str = Field(..., description="Resolved model address.")
    recipe: CasteRecipe = Field(..., description="Caste recipe for this agent.")
    effective_output_tokens: int = Field(
        default=4096,
        description="Model-derived output token cap (from ModelRecord.max_output_tokens).",
    )
    effective_time_limit_s: int = Field(
        default=120,
        description="Effective time limit = caste base * model time_multiplier.",
    )
    effective_tool_calls: int = Field(
        default=10,
        description="Effective tool calls = caste base * model tool_call_multiplier.",
    )


class ColonyContext(BaseModel):
    """Frozen snapshot of colony state passed to strategy and agents."""

    model_config = FrozenConfig

    colony_id: str = Field(..., description="Colony identifier.")
    workspace_id: str = Field(..., description="Workspace identifier.")
    thread_id: str = Field(..., description="Thread identifier.")
    goal: str = Field(..., description="Colony goal text.")
    round_number: int = Field(..., description="Current round number.")
    # NOTE: pheromone_weights uses tuple keys in-memory. For JSON serialization
    # (event checkpoints), convert to "agent_a:agent_b" string keys.
    pheromone_weights: Mapping[tuple[str, str], float] | None = Field(
        default=None, description="Optional pheromone weight map."
    )
    merge_edges: list[MergeEdge] = Field(
        ..., description="Active merge edges for the colony."
    )
    prev_round_summary: str | None = Field(
        default=None, description="Summary from the previous round."
    )
    pending_directives: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]](),
        description="Operator directives queued for injection (Wave 35 C1).",
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Files relevant to this colony's task (Wave 41 B2).",
    )
    workspace_dir: str = Field(
        default="",
        description="Workspace working directory path (Wave 41 B1).",
    )
    structural_context: str = Field(
        default="",
        description="Budget-limited structural workspace context (Wave 42 P1).",
    )
    structural_deps: dict[str, list[str]] = Field(
        default_factory=dict,
        description="File dependency graph subset for target_files (Wave 42 P2).",
    )
    operational_playbook: str = Field(
        default="",
        description="Task-class-keyed procedural guidance (Wave 54).",
    )
    project_context: str = Field(
        default="",
        description="Operator-authored project-specific knowledge (Wave 63).",
    )
    task_class: str = Field(
        default="generic",
        description="Classified task type for domain-boundary filtering (Wave 58.5).",
    )
    stall_count: int = Field(
        default=0,
        description="Consecutive stalled rounds for convergence status (Wave 54).",
    )
    convergence_progress: float = Field(
        default=0.0,
        description="Goal progress from last governance evaluation (Wave 54).",
    )


# ---------------------------------------------------------------------------
# Vector and sandbox data structures
# ---------------------------------------------------------------------------


class VectorDocument(BaseModel):
    """Frozen document for vector store upsert."""

    model_config = FrozenConfig

    id: str = Field(..., description="Document identifier.")
    content: str = Field(..., description="Document content.")
    metadata: dict[str, Any] = Field(..., description="Arbitrary metadata.")


class VectorSearchHit(BaseModel):
    """Frozen search result from the vector store."""

    model_config = FrozenConfig

    id: str = Field(..., description="Matching document identifier.")
    content: str = Field(..., description="Document content.")
    score: float = Field(..., description="Similarity score.")
    metadata: dict[str, Any] = Field(..., description="Document metadata.")


class SandboxExecutionResult(BaseModel):
    """Frozen result from sandbox code execution."""

    model_config = FrozenConfig

    stdout: str = Field(..., description="Standard output.")
    stderr: str = Field(..., description="Standard error.")
    exit_code: int = Field(..., description="Process exit code.")


class TestFailure(BaseModel):
    """Structured representation of a single test failure (Wave 41 B1)."""

    model_config = FrozenConfig

    test_name: str = Field(..., description="Fully qualified test name.")
    error_type: str = Field(default="", description="Exception or error type.")
    message: str = Field(default="", description="Error message summary.")
    file_path: str = Field(default="", description="Source file if available.")
    line_number: int | None = Field(default=None, description="Line number if available.")


class WorkspaceExecutionResult(BaseModel):
    """Structured result from workspace command execution (Wave 41 B1).

    Extends beyond raw stdout/stderr to include parsed test results and
    structured failure information for retry reasoning.
    """

    model_config = FrozenConfig

    stdout: str = Field(default="", description="Standard output (truncated).")
    stderr: str = Field(default="", description="Standard error (truncated).")
    exit_code: int = Field(..., description="Process exit code.")
    command: str = Field(default="", description="The command that was executed.")
    working_dir: str = Field(default="", description="Working directory used.")
    timed_out: bool = Field(default=False, description="Whether execution timed out.")
    files_created: list[str] = Field(
        default_factory=list,
        description="Workspace-relative files or directories created by the command.",
    )
    files_modified: list[str] = Field(
        default_factory=list,
        description="Workspace-relative files modified by the command.",
    )
    files_deleted: list[str] = Field(
        default_factory=list,
        description="Workspace-relative files or directories deleted by the command.",
    )
    warning: str = Field(
        default="",
        description="Execution warning when the process result and workspace state disagree.",
    )
    # Structured test results (populated when test output is detected)
    tests_passed: int = Field(default=0, description="Number of tests passed.")
    tests_failed: int = Field(default=0, description="Number of tests failed.")
    tests_errored: int = Field(default=0, description="Number of tests errored.")
    test_failures: list[TestFailure] = Field(
        default_factory=lambda: list[TestFailure](),
        description="Structured failure details.",
    )
    language: str = Field(default="", description="Detected language/runner.")


# ---------------------------------------------------------------------------
# Wave 33 — Federation types (ADR-042)
# ---------------------------------------------------------------------------


class Resolution(StrEnum):
    """Conflict resolution outcome (Wave 33 C7, Wave 42 class-aware)."""

    winner = "winner"
    competing = "competing"
    complement = "complement"        # Wave 42: linked co-usable entries
    temporal_update = "temporal_update"  # Wave 42: newer supersedes older


class ProvenanceChain(BaseModel):
    """PROV-JSONLD Lite provenance record for knowledge entries (Wave 33 C9)."""

    model_config = FrozenConfig

    generated_by: str = Field(..., description="thread_id + step")
    attributed_to: str = Field(..., description="instance_id or colony_id")
    derived_from: list[str] = Field(
        default_factory=list, description="Source entry IDs",
    )
    generated_at: str = Field(..., description="ISO timestamp")


class KnowledgeExchangeEntry(BaseModel):
    """Serialized knowledge entry for federation exchange (Wave 33 C8)."""

    model_config = FrozenConfig

    entry_id: str
    content: str
    entry_type: str
    polarity: str
    domains: list[str]
    observation_crdt: dict[str, Any] = Field(
        default_factory=dict, description="Serialized ObservationCRDT",
    )
    provenance: ProvenanceChain
    exchange_hop: int = 0
    decay_class: str = "ephemeral"


class ReplicationFilter(BaseModel):
    """Selective replication filter for federation peers (Wave 33 C8)."""

    model_config = FrozenConfig

    domain_allowlist: list[str] = Field(default_factory=list)
    min_confidence: float = Field(default=0.3)
    entry_types: list[str] = Field(
        default_factory=lambda: ["skill", "experience"],
    )
    exclude_thread_ids: list[str] = Field(default_factory=list)


class ValidationFeedback(BaseModel):
    """Feedback on foreign knowledge quality (Wave 33 C8)."""

    model_config = FrozenConfig

    entry_id: str = Field(...)
    success: bool = Field(...)
    peer_id: str = Field(...)


# ---------------------------------------------------------------------------
# Wave 35 — Autonomy levels for self-maintenance (ADR-046)
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    suggest = "suggest"             # briefing shows data, no auto-action (DEFAULT)
    auto_notify = "auto_notify"     # auto-dispatch for opted-in categories, operator notified
    autonomous = "autonomous"       # all eligible categories auto-dispatch


class MaintenancePolicy(BaseModel):
    """Per-workspace self-maintenance autonomy policy (ADR-046)."""

    autonomy_level: AutonomyLevel = AutonomyLevel.suggest
    auto_actions: list[str] = Field(default_factory=list)
    max_maintenance_colonies: int = Field(default=2)
    daily_maintenance_budget: float = Field(default=1.0, gt=0)


# ---------------------------------------------------------------------------
# Wave 35 — Multi-colony delegation planning (ADR-045)
# ---------------------------------------------------------------------------


class ColonyTask(BaseModel):
    """A single task in a Queen's DelegationPlan DAG (Wave 35)."""

    model_config = FrozenConfig

    task_id: str = Field(...)
    task: str = Field(...)
    caste: str = Field(...)  # "coder" | "reviewer" | "researcher" | "archivist"
    strategy: str = Field(default="sequential")  # "sequential" | "stigmergic"
    max_rounds: int = Field(default=5)
    budget_limit: float = Field(default=1.0)
    depends_on: list[str] = Field(default_factory=list)
    input_from: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(
        default_factory=list,
        description="Files the colony should focus on (Wave 41 multi-file).",
    )


class DelegationPlan(BaseModel):
    """Queen's multi-colony execution plan with DAG parallelism (Wave 35)."""

    model_config = FrozenConfig

    reasoning: str = Field(...)
    tasks: list[ColonyTask] = Field(...)
    parallel_groups: list[list[str]] = Field(...)
    estimated_total_cost: float = Field(default=0.0)
    knowledge_gaps: list[str] = Field(default_factory=list)


__all__ = [
    "AgentConfig",
    "Artifact",
    "ArtifactType",
    "AutonomyLevel",
    "CasteRecipe",
    "CasteSlot",
    "CasteToolPolicy",
    "ChatSender",
    "ColonyConfig",
    "ColonyTask",
    "CoordinationStrategyName",
    "ColonyContext",
    "DelegationPlan",
    "DirectiveType",
    "FrozenConfig",
    "InputSource",
    "InputSourceType",
    "KnowledgeAccessItem",
    "KnowledgeExchangeEntry",
    "LLMChunk",
    "LLMMessage",
    "LLMResponse",
    "LLMToolSpec",
    "MaintenancePolicy",
    "MemoryEntry",
    "OperatorDirective",
    "MemoryEntryPolarity",
    "MemoryEntryStatus",
    "MemoryEntryType",
    "MergeEdge",
    "ModelRecord",
    "NodeAddress",
    "NodeType",
    "ProvenanceChain",
    "ReplicationFilter",
    "Resolution",
    "SandboxExecutionResult",
    "SubcasteTier",
    "ToolCategory",
    "ValidationFeedback",
    "VectorDocument",
    "WorkflowStep",
    "WorkflowStepStatus",
    "VectorSearchHit",
]
