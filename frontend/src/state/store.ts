/**
 * FormicOS reactive state store.
 * Derives all state from WS messages (state snapshots + incremental events).
 * Components subscribe to slices via callbacks.
 */
import { WSClient, type ConnectionState } from '../ws/client.js';
import type {
  TreeNode, MergeEdge, QueenThread, ApprovalRequest, CasteDefinition,
  LocalModel, CloudEndpoint, ProtocolStatus, RuntimeConfig,
  OperatorStateSnapshot, WSMessage, WSCommandAction, SkillBankStats,
  QueenChatMessage,
} from '../types.js';

/**
 * In-band marker prepended by queen_runtime when intent fallback is used.
 * Detected and stripped here so the UI can show a "parsed from intent" badge
 * while keeping the chat text clean.  Persisted in event content — replay safe.
 */
const PARSED_MARKER = '\u200BPARSED\u200B';

function stripParsedMarker(text: string): { text: string; parsed: boolean } {
  if (text.startsWith(PARSED_MARKER)) {
    return { text: text.slice(PARSED_MARKER.length), parsed: true };
  }
  return { text, parsed: false };
}

/** Process a QueenThread's messages to detect and strip parsed markers,
 *  and pass through Wave 49 structured metadata fields. */
function processQueenThread(qt: QueenThread): QueenThread {
  return {
    ...qt,
    messages: qt.messages.map(m => {
      if (m.role !== 'queen') return m;
      const { text, parsed } = stripParsedMarker(m.text);
      if (!parsed) return m;
      return { ...m, text, parsed } as QueenChatMessage & { parsed: boolean };
    }),
  };
}

export interface MemoryStats {
  total: number;
  /** Colony IDs that have had memory extracted this session. */
  extractedColonies: Set<string>;
  /** Wave 50: Count of entries promoted to global scope this session. */
  globalPromotions: number;
}

/** Wave 50: Learned template stats tracked from ColonyTemplateCreated events. */
export interface LearnedTemplateStats {
  total: number;
  learned: number;
  operator: number;
}

export interface StoreState {
  tree: TreeNode[];
  merges: MergeEdge[];
  queenThreads: QueenThread[];
  approvals: ApprovalRequest[];
  protocolStatus: ProtocolStatus | null;
  localModels: LocalModel[];
  cloudEndpoints: CloudEndpoint[];
  castes: CasteDefinition[];
  runtimeConfig: RuntimeConfig | null;
  skillBankStats: SkillBankStats;
  memoryStats: MemoryStats;
  templateStats: LearnedTemplateStats;
  connection: ConnectionState;
}

type Subscriber = () => void;

function emptyState(): StoreState {
  return {
    tree: [], merges: [], queenThreads: [], approvals: [],
    protocolStatus: null, localModels: [], cloudEndpoints: [],
    castes: [], runtimeConfig: null,
    skillBankStats: { total: 0, avgConfidence: 0 },
    memoryStats: { total: 0, extractedColonies: new Set(), globalPromotions: 0 },
    templateStats: { total: 0, learned: 0, operator: 0 },
    connection: 'disconnected',
  };
}

class FormicStore {
  private _state: StoreState = emptyState();
  private subs = new Set<Subscriber>();
  private ws: WSClient;

  constructor() {
    this.ws = new WSClient();
    this.ws.onMessage(msg => this.handleMessage(msg));
    this.ws.onStateChange(s => { this._state.connection = s; this.notify(); });
  }

  get state(): Readonly<StoreState> { return this._state; }

  connect(): void { this.ws.connect(); }
  disconnect(): void { this.ws.disconnect(); }

  subscribe(fn: Subscriber): () => void {
    this.subs.add(fn);
    return () => { this.subs.delete(fn); };
  }

  /** Send a WS command */
  send(action: WSCommandAction, workspaceId: string, payload: Record<string, unknown> = {}): void {
    this.ws.send(action, workspaceId, payload);
  }

  /** Convenience: subscribe to a workspace */
  subscribeWorkspace(workspaceId: string, afterSeq?: number): void {
    this.send('subscribe', workspaceId, afterSeq != null ? { afterSeq } : {});
  }

  private handleMessage(msg: WSMessage): void {
    if (msg.type === 'state') {
      this.applySnapshot(msg.state);
    } else if (msg.type === 'event') {
      this.applyEvent(msg.event);
    }
  }

  private applySnapshot(snap: OperatorStateSnapshot): void {
    this._state = {
      tree: snap.tree,
      merges: snap.merges,
      queenThreads: snap.queenThreads.map(processQueenThread),
      approvals: snap.approvals,
      protocolStatus: snap.protocolStatus,
      localModels: snap.localModels,
      cloudEndpoints: snap.cloudEndpoints,
      castes: snap.castes,
      runtimeConfig: snap.runtimeConfig,
      skillBankStats: snap.skillBankStats ?? { total: 0, avgConfidence: 0 },
      memoryStats: this._state.memoryStats,
      templateStats: this._state.templateStats,
      connection: this._state.connection,
    };
    this.notify();
  }

  private applyEvent(event: { type: string; [key: string]: unknown }): void {
    // Incremental event handling — update specific slices.
    // Full re-derivation via snapshot is preferred; events patch between snapshots.
    // Backend sends snake_case fields (Pydantic model_dump_json).
    const t = event.type as string;
    const e = event; // shorthand

    // --- Approval events ---
    if (t === 'ApprovalRequested') {
      this._state.approvals = [...this._state.approvals, {
        id: (e.request_id ?? e.requestId) as string,
        type: (e.approval_type ?? e.approvalType) as string,
        agent: (e.detail as string) ?? '',
        detail: (e.detail as string) ?? '',
        colony: (e.colony_id ?? e.colonyId) as string,
      }];
    } else if (t === 'ApprovalGranted' || t === 'ApprovalDenied') {
      const rid = (e.request_id ?? e.requestId) as string;
      this._state.approvals = this._state.approvals.filter(a => a.id !== rid);

    // --- Merge events ---
    } else if (t === 'MergeCreated') {
      this._state.merges = [...this._state.merges, {
        id: (e.edge_id ?? e.edgeId) as string,
        from: (e.from_colony ?? e.fromColony) as string,
        to: (e.to_colony ?? e.toColony) as string,
        active: true,
        createdBy: (e.created_by ?? e.createdBy) as 'operator' | 'queen' | undefined,
      }];
    } else if (t === 'MergePruned') {
      const eid = (e.edge_id ?? e.edgeId) as string;
      this._state.merges = this._state.merges.map(m =>
        m.id === eid ? { ...m, active: false } : m
      );

    // --- Queen message ---
    } else if (t === 'ThreadCreated') {
      const workspaceId = (e.workspace_id ?? e.workspaceId) as string;
      const threadId = (e.name ?? e.thread_id ?? e.threadId) as string;
      const existing = this._state.tree.some(ws =>
        ws.id === workspaceId && (ws.children ?? []).some(th => th.id === threadId)
      );
      if (!existing) {
        const newThread: TreeNode = {
          id: threadId,
          type: 'thread',
          name: threadId,
          parentId: workspaceId,
          children: [],
        };
        this._state.tree = this._state.tree.map(ws =>
          ws.id === workspaceId
            ? { ...ws, children: [...(ws.children ?? []), newThread] }
            : ws
        );
      }
      if (!this._state.queenThreads.some(qt => qt.id === threadId)) {
        this._state.queenThreads = [...this._state.queenThreads, {
          id: threadId,
          name: threadId,
          workspaceId,
          messages: [],
        }];
      }

    } else if (t === 'ThreadRenamed') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const newName = (e.new_name ?? e.newName) as string;
      this._state.tree = this._state.tree.map(ws => ({
        ...ws,
        children: (ws.children ?? []).map(th =>
          th.id === threadId ? { ...th, name: newName } : th
        ),
      }));
      this._state.queenThreads = this._state.queenThreads.map(qt =>
        qt.id === threadId ? { ...qt, name: newName } : qt
      );

    } else if (t === 'QueenMessage') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const role = e.role as 'operator' | 'queen';
      const rawContent = e.content as string;
      const { text: msgText, parsed } = role === 'queen'
        ? stripParsedMarker(rawContent)
        : { text: rawContent, parsed: false };
      const newMsg: Record<string, unknown> = {
        role, text: msgText, ts: e.timestamp as string,
      };
      if (parsed) (newMsg as any).parsed = true;
      // Wave 49: pass through structured metadata fields when present
      if (e.intent) (newMsg as any).intent = e.intent;
      if (e.render) (newMsg as any).render = e.render;
      if (e.meta) (newMsg as any).meta = e.meta;
      this._state.queenThreads = this._state.queenThreads.map(qt =>
        qt.id === threadId ? {
          ...qt, messages: [...qt.messages, newMsg as any],
        } : qt
      );

    // --- Colony lifecycle ---
    } else if (t === 'ColonySpawned') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const addr = (e.address as string) ?? '';
      const addressParts = addr.split('/');
      const workspaceIdFromAddress = addressParts.length >= 3 ? addressParts[0] : '';
      const colonyId = addr.includes('/') ? addr.split('/').pop()! : `colony-${Date.now()}`;
      const castes = (e.castes ?? []) as Array<{ caste: string; tier?: string; count?: number }>;
      const newColony: TreeNode = {
        id: colonyId,
        type: 'colony',
        name: colonyId,
        parentId: threadId,
        status: 'running',
        children: [],
      };
      // Attach colony-specific fields (Colony extends TreeNode)
      Object.assign(newColony, {
        round: 0,
        maxRounds: (e.max_rounds ?? e.maxRounds ?? 10) as number,
        task: (e.task ?? '') as string,
        strategy: (e.strategy ?? 'stigmergic') as string,
        budgetLimit: (e.budget_limit ?? e.budgetLimit ?? 5) as number,
        castes: castes.map(slot => ({
          caste: slot.caste,
          tier: (slot.tier ?? 'standard') as any,
          count: slot.count ?? 1,
        })),
        templateId: (e.template_id ?? e.templateId ?? '') as string,
        workspaceId: workspaceIdFromAddress,
        displayName: '',
        agents: [],
        convergence: 0,
        convergenceHistory: [],
        cost: 0,
        qualityScore: 0,
        skillsExtracted: 0,
        chatMessages: [],
        pheromones: [],
        topology: null,
        defense: null,
        rounds: [],
      });
      this._state.tree = this._state.tree.map(ws => ({
        ...ws,
        children: (ws.children ?? []).map(th =>
          th.id === threadId
            ? { ...th, children: [...(th.children ?? []), newColony] }
            : th
        ),
      }));

    } else if (t === 'ColonyCompleted') {
      this.updateColony((e.colony_id ?? e.colonyId) as string, c => ({ ...c, status: 'completed' as const }));
    } else if (t === 'ColonyFailed') {
      this.updateColony((e.colony_id ?? e.colonyId) as string, c => ({ ...c, status: 'failed' as const }));
    } else if (t === 'ColonyKilled') {
      this.updateColony((e.colony_id ?? e.colonyId) as string, c => ({ ...c, status: 'killed' as const }));

    // --- Colony naming (Wave 11) ---
    } else if (t === 'ColonyNamed') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const displayName = (e.display_name ?? e.displayName) as string;
      this.updateColony(colId, c => ({ ...c, displayName }));

    } else if (t === 'ColonyChatMessage') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      this.appendColonyChat(colId, {
        sender: (e.sender ?? 'system') as string,
        text: (e.content ?? '') as string,
        ts: (e.timestamp ?? '') as string,
        eventKind: (e.event_kind ?? e.eventKind) as string | undefined,
        sourceColony: (e.source_colony ?? e.sourceColony) as string | undefined,
      });

    } else if (t === 'ColonyServiceActivated') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const serviceType = (e.service_type ?? e.serviceType) as string;
      this.updateColony(colId, c => ({
        ...c,
        status: 'service' as const,
        serviceType,
      }));
      this.appendColonyChat(colId, {
        sender: 'system',
        text: `Colony activated as '${serviceType}' service with ${e.agent_count ?? e.agentCount ?? 0} agents`,
        ts: (e.timestamp ?? '') as string,
        eventKind: 'service',
      });

    } else if (t === 'ServiceQuerySent') {
      const senderColonyId = (e.sender_colony_id ?? e.senderColonyId) as string | undefined;
      const targetColonyId = (e.target_colony_id ?? e.targetColonyId) as string;
      const queryPreview = (e.query_preview ?? e.queryPreview ?? '') as string;
      const serviceType = (e.service_type ?? e.serviceType ?? 'service') as string;
      if (senderColonyId) {
        this.appendColonyChat(senderColonyId, {
          sender: 'system',
          text: `Service query sent to ${serviceType}: ${queryPreview}`,
          ts: (e.timestamp ?? '') as string,
          eventKind: 'service',
        });
      }
      this.appendColonyChat(targetColonyId, {
        sender: 'service',
        text: `Inbound query from ${senderColonyId ?? 'operator'}: ${queryPreview}`,
        ts: (e.timestamp ?? '') as string,
        eventKind: 'service',
        sourceColony: senderColonyId,
      });

    } else if (t === 'ServiceQueryResolved') {
      const sourceColonyId = (e.source_colony_id ?? e.sourceColonyId) as string;
      const responsePreview = (e.response_preview ?? e.responsePreview ?? '') as string;
      const latencyMs = Number(e.latency_ms ?? e.latencyMs ?? 0);
      this.appendColonyChat(sourceColonyId, {
        sender: 'system',
        text: `Service query resolved (${latencyMs.toFixed(0)}ms): ${responsePreview}`,
        ts: (e.timestamp ?? '') as string,
        eventKind: 'service',
      });

    // --- Round events ---
    } else if (t === 'RoundStarted') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const roundNum = (e.round_number ?? e.roundNumber) as number;
      this.updateColony(colId, c => ({ ...c, round: roundNum }));

    } else if (t === 'RoundCompleted') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const conv = (e.convergence ?? 0) as number;
      const cost = (e.cost ?? 0) as number;
      this.updateColony(colId, c => {
        const prev = (c as any).convergenceHistory ?? [];
        return {
          ...c,
          convergence: conv,
          cost: (c as any).cost + cost,
          convergenceHistory: [...prev, conv],
        };
      });

    // --- Agent events ---
    } else if (t === 'AgentTurnStarted') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const agentId = (e.agent_id ?? e.agentId) as string;
      const caste = (e.caste ?? '') as string;
      const model = (e.model ?? '') as string;
      this.updateColony(colId, c => {
        const agents = [...((c as any).agents ?? [])];
        const idx = agents.findIndex((a: any) => a.id === agentId);
        if (idx >= 0) {
          agents[idx] = { ...agents[idx], status: 'active' };
        } else {
          agents.push({ id: agentId, name: agentId, caste, model, tokens: 0, status: 'active', pheromone: 1.0 });
        }
        return { ...c, agents, topology: FormicStore.deriveTopology(agents) };
      });

    } else if (t === 'AgentTurnCompleted') {
      const agentId = (e.agent_id ?? e.agentId) as string;
      const inTok = (e.input_tokens ?? e.inputTokens ?? 0) as number;
      const outTok = (e.output_tokens ?? e.outputTokens ?? 0) as number;
      const colId = this.colonyIdFromEvent(e);
      if (colId) {
        this.updateColony(colId, c => {
          const agents = [...((c as any).agents ?? [])];
          const idx = agents.findIndex((a: any) => a.id === agentId);
          if (idx < 0) return c;
          agents[idx] = { ...agents[idx], status: 'done', tokens: (agents[idx].tokens ?? 0) + inTok + outTok };
          return { ...c, agents };
        });
      } else {
        // Fallback for legacy events that lack address/colony info.
        this._state.tree = this._state.tree.map(ws => ({
          ...ws,
          children: (ws.children ?? []).map(th => ({
            ...th,
            children: (th.children ?? []).map(col => {
              const agents = (col as any).agents;
              if (!agents) return col;
              const idx = agents.findIndex((a: any) => a.id === agentId);
              if (idx < 0) return col;
              const updated = [...agents];
              updated[idx] = { ...updated[idx], status: 'done', tokens: (updated[idx].tokens ?? 0) + inTok + outTok };
              return { ...col, agents: updated };
            }),
          })),
        }));
      }

    // --- Config events ---
    } else if (t === 'WorkspaceConfigChanged') {
      const wsId = (e.workspace_id ?? e.workspaceId) as string;
      const field = (e.field ?? '') as string;
      const newVal = e.new_value ?? e.newValue ?? null;
      this._state.tree = this._state.tree.map(ws => {
        if (ws.id !== wsId) return ws;
        const cfg = { ...((ws as any).config ?? {}) };
        cfg[field] = newVal;
        return { ...ws, config: cfg };
      });

    } else if (t === 'ModelAssignmentChanged') {
      const scope = (e.scope ?? '') as string;
      const caste = (e.caste ?? '') as string;
      const newModel = e.new_model ?? e.newModel ?? null;
      const field = `${caste}_model`;
      this._state.tree = this._state.tree.map(ws => {
        if (ws.id !== scope && scope !== 'system') return ws;
        const cfg = { ...((ws as any).config ?? {}) };
        cfg[field] = newModel;
        return { ...ws, config: cfg };
      });

    // --- Token cost ---
    } else if (t === 'TokensConsumed') {
      const cost = (e.cost ?? 0) as number;
      const agentId = (e.agent_id ?? e.agentId) as string;
      const actualModel = (e.model ?? '') as string;
      const colId = this.colonyIdFromEvent(e);
      if (colId) {
        this.updateColony(colId, c => {
          const agents = [...(((c as any).agents ?? []) as Array<Record<string, unknown>>)];
          const idx = agents.findIndex((a: any) => a.id === agentId);
          if (idx < 0) return c;
          agents[idx] = {
            ...agents[idx],
            model: actualModel || agents[idx].model,
          };
          return {
            ...c,
            agents,
            cost: ((c as any).cost ?? 0) + cost,
          };
        });
      } else {
        // Fallback for legacy events that lack address/colony info.
        this._state.tree = this._state.tree.map(ws => ({
          ...ws,
          children: (ws.children ?? []).map(th => ({
            ...th,
            children: (th.children ?? []).map(col => {
              const agents = [...((((col as any).agents ?? []) as Array<Record<string, unknown>>))];
              const idx = agents.findIndex((a: any) => a.id === agentId);
              if (idx < 0) return col;
              agents[idx] = {
                ...agents[idx],
                model: actualModel || agents[idx].model,
              };
              return {
                ...col,
                agents,
                cost: ((col as any).cost ?? 0) + cost,
              };
            }),
          })),
        }));
      }

    // --- Thread goal/workflow/plan events (Wave 29-35) ---
    } else if (t === 'ThreadGoalSet') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const goal = (e.goal ?? '') as string;
      const expectedOutputs = (e.expected_outputs ?? e.expectedOutputs ?? []) as string[];
      this._state.queenThreads = this._state.queenThreads.map(qt =>
        qt.id === threadId ? { ...qt, goal, expectedOutputs, status: 'active' as const } : qt
      );

    } else if (t === 'ThreadStatusChanged') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const newStatus = (e.new_status ?? e.newStatus) as 'active' | 'completed' | 'archived';
      this._state.queenThreads = this._state.queenThreads.map(qt =>
        qt.id === threadId ? { ...qt, status: newStatus } : qt
      );

    } else if (t === 'WorkflowStepDefined') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const step = {
        step_index: (e.step_index ?? e.stepIndex ?? 0) as number,
        description: (e.description ?? '') as string,
        expected_outputs: (e.expected_outputs ?? e.expectedOutputs ?? []) as string[],
        status: 'pending' as const,
        colony_id: '',
      };
      this._state.queenThreads = this._state.queenThreads.map(qt => {
        if (qt.id !== threadId) return qt;
        const steps = [...(qt.workflow_steps ?? [])];
        const idx = steps.findIndex(s => s.step_index === step.step_index);
        if (idx >= 0) steps[idx] = step; else steps.push(step);
        steps.sort((a, b) => a.step_index - b.step_index);
        return { ...qt, workflow_steps: steps };
      });

    } else if (t === 'WorkflowStepCompleted') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const stepIndex = (e.step_index ?? e.stepIndex ?? 0) as number;
      const colonyId = (e.colony_id ?? e.colonyId ?? '') as string;
      const status = (e.status ?? 'completed') as 'completed' | 'failed' | 'skipped';
      this._state.queenThreads = this._state.queenThreads.map(qt => {
        if (qt.id !== threadId) return qt;
        const steps = (qt.workflow_steps ?? []).map(s =>
          s.step_index === stepIndex ? { ...s, status, colony_id: colonyId || s.colony_id } : s
        );
        return { ...qt, workflow_steps: steps };
      });

    } else if (t === 'ParallelPlanCreated') {
      const threadId = (e.thread_id ?? e.threadId) as string;
      const plan = (e.plan ?? null) as Record<string, unknown> | null;
      const parallelGroups = (e.parallel_groups ?? e.parallelGroups ?? []) as string[][];
      const reasoning = (e.reasoning ?? '') as string;
      const knowledgeGaps = (e.knowledge_gaps ?? e.knowledgeGaps ?? []) as string[];
      const estimatedCost = (e.estimated_cost ?? e.estimatedCost ?? 0) as number;
      this._state.queenThreads = this._state.queenThreads.map(qt =>
        qt.id === threadId ? {
          ...qt,
          active_plan: plan ? { tasks: ((plan as any).tasks ?? []) } : null,
          parallel_groups: parallelGroups,
          plan_reasoning: reasoning,
          plan_knowledge_gaps: knowledgeGaps,
          plan_estimated_cost: estimatedCost,
        } : qt
      );

    // --- Memory events (Wave 26) ---
    } else if (t === 'MemoryEntryCreated') {
      this._state.memoryStats = {
        total: this._state.memoryStats.total + 1,
        extractedColonies: this._state.memoryStats.extractedColonies,
      };
    } else if (t === 'MemoryExtractionCompleted') {
      const colId = (e.colony_id ?? e.colonyId) as string;
      const count = (e.entries_created ?? e.entriesCreated ?? 0) as number;
      const updated = new Set(this._state.memoryStats.extractedColonies);
      updated.add(colId);
      this._state.memoryStats = {
        ...this._state.memoryStats,
        total: this._state.memoryStats.total,
        extractedColonies: updated,
      };
      // Update the colony's memory extraction count in-tree if possible
      if (count > 0) {
        this.updateColony(colId, c => ({
          ...c,
          memoryEntriesExtracted: count,
        }));
      }

    // --- Wave 50: Template stats ---
    } else if (t === 'ColonyTemplateCreated') {
      const isLearned = (e.learned ?? false) as boolean;
      this._state.templateStats = {
        total: this._state.templateStats.total + 1,
        learned: this._state.templateStats.learned + (isLearned ? 1 : 0),
        operator: this._state.templateStats.operator + (isLearned ? 0 : 1),
      };

    // --- Wave 50: Global scope promotion tracking ---
    } else if (t === 'MemoryEntryScopeChanged') {
      const newWorkspaceId = (e.new_workspace_id ?? e.newWorkspaceId) as string | undefined;
      // Empty string new_workspace_id = promoted to global scope
      if (newWorkspaceId === '') {
        this._state.memoryStats = {
          ...this._state.memoryStats,
          globalPromotions: this._state.memoryStats.globalPromotions + 1,
        };
      }
    }

    this.notify();
  }

  /** Immutably update a colony by id within the tree, cloning at each level for Lit reactivity. */
  private updateColony(colonyId: string, updater: (colony: TreeNode) => TreeNode): void {
    this._state.tree = this._state.tree.map(ws => ({
      ...ws,
      children: (ws.children ?? []).map(th => ({
        ...th,
        children: (th.children ?? []).map(col =>
          col.id === colonyId ? updater(col) : col
        ),
      })),
    }));
  }

  private appendColonyChat(colonyId: string, message: Record<string, unknown>): void {
    this.updateColony(colonyId, c => ({
      ...c,
      chatMessages: [...(((c as any).chatMessages ?? []) as Record<string, unknown>[]), message],
    }));
  }

  private colonyIdFromEvent(event: { [key: string]: unknown }): string | null {
    const explicit = (event.colony_id ?? event.colonyId) as string | undefined;
    if (explicit) return explicit;
    const address = event.address as string | undefined;
    if (!address) return null;
    const parts = address.split('/');
    return parts.length >= 3 ? parts[parts.length - 1] : null;
  }

  /** Derive a basic topology layout from agents (circle arrangement, no edges).
   *  Matches the server-side _build_topology in view_state.py.
   *  Edges require pheromone data which only arrives in full snapshots. */
  private static deriveTopology(agents: any[]): { nodes: any[]; edges: any[] } | null {
    if (agents.length === 0) return null;
    const colors: Record<string, string> = {
      queen: '#E8581A', coder: '#2DD4A8', reviewer: '#A78BFA',
      researcher: '#5B9CF5', archivist: '#F5B731',
    };
    const cx = 200, cy = 135, radius = 100;
    const nodes = agents.map((a: any, i: number) => {
      const angle = (2 * Math.PI * i) / agents.length - Math.PI / 2;
      return {
        id: a.id,
        label: (a.caste || '').toUpperCase(),
        x: Math.round(cx + radius * Math.cos(angle)),
        y: Math.round(cy + radius * Math.sin(angle)),
        color: colors[a.caste] || '#888888',
        caste: a.caste,
      };
    });
    return { nodes, edges: [] };
  }

  private notify(): void {
    this.subs.forEach(fn => fn());
  }
}

/** Singleton store instance */
export const store = new FormicStore();

// Tree utility functions
export function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      const found = findNode(n.children, id);
      if (found) return found;
    }
  }
  return null;
}

export function allColonies(nodes: TreeNode[]): TreeNode[] {
  const result: TreeNode[] = [];
  for (const n of nodes) {
    if (n.type === 'colony') result.push(n);
    if (n.children) result.push(...allColonies(n.children));
  }
  return result;
}

export function breadcrumb(nodes: TreeNode[], id: string, path: TreeNode[] = []): TreeNode[] | null {
  for (const n of nodes) {
    const next = [...path, n];
    if (n.id === id) return next;
    if (n.children) {
      const found = breadcrumb(n.children, id, next);
      if (found) return found;
    }
  }
  return null;
}
