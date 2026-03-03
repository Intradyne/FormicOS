"""
FormicOS v0.6.0 -- Pydantic v2 Data Models

All structured state uses typed models instead of raw dicts.
These are the canonical schemas for agent state, topology, episodic memory,
TKG tuples, colony configuration, model registry, skill bank, and the
top-level FormicOSConfig (formicos.yaml loader).

This module is the leaf dependency: it must NOT import from any other src/ module.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────────────────────


class BuiltinCaste(str, Enum):
    """Built-in caste names. Reference only — castes are free-form strings."""

    MANAGER = "manager"
    ARCHITECT = "architect"
    CODER = "coder"
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"
    DYTOPO = "dytopo"


# Backward-compat alias
Caste = BuiltinCaste


class AgentStatus(str, Enum):
    """Runtime status of a single agent."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    ERROR = "error"


class DecisionType(str, Enum):
    """Type of governance decision recorded in the audit trail."""

    ROUTING = "routing"
    TERMINATION = "termination"
    ESCALATION = "escalation"
    INTERVENTION = "intervention"
    STALL = "stall"
    MANAGER_GOAL = "manager_goal"


class ColonyStatus(str, Enum):
    """Colony lifecycle state machine."""

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED_BUDGET_EXHAUSTED = "halted_budget_exhausted"
    QUEUED_PENDING_COMPUTE = "queued_pending_compute"


class ModelBackendType(str, Enum):
    """Supported LLM backend protocols."""

    LLAMA_CPP = "llama_cpp"
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"
    ANTHROPIC_API = "anthropic_api"


class SubcasteTier(str, Enum):
    """Model inference tier -- decouples role from resource allocation."""

    HEAVY = "heavy"
    BALANCED = "balanced"
    LIGHT = "light"


class SkillTier(str, Enum):
    """Skill classification tier within the SkillBank."""

    GENERAL = "general"
    TASK_SPECIFIC = "task_specific"
    LESSON = "lesson"


# ── Agent Models ─────────────────────────────────────────────────────────


class AgentState(BaseModel):
    """Runtime state of a single agent within the colony."""

    schema_version: str = "0.6.0"
    agent_id: str
    caste: str
    status: AgentStatus = AgentStatus.IDLE
    model_id: str | None = None
    subcaste_tier: SubcasteTier | None = None
    team_id: str | None = None

    @field_validator("agent_id")
    @classmethod
    def agent_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("agent_id must not be empty or blank")
        return v

    @field_validator("caste")
    @classmethod
    def caste_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class AgentConfig(BaseModel):
    """Per-agent configuration within a colony."""

    schema_version: str = "0.6.0"
    agent_id: str
    caste: str
    model_override: str | None = None
    subcaste_tier: SubcasteTier | None = None
    tools: list[str] = Field(default_factory=list)

    @field_validator("agent_id")
    @classmethod
    def agent_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("agent_id must not be empty or blank")
        return v

    @field_validator("caste")
    @classmethod
    def caste_lowercase(cls, v: str) -> str:
        return v.strip().lower()


# ── Caste Configuration ─────────────────────────────────────────────────


class CasteConfig(BaseModel):
    """Configuration for a single caste (from castes section of formicos.yaml)."""

    system_prompt_file: str
    tools: list[str] = Field(default_factory=list)
    mcp_tools: list[str] = Field(default_factory=list)
    model_override: str | None = None
    subcaste_overrides: dict[str, SubcasteMapEntry] = Field(default_factory=dict)
    description: str = ""


# ── Topology ─────────────────────────────────────────────────────────────


class TopologyEdge(BaseModel):
    """A directed edge in the DyTopo routing graph."""

    schema_version: str = "0.6.0"
    sender: str
    receiver: str
    weight: float

    @field_validator("weight")
    @classmethod
    def weight_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("weight must be non-negative")
        return v


class Topology(BaseModel):
    """Current routing topology for a round."""

    schema_version: str = "0.6.0"
    edges: list[TopologyEdge] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    density: float = 0.0
    isolated_agents: list[str] = Field(default_factory=list)

    @field_validator("density")
    @classmethod
    def density_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("density must be between 0.0 and 1.0")
        return v


# ── Episodic Memory ─────────────────────────────────────────────────────


class Episode(BaseModel):
    """A discrete memory episode from a completed round."""

    schema_version: str = "0.6.0"
    round_num: int
    summary: str
    goal: str
    agent_outputs: dict[str, str] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

    @field_validator("round_num")
    @classmethod
    def round_num_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("round_num must be non-negative")
        return v


class EpochSummary(BaseModel):
    """Compressed summary of N rounds (an epoch)."""

    schema_version: str = "0.6.0"
    epoch_id: int
    summary: str
    round_range: tuple[int, int]
    timestamp: float = Field(default_factory=time.time)

    @model_validator(mode="after")
    def round_range_ordered(self) -> EpochSummary:
        start, end = self.round_range
        if start > end:
            raise ValueError(
                f"round_range start ({start}) must be <= end ({end})"
            )
        if start < 0:
            raise ValueError("round_range start must be non-negative")
        return self


# ── Temporal Knowledge Graph ─────────────────────────────────────────────


class TKGTuple(BaseModel):
    """A fact + timestamp tuple for the Temporal Knowledge Graph."""

    schema_version: str = "0.6.0"
    subject: str
    predicate: str
    object_: str
    round_num: int
    timestamp: float = Field(default_factory=time.time)
    team_id: str | None = None

    @field_validator("round_num")
    @classmethod
    def round_num_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("round_num must be non-negative")
        return v


# ── Decisions ────────────────────────────────────────────────────────────


class GovernanceRecommendation(BaseModel):
    """Structured recommendation from the governance engine (v0.7.3+)."""

    action: str  # e.g. "inject_agent", "escalate", "redelegate", "force_halt"
    affected_agents: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: str = ""


class Decision(BaseModel):
    """A recorded governance decision in the colony's history."""

    schema_version: str = "0.6.0"
    round_num: int
    decision_type: DecisionType
    detail: str
    timestamp: float = Field(default_factory=time.time)
    recommendations: list[str] = Field(default_factory=list)
    enriched_recommendations: list[GovernanceRecommendation] = Field(
        default_factory=list
    )

    @field_validator("round_num")
    @classmethod
    def round_num_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("round_num must be non-negative")
        return v


# ── Round Record ─────────────────────────────────────────────────────────


class RoundRecord(BaseModel):
    """Full record of one orchestration round."""

    schema_version: str = "0.6.0"
    round_num: int
    goal: str
    agent_outputs: dict[str, str] = Field(default_factory=dict)
    topology: Topology | None = None
    episode: Episode | None = None
    decisions: list[Decision] = Field(default_factory=list)

    @field_validator("round_num")
    @classmethod
    def round_num_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("round_num must be non-negative")
        return v


# ── Session Result ───────────────────────────────────────────────────────


class SessionResult(BaseModel):
    """Summary of a completed colony run."""

    schema_version: str = "0.6.0"
    session_id: str
    task: str
    status: ColonyStatus
    rounds_completed: int
    final_answer: str | None = None
    skill_ids: list[str] = Field(default_factory=list)

    @field_validator("rounds_completed")
    @classmethod
    def rounds_completed_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("rounds_completed must be non-negative")
        return v


# ── Tools Scope ──────────────────────────────────────────────────────────


class ToolsScope(BaseModel):
    """Per-colony tool availability filter."""

    builtin: list[str] = Field(default_factory=list)
    mcp: list[str] = Field(default_factory=list)


# ── Team Configuration ───────────────────────────────────────────────────


class TeamConfig(BaseModel):
    """A team within a colony -- a focused group of agents with a shared sub-objective."""

    schema_version: str = "0.6.0"
    team_id: str
    name: str
    objective: str
    members: list[str] = Field(default_factory=list)
    max_members: int = Field(default=5, ge=1)

    @field_validator("team_id")
    @classmethod
    def team_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("team_id must not be empty or blank")
        return v


# ── Colony Configuration ─────────────────────────────────────────────────


class BudgetConstraints(BaseModel):
    """Optional colony spending limits (v0.7.3+)."""

    max_epochs: int | None = None
    max_total_tokens: int | None = None
    max_usd_cents: int | None = None  # deferred to v0.8.0 (needs price matrix)


class VotingNodeConfig(BaseModel):
    """Configuration for a voting parallelism node (v0.8.0).

    When a DyTopo node is marked as a voting node, the orchestrator spawns
    N replicas of the same caste that solve the task independently.  A
    designated reviewer node collects all outputs, validates them (e.g.
    via pytest), and selects the best.

    Workspace isolation: each replica gets a subdirectory under the colony
    workspace: ``workspace/{colony_id}/_voting/{node_id}/{replica_index}/``
    """

    node_id: str
    caste: str = "coder"
    replicas: int = Field(default=3, ge=2, le=7)
    reviewer_agent_id: str
    workspace_strategy: str = "subdirectory"  # "subdirectory" | "git_worktree"
    test_command: str | None = None  # e.g. "pytest -x"
    merge_strategy: str = "reviewer_pick"  # "reviewer_pick" | "first_passing"

    @field_validator("node_id")
    @classmethod
    def node_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("node_id must not be empty")
        return v


class VotingGroupResult(BaseModel):
    """Result of a voting group execution (v0.8.0)."""

    node_id: str
    replica_outputs: dict[str, str] = Field(default_factory=dict)
    test_results: dict[str, str] = Field(default_factory=dict)
    selected_replica: str | None = None
    reviewer_rationale: str = ""


class ColonyConfig(BaseModel):
    """Full configuration for a colony."""

    schema_version: str = "0.6.0"
    colony_id: str
    task: str
    agents: list[AgentConfig] = Field(default_factory=list)
    max_rounds: int = Field(default=10, ge=1, le=100)
    routing_tau: float = Field(default=0.35, ge=0.0, le=1.0)
    routing_k_in: int = Field(default=3, ge=1)
    teams: list[TeamConfig] | None = None
    manager: AgentConfig | None = None
    tools_scope: ToolsScope | None = None
    skill_scope: list[str] | None = None
    max_agents: int = Field(default=10, ge=1)
    budget_constraints: BudgetConstraints | None = None
    webhook_url: str | None = None
    is_test_flight: bool = False  # v0.7.8: deterministic test harness
    voting_nodes: list[VotingNodeConfig] = Field(default_factory=list)  # v0.8.0

    @field_validator("colony_id")
    @classmethod
    def colony_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("colony_id must not be empty or blank")
        return v


# ── Model Registry ───────────────────────────────────────────────────────


class ModelRegistryEntry(BaseModel):
    """A registered LLM backend from the model_registry section of formicos.yaml."""

    schema_version: str = "0.6.0"
    model_id: str = ""
    type: str = "autoregressive"
    backend: ModelBackendType
    endpoint: str | None = None
    model_string: str | None = None
    context_length: int = Field(default=32768, ge=1)
    vram_gb: float | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    requires_approval: bool = False


# ── Skill Bank ───────────────────────────────────────────────────────────


class Skill(BaseModel):
    """A single distilled skill in the SkillBank."""

    schema_version: str = "0.6.0"
    skill_id: str
    content: str
    tier: SkillTier
    category: str | None = None
    embedding: list[float] | None = None
    retrieval_count: int = Field(default=0, ge=0)
    success_correlation: float = Field(default=0.0, ge=0.0, le=1.0)
    source_colony: str | None = None
    author_client_id: str | None = None  # v0.7.7: API-installed skill attribution
    created_at: float = Field(default_factory=time.time)
    superseded_by: str | None = None


# ── Feedback Record ──────────────────────────────────────────────────────


class FeedbackRecord(BaseModel):
    """Structured feedback from Manager to a worker agent."""

    schema_version: str = "0.6.0"
    agent_id: str
    round_num: int
    feedback_text: str
    timestamp: float = Field(default_factory=time.time)

    @field_validator("round_num")
    @classmethod
    def round_num_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("round_num must be non-negative")
        return v


# ── Approval Gate Models ─────────────────────────────────────────────────


class PendingApproval(BaseModel):
    """A pending approval request awaiting human decision."""

    schema_version: str = "0.6.0"
    request_id: str
    agent_id: str
    tool: str
    arguments: dict[str, str] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("request_id")
    @classmethod
    def request_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("request_id must not be empty or blank")
        return v


class ApprovalRecord(BaseModel):
    """A resolved approval decision for the audit trail."""

    schema_version: str = "0.6.0"
    request_id: str
    tool: str
    approved: bool
    responded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_seconds: float = Field(ge=0.0)

    @field_validator("request_id")
    @classmethod
    def request_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("request_id must not be empty or blank")
        return v


# ── Subcaste Map ─────────────────────────────────────────────────────────


class SubcasteMapEntry(BaseModel):
    """Maps a subcaste tier to one or more model registry entries."""

    primary: str
    refine_with: str | None = None
    refine_prompt: str | None = None


# ── Caste Recipes (Configuration as Code) ────────────────────────────────


# Known builtin tool names — kept in sync with agents.py _BUILTIN_TOOL_SCHEMAS.
_KNOWN_BUILTIN_TOOLS: frozenset[str] = frozenset({
    "file_read", "file_write", "file_delete",
    "code_execute", "qdrant_search", "fetch", "web_search",
    "expense_review", "expense_approve", "expense_reject",
})


class EscalationStep(BaseModel):
    """One step in a caste's escalation fallback chain."""

    model_id: str
    requires_approval: bool = True

    @field_validator("model_id")
    @classmethod
    def model_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model_id must not be empty")
        return v.strip()


class GovernanceTriggers(BaseModel):
    """Per-caste governance threshold overrides.  ``None`` = use global default."""

    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rounds_before_force_halt: int | None = Field(default=None, ge=1)
    path_diversity_warning_after: int | None = Field(default=None, ge=1)
    stall_repeat_threshold: int | None = Field(default=None, ge=1)
    stall_window_minutes: int | None = Field(default=None, ge=1)


class CasteRecipe(BaseModel):
    """Extended caste specification loaded from ``caste_recipes.yaml``.

    Every field is optional.  When a recipe exists for a caste name,
    non-``None`` fields override the base :class:`CasteConfig` from
    ``formicos.yaml``.
    """

    # ── Fields that overlay CasteConfig ──────────────────────────────
    system_prompt_file: str | None = None
    description: str | None = None
    tools: list[str] | None = None
    mcp_tools: list[str] | None = None
    model_override: str | None = None
    subcaste_overrides: dict[str, SubcasteMapEntry] | None = None

    # ── Recipe-only fields ───────────────────────────────────────────
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    context_window: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    escalation_fallback: list[EscalationStep] | None = None
    governance_triggers: GovernanceTriggers | None = None

    @field_validator("tools")
    @classmethod
    def validate_builtin_tools(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for name in v:
            if name not in _KNOWN_BUILTIN_TOOLS:
                raise ValueError(
                    f"Unknown builtin tool '{name}'. "
                    f"Valid: {sorted(_KNOWN_BUILTIN_TOOLS)}"
                )
        return v

    @field_validator("mcp_tools")
    @classmethod
    def validate_mcp_tools(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for name in v:
            # MCP tool names follow server_tool format (underscore separator).
            # Empty strings in a list (e.g. mcp_tools: []) are allowed.
            if name and "_" not in name:
                raise ValueError(
                    f"MCP tool '{name}' missing underscore separator. "
                    f"Expected format: 'server_tool'."
                )
        return v

    @field_validator("escalation_fallback")
    @classmethod
    def escalation_max_3(
        cls, v: list[EscalationStep] | None,
    ) -> list[EscalationStep] | None:
        if v is not None and len(v) > 3:
            raise ValueError(
                f"Escalation chain too long ({len(v)}). Maximum 3 fallback steps."
            )
        return v


class CasteRecipesFile(BaseModel):
    """Top-level schema for ``caste_recipes.yaml``."""

    schema_version: str = "0.9.0"
    recipes: dict[str, CasteRecipe] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
# FormicOSConfig -- top-level config mapping to formicos.yaml
# ═══════════════════════════════════════════════════════════════════════════


class IdentityConfig(BaseModel):
    """System identity metadata."""

    name: str = "FormicOS"
    version: str = "0.6.0"


class HardwareConfig(BaseModel):
    """Hardware resource declarations."""

    gpu: str = "rtx5090"
    vram_gb: float = 32.0
    vram_alert_threshold_gb: float = 28.0


class InferenceConfig(BaseModel):
    """Primary LLM inference settings."""

    endpoint: str = "http://llm:8080/v1"
    model: str = "Qwen3-30B-A3B"
    model_alias: str = "gpt-4"
    max_tokens_per_agent: int = Field(default=5000, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=120, ge=1)
    context_size: int = Field(default=131072, ge=1)
    intent_model: str | None = None
    intent_max_tokens: int = Field(default=512, ge=1)


class EmbeddingConfig(BaseModel):
    """Embedding model settings."""

    model: str = "BAAI/bge-m3"
    endpoint: str = "http://embedding:8080/v1"
    dimensions: int = Field(default=1024, ge=1)
    max_tokens: int = Field(default=8192, ge=1)
    batch_size: int = Field(default=32, ge=1)
    routing_model: str = "all-MiniLM-L6-v2"


class RoutingConfig(BaseModel):
    """DyTopo routing thresholds."""

    tau: float = Field(default=0.35, ge=0.0, le=1.0)
    k_in: int = Field(default=3, ge=1)
    broadcast_fallback: bool = True


class ConvergenceConfig(BaseModel):
    """Convergence detection settings."""

    similarity_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    rounds_before_force_halt: int = Field(default=2, ge=1)
    path_diversity_warning_after: int = Field(default=3, ge=1)


class SummarizationConfig(BaseModel):
    """Hierarchical summarization settings."""

    epoch_window: int = Field(default=5, ge=1)
    max_epoch_tokens: int = Field(default=400, ge=1)
    max_agent_summary_tokens: int = Field(default=200, ge=1)
    tree_sitter_languages: list[str] = Field(
        default_factory=lambda: ["python"]
    )


class TemporalConfig(BaseModel):
    """Temporal context management settings."""

    episodic_ttl_hours: int = Field(default=72, ge=1)
    stall_repeat_threshold: int = Field(default=3, ge=1)
    stall_window_minutes: int = Field(default=20, ge=1)
    tkg_max_tuples: int = Field(default=5000, ge=1)


class CloudBurstConfig(BaseModel):
    """Cloud burst (escalation) configuration."""

    enabled: bool = False
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    trigger: str = "2 consecutive test failures"
    requires_approval: bool = True


class PersistenceConfig(BaseModel):
    """Session persistence settings."""

    session_dir: str = ".formicos/sessions"
    autosave_interval_seconds: int = Field(default=30, ge=1)


class QdrantCollectionConfig(BaseModel):
    """A single Qdrant collection definition."""

    embedding: str
    dimensions: int = Field(ge=1)


class QdrantConfig(BaseModel):
    """Qdrant vector database connection settings."""

    host: str = "qdrant"
    port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    collections: dict[str, QdrantCollectionConfig] = Field(default_factory=dict)


class MCPGatewayConfig(BaseModel):
    """MCP Gateway transport and fallback settings."""

    enabled: bool = True
    transport: str = "stdio"
    command: str = "docker"
    args: list[str] = Field(default_factory=lambda: ["mcp", "gateway", "run"])
    docker_fallback_endpoint: str = "http://mcp-gateway:8811"
    sse_retry_attempts: int = Field(default=5, ge=0)
    sse_retry_delay_seconds: int = Field(default=3, ge=0)


class SkillBankConfig(BaseModel):
    """SkillBank persistence and retrieval settings."""

    storage_file: str = ".formicos/skill_bank.json"
    retrieval_top_k: int = Field(default=3, ge=1)
    dedup_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    evolution_interval: int = Field(default=5, ge=1)
    prune_zero_hit_after: int = Field(default=10, ge=1)


class TeamsConfig(BaseModel):
    """Global teams settings."""

    max_teams_per_colony: int = Field(default=4, ge=1)
    team_summary_max_tokens: int = Field(default=200, ge=1)
    allow_dynamic_spawn: bool = True


# ── Top-level Config ─────────────────────────────────────────────────────


class FormicOSConfig(BaseModel):
    """
    Top-level configuration model, mapping 1:1 with formicos.yaml.

    Use load_config() to construct from a YAML file.
    """

    schema_version: str = "1.0"
    identity: IdentityConfig
    hardware: HardwareConfig
    inference: InferenceConfig
    embedding: EmbeddingConfig
    routing: RoutingConfig
    convergence: ConvergenceConfig
    summarization: SummarizationConfig
    temporal: TemporalConfig
    castes: dict[str, CasteConfig]
    cloud_burst: CloudBurstConfig | None = None
    persistence: PersistenceConfig
    approval_required: list[str] = Field(default_factory=list)
    qdrant: QdrantConfig
    mcp_gateway: MCPGatewayConfig
    model_registry: dict[str, ModelRegistryEntry]
    skill_bank: SkillBankConfig
    subcaste_map: dict[str, SubcasteMapEntry]
    teams: TeamsConfig
    colonies: dict[str, ColonyConfig] = Field(default_factory=dict)

    @field_validator("castes")
    @classmethod
    def castes_not_empty(cls, v: dict[str, CasteConfig]) -> dict[str, CasteConfig]:
        if not v:
            raise ValueError("castes must contain at least one entry")
        return v

    @field_validator("model_registry")
    @classmethod
    def model_registry_not_empty(
        cls, v: dict[str, ModelRegistryEntry]
    ) -> dict[str, ModelRegistryEntry]:
        if not v:
            raise ValueError("model_registry must contain at least one entry")
        return v


# ═════════════════════════════════════════════════════════════════════════
# v0.7.0 Contract Models
# ═════════════════════════════════════════════════════════════════════════


# ── API Error Contract ────────────────────────────────────────────────────


class ApiErrorDetail(BaseModel):
    """Inner error object for ApiErrorV1."""

    code: str
    message: str
    detail: Any | None = None
    request_id: str
    ts: str


class ApiErrorV1(BaseModel):
    """Canonical API error envelope (v0.7.0+)."""

    error: ApiErrorDetail


# ── Event Contract ────────────────────────────────────────────────────────


class EventTrace(BaseModel):
    """Tracing metadata for event correlation."""

    request_id: str | None = None
    session_id: str | None = None
    round: int | None = None


class EventEnvelopeV1(BaseModel):
    """Canonical WebSocket event envelope (v0.7.0+)."""

    event_id: str
    seq: int
    ts: str
    colony_id: str | None = None
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace: EventTrace = Field(default_factory=EventTrace)


# ── Colony State Contract ─────────────────────────────────────────────────


class WorkspaceMetaV1(BaseModel):
    """Workspace metadata attached to ColonyStateV1."""

    root: str
    artifact_count: int = 0
    last_updated_ts: str | None = None


class ArtifactRefsV1(BaseModel):
    """References to colony artifacts."""

    results_ref: str | None = None
    session_ref: str | None = None
    topology_ref: str | None = None


class AgentInfoV1(BaseModel):
    """Agent descriptor within ColonyStateV1."""

    agent_id: str
    caste: str
    model_id: str | None = None


class TeamInfoV1(BaseModel):
    """Team descriptor within ColonyStateV1."""

    team_id: str
    name: str
    members: list[str] = Field(default_factory=list)


class ColonyStateV1(BaseModel):
    """Canonical colony state (v0.7.0+)."""

    colony_id: str
    status: str
    task: str
    round: int = 0
    max_rounds: int = 10
    agents: list[AgentInfoV1] = Field(default_factory=list)
    teams: list[TeamInfoV1] = Field(default_factory=list)
    workspace: WorkspaceMetaV1
    artifacts: ArtifactRefsV1 = Field(default_factory=ArtifactRefsV1)
    created_ts: str
    updated_ts: str
    origin: str = "ui"
    client_id: str | None = None


# ── Result Contract ───────────────────────────────────────────────────────


class FailureInfoV1(BaseModel):
    """Failure details for ColonyResultV1."""

    code: str | None = None
    detail: str | None = None


class ColonyResultV1(BaseModel):
    """Canonical colony result (v0.7.0+)."""

    colony_id: str
    status: str
    final_answer: str | None = None
    summary: str | None = None
    files: list[str] = Field(default_factory=list)
    session_ref: str | None = None
    completed_ts: str | None = None
    failure: FailureInfoV1 = Field(default_factory=FailureInfoV1)


# ── Tool Contract ─────────────────────────────────────────────────────────


class ToolApprovalPolicy(BaseModel):
    """Approval policy for a tool."""

    mode: str = "auto"
    policy_id: str | None = None
    timeout_seconds: int = 300


class ToolRetryPolicy(BaseModel):
    """Retry policy for a tool."""

    max_attempts: int = 2
    backoff: str = "exponential"


class ToolSpecV1(BaseModel):
    """Canonical tool specification (v0.7.0+)."""

    id: str
    source: str
    schema_def: dict[str, Any] = Field(default_factory=dict, alias="schema")
    approval_policy: ToolApprovalPolicy = Field(
        default_factory=ToolApprovalPolicy
    )
    timeout: int = 30
    retry_policy: ToolRetryPolicy = Field(default_factory=ToolRetryPolicy)
    enabled: bool = True

    model_config = {"populate_by_name": True}


# ── Skill Contract ────────────────────────────────────────────────────────


class SkillMetadataV1(BaseModel):
    """Metadata block for SkillV1."""

    source_colony: str | None = None
    retrieval_count: int = 0
    success_correlation: float = 0.0
    created_ts: str | None = None
    updated_ts: str | None = None


class SkillV1(BaseModel):
    """Canonical skill shape (v0.7.0+)."""

    skill_id: str
    content: str
    tier: str
    category: str | None = None
    metadata: SkillMetadataV1 = Field(default_factory=SkillMetadataV1)


# ── Session / Persistence Contracts ───────────────────────────────────────


class SnapshotMetadataV1(BaseModel):
    """Metadata for a session snapshot."""

    schema_version: str = "1.0"
    saved_ts: str
    save_reason: str = "autosave"


class SessionSnapshotV1(BaseModel):
    """Canonical session snapshot (v0.7.0+)."""

    session_id: str
    colony_id: str
    state: dict[str, Any] = Field(default_factory=dict)
    topology_history: list[dict[str, Any]] = Field(default_factory=list)
    episodes: list[dict[str, Any]] = Field(default_factory=list)
    tkg: list[dict[str, Any]] = Field(default_factory=list)
    metadata: SnapshotMetadataV1


class RecoveryReportV1(BaseModel):
    """Report emitted after session recovery."""

    recovery_mode: str
    success: bool
    warnings: list[str] = Field(default_factory=list)
    restored_round: int | None = None
    restored_agents: list[str] = Field(default_factory=list)


# ── Runtime Wiring Contract ───────────────────────────────────────────────


class RuntimeWiringContract(BaseModel):
    """Checked before colony start — fail-fast if mandatory deps missing."""

    model_registry: bool = False
    archivist: bool = False
    governance: bool = False
    skill_bank: bool = False
    audit_logger: bool = False
    approval_gate: bool = False
    rag_engine: bool = False  # optional, can be False

    def validate_mandatory(self) -> list[str]:
        """Return names of missing mandatory dependencies."""
        mandatory = (
            "model_registry",
            "archivist",
            "governance",
            "skill_bank",
            "audit_logger",
            "approval_gate",
        )
        return [f for f in mandatory if not getattr(self, f)]


# ═════════════════════════════════════════════════════════════════════════
# v0.7.3 Contract Models
# ═════════════════════════════════════════════════════════════════════════


# ── RFC 7807 Problem Details ────────────────────────────────────────────


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP API errors (v0.7.3+).

    Extends standard RFC 7807 with ``suggested_fix`` — an LLM-friendly hint
    that tells callers how to correct the request.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    suggested_fix: str | None = None
    error_code: str | None = None  # backward compat with ApiErrorV1.error.code


# ── Headless Colony Models (schema forward-compat for v0.8.0) ───────────


class DocumentInject(BaseModel):
    """A document to inject into RAG context (v0.7.3 schema, v0.8.0 logic)."""

    filename: str
    content: str
    mime_type: str = "text/plain"


class ModelOverride(BaseModel):
    """Per-role model override (v0.7.3 schema, v0.8.0 logic)."""

    provider: str
    model_name: str
    temperature: float | None = None
    max_tokens: int | None = None


# ── Telemetry Models ────────────────────────────────────────────────────


class RoundMetrics(BaseModel):
    """Per-round telemetry snapshot (v0.7.3+)."""

    round_num: int
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tool_calls_count: int = 0
    agent_activity: dict[str, int] = Field(default_factory=dict)
    caste_activity: dict[str, int] = Field(default_factory=dict)
    duration_ms: float = 0.0


class ColonyMetrics(BaseModel):
    """Aggregate colony telemetry (v0.7.3+)."""

    colony_id: str
    total_tokens_prompt: int = 0
    total_tokens_completion: int = 0
    total_tool_calls: int = 0
    rounds: list[RoundMetrics] = Field(default_factory=list)
    caste_activity: dict[str, int] = Field(default_factory=dict)


# ── Durable Execution (v0.8.0) ────────────────────────────────────────────


class CheckpointMeta(BaseModel):
    """Durable execution checkpoint written between rounds (v0.8.0).

    Captures all ephemeral orchestrator state needed to resume a crashed
    colony from the last completed round.  Written to the context tree's
    ``colony`` scope as ``checkpoint`` after each round completes.
    """

    schema_version: str = "0.9.0"
    colony_id: str
    session_id: str
    completed_round: int  # last fully completed round number
    max_rounds: int  # current max (may have been extended)
    task: str
    timestamp: float = Field(default_factory=time.time)
    round_history: list[dict[str, Any]] = Field(default_factory=list)
    pheromone_weights: dict[str, float] = Field(
        default_factory=dict,
    )  # "sender|receiver" string keys (JSON compat)
    convergence_streak: int = 0
    prev_summary_vec: list[float] | None = None


class ResumeDirective(BaseModel):
    """Instructions for resuming a colony from a checkpoint (v0.8.0).

    Built from a ``CheckpointMeta`` and passed to the Orchestrator
    constructor to restore ephemeral state before the run() loop resumes.
    """

    colony_id: str
    resume_from_round: int  # completed_round + 1
    max_rounds: int
    session_id: str
    round_history: list[dict[str, Any]] = Field(default_factory=list)
    pheromone_weights: dict[str, float] = Field(default_factory=dict)
    convergence_streak: int = 0
    prev_summary_vec: list[float] | None = None


# ── Timeline & Janitor Models (v0.7.7) ───────────────────────────────────


class TimelineSpan(BaseModel):
    """A single span in the colony execution timeline (v0.7.7)."""

    span_id: str
    round_num: int
    agent_id: str | None = None
    agent_role: str | None = None
    activity_type: str  # "inference", "tool_execution", "routing", "governance", "goal_setting"
    start_ms: float
    duration_ms: float
    is_critical_path: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConvergenceMetrics(BaseModel):
    """Convergence evaluation result from the Janitor Protocol (v0.7.7)."""

    round_num: int
    wall_clock_ms: float
    qa_score: float = 0.0
    baseline_ms: float = 45000.0
    penalty_applied: float = 0.0
    reward_applied: float = 0.0
    route_adjustments: list[dict[str, Any]] = Field(default_factory=list)


# ── Request / Response Models (moved from server.py in v0.7.9) ──────────


class RunAgentSpec(BaseModel):
    """Agent specification in a RunRequest. Permissive input model."""
    caste: str = "dytopo"
    agent_id: str | None = None
    model_override: str | None = None
    subcaste_tier: str | None = None


class RunRequest(BaseModel):
    """POST /api/run body."""
    task: str = Field(..., min_length=1)
    agents: list[RunAgentSpec] | None = None
    max_rounds: int = Field(default=10, ge=1, le=100)


class ExtendRequest(BaseModel):
    """POST /api/colony/extend body."""
    colony_id: str
    rounds: int
    hint: str | None = None


class ExtendRequestV1(BaseModel):
    """POST /api/v1/colonies/{id}/extend body."""
    rounds: int
    hint: str | None = None


class ColonyReuseRequest(BaseModel):
    """POST /api/v1/colonies/{id}/reuse body."""
    task: str
    max_rounds: int | None = None
    preserve_history: bool = True
    clear_workspace: bool = False
    start_immediately: bool = True


class ApproveRequest(BaseModel):
    """POST /api/approve body."""
    request_id: str
    approved: bool


class ApproveRequestV1(BaseModel):
    """POST /api/v1/approvals/{id}/resolve body."""
    approved: bool


class InterveneRequest(BaseModel):
    """POST /api/intervene body."""
    colony_id: str | None = None
    hint: str


class SkillCreateRequest(BaseModel):
    """POST /api/skill-bank/skill body."""
    content: str
    tier: str = "general"
    category: str | None = None
    author_client_id: str | None = None  # v0.7.7: A2A consultation attribution
    colony_id: str | None = None  # v0.7.7: source colony for A2A consultation


class SkillUpdateRequest(BaseModel):
    """PUT /api/skill-bank/skill/{id} body."""
    content: str


class ErrorResponse(BaseModel):
    """Structured error envelope."""
    error_code: str
    error_detail: str
    request_id: str


class ColonyCreateRequest(BaseModel):
    """POST /api/colony/{id}/create body."""
    colony_id: str | None = None
    task: str = Field(..., min_length=1)
    agents: list[RunAgentSpec] | None = None
    max_rounds: int = Field(default=10, ge=1, le=100)
    # v0.7.3 forward-compat (accepted, budget_constraints enforced, rest deferred to v0.8.0)
    webhook_url: str | None = None
    budget_constraints: BudgetConstraints | None = None
    injected_documents: list[DocumentInject] = Field(default_factory=list)
    model_overrides: dict[str, ModelOverride] | None = None
    priority: int = Field(default=10, ge=1, le=100)
    is_test_flight: bool = False  # v0.7.8: deterministic test harness
    voting_nodes: list[VotingNodeConfig] = Field(default_factory=list)  # v0.8.0


class PromptUpdateRequest(BaseModel):
    """PUT /api/prompt/{caste} body."""
    content: str


class CasteCreateRequest(BaseModel):
    """POST /api/castes body."""
    name: str
    system_prompt: str = ""
    tools: list[str] = []
    mcp_tools: list[str] = []
    model_override: str | None = None
    subcaste_overrides: dict = {}
    description: str = ""


class CasteUpdateRequest(BaseModel):
    """PUT /api/castes/{name} body."""
    system_prompt: str | None = None
    tools: list[str] | None = None
    mcp_tools: list[str] | None = None
    model_override: str | None = None
    subcaste_overrides: dict | None = None
    description: str | None = None


class SuggestTeamRequest(BaseModel):
    """POST /api/suggest-team body."""
    task: str


# ── API Key request/response models (v0.7.4) ─────────────────────────────


class APIKeyCreateRequest(BaseModel):
    """POST /api/v1/auth/keys body."""
    client_id: str
    scopes: list[str] | None = None


class APIKeyResponse(BaseModel):
    """Response for a created API key (includes raw token ONCE)."""
    key_id: str
    client_id: str
    prefix: str
    raw_token: str
    scopes: list[str]
    created_at: str


class APIKeyListItem(BaseModel):
    """Single item in GET /api/v1/auth/keys response."""
    key_id: str
    client_id: str
    prefix: str
    status: str
    scopes: list[str]
    created_at: str
    last_used_at: str | None = None


# ── FormicOS Error Hierarchy (v0.7.3) ────────────────────────────────────


class FormicOSError(Exception):
    """Base for all FormicOS domain errors -- caught by global handler."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        suggested_fix: str | None = None,
    ):
        self.status = status
        self.code = code
        self.message = message
        self.suggested_fix = suggested_fix
        super().__init__(message)


# LLM-friendly fix hints keyed by error code.
SUGGESTED_FIXES: dict[str, str] = {
    "COLONY_NOT_FOUND": (
        "Verify colony_id via GET /api/v1/colonies. "
        "Colony may have been destroyed or never created."
    ),
    "INVALID_TRANSITION": (
        "Check colony status via GET /api/v1/colonies/{id}. "
        "Paused colonies must be resumed before other operations."
    ),
    "COLONY_CREATE_FAILED": (
        "Ensure colony_id is unique and task is non-empty. "
        "Check agent caste names match config/prompts/."
    ),
    "COLONY_DESTROY_FAILED": (
        "Colony may already be destroyed. "
        "Retry after checking GET /api/v1/colonies."
    ),
    "SESSION_NOT_FOUND": (
        "List available sessions via GET /api/sessions."
    ),
    "SANDBOX_VIOLATION": (
        "All file paths must be relative to the colony workspace root."
    ),
    "MISSING_FILENAME": (
        "Include the X-Filename header with the uploaded file name."
    ),
    "COLONY_START_FAILED": (
        "Ensure colony is in CREATED or READY state. "
        "Check model registry health via GET /api/models."
    ),
    "COLONY_PAUSE_FAILED": (
        "Colony must be in RUNNING state to pause."
    ),
    "COLONY_RESUME_FAILED": (
        "Colony must be in PAUSED state to resume."
    ),
    "COLONY_EXTEND_FAILED": (
        "Colony must be in RUNNING state to extend rounds."
    ),
    "KEY_NOT_FOUND": (
        "Verify key_id via GET /api/v1/auth/keys. "
        "Key may have already been revoked or never created."
    ),
    "INVALID_CLIENT_ID": (
        "client_id must be a non-empty string identifying the API consumer."
    ),
    "FORBIDDEN": (
        "The authenticated API key does not have access to this colony. "
        "Colonies are isolated by client_id."
    ),
    "QUEUE_COLONY_NOT_FOUND": (
        "Colony is not in the compute queue. "
        "It may have already been promoted to RUNNING or removed."
    ),
    "INGESTION_FILE_NOT_FOUND": (
        "Verify the file_path exists on the server filesystem. "
        "Paths must be absolute or relative to the server working directory."
    ),
    "INGESTION_UNSUPPORTED_FORMAT": (
        "Supported formats: .pdf, .docx, .html, .htm, .md, .txt, .pptx. "
        "Ensure the file extension matches the actual content type."
    ),
    "INGESTION_TASK_NOT_FOUND": (
        "Verify task_id via GET /api/v1/ingestion/tasks. "
        "Old tasks are evicted after 100 entries."
    ),
}


# ── Config Loader ────────────────────────────────────────────────────────


def load_config(path: str | Path | None = None) -> FormicOSConfig:
    """Load and validate formicos.yaml.

    Resolution order:
      1. Explicit ``path`` argument
      2. ``FORMICOS_CONFIG`` environment variable
      3. ``formicos/config/formicos.yaml`` (relative to cwd)

    Raises:
        FileNotFoundError: If no config file is found.
        pydantic.ValidationError: If the YAML content is invalid.
    """
    if path is None:
        env_path = os.environ.get("FORMICOS_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            path = Path("formicos/config/formicos.yaml")

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError("Config file is empty")

    # Rename top-level 'cloud_burst' from YAML key if present
    # (YAML uses snake_case which matches Python field names)
    return FormicOSConfig.model_validate(raw)


def load_caste_recipes(path: str | Path | None = None) -> dict[str, CasteRecipe]:
    """Load and validate ``caste_recipes.yaml``.

    Resolution order:
      1. Explicit ``path`` argument
      2. ``FORMICOS_CASTE_RECIPES`` environment variable
      3. ``config/caste_recipes.yaml`` (relative to cwd)

    Returns an empty dict if the file does not exist (recipes are opt-in).
    """
    if path is None:
        env_path = os.environ.get("FORMICOS_CASTE_RECIPES")
        if env_path:
            path = Path(env_path)
        else:
            path = Path("config/caste_recipes.yaml")

    config_path = Path(path)
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        return {}

    return CasteRecipesFile.model_validate(raw).recipes


def merge_recipe_into_caste_config(
    base: CasteConfig,
    recipe: CasteRecipe,
) -> CasteConfig:
    """Create a new :class:`CasteConfig` by overlaying recipe overrides.

    Only CasteConfig-compatible fields are merged here.  Recipe-only fields
    (``temperature``, ``context_window``, ``max_tokens``,
    ``escalation_fallback``, ``governance_triggers``) are consumed separately
    by :class:`AgentFactory` and :class:`GovernanceEngine`.
    """
    data = base.model_dump()
    for field in ("system_prompt_file", "description", "tools", "mcp_tools", "model_override"):
        val = getattr(recipe, field)
        if val is not None:
            data[field] = val
    if recipe.subcaste_overrides is not None:
        data["subcaste_overrides"] = {
            k: v.model_dump() for k, v in recipe.subcaste_overrides.items()
        }
    return CasteConfig.model_validate(data)


# ── v0.7.9 Response Models (Pydantic Hardening) ────────────────────────


class HardwareState(BaseModel):
    """Hardware state snapshot for diagnostics."""
    free_vram_mb: int = 0


class DiagnosticsPayload(BaseModel):
    """Structured diagnostics payload for Cloud Model debugging.
    Replaces raw dict return from colony_manager.get_diagnostics().
    """
    colony_id: str
    status: str
    round: int = 0
    max_rounds: int = 0
    created_at: float = 0.0
    origin: str = "ui"
    client_id: str | None = None
    hardware_state: HardwareState = Field(default_factory=HardwareState)
    error_traceback: str | None = None
    last_decisions: list[dict] = Field(default_factory=list)
    last_episodes: list[dict] = Field(default_factory=list)
    epoch_summaries: list[dict] = Field(default_factory=list)
    timeline_spans: list[dict] = Field(default_factory=list)
    ws_connections: int = 0


class ColonyFleetItem(BaseModel):
    """Single colony item in fleet listing. Replaces _safe_serialize(info)."""
    colony_id: str
    task: str
    status: str
    round: int = 0
    max_rounds: int = 10
    origin: str = "ui"
    client_id: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
