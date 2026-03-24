# Wave 14 Event Struct Definitions (Stream A Reference)

**Purpose:** Exact Pydantic event structs for Stream A to add to `core/events.py`.
All follow the existing `EventEnvelope` subclass pattern with `Literal` discriminator.

---

## Pattern to follow

Every event in `core/events.py` uses this exact pattern:

```python
class EventName(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["EventName"] = "EventName"
    field_name: type = Field(..., description="...")
```

The `FrozenConfig = ConfigDict(frozen=True, extra="forbid")` is already defined.
The discriminated union is `Annotated[Union[...], Field(discriminator="type")]`.
After adding new events, append them to the `Union` and the `__all__` list.

---

## Modified event

### ColonySpawned (replace existing)

```python
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
```

Import: `from formicos.core.types import CasteSlot`

---

## 8 new events

### ColonyChatMessage

```python
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
```

### CodeExecuted

```python
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
```

### ServiceQuerySent

```python
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
    priority: str = Field(
        default="normal", description="normal or high.",
    )
```

### ServiceQueryResolved

```python
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
```

### ColonyServiceActivated

```python
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
```

### KnowledgeEntityCreated

```python
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
```

### KnowledgeEdgeCreated

```python
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
```

### KnowledgeEntityMerged

```python
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
```

---

## Union update

After adding all 8 events, update the `FormicOSEvent` union:

```python
FormicOSEvent: TypeAlias = Annotated[
    Union[
        # ... existing 27 events ...
        ColonyChatMessage,
        CodeExecuted,
        ServiceQuerySent,
        ServiceQueryResolved,
        ColonyServiceActivated,
        KnowledgeEntityCreated,
        KnowledgeEdgeCreated,
        KnowledgeEntityMerged,
    ],
    Field(discriminator="type"),
]
```

Add all 8 to `__all__`.

---

## Import needed in events.py

```python
from formicos.core.types import CasteSlot
```

This is the only cross-module import the event changes require.
The `ChatSender`, `SubcasteTier` etc. are string enums -- events reference them
by string value, not by type import. Only `CasteSlot` is needed because
`ColonySpawned.castes` is typed as `list[CasteSlot]`.
