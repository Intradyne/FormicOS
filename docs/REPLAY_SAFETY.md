# Replay Safety Classification

Which FormicOS capabilities survive a server restart, and which do not.

FormicOS is event-sourced. On startup, the SQLite event store replays all
persisted events into in-memory projections. Capabilities that emit events
survive restart. Capabilities that only mutate in-memory state do not.

---

## Classification

### Event-Sourced (Durable)

These capabilities emit events and are fully restored on replay.

| Capability | Event(s) | Notes |
|------------|----------|-------|
| Workspace/thread/colony lifecycle | `WorkspaceCreated`, `ThreadCreated`, `ColonySpawned`, `ColonyCompleted`, `ColonyFailed`, `ColonyKilled` | Core lifecycle |
| Colony redirection | `ColonyRedirected` | Goal change + reason persisted |
| Colony escalation | `ColonyEscalated` | Wave 51: tier override survives replay |
| Queen notes | `QueenNoteSaved` | Wave 51: private thread notes, not visible chat |
| Queen messages | `QueenMessage` | Visible operator chat |
| Colony chat | `ColonyChatMessage` | Agent/system/operator messages |
| Knowledge creation + status | `MemoryEntryCreated`, `MemoryEntryStatusChanged` | Full lifecycle |
| Knowledge confidence | `MemoryConfidenceUpdated` | Bayesian Beta posteriors |
| Knowledge scope promotion | `MemoryEntryScopeChanged` | Thread→workspace→global |
| Knowledge extraction | `MemoryExtractionCompleted` | Durable receipt |
| Knowledge access traces | `KnowledgeAccessRecorded` | Round-level access audit |
| Knowledge merging | `MemoryEntryMerged` | CRDT-backed with provenance |
| Knowledge graph | `KnowledgeEntityCreated`, `KnowledgeEdgeCreated`, `KnowledgeEntityMerged` | Entity + edge lifecycle |
| Knowledge distillation | `KnowledgeDistilled` | Cluster synthesis |
| Operator co-authorship | `KnowledgeEntryOperatorAction`, `KnowledgeEntryAnnotated` | Pin/mute/invalidate/annotate |
| Config changes | `WorkspaceConfigChanged`, `ModelAssignmentChanged` | Workspace + model overrides |
| Config suggestion overrides | `ConfigSuggestionOverridden` | Operator editorial |
| Template creation + usage | `ColonyTemplateCreated`, `ColonyTemplateUsed` | Includes learned templates |
| Colony naming | `ColonyNamed` | Display names |
| Merge topology | `MergeCreated`, `MergePruned` | Colony merge edges |
| Thread goals + status | `ThreadGoalSet`, `ThreadStatusChanged` | Workflow management |
| Workflow steps | `WorkflowStepDefined`, `WorkflowStepCompleted` | Queen scaffolding |
| Parallel plans | `ParallelPlanCreated` | DelegationPlan DAG |
| Approval workflow | `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied` | Governance |
| Token accounting | `TokensConsumed` | Cost tracking |
| Code execution audit | `CodeExecuted` | Sandbox audit trail |
| Service queries | `ServiceQuerySent`, `ServiceQueryResolved` | Audit-only |
| Service activation | `ColonyServiceActivated` | Colony→service transition |
| CRDT operations | `CRDTCounterIncremented`, `CRDTTimestampUpdated`, `CRDTSetElementAdded`, `CRDTRegisterAssigned` | Federation primitives |
| Forager cycles | `ForageRequested`, `ForageCycleCompleted` | Web acquisition audit |
| Domain strategy | `DomainStrategyUpdated` | Per-domain fetch preferences |
| Domain overrides | `ForagerDomainOverride` | Operator trust/distrust |
| Round execution | `RoundStarted`, `PhaseEntered`, `AgentTurnStarted`, `AgentTurnCompleted`, `RoundCompleted` | Execution audit |
| Model registry | `ModelRegistered` | Available models |
| Service registration | `DeterministicServiceRegistered` | Startup audit marker |

### File-Backed (External)

These persist outside the event log. They survive restart but are not
replayed from events.

| Capability | Storage | Notes |
|------------|---------|-------|
| Caste recipes | `config/caste_recipes.yaml` | Operator-authored |
| Colony templates | `config/templates/*.yaml` | Built-in templates |
| System settings | `config/formicos.yaml` | Model routing, tiers |
| Queen notes (backup) | `data/workspaces/*/threads/*/queen_notes.yaml` | YAML backup of event-sourced notes |
| Workspace files | `data/workspaces/*/files/` | Queen `write_workspace_file` output |

### Intentionally Ephemeral (Runtime-Only)

These are in-memory only. Lost on restart by design.

| Capability | Storage | Why Ephemeral |
|------------|---------|---------------|
| Autonomy recommendation dismissals | `projections.autonomy_recommendation_dismissals` | Recommendations regenerate each briefing cycle; stale dismissals would mask new recommendations |
| Config change proposals | `_pending_proposals` in `queen_tools.py` | 5-minute TTL; proposals expire naturally |
| Distillation candidates | `projections.distillation_candidates` | Rebuilt during maintenance cycle |
| Competing hypothesis pairs | `projections.competing_pairs` | Rebuilt during maintenance |
| Colony outcome projections | `projections.colony_outcomes` | Replay-derived from existing events |
| Operator behavior signals | `projections.operator_behavior` | Replay-derived from existing events |

### Replay-Derived (Computed)

These are not stored as events but are rebuilt from other events during replay.

| Capability | Source Events | Notes |
|------------|--------------|-------|
| Colony outcomes | `ColonySpawned` + `ColonyCompleted`/`ColonyFailed` + `TokensConsumed` | Performance analytics |
| Operator behavior | `QueenMessage` + spawn/kill patterns | Behavior signal inference |
| Co-occurrence weights | `KnowledgeAccessRecorded` | Knowledge graph edges |

---

## Frozen / Legacy Event Types

These events exist in the closed union for replay compatibility with
historical event logs. No new code should emit them.

| Event | Superseded By | Notes |
|-------|---------------|-------|
| `SkillConfidenceUpdated` | `MemoryConfidenceUpdated` | Pre-Wave 26 skill system |
| `SkillMerged` | `MemoryEntryMerged` | Pre-Wave 26 skill system |
| `ContextUpdated` | — | No projection handler; historical artifact |

---

## Naming Bridge: Memory vs Knowledge

FormicOS uses two naming conventions for the same substrate:

| Context | Term | Why |
|---------|------|-----|
| Event types | `Memory*` (`MemoryEntryCreated`, `MemoryConfidenceUpdated`, etc.) | Historical: events are frozen and cannot be renamed |
| Projection fields | `memory_entries`, `memory_store` | Follows event naming |
| REST API (current) | `/api/v1/knowledge/*` | Operator-facing: "knowledge" is clearer |
| REST API (deprecated) | `/api/v1/memory/*` | Wave 26 original; use `/knowledge` instead |
| UI labels | "Knowledge" | Wave 51: operator-facing labels use "Knowledge" |
| Internal code | Both | Event handlers use "memory"; surfaces use "knowledge" |

The underlying data model is identical. "Memory" in event/projection code
and "Knowledge" in API/UI code refer to the same entries. The event types
cannot be renamed without breaking replay of existing event logs.
