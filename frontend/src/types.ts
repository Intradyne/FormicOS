/**
 * FormicOS frontend types — mirrors docs/contracts/types.ts.
 * Snake-to-camel transform happens at the WS layer.
 */

export type NodeAddress = string;
export type ModelAddress = string;
export type NodeType = 'system' | 'workspace' | 'thread' | 'colony' | 'round' | 'agent_turn';
export type ColonyStatus = 'pending' | 'running' | 'completed' | 'failed' | 'killed' | 'queued' | 'service';
export type AgentStatus = 'pending' | 'active' | 'done' | 'failed';
export type CoordinationStrategy = 'stigmergic' | 'sequential';
export type PhaseName = 'goal' | 'intent' | 'route' | 'execute' | 'compress';
export type CasteId = 'queen' | 'coder' | 'reviewer' | 'researcher' | 'archivist';
export type QueenMessageRole = 'operator' | 'queen' | 'event';
export type EventKind = 'spawn' | 'merge' | 'metric' | 'pheromone' | 'route';
export type SubcasteTier = 'light' | 'standard' | 'heavy' | 'flash';
export type ChatSender = 'operator' | 'queen' | 'system' | 'agent' | 'service';

export interface CasteSlot {
  caste: string;
  tier: SubcasteTier;
  count: number;
}

export interface WorkspaceConfig {
  queenModel: ModelAddress | null;
  coderModel: ModelAddress | null;
  reviewerModel: ModelAddress | null;
  researcherModel: ModelAddress | null;
  archivistModel: ModelAddress | null;
  budget: number;
  strategy: CoordinationStrategy;
}

export interface TreeNode {
  id: string;
  type: NodeType;
  name: string;
  parentId: string | null;
  status?: ColonyStatus;
  children?: TreeNode[];
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
  trend: 'up' | 'down' | 'stable';
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

export interface ColonyChatMessage {
  sender: ChatSender;
  text: string;
  ts: string;
  eventKind?: string;
  sourceColony?: string;
}

export interface Colony extends TreeNode {
  type: 'colony';
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
  qualityScore: number;
  modelsUsed?: string[];
  skillsExtracted: number;
  serviceType?: string | null;
  chatMessages?: ColonyChatMessage[];
  pheromones: PheromoneEdge[];
  topology: TopologySnapshot | null;
  defense: DefenseState | null;
  rounds: RoundRecord[];
  displayName?: string;
  activeGoal?: string;
  redirectHistory?: RedirectHistoryEntry[];
  routingOverride?: RoutingOverride | null;
  validatorVerdict?: string | null;
  validatorTaskType?: string | null;
  validatorReason?: string | null;
  inputSources?: InputSource[];
  /** Client-derived: convergence values per round, populated from RoundCompleted events. */
  convergenceHistory?: number[];
  /** Wave 55: productive tool call count (write_workspace_file, code_execute, etc.) */
  productiveCalls?: number;
  /** Wave 55: observation tool call count (read_workspace_file, git_status, etc.) */
  observationCalls?: number;
  /** Wave 55: unique knowledge entries accessed */
  entriesAccessed?: number;
}

export interface MergeEdge {
  id: string;
  from: string;
  to: string;
  active: boolean;
  createdBy?: 'operator' | 'queen';
}

/** Wave 49: structured intent/render metadata on Queen messages. */
export type QueenMsgIntent = 'notify' | 'ask';
export type QueenMsgRender = 'text' | 'preview_card' | 'result_card';

export interface QueenChatMessage {
  role: QueenMessageRole;
  text: string;
  ts: string;
  kind?: EventKind;
  parsed?: boolean;
  /** Wave 49: explicit intent classification from backend. */
  intent?: QueenMsgIntent;
  /** Wave 49: rendering hint — card type or plain text. */
  render?: QueenMsgRender;
  /** Wave 49: structured payload for preview/result cards. */
  meta?: Record<string, unknown>;
}

/** Wave 49: Preview card payload shape (from Queen preview metadata). */
export interface PreviewCardMeta {
  task: string;
  team: { caste: string; tier: string; count: number }[];
  strategy: string;
  maxRounds: number;
  budgetLimit: number;
  estimatedCost: number;
  fastPath: boolean;
  targetFiles?: string[];
  threadId?: string;
  workspaceId?: string;
  /** Wave 50: Template provenance when a learned template matches. */
  template?: {
    templateId: string;
    templateName: string;
    learned?: boolean;
    successCount?: number;
    failureCount?: number;
    useCount?: number;
    taskCategory?: string;
  };
}

/** Wave 49: Result card payload shape (from Queen follow-up metadata). */
export interface ResultCardMeta {
  colonyId: string;
  task: string;
  displayName?: string;
  status: string;
  rounds: number;
  maxRounds: number;
  cost: number;
  qualityScore?: number;
  entriesExtracted?: number;
  validatorVerdict?: string;
  threadId?: string;
  total_reasoning_tokens?: number;
  total_cache_read_tokens?: number;
}

export interface QueenThread {
  id: string;
  name: string;
  workspaceId: string | null;
  messages: QueenChatMessage[];
  // Wave 29 additions:
  goal?: string;
  expectedOutputs?: string[];
  status?: 'active' | 'completed' | 'archived';
  colonyCount?: number;
  completedColonyCount?: number;
  failedColonyCount?: number;
  artifactTypesProduced?: Record<string, number>;
  // Wave 30 additions:
  workflow_steps?: WorkflowStepPreview[];
  // Wave 35 additions: parallel planning
  active_plan?: DelegationPlanPreview | null;
  parallel_groups?: string[][] | null;
  plan_reasoning?: string;
  plan_knowledge_gaps?: string[];
  plan_estimated_cost?: number;
}

/** Compact frontend view of a DelegationPlan's task list. */
export interface DelegationPlanPreview {
  tasks: DelegationTaskPreview[];
}

export interface DelegationTaskPreview {
  task_id: string;
  task: string;
  caste: string;
  colony_id?: string;
}

export interface ApprovalRequest {
  id: string;
  type: string;
  agent: string;
  detail: string;
  colony: string;
}

export interface CasteDefinition {
  id: CasteId;
  name: string;
  icon: string;
  color: string;
  desc: string;
}

export interface SlotDetail {
  id: number;
  state: number;       // 0=idle, 1=processing
  nCtx: number;        // per-slot context window
  promptTokens: number; // current tokens cached
}

export interface VramInfo {
  usedMb: number;
  totalMb: number;
}

export interface LocalModel {
  id: string;
  name: string;
  status: 'loaded' | 'available' | 'error';
  vram: VramInfo | null;   // real GPU VRAM if probed, else null
  ctx: number;
  configuredCtx: number; // from formicos.yaml, before --fit on auto-sizing
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
  status: 'connected' | 'no_key' | 'error' | 'cooldown';
  spend: number;
  limit: number;
}

export interface ModelRegistryEntry {
  address: ModelAddress;
  provider: string;
  contextWindow: number;
  supportsTools: boolean;
  status: 'available' | 'unavailable' | 'no_key' | 'loaded' | 'error';
  maxOutputTokens: number;
  timeMultiplier: number;
  toolCallMultiplier: number;
}

export interface ModelDefaults {
  queen: ModelAddress;
  coder: ModelAddress;
  reviewer: ModelAddress;
  researcher: ModelAddress;
  archivist: ModelAddress;
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
  tier: 'standard' | 'heavy' | 'max';
  reason: string;
  setAtRound: number;
}

export type InputSourceType = 'colony';

export interface InputSource {
  type: InputSourceType;
  colonyId: string;
  summary: string;
}

export interface ArtifactPreview {
  id: string;
  name: string;
  artifact_type: string;
  mime_type: string;
  source_agent_id: string;
  source_round: number;
  content_preview: string;
}

export interface ArtifactDetail extends ArtifactPreview {
  content: string;
  source_colony_id: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

// Wave 27: Unified knowledge catalog (Track B)

export type SourceSystem = 'legacy_skill_bank' | 'institutional_memory';
export type CanonicalType = 'skill' | 'experience';

export interface KnowledgeItemPreview {
  id: string;
  canonical_type: CanonicalType;
  source_system: SourceSystem;
  status: string;
  confidence: number;
  conf_alpha?: number;
  conf_beta?: number;
  last_accessed?: string;
  title: string;
  summary: string;
  content_preview: string;
  source_colony_id: string;
  source_artifact_ids: string[];
  domains: string[];
  tool_refs: string[];
  created_at: string;
  polarity: string;
  legacy_metadata: Record<string, any>;
  score: number;
  thread_id?: string;
  /** Wave 55: usage count from KnowledgeAccessRecorded events */
  usage_count?: number;
}

// Wave 46: Forager provenance for web-sourced entries
export interface ForagerProvenance {
  source_url: string;
  source_domain: string;
  source_credibility: number;
  fetch_timestamp: string;
  forager_trigger: string;
  forager_query: string;
  quality_score: number;
  fetch_level: number;
}

// Wave 37: Provenance and trust rationale metadata
export interface KnowledgeProvenance {
  source_colony_id: string;
  source_round: string;
  source_agent: string;
  source_peer: string;
  is_federated: boolean;
  created_at: string;
  workspace_id: string;
  thread_id: string;
  decay_class: string;
  forager_provenance?: ForagerProvenance;
}

export interface TrustRationale {
  admission_score: number;
  rationale: string;
  flags: string[];
  admitted: boolean;
}

export interface KnowledgeItemDetail extends KnowledgeItemPreview {
  content?: string;
  provenance?: KnowledgeProvenance;
  trust_rationale?: TrustRationale;
}

// Wave 30: Workflow step preview
export interface WorkflowStepPreview {
  step_index: number;
  description: string;
  expected_outputs: string[];
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  colony_id: string;
}

// Wave 30: Contradiction pair for operator review
export interface ContradictionPair {
  entry_a: string;
  entry_b: string;
  title_a: string;
  title_b: string;
  polarity_a: string;
  polarity_b: string;
  shared_domains: string[];
  jaccard: number;
  conf_a: number;
  conf_b: number;
  source_colony_a: string;
  source_colony_b: string;
}

export interface KnowledgeListResponse {
  items: KnowledgeItemPreview[];
  total: number;
  _deprecated?: string;
}

export interface KnowledgeSearchResponse {
  results: KnowledgeItemPreview[];
  total: number;
}

// Wave 26: Institutional memory (Track C)

export interface MemoryListResponse {
  entries: MemoryEntryPreview[];
  total: number;
}

export interface MemorySearchResponse {
  results: MemoryEntryPreview[];
  total: number;
}

export type MemoryEntryType = 'skill' | 'experience';
export type MemoryEntryStatus = 'candidate' | 'verified' | 'rejected' | 'stale';
export type MemoryEntryPolarity = 'positive' | 'negative' | 'neutral';

export interface MemoryEntryPreview {
  id: string;
  entry_type: MemoryEntryType;
  status: MemoryEntryStatus;
  polarity: MemoryEntryPolarity;
  title: string;
  content: string;
  summary: string;
  source_colony_id: string;
  source_artifact_ids: string[];
  source_round: number;
  domains: string[];
  tool_refs: string[];
  confidence: number;
  scan_status: string;
  created_at: string;
  workspace_id: string;
}

// Wave 28: Knowledge access trace types
export interface KnowledgeAccessItemPreview {
  id: string;
  source_system: string;
  canonical_type: string;
  title: string;
  confidence: number;
  conf_alpha?: number;
  conf_beta?: number;
  score: number;
}

export interface KnowledgeAccessTrace {
  round: number;
  access_mode: string;
  items: KnowledgeAccessItemPreview[];
}

export interface ColonyTranscript {
  colony_id: string;
  display_name: string;
  original_task: string;
  active_goal: string;
  status: string;
  quality_score: number;
  skills_extracted: number;
  cost: number;
  rounds_completed: number;
  final_output: string;
  artifacts: ArtifactPreview[];
  knowledge_trace?: KnowledgeAccessTrace[];
  total_reasoning_tokens?: number;
  total_cache_read_tokens?: number;
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

export interface ProtocolStatus {
  mcp: {
    status: 'active' | 'inactive';
    tools: number;
    transport?: string;
    endpoint?: string;
  };
  agui: {
    status: 'active' | 'inactive';
    events: number;
    endpoint?: string;
    semantics?: string;
  };
  a2a: {
    status: 'active' | 'inactive';
    endpoint?: string;
    semantics?: string;
    note?: string;
  };
}

export interface RuntimeConfig {
  system: { host: string; port: number; dataDir: string };
  models: { defaults: ModelDefaults; registry: ModelRegistryEntry[] };
  embedding: { model: string; dimensions: number };
  governance: GovernanceConfig;
  routing: RoutingConfig;
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

export interface SkillEntry {
  id: string;
  text_preview: string;
  confidence: number;
  conf_alpha?: number;
  conf_beta?: number;
  algorithm_version: string;
  extracted_at: string;
  source_colony: string;
  merge_count?: number;
}

export interface SuggestTeamEntry {
  caste: string;
  count: number;
  reasoning: string;
}

// Event types — Wave 11 Phase A (ADR-015)

export interface ColonyTemplateCreatedEvent {
  type: 'ColonyTemplateCreated';
  templateId: string;
  name: string;
  description: string;
  castes: CasteSlot[];
  strategy: CoordinationStrategy;
  sourceColonyId: string | null;
  /** Wave 50: additive fields for learned templates */
  learned?: boolean;
  taskCategory?: string;
  maxRounds?: number;
  budgetLimit?: number;
  fastPath?: boolean;
  targetFilesPattern?: string;
}

export interface ColonyTemplateUsedEvent {
  type: 'ColonyTemplateUsed';
  templateId: string;
  colonyId: string;
}

export interface ColonyNamedEvent {
  type: 'ColonyNamed';
  colonyId: string;
  displayName: string;
  namedBy: string;
}

export interface SkillConfidenceUpdatedEvent {
  type: 'SkillConfidenceUpdated';
  colonyId: string;
  skillsUpdated: number;
  colonySucceeded: boolean;
}

export interface SkillMergedEvent {
  type: 'SkillMerged';
  survivingSkillId: string;
  mergedSkillId: string;
  mergeReason: string;
}

export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
  castes: CasteSlot[];
  strategy: CoordinationStrategy;
  budgetLimit?: number;
  maxRounds?: number;
  sourceColonyId: string | null;
  useCount: number;
  tags?: string[];
  version?: number;
}

// WS message types
export interface WSEventMessage {
  type: 'event';
  event: { type: string; [key: string]: unknown };
}

export interface WSStateMessage {
  type: 'state';
  state: OperatorStateSnapshot;
}

export type WSMessage = WSEventMessage | WSStateMessage;

export type WSCommandAction =
  | 'subscribe' | 'unsubscribe' | 'send_queen_message'
  | 'create_merge' | 'prune_merge' | 'broadcast'
  | 'approve' | 'deny' | 'kill_colony' | 'spawn_colony' | 'update_config'
  | 'create_thread' | 'rename_colony' | 'rename_thread'
  | 'chat_colony' | 'activate_service';

export interface WSCommand {
  action: WSCommandAction;
  workspaceId: string;
  payload: Record<string, unknown>;
}

// Event type manifest — must match EVENT_TYPE_NAMES in events.py (ADR-036)
export const EVENT_NAMES = [
  'WorkspaceCreated',
  'ThreadCreated',
  'ThreadRenamed',
  'ColonySpawned',
  'ColonyCompleted',
  'ColonyFailed',
  'ColonyKilled',
  'RoundStarted',
  'PhaseEntered',
  'AgentTurnStarted',
  'AgentTurnCompleted',
  'RoundCompleted',
  'MergeCreated',
  'MergePruned',
  'ContextUpdated',
  'WorkspaceConfigChanged',
  'ModelRegistered',
  'ModelAssignmentChanged',
  'ApprovalRequested',
  'ApprovalGranted',
  'ApprovalDenied',
  'QueenMessage',
  'TokensConsumed',
  'ColonyTemplateCreated',
  'ColonyTemplateUsed',
  'ColonyNamed',
  'SkillConfidenceUpdated',
  'SkillMerged',
  'ColonyChatMessage',
  'CodeExecuted',
  'ServiceQuerySent',
  'ServiceQueryResolved',
  'ColonyServiceActivated',
  'KnowledgeEntityCreated',
  'KnowledgeEdgeCreated',
  'KnowledgeEntityMerged',
  'ColonyRedirected',
  'MemoryEntryCreated',
  'MemoryEntryStatusChanged',
  'MemoryExtractionCompleted',
  'KnowledgeAccessRecorded',
  'ThreadGoalSet',
  'ThreadStatusChanged',
  'MemoryEntryScopeChanged',
  'DeterministicServiceRegistered',
  'MemoryConfidenceUpdated',
  'WorkflowStepDefined',
  'WorkflowStepCompleted',
  'CRDTCounterIncremented',
  'CRDTTimestampUpdated',
  'CRDTSetElementAdded',
  'CRDTRegisterAssigned',
  'MemoryEntryMerged',
  'ParallelPlanCreated',
  'KnowledgeDistilled',
  'KnowledgeEntryOperatorAction',
  'KnowledgeEntryAnnotated',
  'ConfigSuggestionOverridden',
  'ForageRequested',
  'ForageCycleCompleted',
  'DomainStrategyUpdated',
  'ForagerDomainOverride',
  'ColonyEscalated',
  'QueenNoteSaved',
  'MemoryEntryRefined',
] as const;

// Wave 19 event types (ADR-032)
export interface ColonyRedirectedEvent {
  type: 'ColonyRedirected';
  colonyId: string;
  redirectIndex: number;
  originalGoal: string;
  newGoal: string;
  reason: string;
  trigger: string;
  roundAtRedirect: number;
}

// Wave 29 event types
export interface ThreadGoalSetEvent {
  type: 'ThreadGoalSet';
  workspaceId: string;
  threadId: string;
  goal: string;
  expectedOutputs: string[];
}

export interface ThreadStatusChangedEvent {
  type: 'ThreadStatusChanged';
  workspaceId: string;
  threadId: string;
  oldStatus: string;
  newStatus: string;
  reason: string;
}

export interface MemoryEntryScopeChangedEvent {
  type: 'MemoryEntryScopeChanged';
  entryId: string;
  oldThreadId: string;
  newThreadId: string;
  workspaceId: string;
  /** Wave 50: target workspace. Empty string = global scope. */
  newWorkspaceId?: string;
}

export interface DeterministicServiceRegisteredEvent {
  type: 'DeterministicServiceRegistered';
  serviceName: string;
  description: string;
  workspaceId: string;
}

// Wave 30 event types
export interface MemoryConfidenceUpdatedEvent {
  type: 'MemoryConfidenceUpdated';
  entryId: string;
  oldAlpha: number;
  oldBeta: number;
  newAlpha: number;
  newBeta: number;
  trigger: string;
  colonyId: string;
}

export interface WorkflowStepDefinedEvent {
  type: 'WorkflowStepDefined';
  workspaceId: string;
  threadId: string;
  stepIndex: number;
  description: string;
  expectedOutputs: string[];
}

export interface WorkflowStepCompletedEvent {
  type: 'WorkflowStepCompleted';
  workspaceId: string;
  threadId: string;
  stepIndex: number;
  colonyId: string;
  status: string;
  artifactTypes: string[];
}

// Wave 16 event types
export interface ThreadRenamedEvent {
  type: 'ThreadRenamed';
  workspaceId: string;
  threadId: string;
  newName: string;
  renamedBy: string;
}
