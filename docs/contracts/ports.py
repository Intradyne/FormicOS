"""FormicOS Port Interfaces - CONTRACT FILE.

DO NOT MODIFY without operator approval. Coders implement AGAINST these
interfaces, never modify them. If a port is wrong, STOP and flag it.

These are typing.Protocol definitions (ADR-004). Adapters satisfy them
by implementing the right method signatures. No inheritance required.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from formicos.core.events import FormicOSEvent
    from formicos.core.types import (
        AgentConfig,
        ColonyContext,
        LLMChunk,
        LLMMessage,
        LLMResponse,
        LLMToolSpec,
        SandboxExecutionResult,
        VectorDocument,
        VectorSearchHit,
    )


EventTypeName = Literal[
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

PheromoneWeights = Mapping[tuple[str, str], float]


# --- LLM Port ---


class LLMPort(Protocol):
    """Provider-neutral completion interface used by engine and Queen flows."""

    async def complete(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Return a single structured completion."""
        ...

    async def stream(
        self,
        model: str,
        messages: Sequence[LLMMessage],
        tools: Sequence[LLMToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        """Yield incremental chunks and a final completion marker."""
        ...


# --- Event Store Port ---


class EventStorePort(Protocol):
    """Append-only event log with replay/query support."""

    async def append(self, event: FormicOSEvent) -> int:
        """Store one immutable event and return its assigned sequence number."""
        ...

    async def query(
        self,
        address: str | None = None,
        event_type: EventTypeName | None = None,
        after_seq: int = 0,
        limit: int = 1000,
    ) -> list[FormicOSEvent]:
        """Return events filtered by address prefix, type, and lower sequence bound."""
        ...

    async def replay(self, after_seq: int = 0) -> AsyncIterator[FormicOSEvent]:
        """Stream events in sequence order for projection rebuilds and subscribers."""
        ...


# --- Vector Store Port ---


class VectorPort(Protocol):
    """Semantic memory store for durable compressed colony output."""

    async def upsert(self, collection: str, docs: Sequence[VectorDocument]) -> int:
        """Insert or update documents and return the number of upserted records."""
        ...

    async def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
    ) -> list[VectorSearchHit]:
        """Return ranked semantic matches for a natural-language query."""
        ...

    async def delete(self, collection: str, ids: Sequence[str]) -> int:
        """Delete documents by identifier and return the number removed."""
        ...


# --- Coordination Strategy Port ---


class CoordinationStrategy(Protocol):
    """Convert colony context into ordered agent execution groups."""

    async def resolve_topology(
        self,
        agents: Sequence[AgentConfig],
        context: ColonyContext,
        pheromone_weights: PheromoneWeights | None = None,
    ) -> list[list[str]]:
        """Return ordered execution groups where each inner list may run in parallel."""
        ...


# --- Sandbox Port (deferred - interface only, no adapter in alpha) ---


class SandboxPort(Protocol):
    """Deferred execution sandbox for future post-alpha code-isolation work."""

    async def create(self) -> str:
        """Create a sandbox instance and return its identifier."""
        ...

    async def execute(self, sandbox_id: str, code: str) -> SandboxExecutionResult:
        """Execute code in a sandbox and return structured stdout/stderr/exit metadata."""
        ...

    async def destroy(self, sandbox_id: str) -> None:
        """Destroy a sandbox instance."""
        ...


__all__ = [
    "CoordinationStrategy",
    "EventStorePort",
    "EventTypeName",
    "LLMPort",
    "PheromoneWeights",
    "SandboxPort",
    "VectorPort",
]
