/**
 * FormicOS frontend types - CONTRACT FILE.
 *
 * DO NOT MODIFY without operator approval.
 * These types mirror the Python models in core/types.py and core/events.py.
 * The WebSocket layer is responsible for snake_case <-> camelCase transforms.
 *
 * Locked during Phase 2 using the prototype data shapes plus the algorithm and
 * contract reference in docs/waves/phase2/algorithm_reference.md.
 */

export type NodeAddress = string;
export type ModelAddress = string;
export type NodeType = "system" | "workspace" | "thread" | "colony" | "round" | "agent_turn";
export type ColonyStatus = "pending" | "running" | "completed" | "failed" | "killed" | "queued" | "service";
export type AgentStatus = "pending" | "active" | "done" | "failed";
export type CoordinationStrategy = "stigmergic" | "sequential";
export type PhaseName = "goal" | "intent" | "route" | "execute" | "compress";
export type ContextOperation = "set" | "delete";
export type CasteId = "queen" | "coder" | "reviewer" | "researcher" | "archivist";
export type QueenMessageRole = "operator" | "queen" | "event";
export type EventKind = "spawn" | "merge" | "metric" | "pheromone" | "route";
export type SubcasteTier = "light" | "standard" | "heavy" | "flash";
export type ChatSender = "operator" | "queen" | "system" | "agent" | "service";

export interface CasteSlot {
  caste: string;
  tier: SubcasteTier;
  count: number;
}

export interface InputSource {
  type: "colony";
  colonyId: string;
  summary: string;
}

export type EventTypeName =
  | "WorkspaceCreated"
  | "ThreadCreated"
  | "ThreadRenamed"
  | "ColonySpawned"
  | "ColonyCompleted"
  | "ColonyFailed"
  | "ColonyKilled"
  | "RoundStarted"
  | "PhaseEntered"
  | "AgentTurnStarted"
  | "AgentTurnCompleted"
  | "RoundCompleted"
  | "MergeCreated"
  | "MergePruned"
  | "ContextUpdated"
  | "WorkspaceConfigChanged"
  | "ModelRegistered"
  | "ModelAssignmentChanged"
  | "ApprovalRequested"
  | "ApprovalGranted"
  | "ApprovalDenied"
  | "QueenMessage"
  | "TokensConsumed"
  | "ColonyTemplateCreated"
  | "ColonyTemplateUsed"
  | "ColonyNamed"
  | "SkillConfidenceUpdated"
  | "SkillMerged"
  | "ColonyChatMessage"
  | "CodeExecuted"
  | "ServiceQuerySent"
  | "ServiceQueryResolved"
  | "ColonyServiceActivated"
  | "KnowledgeEntityCreated"
  | "KnowledgeEdgeCreated"
  | "KnowledgeEntityMerged"
  | "ColonyRedirected"
  | "MemoryEntryCreated"
  | "MemoryEntryStatusChanged"
  | "MemoryExtractionCompleted"
  | "KnowledgeAccessRecorded"
  | "ThreadGoalSet"
  | "ThreadStatusChanged"
  | "MemoryEntryScopeChanged"
  | "DeterministicServiceRegistered"
  | "MemoryConfidenceUpdated"
  | "WorkflowStepDefined"
  | "WorkflowStepCompleted"
  | "CRDTCounterIncremented"
  | "CRDTTimestampUpdated"
  | "CRDTSetElementAdded"
  | "CRDTRegisterAssigned"
  | "MemoryEntryMerged"
  | "ParallelPlanCreated"
  | "KnowledgeDistilled"
  | "KnowledgeEntryOperatorAction"
  | "KnowledgeEntryAnnotated"
  | "ConfigSuggestionOverridden"
  | "ForageRequested"
  | "ForageCycleCompleted"
  | "DomainStrategyUpdated"
  | "ForagerDomainOverride"
  | "ColonyEscalated"
  | "QueenNoteSaved"
  | "MemoryEntryRefined";

// Configuration

export interface WorkspaceConfig {
  queenModel: ModelAddress | null;
  coderModel: ModelAddress | null;
  reviewerModel: ModelAddress | null;
  researcherModel: ModelAddress | null;
  archivistModel: ModelAddress | null;
  budget: number;
  strategy: CoordinationStrategy;
}

export interface ModelDefaults {
  queen: ModelAddress;
  coder: ModelAddress;
  reviewer: ModelAddress;
  researcher: ModelAddress;
  archivist: ModelAddress;
}

export interface ModelRecord {
  address: ModelAddress;
  provider: string;
  endpoint?: string;
  apiKeyEnv?: string;
  contextWindow: number;
  supportsTools: boolean;
  supportsVision?: boolean;
  status: "available" | "unavailable" | "no_key" | "loaded";
  costPerInputToken?: number;
  costPerOutputToken?: number;
}

export interface EmbeddingConfig {
  model: string;
  dimensions: number;
}

export interface GovernanceConfig {
  maxRoundsPerColony: number;
  stallDetectionWindow: number;
  convergenceThreshold: number;
  defaultBudgetPerColony: number;
  maxRedirectsPerColony: number;
}

export interface RoutingConfig {
  defaultStrategy: CoordinationStrategy;
  tauThreshold: number;
  kInCap: number;
  pheromoneDecayRate: number;
  pheromoneReinforceRate: number;
}

export interface SystemConfig {
  host: string;
  port: number;
  dataDir: string;
}

export interface RuntimeConfig {
  system: SystemConfig;
  models: {
    defaults: ModelDefaults;
    registry: ModelRecord[];
  };
  embedding: EmbeddingConfig;
  governance: GovernanceConfig;
  routing: RoutingConfig;
}

// Tree and runtime state

export interface TreeNode {
  id: string;
  type: NodeType;
  name: string;
  parentId: string | null;
  status?: ColonyStatus;
  children?: TreeNode[];
}

export interface Workspace extends TreeNode {
  type: "workspace";
  config: WorkspaceConfig;
  children: Thread[];
}

export interface Thread extends TreeNode {
  type: "thread";
  children: Colony[];
}

export interface AgentRecord {
  id: string;
  name: string;
  caste: CasteId;
  model: ModelAddress;
  tokens: number;
  status: AgentStatus;
  pheromone: number;
}

export interface PheromoneEdge {
  from: string;
  to: string;
  weight: number;
  trend: "up" | "down" | "stable";
}

export interface TopologyNode {
  id: string;
  label: string;
  x: number;
  y: number;
  color: string;
  caste: CasteId;
}

export interface TopologyEdge {
  from: string;
  to: string;
  weight: number;
}

export interface TopologySnapshot {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface DefenseSignal {
  name: string;
  value: number;
  threshold: number;
}

export interface DefenseState {
  composite: number;
  signals: DefenseSignal[];
}

export interface RoundAgent {
  agentId: string;
  id?: string;
  name: string;
  model: ModelAddress;
  tokens: number;
  status: AgentStatus;
  output?: string;
  toolCalls?: string[];
}

export interface RoundRecord {
  roundNumber: number;
  phase: PhaseName;
  agents: RoundAgent[];
  convergence?: number;
  cost?: number;
  durationMs?: number;
}

export interface ColonyChatEntry {
  sender: ChatSender;
  text: string;
  ts: string;
  eventKind?: string;
  sourceColony?: string;
}

export interface Colony {
  id: string;
  type: "colony";
  name: string;
  parentId: string;
  status: ColonyStatus;
  round: number;
  maxRounds: number;
  task: string;
  strategy: CoordinationStrategy;
  agents: AgentRecord[];
  convergence: number;
  cost: number;
  budgetLimit?: number;
  castes?: CasteSlot[];
  templateId?: string;
  qualityScore?: number;
  modelsUsed?: string[];
  skillsExtracted?: number;
  serviceType?: string | null;
  chatMessages?: ColonyChatEntry[];
  pheromones: PheromoneEdge[];
  topology: TopologySnapshot | null;
  defense: DefenseState | null;
  rounds: RoundRecord[];
  displayName?: string;
  activeGoal?: string;
  redirectHistory?: RedirectHistoryEntry[];
  routingOverride?: RoutingOverride | null;
  inputSources?: InputSource[];
}

export interface MergeEdge {
  id: string;
  from: string;
  to: string;
  active: boolean;
  createdBy?: "operator" | "queen";
}

export interface RedirectHistoryEntry {
  redirectIndex: number;
  newGoal: string;
  reason: string;
  trigger: string;
  round: number;
  timestamp: string;
}

export interface RoutingOverride {
  tier: "standard" | "heavy" | "max";
  reason: string;
  setAtRound: number;
}

export interface SlotDetail {
  id: number;
  state: number;
  nCtx: number;
  promptTokens: number;
}

export interface VramInfo {
  usedMb: number;
  totalMb: number;
}

export interface LocalModel {
  id: string;
  name: string;
  status: "loaded" | "available" | "error";
  vram: VramInfo | null;
  ctx: number;
  configuredCtx: number;
  maxCtx: number;
  backend: string;
  provider: string;
  slotsTotal: number;
  slotsIdle: number;
  slotsProcessing: number;
  slotDetails: SlotDetail[] | null;
}

export interface CloudEndpoint {
  id: string;
  provider: string;
  models: string[];
  status: "connected" | "no_key" | "error" | "cooldown";
  spend: number;
  limit: number;
}

export interface CasteDefinition {
  id: CasteId;
  name: string;
  icon: string;
  color: string;
  desc: string;
}

/** Wave 49: structured intent/render metadata on Queen messages. */
export type QueenMsgIntent = 'notify' | 'ask';
export type QueenMsgRender = 'text' | 'preview_card' | 'result_card';

export interface QueenChatMessage {
  role: QueenMessageRole;
  text: string;
  ts: string;
  kind?: EventKind;
  /** Wave 49: explicit intent classification from backend. */
  intent?: QueenMsgIntent;
  /** Wave 49: rendering hint — card type or plain text. */
  render?: QueenMsgRender;
  /** Wave 49: structured payload for preview/result cards. */
  meta?: Record<string, unknown>;
}

export interface QueenThread {
  id: string;
  name: string;
  workspaceId: string | null;
  messages: QueenChatMessage[];
}

export interface ApprovalRequest {
  id: string;
  type: string;
  agent: string;
  detail: string;
  colony: string;
}

export interface ProtocolStatus {
  mcp: {
    status: "active" | "inactive";
    tools: number;
    transport?: string;
    endpoint?: string;
  };
  agui: {
    status: "active" | "inactive";
    events: number;
    endpoint?: string;
    semantics?: string;
  };
  a2a: {
    status: "active" | "inactive";
    endpoint?: string;
    semantics?: string;
    note?: string;
  };
}

export interface SkillBankStats {
  total: number;
  avgConfidence: number;
}

export interface OperatorStateSnapshot {
  tree: TreeNode[];
  merges: MergeEdge[];
  queenThreads: QueenThread[];
  approvals: ApprovalRequest[];
  protocolStatus: ProtocolStatus;
  localModels: LocalModel[];
  cloudEndpoints: CloudEndpoint[];
  castes: CasteDefinition[];
  runtimeConfig: RuntimeConfig;
  skillBankStats: SkillBankStats;
}

// Events

export interface BaseEvent {
  seq: number;
  timestamp: string;
  address: NodeAddress;
  traceId?: string | null;
}

export interface WorkspaceCreatedEvent extends BaseEvent {
  type: "WorkspaceCreated";
  name: string;
  config: WorkspaceConfig;
}

export interface ThreadCreatedEvent extends BaseEvent {
  type: "ThreadCreated";
  workspaceId: string;
  name: string;
  goal?: string;
  expectedOutputs?: string[];
}

export interface ThreadRenamedEvent extends BaseEvent {
  type: "ThreadRenamed";
  workspaceId: string;
  threadId: string;
  newName: string;
  renamedBy: string;
}

export interface ColonySpawnedEvent extends BaseEvent {
  type: "ColonySpawned";
  threadId: string;
  task: string;
  castes: CasteSlot[];
  modelAssignments: Record<string, ModelAddress>;
  strategy: CoordinationStrategy;
  maxRounds: number;
  budgetLimit: number;
  templateId: string;
  inputSources: InputSource[];
  stepIndex: number;
  targetFiles?: string[];
  fastPath?: boolean;
  /** Wave 50: who initiated — queen, operator, api, or empty. */
  spawnSource?: string;
}

export interface ColonyCompletedEvent extends BaseEvent {
  type: "ColonyCompleted";
  colonyId: string;
  summary: string;
  skillsExtracted: number;
  artifacts: Record<string, unknown>[];
}

export interface ColonyFailedEvent extends BaseEvent {
  type: "ColonyFailed";
  colonyId: string;
  reason: string;
}

export interface ColonyKilledEvent extends BaseEvent {
  type: "ColonyKilled";
  colonyId: string;
  killedBy: string;
}

export interface ColonyRedirectedEvent extends BaseEvent {
  type: "ColonyRedirected";
  colonyId: string;
  redirectIndex: number;
  originalGoal: string;
  newGoal: string;
  reason: string;
  trigger: string;
  roundAtRedirect: number;
}

// Wave 26: Institutional Memory events

export interface MemoryEntryCreatedEvent extends BaseEvent {
  type: "MemoryEntryCreated";
  entry: Record<string, unknown>;
  workspaceId: string;
}

export interface MemoryEntryStatusChangedEvent extends BaseEvent {
  type: "MemoryEntryStatusChanged";
  entryId: string;
  oldStatus: string;
  newStatus: string;
  reason: string;
  workspaceId: string;
}

export interface MemoryExtractionCompletedEvent extends BaseEvent {
  type: "MemoryExtractionCompleted";
  colonyId: string;
  entriesCreated: number;
  workspaceId: string;
}

export interface KnowledgeAccessItemContract {
  id: string;
  sourceSystem: string;
  canonicalType: string;
  title: string;
  confidence: number;
  score: number;
}

export interface KnowledgeAccessRecordedEvent extends BaseEvent {
  type: "KnowledgeAccessRecorded";
  colonyId: string;
  roundNumber: number;
  workspaceId: string;
  accessMode: string;
  items: KnowledgeAccessItemContract[];
}

export interface RoundStartedEvent extends BaseEvent {
  type: "RoundStarted";
  colonyId: string;
  roundNumber: number;
}

export interface PhaseEnteredEvent extends BaseEvent {
  type: "PhaseEntered";
  colonyId: string;
  roundNumber: number;
  phase: PhaseName;
}

export interface AgentTurnStartedEvent extends BaseEvent {
  type: "AgentTurnStarted";
  colonyId: string;
  roundNumber: number;
  agentId: string;
  caste: string;
  model: ModelAddress;
}

export interface AgentTurnCompletedEvent extends BaseEvent {
  type: "AgentTurnCompleted";
  agentId: string;
  outputSummary: string;
  inputTokens: number;
  outputTokens: number;
  toolCalls: string[];
  durationMs: number;
}

export interface RoundCompletedEvent extends BaseEvent {
  type: "RoundCompleted";
  colonyId: string;
  roundNumber: number;
  convergence: number;
  cost: number;
  durationMs: number;
  validatorTaskType?: string | null;
  validatorVerdict?: string | null;
  validatorReason?: string | null;
}

export interface MergeCreatedEvent extends BaseEvent {
  type: "MergeCreated";
  edgeId: string;
  fromColony: string;
  toColony: string;
  createdBy: string;
}

export interface MergePrunedEvent extends BaseEvent {
  type: "MergePruned";
  edgeId: string;
  prunedBy: string;
}

export interface ContextUpdatedEvent extends BaseEvent {
  type: "ContextUpdated";
  key: string;
  value: string;
  operation: ContextOperation;
}

export interface WorkspaceConfigChangedEvent extends BaseEvent {
  type: "WorkspaceConfigChanged";
  workspaceId: string;
  field: string;
  oldValue: string | null;
  newValue: string | null;
}

export interface ModelRegisteredEvent extends BaseEvent {
  type: "ModelRegistered";
  providerPrefix: string;
  modelName: string;
  contextWindow: number;
  supportsTools: boolean;
}

export interface ModelAssignmentChangedEvent extends BaseEvent {
  type: "ModelAssignmentChanged";
  scope: string;
  caste: string;
  oldModel: ModelAddress | null;
  newModel: ModelAddress | null;
}

export interface ApprovalRequestedEvent extends BaseEvent {
  type: "ApprovalRequested";
  requestId: string;
  approvalType: string;
  detail: string;
  colonyId: string;
}

export interface ApprovalGrantedEvent extends BaseEvent {
  type: "ApprovalGranted";
  requestId: string;
}

export interface ApprovalDeniedEvent extends BaseEvent {
  type: "ApprovalDenied";
  requestId: string;
}

export interface QueenMessageEvent extends BaseEvent {
  type: "QueenMessage";
  threadId: string;
  role: "operator" | "queen";
  content: string;
  /** Wave 49: explicit intent classification from backend. */
  intent?: QueenMsgIntent | null;
  /** Wave 49: rendering hint — card type or plain text. */
  render?: QueenMsgRender | null;
  /** Wave 49: structured payload for preview/result cards. */
  meta?: Record<string, unknown> | null;
}

export interface TokensConsumedEvent extends BaseEvent {
  type: "TokensConsumed";
  agentId: string;
  model: ModelAddress;
  inputTokens: number;
  outputTokens: number;
  cost: number;
  reasoningTokens?: number;
  cacheReadTokens?: number;
}

export interface ColonyTemplateCreatedEvent extends BaseEvent {
  type: "ColonyTemplateCreated";
  templateId: string;
  name: string;
  description: string;
  castes: CasteSlot[];
  strategy: CoordinationStrategy;
  sourceColonyId?: string | null;
  /** Wave 50: additive fields for learned templates */
  learned?: boolean;
  taskCategory?: string;
  maxRounds?: number;
  budgetLimit?: number;
  fastPath?: boolean;
  targetFilesPattern?: string;
}

export interface ColonyTemplateUsedEvent extends BaseEvent {
  type: "ColonyTemplateUsed";
  templateId: string;
  colonyId: string;
}

export interface ColonyNamedEvent extends BaseEvent {
  type: "ColonyNamed";
  colonyId: string;
  displayName: string;
  namedBy: string;
}

export interface SkillConfidenceUpdatedEvent extends BaseEvent {
  type: "SkillConfidenceUpdated";
  colonyId: string;
  skillsUpdated: number;
  colonySucceeded: boolean;
}

export interface SkillMergedEvent extends BaseEvent {
  type: "SkillMerged";
  survivingSkillId: string;
  mergedSkillId: string;
  mergeReason: string;
}

// Wave 14 events

export interface ColonyChatMessageEvent extends BaseEvent {
  type: "ColonyChatMessage";
  colonyId: string;
  workspaceId: string;
  sender: ChatSender;
  content: string;
  agentId?: string | null;
  caste?: string | null;
  eventKind?: string | null;
  directiveType?: string | null;
  sourceColony?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CodeExecutedEvent extends BaseEvent {
  type: "CodeExecuted";
  colonyId: string;
  agentId: string;
  codePreview: string;
  trustTier: string;
  exitCode: number;
  stdoutPreview: string;
  stderrPreview: string;
  durationMs: number;
  peakMemoryMb: number;
  blocked: boolean;
}

export interface ServiceQuerySentEvent extends BaseEvent {
  type: "ServiceQuerySent";
  requestId: string;
  serviceType: string;
  targetColonyId: string;
  senderColonyId?: string | null;
  queryPreview: string;
  priority: number;
}

export interface ServiceQueryResolvedEvent extends BaseEvent {
  type: "ServiceQueryResolved";
  requestId: string;
  serviceType: string;
  sourceColonyId: string;
  responsePreview: string;
  latencyMs: number;
  artifactCount: number;
}

export interface ColonyServiceActivatedEvent extends BaseEvent {
  type: "ColonyServiceActivated";
  colonyId: string;
  workspaceId: string;
  serviceType: string;
  agentCount: number;
  skillCount: number;
  kgEntityCount: number;
}

export interface KnowledgeEntityCreatedEvent extends BaseEvent {
  type: "KnowledgeEntityCreated";
  entityId: string;
  name: string;
  entityType: string;
  workspaceId: string;
  sourceColonyId?: string | null;
}

export interface KnowledgeEdgeCreatedEvent extends BaseEvent {
  type: "KnowledgeEdgeCreated";
  edgeId: string;
  fromEntityId: string;
  toEntityId: string;
  predicate: string;
  confidence: number;
  workspaceId: string;
  sourceColonyId?: string | null;
  sourceRound?: number | null;
}

export interface KnowledgeEntityMergedEvent extends BaseEvent {
  type: "KnowledgeEntityMerged";
  survivorId: string;
  mergedId: string;
  similarityScore: number;
  mergeMethod: string;
  workspaceId: string;
}

// Wave 29 events

export interface ThreadGoalSetEvent extends BaseEvent {
  type: "ThreadGoalSet";
  workspaceId: string;
  threadId: string;
  goal: string;
  expectedOutputs: string[];
}

export interface ThreadStatusChangedEvent extends BaseEvent {
  type: "ThreadStatusChanged";
  workspaceId: string;
  threadId: string;
  oldStatus: string;
  newStatus: string;
  reason: string;
}

export interface MemoryEntryScopeChangedEvent extends BaseEvent {
  type: "MemoryEntryScopeChanged";
  entryId: string;
  oldThreadId: string;
  newThreadId: string;
  workspaceId: string;
  /** Wave 50: target workspace. Empty string = global scope. */
  newWorkspaceId?: string;
}

export interface DeterministicServiceRegisteredEvent extends BaseEvent {
  type: "DeterministicServiceRegistered";
  serviceName: string;
  description: string;
  workspaceId: string;
}

// Wave 30 events

export interface WorkflowStep {
  stepIndex: number;
  description: string;
  expectedOutputs: string[];
  templateId: string;
  strategy: string;
  status: string;
  colonyId: string;
  inputFromStep: number;
}

export interface MemoryConfidenceUpdatedEvent extends BaseEvent {
  type: "MemoryConfidenceUpdated";
  entryId: string;
  colonyId: string;
  colonySucceeded: boolean;
  oldAlpha: number;
  oldBeta: number;
  newAlpha: number;
  newBeta: number;
  newConfidence: number;
  workspaceId: string;
  threadId: string;
  reason: string;
}

export interface WorkflowStepDefinedEvent extends BaseEvent {
  type: "WorkflowStepDefined";
  workspaceId: string;
  threadId: string;
  step: WorkflowStep;
}

export interface WorkflowStepCompletedEvent extends BaseEvent {
  type: "WorkflowStepCompleted";
  workspaceId: string;
  threadId: string;
  stepIndex: number;
  colonyId: string;
  success: boolean;
  artifactsProduced: string[];
}

// Wave 33 events

export interface CRDTCounterIncrementedEvent extends BaseEvent {
  type: "CRDTCounterIncremented";
  entryId: string;
  instanceId: string;
  field: "successes" | "failures";
  delta: number;
  workspaceId: string;
}

export interface CRDTTimestampUpdatedEvent extends BaseEvent {
  type: "CRDTTimestampUpdated";
  entryId: string;
  instanceId: string;
  obsTimestamp: number;
  workspaceId: string;
}

export interface CRDTSetElementAddedEvent extends BaseEvent {
  type: "CRDTSetElementAdded";
  entryId: string;
  field: "domains" | "archived_by";
  element: string;
  workspaceId: string;
}

export interface CRDTRegisterAssignedEvent extends BaseEvent {
  type: "CRDTRegisterAssigned";
  entryId: string;
  field: "content" | "entry_type" | "decay_class";
  value: string;
  lwwTimestamp: number;
  instanceId: string;
  workspaceId: string;
}

export interface MemoryEntryMergedEvent extends BaseEvent {
  type: "MemoryEntryMerged";
  targetId: string;
  sourceId: string;
  mergedContent: string;
  mergedDomains: string[];
  mergedFrom: string[];
  contentStrategy: "keep_longer" | "keep_target" | "llm_selected";
  similarity: number;
  mergeSource: "dedup" | "federation" | "extraction";
  workspaceId: string;
}

export interface ParallelPlanCreatedEvent extends BaseEvent {
  type: "ParallelPlanCreated";
  threadId: string;
  workspaceId: string;
  plan: Record<string, unknown>;
  parallelGroups: string[][];
  reasoning: string;
  knowledgeGaps: string[];
  estimatedCost: number;
}

export interface KnowledgeDistilledEvent extends BaseEvent {
  type: "KnowledgeDistilled";
  distilledEntryId: string;
  sourceEntryIds: string[];
  workspaceId: string;
  clusterAvgWeight: number;
  distillationStrategy: string;
}

// Wave 39 — Operator co-authorship (ADR-049)

export type OperatorActionName =
  | "pin"
  | "unpin"
  | "mute"
  | "unmute"
  | "invalidate"
  | "reinstate";

export interface KnowledgeEntryOperatorActionEvent extends BaseEvent {
  type: "KnowledgeEntryOperatorAction";
  entryId: string;
  workspaceId: string;
  action: OperatorActionName;
  actor: string;
  reason: string;
}

export interface KnowledgeEntryAnnotatedEvent extends BaseEvent {
  type: "KnowledgeEntryAnnotated";
  entryId: string;
  workspaceId: string;
  annotationText: string;
  tag: string;
  actor: string;
}

export interface ConfigSuggestionOverriddenEvent extends BaseEvent {
  type: "ConfigSuggestionOverridden";
  workspaceId: string;
  suggestionCategory: string;
  originalConfig: Record<string, unknown>;
  overriddenConfig: Record<string, unknown>;
  reason: string;
  actor: string;
}

// Wave 44 — Forager events

export type ForageMode = "reactive" | "proactive" | "operator";
export type DomainOverrideAction = "trust" | "distrust" | "reset";

export interface ForageRequestedEvent extends BaseEvent {
  type: "ForageRequested";
  workspaceId: string;
  threadId: string;
  colonyId: string;
  mode: ForageMode;
  reason: string;
  gapDomain: string;
  gapQuery: string;
  maxResults: number;
}

export interface ForageCycleCompletedEvent extends BaseEvent {
  type: "ForageCycleCompleted";
  workspaceId: string;
  forageRequestSeq: number;
  queriesIssued: number;
  pagesFetched: number;
  pagesRejected: number;
  entriesAdmitted: number;
  entriesDeduplicated: number;
  durationMs: number;
  error: string;
}

export interface DomainStrategyUpdatedEvent extends BaseEvent {
  type: "DomainStrategyUpdated";
  workspaceId: string;
  domain: string;
  preferredLevel: number;
  successCount: number;
  failureCount: number;
  reason: string;
}

export interface ForagerDomainOverrideEvent extends BaseEvent {
  type: "ForagerDomainOverride";
  workspaceId: string;
  domain: string;
  action: DomainOverrideAction;
  actor: string;
  reason: string;
}

// Wave 51: Replay safety events

export interface ColonyEscalatedEvent extends BaseEvent {
  type: "ColonyEscalated";
  colonyId: string;
  tier: string;
  reason: string;
  setAtRound: number;
}

/** Private Queen note — NOT visible in operator chat. */
export interface QueenNoteSavedEvent extends BaseEvent {
  type: "QueenNoteSaved";
  workspaceId: string;
  threadId: string;
  content: string;
}

/** In-place content improvement of a knowledge entry (Wave 59, ADR-048). */
export interface MemoryEntryRefinedEvent extends BaseEvent {
  type: "MemoryEntryRefined";
  entryId: string;
  workspaceId: string;
  oldContent: string;
  newContent: string;
  newTitle: string;
  refinementSource: "extraction" | "maintenance" | "operator";
  sourceColonyId: string;
}

export type FormicOSEvent =
  | WorkspaceCreatedEvent
  | ThreadCreatedEvent
  | ThreadRenamedEvent
  | ColonySpawnedEvent
  | ColonyCompletedEvent
  | ColonyFailedEvent
  | ColonyKilledEvent
  | RoundStartedEvent
  | PhaseEnteredEvent
  | AgentTurnStartedEvent
  | AgentTurnCompletedEvent
  | RoundCompletedEvent
  | MergeCreatedEvent
  | MergePrunedEvent
  | ContextUpdatedEvent
  | WorkspaceConfigChangedEvent
  | ModelRegisteredEvent
  | ModelAssignmentChangedEvent
  | ApprovalRequestedEvent
  | ApprovalGrantedEvent
  | ApprovalDeniedEvent
  | QueenMessageEvent
  | TokensConsumedEvent
  | ColonyTemplateCreatedEvent
  | ColonyTemplateUsedEvent
  | ColonyNamedEvent
  | SkillConfidenceUpdatedEvent
  | SkillMergedEvent
  | ColonyChatMessageEvent
  | CodeExecutedEvent
  | ServiceQuerySentEvent
  | ServiceQueryResolvedEvent
  | ColonyServiceActivatedEvent
  | KnowledgeEntityCreatedEvent
  | KnowledgeEdgeCreatedEvent
  | KnowledgeEntityMergedEvent
  | ColonyRedirectedEvent
  | MemoryEntryCreatedEvent
  | MemoryEntryStatusChangedEvent
  | MemoryExtractionCompletedEvent
  | KnowledgeAccessRecordedEvent
  | ThreadGoalSetEvent
  | ThreadStatusChangedEvent
  | MemoryEntryScopeChangedEvent
  | DeterministicServiceRegisteredEvent
  | MemoryConfidenceUpdatedEvent
  | WorkflowStepDefinedEvent
  | WorkflowStepCompletedEvent
  | CRDTCounterIncrementedEvent
  | CRDTTimestampUpdatedEvent
  | CRDTSetElementAddedEvent
  | CRDTRegisterAssignedEvent
  | MemoryEntryMergedEvent
  | ParallelPlanCreatedEvent
  | KnowledgeDistilledEvent
  | KnowledgeEntryOperatorActionEvent
  | KnowledgeEntryAnnotatedEvent
  | ConfigSuggestionOverriddenEvent
  | ForageRequestedEvent
  | ForageCycleCompletedEvent
  | DomainStrategyUpdatedEvent
  | ForagerDomainOverrideEvent
  | ColonyEscalatedEvent
  | QueenNoteSavedEvent
  | MemoryEntryRefinedEvent;

// WebSocket commands

export interface SubscribeCommand {
  action: "subscribe";
  workspaceId: string;
  payload: {
    afterSeq?: number;
  };
}

export interface UnsubscribeCommand {
  action: "unsubscribe";
  workspaceId: string;
  payload: Record<string, never>;
}

export interface SendQueenMessageCommand {
  action: "send_queen_message";
  workspaceId: string;
  payload: {
    threadId: string;
    content: string;
  };
}

export interface CreateMergeCommand {
  action: "create_merge";
  workspaceId: string;
  payload: {
    fromColony: string;
    toColony: string;
    createdBy?: "operator" | "queen";
  };
}

export interface PruneMergeCommand {
  action: "prune_merge";
  workspaceId: string;
  payload: {
    edgeId: string;
  };
}

export interface BroadcastCommand {
  action: "broadcast";
  workspaceId: string;
  payload: {
    threadId: string;
    fromColony: string;
  };
}

export interface ApproveCommand {
  action: "approve";
  workspaceId: string;
  payload: {
    requestId: string;
  };
}

export interface DenyCommand {
  action: "deny";
  workspaceId: string;
  payload: {
    requestId: string;
  };
}

export interface KillColonyCommand {
  action: "kill_colony";
  workspaceId: string;
  payload: {
    colonyId: string;
    killedBy?: "operator" | "governance";
  };
}

export interface SpawnColonyCommand {
  action: "spawn_colony";
  workspaceId: string;
  payload: {
    threadId: string;
    task: string;
    castes: CasteSlot[];
    modelAssignments?: Record<string, ModelAddress>;
    strategy: CoordinationStrategy;
    maxRounds: number;
    budgetLimit: number;
  };
}

export interface UpdateConfigCommand {
  action: "update_config";
  workspaceId: string;
  payload: {
    scope: "system" | "workspace";
    targetId: string | null;
    field: string;
    value: string | number | null;
  };
}

export type WSCommand =
  | SubscribeCommand
  | UnsubscribeCommand
  | SendQueenMessageCommand
  | CreateMergeCommand
  | PruneMergeCommand
  | BroadcastCommand
  | ApproveCommand
  | DenyCommand
  | KillColonyCommand
  | SpawnColonyCommand
  | UpdateConfigCommand;

export type WSCommandAction = WSCommand["action"];

export interface WSEventMessage {
  type: "event";
  event: FormicOSEvent;
}

export interface WSStateMessage {
  type: "state";
  state: OperatorStateSnapshot;
}

export type WSMessage = WSEventMessage | WSStateMessage;
