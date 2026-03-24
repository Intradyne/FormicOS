"""Event-driven read-model projections (ADR-001).

Processes FormicOS events into in-memory state used by view_state, WS handler,
and MCP tools. Single source of derived truth — no shadow stores.
"""
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any

import structlog

from formicos.core.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    CodeExecuted,
    ColonyChatMessage,
    ColonyCompleted,
    ColonyFailed,
    ColonyKilled,
    ColonyNamed,
    ColonyRedirected,
    ColonyServiceActivated,
    ColonySpawned,
    ColonyTemplateCreated,
    ColonyTemplateUsed,
    ConfigSuggestionOverridden,
    CRDTCounterIncremented,
    CRDTRegisterAssigned,
    CRDTSetElementAdded,
    CRDTTimestampUpdated,
    DomainStrategyUpdated,
    ForageCycleCompleted,
    ForagerDomainOverride,
    ForageRequested,
    FormicOSEvent,
    KnowledgeAccessRecorded,
    KnowledgeDistilled,
    KnowledgeEdgeCreated,
    KnowledgeEntityCreated,
    KnowledgeEntityMerged,
    KnowledgeEntryAnnotated,
    KnowledgeEntryOperatorAction,
    MemoryConfidenceUpdated,
    MemoryEntryCreated,
    MemoryEntryMerged,
    MemoryEntryScopeChanged,
    MemoryEntryStatusChanged,
    MemoryExtractionCompleted,
    MergeCreated,
    MergePruned,
    ModelAssignmentChanged,
    ModelRegistered,
    PhaseEntered,
    QueenMessage,
    RoundCompleted,
    RoundStarted,
    ServiceQueryResolved,
    ServiceQuerySent,
    SkillConfidenceUpdated,
    SkillMerged,
    ThreadCreated,
    ThreadGoalSet,
    ThreadRenamed,
    ThreadStatusChanged,
    TokensConsumed,
    WorkflowStepCompleted,
    WorkflowStepDefined,
    WorkspaceConfigChanged,
    WorkspaceCreated,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Projection data structures (mutable in-memory read models)
# ---------------------------------------------------------------------------


@dataclass
class ColonyOutcome:
    """Replay-derived outcome summary for a completed colony (Wave 35.5 C3).

    Computed silently from existing events. No new event types.
    Internal foundation for future outcome analysis (Wave 36+).
    """

    colony_id: str
    workspace_id: str
    thread_id: str
    succeeded: bool
    total_rounds: int
    total_cost: float
    duration_ms: int
    entries_extracted: int
    entries_accessed: int
    quality_score: float
    caste_composition: list[str]
    strategy: str
    maintenance_source: str | None = None
    # Wave 38 2B: escalation outcome matrix fields
    escalated: bool = False
    starting_tier: str | None = None  # tier before routing_override
    escalated_tier: str | None = None  # tier from routing_override
    escalation_reason: str | None = None
    escalation_round: int | None = None  # round when override was set
    pre_escalation_cost: float = 0.0  # cost accumulated before escalation
    # Wave 39 1B: task-type validator outcome
    validator_verdict: str | None = None  # pass | fail | inconclusive
    validator_task_type: str | None = None


# ---------------------------------------------------------------------------
# Operator behavior projection (Wave 37, Pillar 4B)
# ---------------------------------------------------------------------------


@dataclass
class OperatorFeedbackRecord:
    """A single operator feedback signal derived from existing events."""

    entry_id: str
    workspace_id: str
    colony_id: str
    direction: str  # "positive" | "negative"
    timestamp: str


@dataclass
class OperatorKillRecord:
    """Operator-initiated colony kill."""

    colony_id: str
    workspace_id: str
    killed_by: str
    strategy: str
    round_at_kill: int
    timestamp: str


@dataclass
class OperatorDirectiveRecord:
    """Directive sent by operator to a running colony."""

    colony_id: str
    workspace_id: str
    directive_type: str  # context_update | priority_shift | constraint_add | strategy_change
    timestamp: str


@dataclass
class SuggestionFollowThrough:
    """Inferred suggestion acceptance: colony spawned matching a briefing suggestion."""

    insight_category: str  # contradiction | coverage | staleness
    colony_id: str
    workspace_id: str
    timestamp: str


@dataclass
class OperatorBehaviorProjection:
    """Replay-derived operator behavior signals (Wave 37, Pillar 4B).

    Collects operator actions from existing events. No new event types.
    Designed to answer: which categories does this operator act on,
    which are usually ignored, and which directive patterns are sent.

    Honesty constraint: accepted suggestions are INFERRED from matching
    colony spawns. Rejected suggestions are NOT tracked — the current
    event surface does not support exact rejection tracking.
    """

    feedback_records: list[OperatorFeedbackRecord] = field(default_factory=list)
    kill_records: list[OperatorKillRecord] = field(default_factory=list)
    directive_records: list[OperatorDirectiveRecord] = field(default_factory=list)
    suggestion_follow_throughs: list[SuggestionFollowThrough] = field(
        default_factory=list,
    )

    # Aggregate counters by domain/category for quick queries
    feedback_by_domain: dict[str, dict[str, int]] = field(default_factory=dict)
    # domain -> {"positive": N, "negative": N}
    kills_by_strategy: dict[str, int] = field(default_factory=dict)
    directives_by_type: dict[str, int] = field(default_factory=dict)
    suggestion_categories_acted_on: dict[str, int] = field(default_factory=dict)

    def record_feedback(
        self,
        entry_id: str,
        workspace_id: str,
        colony_id: str,
        direction: str,
        timestamp: str,
        domains: list[str],
    ) -> None:
        """Record a feedback signal and update domain aggregates."""
        self.feedback_records.append(OperatorFeedbackRecord(
            entry_id=entry_id,
            workspace_id=workspace_id,
            colony_id=colony_id,
            direction=direction,
            timestamp=timestamp,
        ))
        for domain in domains:
            bucket = self.feedback_by_domain.setdefault(
                domain, {"positive": 0, "negative": 0},
            )
            bucket[direction] = bucket.get(direction, 0) + 1

    def record_kill(
        self,
        colony_id: str,
        workspace_id: str,
        killed_by: str,
        strategy: str,
        round_at_kill: int,
        timestamp: str,
    ) -> None:
        """Record a colony kill event."""
        self.kill_records.append(OperatorKillRecord(
            colony_id=colony_id,
            workspace_id=workspace_id,
            killed_by=killed_by,
            strategy=strategy,
            round_at_kill=round_at_kill,
            timestamp=timestamp,
        ))
        self.kills_by_strategy[strategy] = (
            self.kills_by_strategy.get(strategy, 0) + 1
        )

    def record_directive(
        self,
        colony_id: str,
        workspace_id: str,
        directive_type: str,
        timestamp: str,
    ) -> None:
        """Record a directive usage pattern."""
        self.directive_records.append(OperatorDirectiveRecord(
            colony_id=colony_id,
            workspace_id=workspace_id,
            directive_type=directive_type,
            timestamp=timestamp,
        ))
        self.directives_by_type[directive_type] = (
            self.directives_by_type.get(directive_type, 0) + 1
        )

    def record_suggestion_follow_through(
        self,
        insight_category: str,
        colony_id: str,
        workspace_id: str,
        timestamp: str,
    ) -> None:
        """Record an inferred suggestion acceptance."""
        self.suggestion_follow_throughs.append(SuggestionFollowThrough(
            insight_category=insight_category,
            colony_id=colony_id,
            workspace_id=workspace_id,
            timestamp=timestamp,
        ))
        self.suggestion_categories_acted_on[insight_category] = (
            self.suggestion_categories_acted_on.get(insight_category, 0) + 1
        )

    def domain_demotion_rate(self, domain: str) -> float:
        """Fraction of negative feedback for a domain. Returns 0.0 if no data."""
        bucket = self.feedback_by_domain.get(domain)
        if not bucket:
            return 0.0
        total = bucket.get("positive", 0) + bucket.get("negative", 0)
        if total == 0:
            return 0.0
        return bucket.get("negative", 0) / total


@dataclass
class BudgetSnapshot:
    """Aggregated budget truth for a scope (workspace or colony).

    Wave 43 Pillar 3: first real budget truth surface. All fields are
    replay-derived from TokensConsumed and RoundCompleted events.
    """

    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_cache_read_tokens: int = 0
    # model → {cost, input_tokens, output_tokens, reasoning_tokens, cache_read_tokens}
    model_usage: dict[str, dict[str, float]] = field(default_factory=dict)
    # Enforcement state (runtime-only, not persisted)
    warning_issued: bool = False
    downgrade_active: bool = False

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def api_cost(self) -> float:
        """Real USD cost from cloud providers only."""
        return sum(
            v.get("cost", 0.0) for v in self.model_usage.values()
            if v.get("cost", 0.0) > 0
        )

    @property
    def local_tokens(self) -> int:
        """Total tokens processed by local models (cost == 0)."""
        return sum(
            int(v.get("input_tokens", 0) + v.get("output_tokens", 0))
            for v in self.model_usage.values()
            if v.get("cost", 0.0) == 0
        )

    def record_token_spend(
        self, model: str, input_tokens: int, output_tokens: int, cost: float,
        reasoning_tokens: int = 0, cache_read_tokens: int = 0,
    ) -> None:
        """Record a token spend from a TokensConsumed event."""
        self.total_cost += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_reasoning_tokens += reasoning_tokens
        self.total_cache_read_tokens += cache_read_tokens
        usage = self.model_usage.setdefault(model, {
            "cost": 0.0, "input_tokens": 0.0, "output_tokens": 0.0,
            "reasoning_tokens": 0.0, "cache_read_tokens": 0.0,
        })
        usage["cost"] = usage.get("cost", 0.0) + cost
        usage["input_tokens"] = usage.get("input_tokens", 0.0) + input_tokens
        usage["output_tokens"] = usage.get("output_tokens", 0.0) + output_tokens
        usage["reasoning_tokens"] = usage.get("reasoning_tokens", 0.0) + reasoning_tokens
        usage["cache_read_tokens"] = usage.get("cache_read_tokens", 0.0) + cache_read_tokens


@dataclass
class ColonyProjection:
    """Mutable read model for a single colony."""

    id: str
    thread_id: str
    workspace_id: str
    task: str
    status: str = "pending"  # pending | running | completed | failed | killed
    round_number: int = 0
    max_rounds: int = 25
    strategy: str = "stigmergic"
    castes: list[Any] = field(default_factory=list)
    model_assignments: dict[str, str] = field(default_factory=dict)
    convergence: float = 0.0
    cost: float = 0.0
    budget_limit: float = 5.0
    template_id: str = ""
    agents: dict[str, AgentProjection] = field(default_factory=dict)
    round_records: list[RoundProjection] = field(default_factory=list)
    quality_score: float = 0.0
    skills_extracted: int = 0
    display_name: str | None = None
    service_type: str | None = None
    chat_messages: list[ChatMessageProjection] = field(default_factory=list)
    kg_entity_count: int = 0
    kg_edge_count: int = 0
    pheromone_weights: dict[tuple[str, str], float] = field(default_factory=dict)
    active_goal: str = ""
    redirect_history: list[dict[str, Any]] = field(default_factory=list)
    redirect_boundaries: list[int] = field(default_factory=list)
    routing_override: dict[str, Any] | None = None
    input_sources: list[dict[str, Any]] = field(default_factory=list)
    # Artifact model (Wave 25) — accumulated live, persisted on ColonyCompleted
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    expected_output_types: list[str] = field(default_factory=list)
    # Knowledge access traces (Wave 28) — replayed from KnowledgeAccessRecorded
    knowledge_accesses: list[dict[str, Any]] = field(default_factory=list)
    # Failure metadata (C1 Wave 24) — populated from ColonyFailed / ColonyKilled events
    failure_reason: str | None = None
    failed_at_round: int | None = None
    killed_by: str | None = None
    killed_at_round: int | None = None
    # Wave 35.5 C3: outcome tracking fields
    spawned_at: str = ""
    completed_at: str = ""
    entries_extracted_count: int = 0
    # Wave 39 1B: task-type validator state (replay-derivable from round outputs)
    validator_task_type: str | None = None
    validator_verdict: str | None = None  # pass | fail | inconclusive
    validator_reason: str | None = None
    # Wave 50: spawn provenance
    spawn_source: str = ""
    # Wave 41 B2: target files for multi-file coordination
    target_files: list[str] = field(default_factory=list)
    # Wave 47: fast-path flag (replay-safe from ColonySpawned)
    fast_path: bool = False
    # Wave 43: colony-level budget truth (from TokensConsumed events)
    budget_truth: BudgetSnapshot = field(default_factory=BudgetSnapshot)
    # Wave 55: productive vs observation tool call counts (derived from AgentTurnCompleted)
    productive_calls: int = 0
    observation_calls: int = 0
    # Wave 57: governance state for eval timeout decisions
    last_governance_action: str = "continue"
    last_round_productive: bool = False
    last_round_productive_ratio: float = 0.0
    last_round_completed_at: float = 0.0
    # Wave 57+: idle watchdog — monotonic timestamp of last colony activity
    last_activity_at: float = 0.0


@dataclass
class ChatMessageProjection:
    """Single message in a colony chat."""

    sender: str  # operator | queen | system | agent | service
    content: str
    timestamp: str
    event_kind: str | None = None
    source_colony: str | None = None
    seq: int = 0


@dataclass
class AgentProjection:
    """Mutable read model for an agent within a colony."""

    id: str
    caste: str
    model: str
    status: str = "pending"  # pending | active | done | failed
    tokens: int = 0


@dataclass
class RoundProjection:
    """Read model for a round (in-progress or completed)."""

    round_number: int
    current_phase: str = "goal"
    convergence: float = 0.0
    cost: float = 0.0
    duration_ms: int = 0
    agent_outputs: dict[str, str] = field(default_factory=dict)
    tool_calls: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class MergeProjection:
    """Read model for a merge edge between colonies."""

    id: str
    from_colony: str
    to_colony: str
    created_by: str
    active: bool = True


@dataclass
class ApprovalProjection:
    """Read model for a pending approval request."""

    id: str
    approval_type: str
    detail: str
    colony_id: str


@dataclass
class TemplateProjection:
    """Read model for a colony template."""

    id: str
    name: str
    description: str
    castes: list[Any] = field(default_factory=list)
    strategy: str = "stigmergic"
    source_colony_id: str | None = None
    use_count: int = 0
    # Wave 50: learned template fields (event-carried via ColonyTemplateCreated)
    learned: bool = False
    task_category: str = ""
    max_rounds: int = 25
    budget_limit: float = 1.0
    fast_path: bool = False
    target_files_pattern: str = ""
    # Wave 50: replay-derived from colony outcomes cross-referenced via template_id
    success_count: int = 0
    failure_count: int = 0


@dataclass
class QueenMessageProjection:
    """Single message in a Queen chat thread."""

    role: str  # operator | queen
    content: str
    timestamp: str
    # Wave 49: structured metadata for conversational cards.
    intent: str | None = None  # notify | ask
    render: str | None = None  # text | preview_card | result_card
    meta: dict[str, Any] | None = None


@dataclass
class ThreadProjection:
    """Read model for a thread."""

    id: str
    workspace_id: str
    name: str
    colonies: dict[str, ColonyProjection] = field(default_factory=dict)
    queen_messages: list[QueenMessageProjection] = field(default_factory=list)
    # Wave 29 additions:
    goal: str = ""
    expected_outputs: list[str] = field(default_factory=list)
    status: str = "active"  # active | completed | archived
    colony_count: int = 0
    completed_colony_count: int = 0
    failed_colony_count: int = 0
    artifact_types_produced: dict[str, int] = field(default_factory=dict)
    # Wave 30 additions:
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)
    # Wave 31: replay-safe step continuation counter
    continuation_depth: int = 0
    # Wave 35: parallel planning
    active_plan: dict[str, Any] | None = None
    parallel_groups: list[list[str]] | None = None


@dataclass
class WorkspaceProjection:
    """Read model for a workspace."""

    id: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    threads: dict[str, ThreadProjection] = field(default_factory=dict)
    # Wave 43: workspace-level budget truth
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)
    budget_limit: float = 50.0  # workspace-level default; configurable


@dataclass
class CooccurrenceEntry:
    """Weight for a co-occurrence pair of knowledge entries (Wave 33 A5)."""

    weight: float = 1.0
    last_reinforced: str = ""
    reinforcement_count: int = 0


def cooccurrence_key(id_a: str, id_b: str) -> tuple[str, str]:
    """Canonical pair ordering for co-occurrence tracking."""
    return (min(id_a, id_b), max(id_a, id_b))


# ---------------------------------------------------------------------------
# Wave 39: Operator editorial overlays (ADR-049)
# ---------------------------------------------------------------------------


@dataclass
class OperatorAnnotation:
    """A single operator annotation on a knowledge entry."""

    annotation_text: str
    tag: str
    actor: str
    timestamp: str


@dataclass
class ConfigOverrideRecord:
    """Record of an operator overriding a system recommendation."""

    suggestion_category: str
    original_config: dict[str, Any]
    overridden_config: dict[str, Any]
    reason: str
    actor: str
    timestamp: str


@dataclass
class OperatorOverlayState:
    """Replay-derived operator editorial overlays (Wave 39 ADR-049).

    Local-first: does not mutate shared Beta confidence truth.
    Does not federate behavioral overrides by default.
    """

    pinned_entries: set[str] = field(default_factory=set)
    muted_entries: set[str] = field(default_factory=set)
    invalidated_entries: set[str] = field(default_factory=set)
    # Per-entry annotations (entry_id -> list of annotations)
    annotations: dict[str, list[OperatorAnnotation]] = field(default_factory=dict)
    # Config override history (workspace_id -> list of overrides)
    config_overrides: dict[str, list[ConfigOverrideRecord]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Wave 44: Forager projection data structures
# ---------------------------------------------------------------------------


@dataclass
class DomainStrategyProjection:
    """Replay-derived fetch-level preference for a domain (Wave 44).

    Wave 45: added reason, level_changes, and success_rate for operator
    visibility into domain strategy evolution.
    """

    domain: str
    preferred_level: int  # 1=httpx+trafilatura, 2=fallback, 3=browser
    success_count: int = 0
    failure_count: int = 0
    last_updated: str = ""
    reason: str = ""  # Wave 45: why the strategy was last updated
    level_changes: int = 0  # Wave 45: how many times the level changed

    @property
    def success_rate(self) -> float:
        """Fraction of successful fetches (0.0 if no fetches recorded)."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total


@dataclass
class ForageCycleSummary:
    """Replay-derived summary of a completed forage cycle (Wave 44).

    Wave 48: colony_id and thread_id preserved from the originating
    ForageRequested event for audit attribution.
    """

    forage_request_seq: int
    mode: str  # reactive | proactive | operator
    reason: str
    queries_issued: int = 0
    pages_fetched: int = 0
    pages_rejected: int = 0
    entries_admitted: int = 0
    entries_deduplicated: int = 0
    duration_ms: int = 0
    error: str = ""
    timestamp: str = ""
    # Wave 48: linkage from originating ForageRequested
    colony_id: str = ""
    thread_id: str = ""
    gap_domain: str = ""
    gap_query: str = ""


@dataclass
class DomainOverrideProjection:
    """Replay-derived operator domain trust override (Wave 44)."""

    domain: str
    action: str  # trust | distrust | reset
    actor: str
    reason: str = ""
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Projection store
# ---------------------------------------------------------------------------


class ProjectionStore:
    """In-memory event-sourced read model store.

    Call ``apply(event)`` for each event. Query via attributes.
    Thread-safe at alpha scale (single asyncio loop, no concurrent writes).
    """

    def __init__(self) -> None:
        self.workspaces: dict[str, WorkspaceProjection] = {}
        self.colonies: dict[str, ColonyProjection] = {}
        self.merges: dict[str, MergeProjection] = {}
        self.approvals: dict[str, ApprovalProjection] = {}
        self.templates: dict[str, TemplateProjection] = {}
        self.memory_entries: dict[str, dict[str, Any]] = {}
        self.memory_extractions_completed: set[str] = set()
        # Wave 33 A5: co-occurrence reinforcement weights
        self.cooccurrence_weights: dict[tuple[str, str], CooccurrenceEntry] = {}
        # Wave 34.5: distillation candidate clusters (ephemeral, rebuilt on maintenance)
        self.distillation_candidates: list[list[str]] = []
        # Wave 35.5 C3: replay-derived colony outcomes (internal foundation)
        self.colony_outcomes: dict[str, ColonyOutcome] = {}
        # Wave 37 4B: operator behavior signals (replay-derived)
        self.operator_behavior = OperatorBehaviorProjection()
        # Wave 39: operator editorial overlays (ADR-049)
        self.operator_overlays = OperatorOverlayState()
        # Wave 37 4B: recent briefing suggestions for follow-through inference
        self._recent_suggestions: list[dict[str, Any]] = []
        # Wave 39 4B: earned autonomy recommendation dismissals
        # INTENTIONALLY EPHEMERAL (Wave 51): not event-sourced, lost on restart.
        # Recommendations regenerate each briefing cycle; stale dismissals
        # would mask new recommendations. category -> ISO timestamp.
        self.autonomy_recommendation_dismissals: dict[str, str] = {}
        # Wave 44: forager projection state
        # workspace_id -> domain -> DomainStrategyProjection
        self.domain_strategies: dict[str, dict[str, DomainStrategyProjection]] = {}
        # workspace_id -> list of completed forage cycle summaries
        self.forage_cycles: dict[str, list[ForageCycleSummary]] = {}
        # workspace_id -> list of pending forage request seqs (not yet completed)
        self._pending_forage_requests: dict[str, dict[int, ForageRequested]] = {}
        # workspace_id -> domain -> DomainOverrideProjection (latest action per domain)
        self.domain_overrides: dict[str, dict[str, DomainOverrideProjection]] = {}
        # Wave 59.5: entry-to-KG-node mapping (populated by runtime, NOT by handlers)
        self.entry_kg_nodes: dict[str, str] = {}
        # Wave 55: knowledge entry usage tracking (entry_id -> {count, last_accessed})
        self.knowledge_entry_usage: dict[str, dict[str, Any]] = {}
        # Wave 45: competing hypothesis pairs (entry_id -> set of competing entry_ids)
        self.competing_pairs: dict[str, set[str]] = {}
        self._competing_pairs_dirty: bool = False
        # Wave 51: replay-safe Queen notes (workspace_id/thread_id -> list of notes)
        self.queen_notes: dict[str, list[dict[str, str]]] = {}
        # Wave 59.5: entry_id -> kg_node_id bridge (populated by runtime, NOT handlers)
        self.entry_kg_nodes: dict[str, str] = {}
        self.last_seq: int = 0

    def apply(self, event: FormicOSEvent) -> None:
        """Process a single event and update projections."""
        seq: int = event.seq  # pyright: ignore[reportAttributeAccessIssue]
        if seq > self.last_seq:
            self.last_seq = seq

        handler = _HANDLERS.get(type(event).__name__)
        if handler is not None:
            handler(self, event)

    def replay(self, events: list[FormicOSEvent]) -> None:
        """Replay a batch of events to rebuild state."""
        for event in events:
            self.apply(event)
        # Individual handlers set _competing_pairs_dirty; after replay the
        # flag is already True if any memory-affecting events were replayed.
        # Competing pairs will be rebuilt lazily on first retrieval access.

    # -- Wave 45: competing hypothesis tracking --

    def rebuild_competing_pairs(self) -> None:
        """Scan memory entries for competing hypotheses and update tracking.

        Uses the existing contradiction detection and classification from
        conflict_resolution.py. When two entries resolve as ``competing``
        (Phase 3: scores too close to pick a winner), they are recorded
        as a bidirectional pair.

        This is replay-derived state — it can be rebuilt from memory_entries
        at any time.
        """
        from formicos.surface.conflict_resolution import (  # noqa: PLC0415
            Resolution,
            detect_contradictions,
            resolve_classified,
        )

        pairs: dict[str, set[str]] = {}
        eligible = {
            eid: e for eid, e in self.memory_entries.items()
            if e.get("status") in {"verified", "stable", "promoted"}
            and e.get("conf_alpha", 0) >= 5.0
        }

        if len(eligible) < 2:
            self.competing_pairs = pairs
            self._competing_pairs_dirty = False
            return

        detected = detect_contradictions(
            eligible,
            status_filter={"verified", "stable", "promoted"},
            min_alpha=5.0,
        )

        from formicos.surface.conflict_resolution import (  # noqa: PLC0415
            PairRelation,
        )

        for pair in detected:
            if pair.relation != PairRelation.contradiction:
                continue
            ea = eligible.get(pair.entry_a_id, {})
            eb = eligible.get(pair.entry_b_id, {})
            if not ea or not eb:
                continue
            result = resolve_classified(ea, eb, pair)
            if result.resolution == Resolution.competing:
                pairs.setdefault(pair.entry_a_id, set()).add(pair.entry_b_id)
                pairs.setdefault(pair.entry_b_id, set()).add(pair.entry_a_id)

        self.competing_pairs = pairs
        self._competing_pairs_dirty = False

    def get_competing_context(
        self, entry_id: str,
    ) -> list[dict[str, Any]]:
        """Return competing entry summaries for retrieval annotation.

        Lazily rebuilds competing pairs when memory entries have changed
        since the last rebuild, ensuring retrieval always reflects current
        projection state without requiring explicit caller coordination.
        """
        if self._competing_pairs_dirty:
            self.rebuild_competing_pairs()
            self._competing_pairs_dirty = False
        competitors = self.competing_pairs.get(entry_id)
        if not competitors:
            return []
        result: list[dict[str, Any]] = []
        for cid in competitors:
            entry = self.memory_entries.get(cid)
            if entry is None:
                continue
            alpha = entry.get("conf_alpha", 5.0)
            beta = entry.get("conf_beta", 5.0)
            result.append({
                "id": cid,
                "title": entry.get("title", ""),
                "confidence_mean": round(alpha / (alpha + beta), 3),
                "status": entry.get("status", ""),
            })
        return result

    # -- Lookup helpers --

    def get_thread(self, workspace_id: str, thread_id: str) -> ThreadProjection | None:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            return None
        return ws.threads.get(thread_id)

    def get_colony(self, colony_id: str) -> ColonyProjection | None:
        return self.colonies.get(colony_id)

    def workspace_colonies(self, workspace_id: str) -> list[ColonyProjection]:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            return []
        result: list[ColonyProjection] = []
        for thread in ws.threads.values():
            result.extend(thread.colonies.values())
        return result

    def active_merges(self) -> list[MergeProjection]:
        return [m for m in self.merges.values() if m.active]

    def pending_approvals(self) -> list[ApprovalProjection]:
        return list(self.approvals.values())

    # -- Wave 43: budget truth queries --

    def workspace_budget(self, workspace_id: str) -> BudgetSnapshot | None:
        """Return workspace-level budget snapshot, or None if workspace unknown."""
        ws = self.workspaces.get(workspace_id)
        return ws.budget if ws is not None else None

    def colony_budget(self, colony_id: str) -> BudgetSnapshot | None:
        """Return colony-level budget snapshot, or None if colony unknown."""
        colony = self.colonies.get(colony_id)
        return colony.budget_truth if colony is not None else None

    def workspace_budget_utilization(self, workspace_id: str) -> float:
        """Return workspace budget utilization as a fraction [0, 1+].

        Returns 0.0 if workspace is unknown.
        """
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            return 0.0
        if ws.budget_limit <= 0:
            return 0.0
        return ws.budget.total_cost / ws.budget_limit


# ---------------------------------------------------------------------------
# Event handlers (keyed by event type name for dispatch)
# ---------------------------------------------------------------------------


def _on_workspace_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkspaceCreated = event  # type: ignore[assignment]
    store.workspaces[e.name] = WorkspaceProjection(
        id=e.name, name=e.name, config=dict(e.config),
    )


def _on_thread_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadCreated = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        ws.threads[e.name] = ThreadProjection(
            id=e.name, workspace_id=e.workspace_id, name=e.name,
            goal=getattr(e, "goal", ""),
            expected_outputs=list(getattr(e, "expected_outputs", [])),
        )


def _on_thread_renamed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadRenamed = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.name = e.new_name


def _infer_suggestion_follow_through(
    store: ProjectionStore,
    colony_id: str,
    e: Any,
) -> None:
    """Infer whether a colony spawn matches a recent briefing suggestion (Wave 37 4B).

    Honesty constraint: we only mark accepted suggestions where a matching
    colony spawn follows. We do NOT track rejected suggestions — the event
    surface does not support exact rejection tracking.
    """
    if not store._recent_suggestions:
        return
    task_lower = e.task.lower() if hasattr(e, "task") else ""
    if not task_lower:
        return
    for suggestion in store._recent_suggestions:
        stask = suggestion.get("task", "").lower()
        if not stask:
            continue
        # Fuzzy match: if the colony task contains key words from the suggestion
        suggestion_words = set(stask.split())
        task_words = set(task_lower.split())
        if not suggestion_words:
            continue
        overlap = len(suggestion_words & task_words) / len(suggestion_words)
        if overlap >= 0.4:
            ws_id = e.address.split("/")[0] if hasattr(e, "address") and "/" in e.address else ""
            store.operator_behavior.record_suggestion_follow_through(
                insight_category=suggestion.get("category", "unknown"),
                colony_id=colony_id,
                workspace_id=ws_id,
                timestamp=e.timestamp.isoformat(),
            )
            store._recent_suggestions.remove(suggestion)
            break


def _on_colony_spawned(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonySpawned = event  # type: ignore[assignment]
    colony_id = e.address.rsplit("/", 1)[-1] if "/" in e.address else e.address
    colony = ColonyProjection(
        id=colony_id,
        thread_id=e.thread_id,
        workspace_id=e.address.split("/")[0] if "/" in e.address else "",
        task=e.task,
        active_goal=e.task,
        status="running",
        max_rounds=e.max_rounds,
        strategy=e.strategy,
        castes=list(e.castes),
        model_assignments=dict(e.model_assignments),
        budget_limit=e.budget_limit,
        template_id=e.template_id,
        input_sources=[src.model_dump() for src in e.input_sources],
        spawned_at=e.timestamp.isoformat(),
        # Wave 41: replay-safe target_files from event
        target_files=list(e.target_files) if e.target_files else [],
        # Wave 47: replay-safe fast_path from event
        fast_path=bool(getattr(e, "fast_path", False)),
        # Wave 50: spawn provenance
        spawn_source=getattr(e, "spawn_source", ""),
    )
    store.colonies[colony_id] = colony
    # Wave 37 4B: infer suggestion follow-through from matching colony spawns
    _infer_suggestion_follow_through(store, colony_id, e)
    # Place colony in its thread
    for ws in store.workspaces.values():
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            # Wave 32.5: re-activate completed thread when new colony spawns
            if thread.status == "completed":
                thread.status = "active"
            thread.colonies[colony_id] = colony
            colony.workspace_id = ws.id
            # Wave 29: track thread progress
            thread.colony_count += 1
            # Wave 30: derive step "running" from step_index
            _step_idx = getattr(e, "step_index", -1)
            if _step_idx >= 0:
                for _ws in thread.workflow_steps:
                    if _ws.get("step_index") == _step_idx and _ws.get("status") == "pending":
                        _ws["status"] = "running"
                        _ws["colony_id"] = colony_id
                        break
            break


def _build_colony_outcome(
    store: ProjectionStore, colony: ColonyProjection, succeeded: bool, end_ts: str,
) -> None:
    """Derive a ColonyOutcome from existing projection state (Wave 35.5 C3)."""
    colony.completed_at = end_ts
    # Duration: parse ISO timestamps
    duration_ms = 0
    if colony.spawned_at and end_ts:
        try:
            from datetime import datetime
            start = datetime.fromisoformat(colony.spawned_at)
            end = datetime.fromisoformat(end_ts)
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = 0

    # Caste composition from agents
    caste_set: list[str] = []
    for agent in colony.agents.values():
        if agent.caste not in caste_set:
            caste_set.append(agent.caste)

    # Entries accessed: count unique items across all access records
    entries_accessed = 0
    seen_ids: set[str] = set()
    for access in colony.knowledge_accesses:
        for item in access.get("items", []):
            item_id = item.get("id", "")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                entries_accessed += 1

    # Maintenance provenance from colony tags/chat
    maintenance_source: str | None = None
    for msg in colony.chat_messages:
        if msg.event_kind == "service" and "maintenance" in msg.content.lower():
            maintenance_source = "self-maintenance"
            break

    # Wave 38 2B: derive escalation fields from routing_override
    escalated = colony.routing_override is not None
    escalated_tier: str | None = None
    escalation_reason: str | None = None
    escalation_round: int | None = None
    starting_tier: str | None = None
    pre_escalation_cost: float = 0.0
    if escalated and colony.routing_override is not None:
        escalated_tier = colony.routing_override.get("tier")
        escalation_reason = colony.routing_override.get("reason")
        escalation_round = colony.routing_override.get("set_at_round")
        # Starting tier: derive from actual spawned caste tiers
        caste_tiers = sorted({
            getattr(c, "tier", "standard") for c in colony.castes
        }) if colony.castes else ["standard"]
        starting_tier = ",".join(str(t) for t in caste_tiers)
        # Pre-escalation cost: sum round costs before the escalation round
        if escalation_round is not None:
            pre_escalation_cost = sum(
                r.cost for r in colony.round_records
                if r.round_number < escalation_round
            )

    store.colony_outcomes[colony.id] = ColonyOutcome(
        colony_id=colony.id,
        workspace_id=colony.workspace_id,
        thread_id=colony.thread_id,
        succeeded=succeeded,
        total_rounds=colony.round_number,
        total_cost=colony.cost,
        duration_ms=duration_ms,
        entries_extracted=colony.entries_extracted_count,
        entries_accessed=entries_accessed,
        quality_score=colony.quality_score,
        caste_composition=caste_set,
        strategy=colony.strategy,
        maintenance_source=maintenance_source,
        escalated=escalated,
        starting_tier=starting_tier,
        escalated_tier=escalated_tier,
        escalation_reason=escalation_reason,
        escalation_round=escalation_round,
        pre_escalation_cost=round(pre_escalation_cost, 6),
        validator_verdict=colony.validator_verdict,
        validator_task_type=colony.validator_task_type,
    )


def _on_colony_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyCompleted = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "completed"
        colony.skills_extracted = e.skills_extracted
        colony.artifacts = getattr(e, "artifacts", [])  # Wave 25: replay-safe
        _build_colony_outcome(store, colony, True, e.timestamp.isoformat())
        # Wave 50: cross-event template success tracking
        if colony.template_id:
            tmpl = store.templates.get(colony.template_id)
            if tmpl is not None:
                tmpl.success_count += 1
        # Wave 29: track thread progress
        if colony.thread_id:
            ws = store.workspaces.get(colony.workspace_id)
            if ws is not None:
                thread = ws.threads.get(colony.thread_id)
                if thread is not None:
                    thread.completed_colony_count += 1
                    for art in e.artifacts:
                        atype = str(art.get("artifact_type", "generic"))
                        thread.artifact_types_produced[atype] = (
                            thread.artifact_types_produced.get(atype, 0) + 1
                        )


def _on_colony_failed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyFailed = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "failed"
        colony.failure_reason = e.reason
        colony.failed_at_round = colony.round_number
        _build_colony_outcome(store, colony, False, e.timestamp.isoformat())
        # Wave 50: cross-event template failure tracking
        if colony.template_id:
            tmpl = store.templates.get(colony.template_id)
            if tmpl is not None:
                tmpl.failure_count += 1
        # Wave 29: track thread progress
        if colony.thread_id:
            ws = store.workspaces.get(colony.workspace_id)
            if ws is not None:
                thread = ws.threads.get(colony.thread_id)
                if thread is not None:
                    thread.failed_colony_count += 1


def _on_colony_killed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyKilled = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "killed"
        colony.killed_by = e.killed_by
        colony.killed_at_round = colony.round_number
        _build_colony_outcome(store, colony, False, e.timestamp.isoformat())
        # Wave 37 4B: record operator kill signal
        store.operator_behavior.record_kill(
            colony_id=e.colony_id,
            workspace_id=colony.workspace_id,
            killed_by=e.killed_by,
            strategy=colony.strategy,
            round_at_kill=colony.round_number,
            timestamp=e.timestamp.isoformat(),
        )


def _get_or_create_round(
    colony: ColonyProjection, round_number: int,
) -> RoundProjection:
    """Return the RoundProjection for *round_number*, creating it if absent."""
    for r in colony.round_records:
        if r.round_number == round_number:
            return r
    rp = RoundProjection(round_number=round_number)
    colony.round_records.append(rp)
    return rp


def _on_round_started(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: RoundStarted = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.round_number = e.round_number
        _get_or_create_round(colony, e.round_number)
        colony.last_activity_at = _time.monotonic()


def _on_agent_turn_started(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: AgentTurnStarted = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        if e.agent_id not in colony.agents:
            colony.agents[e.agent_id] = AgentProjection(
                id=e.agent_id, caste=e.caste, model=e.model,
            )
        colony.agents[e.agent_id].status = "active"
        colony.last_activity_at = _time.monotonic()


_PRODUCTIVE_TOOL_NAMES = frozenset({
    "write_workspace_file", "patch_file", "code_execute",
    "workspace_execute", "git_commit",
})
_OBSERVATION_TOOL_NAMES = frozenset({
    "list_workspace_files", "read_workspace_file", "memory_search",
    "git_status", "git_diff", "git_log", "knowledge_detail",
    "transcript_search", "artifact_inspect", "knowledge_feedback",
    "memory_write",
})


def _on_agent_turn_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: AgentTurnCompleted = event  # type: ignore[assignment]
    colony_id = e.address.rsplit("/", 1)[-1] if "/" in e.address else e.address
    colony = store.colonies.get(colony_id)
    if colony is None:
        for candidate in store.colonies.values():
            if e.agent_id in candidate.agents:
                colony = candidate
                break
    if colony is None:
        return

    agent = colony.agents.get(e.agent_id)
    if agent is not None:
        agent.status = "done"
        agent.tokens += e.input_tokens + e.output_tokens
    rp = _get_or_create_round(colony, colony.round_number)
    rp.agent_outputs[e.agent_id] = e.output_summary
    rp.tool_calls[e.agent_id] = list(e.tool_calls)
    colony.last_activity_at = _time.monotonic()
    # Wave 55: accumulate productive/observation counts
    for tc in e.tool_calls:
        if tc in _PRODUCTIVE_TOOL_NAMES:
            colony.productive_calls += 1
        elif tc in _OBSERVATION_TOOL_NAMES:
            colony.observation_calls += 1


def _on_round_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: RoundCompleted = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.convergence = e.convergence
        colony.cost += e.cost
        rp = _get_or_create_round(colony, e.round_number)
        rp.convergence = e.convergence
        rp.cost = e.cost
        rp.duration_ms = e.duration_ms
        # Wave 39 1B: replay-safe validator state reconstruction
        if e.validator_verdict is not None:
            colony.validator_task_type = e.validator_task_type
            colony.validator_verdict = e.validator_verdict
            colony.validator_reason = e.validator_reason


def _on_phase_entered(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: PhaseEntered = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        rp = _get_or_create_round(colony, e.round_number)
        rp.current_phase = e.phase


def _on_merge_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MergeCreated = event  # type: ignore[assignment]
    store.merges[e.edge_id] = MergeProjection(
        id=e.edge_id,
        from_colony=e.from_colony,
        to_colony=e.to_colony,
        created_by=e.created_by,
    )


def _on_merge_pruned(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MergePruned = event  # type: ignore[assignment]
    merge = store.merges.get(e.edge_id)
    if merge is not None:
        merge.active = False


def _on_queen_message(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: QueenMessage = event  # type: ignore[assignment]
    for ws in store.workspaces.values():
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.queen_messages.append(QueenMessageProjection(
                role=e.role,
                content=e.content,
                timestamp=str(e.timestamp),
                intent=e.intent,
                render=e.render,
                meta=e.meta,
            ))
            break


def _on_workspace_config_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkspaceConfigChanged = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        if e.new_value is None:
            ws.config.pop(e.field, None)
        else:
            ws.config[e.field] = e.new_value


def _on_approval_requested(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ApprovalRequested = event  # type: ignore[assignment]
    store.approvals[e.request_id] = ApprovalProjection(
        id=e.request_id,
        approval_type=e.approval_type,
        detail=e.detail,
        colony_id=e.colony_id,
    )


def _on_approval_granted(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ApprovalGranted = event  # type: ignore[assignment]
    store.approvals.pop(e.request_id, None)


def _on_approval_denied(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ApprovalDenied = event  # type: ignore[assignment]
    store.approvals.pop(e.request_id, None)


def _on_tokens_consumed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: TokensConsumed = event  # type: ignore[assignment]
    matched_colony: ColonyProjection | None = None
    for colony in store.colonies.values():
        agent = colony.agents.get(e.agent_id)
        if agent is not None:
            # Update agent model to reflect the actual serving model
            # (may differ from planned route after LLMRouter fallback).
            if e.model:
                agent.model = e.model
            agent.tokens += e.input_tokens + e.output_tokens
            matched_colony = colony
            break

    # Wave 43: colony-level budget truth from TokensConsumed
    if matched_colony is not None:
        matched_colony.budget_truth.record_token_spend(
            e.model, e.input_tokens, e.output_tokens, e.cost,
            reasoning_tokens=e.reasoning_tokens,
            cache_read_tokens=e.cache_read_tokens,
        )
        # Wave 43: workspace-level budget truth
        ws = store.workspaces.get(matched_colony.workspace_id)
        if ws is not None:
            ws.budget.record_token_spend(
                e.model, e.input_tokens, e.output_tokens, e.cost,
                reasoning_tokens=e.reasoning_tokens,
                cache_read_tokens=e.cache_read_tokens,
            )


def _on_model_registered(store: ProjectionStore, event: FormicOSEvent) -> None:
    _: ModelRegistered = event  # type: ignore[assignment]


def _on_model_assignment_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ModelAssignmentChanged = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.scope)
    if ws is not None:
        if e.new_model is None:
            ws.config.pop(f"{e.caste}_model", None)
        else:
            ws.config[f"{e.caste}_model"] = e.new_model


def _on_colony_template_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyTemplateCreated = event  # type: ignore[assignment]
    store.templates[e.template_id] = TemplateProjection(
        id=e.template_id,
        name=e.name,
        description=e.description,
        castes=list(e.castes),
        strategy=e.strategy,
        source_colony_id=e.source_colony_id,
        # Wave 50: event-carried learned template fields
        learned=getattr(e, "learned", False),
        task_category=getattr(e, "task_category", ""),
        max_rounds=getattr(e, "max_rounds", 25),
        budget_limit=getattr(e, "budget_limit", 1.0),
        fast_path=getattr(e, "fast_path", False),
        target_files_pattern=getattr(e, "target_files_pattern", ""),
    )


def _on_colony_template_used(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyTemplateUsed = event  # type: ignore[assignment]
    tmpl = store.templates.get(e.template_id)
    if tmpl is not None:
        tmpl.use_count += 1


def _on_colony_named(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyNamed = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.display_name = e.display_name


def _on_skill_confidence_updated(store: ProjectionStore, event: FormicOSEvent) -> None:
    _: SkillConfidenceUpdated = event  # type: ignore[assignment]
    # Audit trail event — no projection state change needed.


def _on_skill_merged(store: ProjectionStore, event: FormicOSEvent) -> None:
    _: SkillMerged = event  # type: ignore[assignment]
    # Audit trail event — no projection state change needed.


def _on_colony_chat_message(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyChatMessage = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.chat_messages.append(ChatMessageProjection(
            sender=e.sender,
            content=e.content,
            timestamp=str(e.timestamp),
            event_kind=e.event_kind,
            source_colony=e.source_colony,
            seq=e.seq,
        ))
        # Wave 37 4B: capture operator directive patterns
        if e.sender == "operator" and e.metadata:
            directive_type = e.metadata.get("directive_type", "")
            if directive_type:
                store.operator_behavior.record_directive(
                    colony_id=e.colony_id,
                    workspace_id=e.workspace_id,
                    directive_type=directive_type,
                    timestamp=e.timestamp.isoformat(),
                )


def _on_code_executed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: CodeExecuted = event  # type: ignore[assignment]
    colony_id = e.address.rsplit("/", 1)[-1] if "/" in e.address else ""
    colony = store.colonies.get(colony_id)
    if colony is not None:
        colony.last_activity_at = _time.monotonic()


def _on_service_query_sent(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ServiceQuerySent = event  # type: ignore[assignment]
    # Add chat message to the sender colony
    if e.sender_colony_id:
        colony = store.colonies.get(e.sender_colony_id)
        if colony is not None:
            colony.chat_messages.append(ChatMessageProjection(
                sender="system", event_kind="service",
                content=f"Service query sent to {e.service_type}: {e.query_preview}",
                timestamp=str(e.timestamp), seq=e.seq,
            ))
    # Add chat message to the target service colony
    target = store.colonies.get(e.target_colony_id)
    if target is not None:
        target.chat_messages.append(ChatMessageProjection(
            sender="service", event_kind="service",
            content=f"Inbound query from {e.sender_colony_id or 'operator'}: {e.query_preview}",
            timestamp=str(e.timestamp), seq=e.seq,
            source_colony=e.sender_colony_id,
        ))


def _on_service_query_resolved(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ServiceQueryResolved = event  # type: ignore[assignment]
    colony = store.colonies.get(e.source_colony_id)
    if colony is not None:
        colony.chat_messages.append(ChatMessageProjection(
            sender="system", event_kind="service",
            content=f"Service query resolved ({e.latency_ms:.0f}ms): {e.response_preview}",
            timestamp=str(e.timestamp), seq=e.seq,
        ))


def _on_colony_service_activated(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyServiceActivated = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.status = "service"
        colony.service_type = e.service_type
        colony.chat_messages.append(ChatMessageProjection(
            sender="system", event_kind="service",
            content=f"Colony activated as '{e.service_type}' service with {e.agent_count} agents",
            timestamp=str(e.timestamp), seq=e.seq,
        ))


def _on_knowledge_entity_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeEntityCreated = event  # type: ignore[assignment]
    if e.source_colony_id:
        colony = store.colonies.get(e.source_colony_id)
        if colony is not None:
            colony.kg_entity_count += 1


def _on_knowledge_edge_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeEdgeCreated = event  # type: ignore[assignment]
    if e.source_colony_id:
        colony = store.colonies.get(e.source_colony_id)
        if colony is not None:
            colony.kg_edge_count += 1


def _on_knowledge_entity_merged(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeEntityMerged = event  # type: ignore[assignment]
    # Merges reduce entity count by 1 in the workspace.
    # We don't track which colony the merged entity belonged to,
    # so this is logged but not projected onto a specific colony.
    log.debug(
        "projection.kg_entity_merged",
        survivor_id=e.survivor_id,
        merged_id=e.merged_id,
        similarity=e.similarity_score,
    )


def _on_colony_redirected(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ColonyRedirected = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.active_goal = e.new_goal
        colony.redirect_history.append({
            "redirect_index": e.redirect_index,
            "new_goal": e.new_goal,
            "reason": e.reason,
            "trigger": e.trigger,
            "round": e.round_at_redirect,
            "timestamp": e.timestamp.isoformat(),
        })
        colony.redirect_boundaries.append(e.round_at_redirect)


def _on_knowledge_access_recorded(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeAccessRecorded = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.knowledge_accesses.append({
            "round": e.round_number,
            "access_mode": e.access_mode,
            "items": [item.model_dump() for item in e.items],
        })
    # Wave 55: accumulate per-entry usage counts
    ts = e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp)
    for item in e.items:
        item_id = item.id if hasattr(item, "id") else item.get("id", "")  # type: ignore[union-attr]
        if item_id:
            usage = store.knowledge_entry_usage.get(item_id)
            if usage is None:
                store.knowledge_entry_usage[item_id] = {"count": 1, "last_accessed": ts}
            else:
                usage["count"] = usage.get("count", 0) + 1
                usage["last_accessed"] = ts


def _on_memory_entry_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryCreated = event  # type: ignore[assignment]
    entry = e.entry
    entry_id = entry.get("id", "")
    if entry_id:
        data = dict(entry)
        # Wave 32 A1: seed last_confidence_update for gamma-decay
        data.setdefault("last_confidence_update", data.get("created_at", ""))
        # Wave 50: derive initial scope from thread_id presence
        if "scope" not in data:
            data["scope"] = "thread" if data.get("thread_id") else "workspace"
        store.memory_entries[entry_id] = data
        # Wave 45.5: new entry may form a competing pair
        store._competing_pairs_dirty = True
        # Wave 35.5 C3: track entries extracted per colony for outcome projection
        source_colony = entry.get("source_colony_id", "")
        if source_colony:
            colony = store.colonies.get(source_colony)
            if colony is not None:
                colony.entries_extracted_count += 1


def _on_memory_entry_status_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryStatusChanged = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["status"] = e.new_status
        entry["last_status_reason"] = e.reason
        # Wave 38: bi-temporal tracking — record when status changed
        entry["status_changed_at"] = e.timestamp.isoformat()
        if e.new_status == "rejected":
            entry["invalidated_at"] = e.timestamp.isoformat()
        # Wave 45.5: status change affects competing-pair eligibility
        store._competing_pairs_dirty = True


def _on_memory_extraction_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryExtractionCompleted = event  # type: ignore[assignment]
    store.memory_extractions_completed.add(e.colony_id)


def _on_thread_goal_set(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadGoalSet = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.goal = e.goal
            thread.expected_outputs = list(e.expected_outputs)


def _on_thread_status_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadStatusChanged = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.status = e.new_status


def _on_memory_entry_scope_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryScopeChanged = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["thread_id"] = e.new_thread_id
        # Wave 50: workspace-to-global promotion
        new_ws = getattr(e, "new_workspace_id", None)
        if new_ws is not None and new_ws == "":
            # Empty new_workspace_id = global scope
            entry["scope"] = "global"
            entry["workspace_id"] = ""  # clear so downstream filters include it
        elif not e.new_thread_id:
            entry["scope"] = "workspace"
        else:
            entry["scope"] = "thread"


def _on_memory_confidence_updated(
    store: ProjectionStore, event: FormicOSEvent,
) -> None:
    e: MemoryConfidenceUpdated = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["conf_alpha"] = e.new_alpha
        entry["conf_beta"] = e.new_beta
        entry["confidence"] = e.new_confidence
        # Wave 32 A1: track update timestamp for gamma-decay
        entry["last_confidence_update"] = e.timestamp.isoformat()
        # Wave 45.5: confidence change affects competing-pair resolution
        store._competing_pairs_dirty = True
        # Wave 35 C3: track peak alpha for mastery-restoration bonus
        current_peak = float(entry.get("peak_alpha", entry.get("conf_alpha", 5.0)))
        if e.new_alpha > current_peak:
            entry["peak_alpha"] = e.new_alpha
        # Wave 37 4B: capture feedback signal from colony-driven updates
        # A colony_id indicates tool-driven feedback (not archival decay).
        if e.colony_id and e.reason == "colony_outcome":
            direction = "positive" if e.colony_succeeded else "negative"
            domains = entry.get("domains", [])
            if isinstance(domains, list):
                store.operator_behavior.record_feedback(
                    entry_id=e.entry_id,
                    workspace_id=e.workspace_id,
                    colony_id=e.colony_id,
                    direction=direction,
                    timestamp=e.timestamp.isoformat(),
                    domains=[str(d) for d in domains],
                )


# Wave 30 (Track B): workflow step handlers


def _on_workflow_step_defined(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkflowStepDefined = event  # type: ignore[assignment]
    ws = store.workspaces.get(getattr(e, "workspace_id", ""))
    if ws is None:
        return
    thread = ws.threads.get(e.thread_id)
    if thread is not None:
        thread.workflow_steps.append(e.step.model_dump())


def _on_workflow_step_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkflowStepCompleted = event  # type: ignore[assignment]
    ws = store.workspaces.get(getattr(e, "workspace_id", ""))
    if ws is None:
        return
    thread = ws.threads.get(e.thread_id)
    if thread is None:
        return
    for step in thread.workflow_steps:
        if step.get("step_index") == e.step_index:
            step["status"] = "completed" if e.success else "failed"
            step["colony_id"] = e.colony_id
            if e.success:
                thread.continuation_depth += 1
            break


# ---------------------------------------------------------------------------
# Wave 33: CRDT state projection handlers + MemoryEntryMerged
# ---------------------------------------------------------------------------


def _on_crdt_counter_incremented(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: CRDTCounterIncremented = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    crdt_state = entry.setdefault("crdt_state", {})
    counters = crdt_state.setdefault(e.field, {})
    counters[e.instance_id] = counters.get(e.instance_id, 0) + e.delta


def _on_crdt_timestamp_updated(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: CRDTTimestampUpdated = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    crdt_state = entry.setdefault("crdt_state", {})
    timestamps = crdt_state.setdefault("last_obs_ts", {})
    current = timestamps.get(e.instance_id, {})
    if e.obs_timestamp > current.get("timestamp", 0.0):
        timestamps[e.instance_id] = {
            "timestamp": e.obs_timestamp,
            "instance_id": e.instance_id,
        }


def _on_crdt_set_element_added(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: CRDTSetElementAdded = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    crdt_state = entry.setdefault("crdt_state", {})
    elements = crdt_state.setdefault(e.field, [])
    if e.element not in elements:
        elements.append(e.element)


def _on_crdt_register_assigned(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: CRDTRegisterAssigned = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    crdt_state = entry.setdefault("crdt_state", {})
    current = crdt_state.get(e.field, {})
    if e.lww_timestamp > current.get("timestamp", 0.0) or (
        e.lww_timestamp == current.get("timestamp", 0.0)
        and e.instance_id > current.get("instance_id", "")
    ):
        crdt_state[e.field] = {
            "value": e.value,
            "timestamp": e.lww_timestamp,
            "instance_id": e.instance_id,
        }


def _on_memory_entry_merged(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryMerged = event  # type: ignore[assignment]
    target = store.memory_entries.get(e.target_id)
    if target:
        target["content"] = e.merged_content
        target["domains"] = e.merged_domains
        target["merged_from"] = e.merged_from
        target["merge_count"] = target.get("merge_count", 0) + 1
    source = store.memory_entries.get(e.source_id)
    if source:
        source["status"] = "rejected"
        source["rejection_reason"] = f"merged_into:{e.target_id}"
    # Wave 45.5: merge changes entry state — may affect competing pairs
    store._competing_pairs_dirty = True


def _on_memory_entry_refined(store: ProjectionStore, event: FormicOSEvent) -> None:
    from formicos.core.events import MemoryEntryRefined
    e: MemoryEntryRefined = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    entry["content"] = e.new_content
    if e.new_title:
        entry["title"] = e.new_title
    entry["refinement_count"] = entry.get("refinement_count", 0) + 1
    ts = e.timestamp
    entry["last_refined_at"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


def _on_parallel_plan_created(store: ProjectionStore, event: FormicOSEvent) -> None:
    from formicos.core.events import ParallelPlanCreated
    e: ParallelPlanCreated = event  # type: ignore[assignment]
    thread = store.get_thread(e.workspace_id, e.thread_id)
    if thread:
        thread.active_plan = e.plan
        thread.parallel_groups = e.parallel_groups


def _on_knowledge_distilled(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: KnowledgeDistilled = event  # type: ignore[assignment]
    # Upgrade existing entry (created by archivist's MemoryEntryCreated)
    entry = store.memory_entries.get(e.distilled_entry_id)
    if not entry:
        return  # Entry should exist from extraction; skip if replay order differs

    source_alphas = [
        store.memory_entries.get(sid, {}).get("conf_alpha", 5.0)
        for sid in e.source_entry_ids
    ]
    entry["decay_class"] = "stable"
    entry["conf_alpha"] = min(sum(source_alphas) / 2, 30.0)
    entry["merged_from"] = e.source_entry_ids
    entry["distillation_strategy"] = e.distillation_strategy

    # Mark source entries
    for sid in e.source_entry_ids:
        source = store.memory_entries.get(sid)
        if source:
            source["distilled_into"] = e.distilled_entry_id


# ---------------------------------------------------------------------------
# Wave 39: Operator co-authorship event handlers (ADR-049)
# ---------------------------------------------------------------------------


def _on_knowledge_entry_operator_action(
    store: ProjectionStore, event: FormicOSEvent,
) -> None:
    e: KnowledgeEntryOperatorAction = event  # type: ignore[assignment]
    overlays = store.operator_overlays
    action = e.action

    if action == "pin":
        overlays.pinned_entries.add(e.entry_id)
    elif action == "unpin":
        overlays.pinned_entries.discard(e.entry_id)
    elif action == "mute":
        overlays.muted_entries.add(e.entry_id)
    elif action == "unmute":
        overlays.muted_entries.discard(e.entry_id)
    elif action == "invalidate":
        overlays.invalidated_entries.add(e.entry_id)
    elif action == "reinstate":
        overlays.invalidated_entries.discard(e.entry_id)


def _on_knowledge_entry_annotated(
    store: ProjectionStore, event: FormicOSEvent,
) -> None:
    e: KnowledgeEntryAnnotated = event  # type: ignore[assignment]
    annotation = OperatorAnnotation(
        annotation_text=e.annotation_text,
        tag=e.tag,
        actor=e.actor,
        timestamp=str(e.timestamp.isoformat()),
    )
    if e.entry_id not in store.operator_overlays.annotations:
        store.operator_overlays.annotations[e.entry_id] = []
    store.operator_overlays.annotations[e.entry_id].append(annotation)


def _on_config_suggestion_overridden(
    store: ProjectionStore, event: FormicOSEvent,
) -> None:
    e: ConfigSuggestionOverridden = event  # type: ignore[assignment]
    record = ConfigOverrideRecord(
        suggestion_category=e.suggestion_category,
        original_config=dict(e.original_config),
        overridden_config=dict(e.overridden_config),
        reason=e.reason,
        actor=e.actor,
        timestamp=str(e.timestamp.isoformat()),
    )
    if e.workspace_id not in store.operator_overlays.config_overrides:
        store.operator_overlays.config_overrides[e.workspace_id] = []
    store.operator_overlays.config_overrides[e.workspace_id].append(record)


# ---------------------------------------------------------------------------
# Wave 44: Forager event handlers
# ---------------------------------------------------------------------------


def _on_forage_requested(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ForageRequested = event  # type: ignore[assignment]
    ws_pending = store._pending_forage_requests.setdefault(e.workspace_id, {})
    ws_pending[e.seq] = e


def _on_forage_cycle_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ForageCycleCompleted = event  # type: ignore[assignment]
    # Look up the original request for mode/reason context
    ws_pending = store._pending_forage_requests.get(e.workspace_id, {})
    original = ws_pending.pop(e.forage_request_seq, None)

    summary = ForageCycleSummary(
        forage_request_seq=e.forage_request_seq,
        mode=original.mode if original else "unknown",
        reason=original.reason if original else "",
        queries_issued=e.queries_issued,
        pages_fetched=e.pages_fetched,
        pages_rejected=e.pages_rejected,
        entries_admitted=e.entries_admitted,
        entries_deduplicated=e.entries_deduplicated,
        duration_ms=e.duration_ms,
        error=e.error,
        timestamp=str(e.timestamp.isoformat()),
        # Wave 48: preserve linkage from originating ForageRequested
        colony_id=original.colony_id if original else "",
        thread_id=original.thread_id if original else "",
        gap_domain=original.gap_domain if original else "",
        gap_query=original.gap_query if original else "",
    )
    store.forage_cycles.setdefault(e.workspace_id, []).append(summary)


def _on_domain_strategy_updated(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: DomainStrategyUpdated = event  # type: ignore[assignment]
    ws_strategies = store.domain_strategies.setdefault(e.workspace_id, {})
    existing = ws_strategies.get(e.domain)
    # Wave 45: track level changes for operator visibility
    level_changes = 0
    if existing is not None:
        level_changes = existing.level_changes
        if existing.preferred_level != e.preferred_level:
            level_changes += 1
    ws_strategies[e.domain] = DomainStrategyProjection(
        domain=e.domain,
        preferred_level=e.preferred_level,
        success_count=e.success_count,
        failure_count=e.failure_count,
        last_updated=str(e.timestamp.isoformat()),
        reason=e.reason,
        level_changes=level_changes,
    )


def _on_forager_domain_override(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ForagerDomainOverride = event  # type: ignore[assignment]
    ws_overrides = store.domain_overrides.setdefault(e.workspace_id, {})
    if e.action == "reset":
        ws_overrides.pop(e.domain, None)
    else:
        ws_overrides[e.domain] = DomainOverrideProjection(
            domain=e.domain,
            action=e.action,
            actor=e.actor,
            reason=e.reason,
            timestamp=str(e.timestamp.isoformat()),
        )


# ---------------------------------------------------------------------------
# Wave 51 — Replay safety handlers
# ---------------------------------------------------------------------------


def _on_colony_escalated(store: ProjectionStore, event: FormicOSEvent) -> None:
    from formicos.core.events import ColonyEscalated  # noqa: PLC0415
    e: ColonyEscalated = event  # type: ignore[assignment]
    colony = store.colonies.get(e.colony_id)
    if colony is not None:
        colony.routing_override = {
            "tier": e.tier,
            "reason": e.reason,
            "set_at_round": e.set_at_round,
        }


def _on_queen_note_saved(store: ProjectionStore, event: FormicOSEvent) -> None:
    from formicos.core.events import QueenNoteSaved  # noqa: PLC0415
    e: QueenNoteSaved = event  # type: ignore[assignment]
    key = f"{e.workspace_id}/{e.thread_id}"
    notes = store.queen_notes.setdefault(key, [])
    notes.append({
        "content": e.content,
        "timestamp": e.timestamp.isoformat(),
    })
    # Cap at 50 notes per thread (same limit as queen_tools._MAX_NOTES)
    if len(notes) > 50:
        store.queen_notes[key] = notes[-50:]


_HANDLERS: dict[str, Any] = {
    "WorkspaceCreated": _on_workspace_created,
    "ThreadCreated": _on_thread_created,
    "ThreadRenamed": _on_thread_renamed,
    "ColonySpawned": _on_colony_spawned,
    "ColonyCompleted": _on_colony_completed,
    "ColonyFailed": _on_colony_failed,
    "ColonyKilled": _on_colony_killed,
    "RoundStarted": _on_round_started,
    "PhaseEntered": _on_phase_entered,
    "AgentTurnStarted": _on_agent_turn_started,
    "AgentTurnCompleted": _on_agent_turn_completed,
    "RoundCompleted": _on_round_completed,
    "MergeCreated": _on_merge_created,
    "MergePruned": _on_merge_pruned,
    "QueenMessage": _on_queen_message,
    "WorkspaceConfigChanged": _on_workspace_config_changed,
    "ApprovalRequested": _on_approval_requested,
    "ApprovalGranted": _on_approval_granted,
    "ApprovalDenied": _on_approval_denied,
    "TokensConsumed": _on_tokens_consumed,
    "ModelRegistered": _on_model_registered,
    "ModelAssignmentChanged": _on_model_assignment_changed,
    "ColonyTemplateCreated": _on_colony_template_created,
    "ColonyTemplateUsed": _on_colony_template_used,
    "ColonyNamed": _on_colony_named,
    "SkillConfidenceUpdated": _on_skill_confidence_updated,
    "SkillMerged": _on_skill_merged,
    "ColonyChatMessage": _on_colony_chat_message,
    "CodeExecuted": _on_code_executed,
    "ServiceQuerySent": _on_service_query_sent,
    "ServiceQueryResolved": _on_service_query_resolved,
    "ColonyServiceActivated": _on_colony_service_activated,
    "KnowledgeEntityCreated": _on_knowledge_entity_created,
    "KnowledgeEdgeCreated": _on_knowledge_edge_created,
    "KnowledgeEntityMerged": _on_knowledge_entity_merged,
    "ColonyRedirected": _on_colony_redirected,
    "KnowledgeAccessRecorded": _on_knowledge_access_recorded,
    "MemoryEntryCreated": _on_memory_entry_created,
    "MemoryEntryStatusChanged": _on_memory_entry_status_changed,
    "MemoryExtractionCompleted": _on_memory_extraction_completed,
    "MemoryEntryScopeChanged": _on_memory_entry_scope_changed,
    "ThreadGoalSet": _on_thread_goal_set,
    "ThreadStatusChanged": _on_thread_status_changed,
    "DeterministicServiceRegistered": lambda store, event: None,  # type: ignore[misc]  # no projection effect
    "MemoryConfidenceUpdated": _on_memory_confidence_updated,
    "WorkflowStepDefined": _on_workflow_step_defined,
    "WorkflowStepCompleted": _on_workflow_step_completed,
    "CRDTCounterIncremented": _on_crdt_counter_incremented,
    "CRDTTimestampUpdated": _on_crdt_timestamp_updated,
    "CRDTSetElementAdded": _on_crdt_set_element_added,
    "CRDTRegisterAssigned": _on_crdt_register_assigned,
    "MemoryEntryMerged": _on_memory_entry_merged,
    "MemoryEntryRefined": _on_memory_entry_refined,
    "ParallelPlanCreated": _on_parallel_plan_created,
    "KnowledgeDistilled": _on_knowledge_distilled,
    "KnowledgeEntryOperatorAction": _on_knowledge_entry_operator_action,
    "KnowledgeEntryAnnotated": _on_knowledge_entry_annotated,
    "ConfigSuggestionOverridden": _on_config_suggestion_overridden,
    "ForageRequested": _on_forage_requested,
    "ForageCycleCompleted": _on_forage_cycle_completed,
    "DomainStrategyUpdated": _on_domain_strategy_updated,
    "ForagerDomainOverride": _on_forager_domain_override,
    "ColonyEscalated": _on_colony_escalated,
    "QueenNoteSaved": _on_queen_note_saved,
}


# ---------------------------------------------------------------------------
# Wave 39 1A: Colony audit-view assembly (read-model, not a second truth store)
# ---------------------------------------------------------------------------


def build_colony_audit_view(
    colony: ColonyProjection,
    store: ProjectionStore | None = None,
) -> dict[str, Any]:
    """Assemble a structured audit narrative from replay-safe projection state.

    Returns a dict suitable for the colony-audit.ts frontend component.
    All data is derived from existing projection truth — no runtime-only
    internals are presented as exact historical fact.

    Wave 48: accepts optional ``store`` to cross-reference Forager provenance
    and memory entry metadata for richer audit attribution.
    """
    # Wave 48: build a set of Forager-sourced entry IDs and provenance map
    forager_entry_ids: set[str] = set()
    forager_provenance: dict[str, dict[str, Any]] = {}
    if store is not None:
        for entry_dict in store.memory_entries.values():
            # Forager-sourced entries have source metadata
            if entry_dict.get("web_source_url") or entry_dict.get("source_system") == "forager":
                eid = entry_dict.get("id", "")
                forager_entry_ids.add(eid)
                forager_provenance[eid] = {
                    "source_url": entry_dict.get("web_source_url", ""),
                    "source_domain": entry_dict.get("web_source_domain", ""),
                    "source_credibility": entry_dict.get("credibility_score"),
                }

    # Wave 48: find forage cycles linked to this colony
    linked_forage_cycles: list[dict[str, Any]] = []
    if store is not None:
        ws_cycles = store.forage_cycles.get(colony.workspace_id, [])
        for cycle in ws_cycles:
            if cycle.colony_id == colony.id:
                linked_forage_cycles.append({
                    "mode": cycle.mode,
                    "reason": cycle.reason,
                    "queries_issued": cycle.queries_issued,
                    "entries_admitted": cycle.entries_admitted,
                    "gap_domain": cycle.gap_domain,
                    "gap_query": cycle.gap_query,
                    "timestamp": cycle.timestamp,
                })

    # Knowledge accesses (replay-safe via KnowledgeAccessRecorded)
    knowledge_used: list[dict[str, Any]] = []
    for access in colony.knowledge_accesses:
        for item in access.get("items", []):
            item_id = item.get("id", "")
            entry: dict[str, Any] = {
                "id": item_id,
                "title": item.get("title", ""),
                "source_system": item.get("source_system", ""),
                "canonical_type": item.get("canonical_type", ""),
                "confidence": item.get("confidence"),
                "round": access.get("round"),
                "access_mode": access.get("access_mode", ""),
                # Wave 48: Forager attribution
                "forager_sourced": item_id in forager_entry_ids,
            }
            # Add provenance when available
            if item_id in forager_provenance:
                entry["provenance"] = forager_provenance[item_id]
            knowledge_used.append(entry)

    # Directives received (replay-safe via ColonyChatMessage)
    directives: list[dict[str, str]] = []
    for msg in colony.chat_messages:
        if msg.sender == "operator" or msg.event_kind == "directive":
            directives.append({
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "event_kind": msg.event_kind or "",
            })

    # Governance actions (replay-safe via chat messages and projection state)
    governance_actions: list[dict[str, Any]] = []
    for msg in colony.chat_messages:
        if msg.event_kind == "governance":
            governance_actions.append({
                "content": msg.content,
                "timestamp": msg.timestamp,
            })

    # Escalation info (replay-safe via routing_override on projection)
    escalation: dict[str, Any] | None = None
    if colony.routing_override is not None:
        escalation = {
            "tier": colony.routing_override.get("tier"),
            "reason": colony.routing_override.get("reason"),
            "set_at_round": colony.routing_override.get("set_at_round"),
        }

    # Redirect history (replay-safe via ColonyRedirected events)
    redirects = colony.redirect_history

    # Validator state (replay-derivable from round outputs)
    validator: dict[str, str] | None = None
    if colony.validator_verdict is not None:
        validator = {
            "task_type": colony.validator_task_type or "unknown",
            "verdict": colony.validator_verdict,
            "reason": colony.validator_reason or "",
        }

    # Completion state classification for tri-state display
    completion_state = _classify_completion_state(colony)

    return {
        "colony_id": colony.id,
        "task": colony.task,
        "status": colony.status,
        "completion_state": completion_state,
        "knowledge_used": knowledge_used,
        "directives": directives,
        "governance_actions": governance_actions,
        "escalation": escalation,
        "redirects": redirects,
        "validator": validator,
        "round_count": colony.round_number,
        "max_rounds": colony.max_rounds,
        "quality_score": colony.quality_score,
        "cost": colony.cost,
        "entries_extracted": colony.entries_extracted_count,
        # Wave 48: Forager-linked forage cycles for this colony
        "forage_cycles": linked_forage_cycles,
        "replay_safe_note": (
            "All data in this audit view is derived from replay-safe "
            "projection state. Exact runtime-only internals (e.g. retrieval "
            "ranking scores) are not shown because they are not persisted."
        ),
    }


def _classify_completion_state(colony: ColonyProjection) -> str:
    """Classify a colony into tri-state completion for display.

    Returns one of:
    - "validated" — completed with validator pass
    - "unvalidated" — completed without validator confirmation
    - "stalled" — failed or killed (force-halted)
    - "running" — still executing
    - "pending" — not yet started
    """
    if colony.status in ("failed", "killed"):
        return "stalled"
    if colony.status == "completed":
        if colony.validator_verdict == "pass":
            return "validated"
        return "unvalidated"
    if colony.status == "running":
        return "running"
    return "pending"


def build_thread_timeline(
    store: ProjectionStore,
    workspace_id: str,
    thread_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Build a chronological timeline of events for a thread.

    Wave 48: Thread-scoped timeline for operator audit. All data is drawn
    from replay-safe projection state.

    Returns a list of timeline entries sorted chronologically, each with:
    - type: category of entry (colony, forage, knowledge, operator, workflow)
    - timestamp: ISO timestamp
    - summary: human-readable one-line summary
    - detail: structured payload for the entry type
    """
    thread = store.get_thread(workspace_id, thread_id)
    if thread is None:
        return []

    entries: list[dict[str, Any]] = []

    # Colony lifecycle entries
    for colony in thread.colonies.values():
        # Colony spawned
        if colony.spawned_at:
            team = ", ".join(str(c) for c in colony.castes[:4])
            entries.append({
                "type": "colony",
                "subtype": "spawned",
                "timestamp": colony.spawned_at,
                "summary": f"Colony {colony.id[:12]} spawned: {colony.task[:80]}",
                "detail": {
                    "colony_id": colony.id,
                    "task": colony.task[:200],
                    "strategy": colony.strategy,
                    "castes": team,
                    "fast_path": colony.fast_path,
                },
            })
        # Colony completed/failed
        if colony.completed_at:
            state = _classify_completion_state(colony)
            entries.append({
                "type": "colony",
                "subtype": state,
                "timestamp": colony.completed_at,
                "summary": (
                    f"Colony {colony.id[:12]} {state} "
                    f"(round {colony.round_number}/{colony.max_rounds}, "
                    f"${colony.cost:.2f})"
                ),
                "detail": {
                    "colony_id": colony.id,
                    "status": colony.status,
                    "round_count": colony.round_number,
                    "quality_score": colony.quality_score,
                    "cost": colony.cost,
                    "entries_extracted": colony.entries_extracted_count,
                },
            })

    # Queen messages / operator directives in the thread
    for msg in thread.queen_messages:
        entries.append({
            "type": "operator" if msg.role == "operator" else "queen",
            "subtype": msg.role,
            "timestamp": msg.timestamp,
            "summary": f"[{msg.role}] {msg.content[:100]}",
            "detail": {
                "role": msg.role,
                "content": msg.content[:500],
            },
        })

    # Workflow steps
    for step in thread.workflow_steps:
        step_ts = step.get("created_at", step.get("timestamp", ""))
        entries.append({
            "type": "workflow",
            "subtype": "step",
            "timestamp": step_ts,
            "summary": f"Step: {step.get('description', step.get('name', ''))[:80]}",
            "detail": step,
        })

    # Forage cycles linked to this thread
    ws_cycles = store.forage_cycles.get(workspace_id, [])
    for cycle in ws_cycles:
        if cycle.thread_id == thread_id:
            entries.append({
                "type": "forage",
                "subtype": cycle.mode,
                "timestamp": cycle.timestamp,
                "summary": (
                    f"Forage ({cycle.mode}): {cycle.entries_admitted} entries "
                    f"admitted, {cycle.queries_issued} queries"
                ),
                "detail": {
                    "mode": cycle.mode,
                    "reason": cycle.reason,
                    "colony_id": cycle.colony_id,
                    "queries_issued": cycle.queries_issued,
                    "entries_admitted": cycle.entries_admitted,
                    "gap_domain": cycle.gap_domain,
                    "gap_query": cycle.gap_query,
                    "duration_ms": cycle.duration_ms,
                },
            })

    # Knowledge entries created by colonies in this thread
    thread_colony_ids = set(thread.colonies.keys())
    for entry_dict in store.memory_entries.values():
        source_colony = entry_dict.get("source_colony_id", "")
        if source_colony in thread_colony_ids:
            entries.append({
                "type": "knowledge",
                "subtype": entry_dict.get("category", "skill"),
                "timestamp": entry_dict.get("created_at", ""),
                "summary": (
                    f"Knowledge: {entry_dict.get('title', '')[:80]} "
                    f"({entry_dict.get('category', 'skill')})"
                ),
                "detail": {
                    "entry_id": entry_dict.get("id", ""),
                    "title": entry_dict.get("title", ""),
                    "category": entry_dict.get("category", ""),
                    "source_colony_id": source_colony,
                    "status": entry_dict.get("status", ""),
                },
            })

    # Sort chronologically, then limit
    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries[:limit]


__all__ = [
    "AgentProjection",
    "ApprovalProjection",
    "ChatMessageProjection",
    "ColonyOutcome",
    "ColonyProjection",
    "ConfigOverrideRecord",
    "DomainOverrideProjection",
    "DomainStrategyProjection",
    "ForageCycleSummary",
    "MergeProjection",
    "OperatorAnnotation",
    "OperatorBehaviorProjection",
    "OperatorOverlayState",
    "ProjectionStore",
    "QueenMessageProjection",
    "build_colony_audit_view",
    "build_thread_timeline",
    "RoundProjection",
    "TemplateProjection",
    "ThreadProjection",
    "WorkspaceProjection",
]
