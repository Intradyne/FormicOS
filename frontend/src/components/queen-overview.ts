import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { allColonies, colonyName, providerOf, providerColor, formatCost } from '../helpers.js';
import type { TreeNode, ApprovalRequest, QueenThread, LocalModel, CasteDefinition, Colony, SkillBankStats, CloudEndpoint, RuntimeConfig } from '../types.js';
import './atoms.js';
import './queen-chat.js';
import './approval-queue.js';
import './proactive-briefing.js';
import './config-memory.js';
import './demo-guide.js';
import './learning-card.js';
import './budget-panel.js';

interface OutcomeSummary {
  total_colonies: number;
  succeeded: number;
  failed: number;
  total_cost: number;
  total_extracted: number;
  total_accessed: number;
  avg_quality: number;
  maintenance_spend: number;
  total_reasoning_tokens?: number;
  total_cache_read_tokens?: number;
}

interface ColonyOutcomeData {
  colony_id: string;
  quality_score: number;
  total_cost: number;
  entries_extracted: number;
  maintenance_source: string | null;
}

@customElement('fc-queen-overview')
export class FcQueenOverview extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; gap: 16px; height: 100%; overflow: hidden; }
    .main { flex: 1; min-height: 0; overflow: auto; padding-right: 4px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
    .title-row h1 { font-family: var(--f-display); font-size: 22px; font-weight: 700; color: var(--v-fg); letter-spacing: -0.04em; margin: 0; }
    .title-icon { font-size: 22px; filter: drop-shadow(0 0 8px var(--v-accent-glow)); }
    .subtitle { font-size: 11px; color: var(--v-fg-muted); margin: 0 0 14px; }
    .section-header {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase;
      margin: 16px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--v-border);
    }
    .resource-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px; }
    .health-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
    .ws-section { margin-bottom: 20px; }
    .ws-header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
    .colony-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .colony-card { padding: 12px; }
    .col-header { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; flex-wrap: wrap; }
    .col-name { font-family: var(--f-display); font-size: 12px; font-weight: 600; color: var(--v-fg); }
    .col-id { font-size: 8px; color: var(--v-fg-dim); margin-bottom: 2px; }
    .col-task { font-size: 10px; color: var(--v-fg-muted); margin-bottom: 5px; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .col-meta { display: flex; gap: 8px; font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-muted); font-feature-settings: 'tnum'; align-items: center; flex-wrap: wrap; }
    .progress { height: 2px; background: rgba(255,255,255,0.03); border-radius: 1px; margin-top: 7px; }
    .progress-fill { height: 100%; border-radius: 1px; transition: width 0.4s; }
    .knowledge-badge { font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 6px; background: rgba(163,130,250,0.15); color: var(--v-purple); font-weight: 600; }
    .outcome-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 6px; font-weight: 600;
    }
    .outcome-quality { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .outcome-spinning { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .outcome-cost { background: rgba(232,88,26,0.08); color: var(--v-accent); }
    .provider-dots { display: flex; gap: 2px; margin-left: auto; align-items: center; }
    .provider-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
    .posture-card { padding: 12px; display: flex; flex-direction: column; gap: 4px; }
    .posture-label { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); text-transform: uppercase; letter-spacing: 0.5px; }
    .posture-value { font-size: 13px; font-family: var(--f-mono); color: var(--v-fg); font-weight: 600; }
    .posture-detail { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted); }
    .posture-autonomy { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 9px; font-family: var(--f-mono); font-weight: 600; text-transform: uppercase; }
    .autonomy-suggest { background: rgba(91,156,245,0.12); color: var(--v-blue); }
    .autonomy-auto_notify { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .autonomy-autonomous { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .service-section { margin-bottom: 20px; }
    .service-card { padding: 12px; border-color: rgba(34,211,238,0.12); }
    .service-card:hover { border-color: rgba(34,211,238,0.25); }
    .service-icon { font-size: 10px; color: var(--v-service); }
    .service-type-label {
      font-size: 8px; font-family: var(--f-mono); font-weight: 700; color: var(--v-service);
      letter-spacing: 0.1em; text-transform: uppercase;
    }
    .chat-column { width: 320px; flex-shrink: 0; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 8px; }
    .chat-column.expanded { width: min(720px, 100%); }
    .chat-actions { display: flex; justify-content: flex-end; }
    fc-queen-chat { flex: 1; min-height: 0; }
    /* Active Plans section */
    .active-plans { margin-bottom: 16px; }
    .active-plans .section-title {
      font-size: 10px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.1em; text-transform: uppercase;
      margin-bottom: 6px;
    }
    .plan-cards { display: flex; flex-direction: column; gap: 6px; }
    .plan-card {
      display: flex; flex-direction: column; gap: 6px;
      padding: 8px 12px; border-radius: 6px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
      cursor: pointer; transition: border-color 0.15s;
    }
    .plan-header {
      display: flex; align-items: center; gap: 8px;
    }
    .plan-group-bar {
      display: flex; gap: 2px; height: 4px;
    }
    .group-segment {
      flex: 1; border-radius: 2px; min-width: 8px;
    }
    .group-segment.done { background: var(--v-success); }
    .group-segment.active { background: var(--v-blue); animation: pulse 1.5s infinite; }
    .group-segment.pending { background: rgba(255,255,255,0.06); }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .plan-card:hover { border-color: var(--v-border-hover); }
    .plan-thread-name {
      font-family: var(--f-display); font-size: 11px; font-weight: 600;
      color: var(--v-fg); flex: 1; min-width: 0;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .plan-groups {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-muted);
      font-feature-settings: 'tnum'; white-space: nowrap;
    }
    .plan-running {
      font-size: 9px; font-family: var(--f-mono);
      padding: 1px 6px; border-radius: 4px;
      background: rgba(91,156,245,0.12); color: var(--v-blue);
      white-space: nowrap;
    }
    .recent-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
    /* Wave 49: compact status header above chat in chat-first mode */
    .compact-header {
      display: flex; align-items: center; gap: 10px; padding: 8px 12px;
      border-radius: 8px; background: rgba(255,255,255,0.015);
      border: 1px solid var(--v-border); margin-bottom: 6px; flex-shrink: 0;
    }
    .ch-stat {
      display: flex; align-items: center; gap: 4px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      font-feature-settings: 'tnum';
    }
    .ch-stat .ch-val { color: var(--v-fg); font-weight: 600; }
    .ch-stat .ch-accent { color: var(--v-accent); font-weight: 600; }
    .ch-sep { width: 1px; height: 14px; background: var(--v-border); flex-shrink: 0; }
  `];

  @property({ type: Array }) tree: TreeNode[] = [];
  @property({ type: Array }) approvals: ApprovalRequest[] = [];
  @property({ type: Array }) localModels: LocalModel[] = [];
  @property({ type: Array }) cloudEndpoints: CloudEndpoint[] = [];
  @property({ type: Array }) queenThreads: QueenThread[] = [];
  @property() activeQT = '';
  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: Object }) skillBankStats: SkillBankStats = { total: 0, avgConfidence: 0 };
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  /** Wave 60.5: dashboard-first default. Chat available on demand. */
  @state() private chatExpanded = false;
  @state() private _fedPeers: { instanceId: string; trustScore: number; lastSync: string; eventsPending: number }[] = [];
  @state() private _fedLoaded = false;
  private _fedWorkspaceId = '';
  @state() private _outcomeSummary: OutcomeSummary | null = null;
  @state() private _outcomeMap: Map<string, ColonyOutcomeData> = new Map();
  @state() private _outcomesFailed = false;
  @state() private _fedFailed = false;
  private _outcomesWorkspaceId = '';

  render() {
    const cols = allColonies(this.tree);
    const running = cols.filter(c => c.status === 'running');
    const completed = cols.filter(c => c.status === 'completed');
    const totalCost = cols.reduce((a, c) => a + ((c as any).cost ?? 0), 0);
    const totalTok = cols.reduce((a, c) => a + ((c as any).agents ?? []).reduce((b: number, ag: any) => b + (ag.tokens ?? 0), 0), 0);
    const recentCompleted = completed.slice(-6).reverse();

    return html`
      <div class="main" style=${this.chatExpanded ? 'display:none' : ''}>
        <div class="title-row">
          <span class="title-icon">\u265B</span>
          <h1><fc-gradient-text>Supercolony</fc-gradient-text></h1>
          <fc-pill color="var(--v-success)" glow><fc-dot status="running" .size=${4}></fc-dot> ${running.length} active</fc-pill>
          <div style="margin-left:auto"><fc-btn variant="primary" sm @click=${() => this.re('spawn-colony-request', null)}>+ New Colony</fc-btn></div>
        </div>
        <p class="subtitle">
          ${cols.length} colonies \u00B7
          <span class="mono tnum">${(totalTok / 1000).toFixed(0)}k</span> tokens \u00B7
          <span class="mono" style="color:var(--v-accent)">${formatCost(totalCost)}</span>
          ${this.skillBankStats.total > 0 ? html`
            \u00B7 <span class="mono">${this.skillBankStats.total} knowledge entries</span> \u00B7
            avg confidence <span class="mono">${(this.skillBankStats.avgConfidence * 100).toFixed(0)}%</span>
          ` : nothing}
        </p>

        <!-- ROW 1: What needs attention -->
        <fc-proactive-briefing
          .workspaceId=${this.activeWorkspaceId}
        ></fc-proactive-briefing>

        ${this._isDemoWorkspace ? html`
          <fc-demo-guide
            .workspaceId=${this.activeWorkspaceId}
            .tree=${this.tree}
          ></fc-demo-guide>
        ` : nothing}

        <!-- ROW 2: Budget control panel (Wave 61) -->
        <fc-budget-panel .workspaceId=${this.activeWorkspaceId}></fc-budget-panel>

        ${this.approvals.length > 0 ? html`
          <fc-approval-queue .approvals=${this.approvals}
            @approve=${(e: CustomEvent) => this.re('approve', e.detail)}
            @deny=${(e: CustomEvent) => this.re('deny', e.detail)}
          ></fc-approval-queue>` : nothing}

        ${this._renderActivePlans()}

        <!-- System health -->
        <div class="health-grid">
          ${this._renderKnowledgePulse()}
          ${this._renderMaintenancePosture()}
          ${this._renderFederationSummary()}
        </div>

        <!-- Learning loop -->
        <fc-learning-card .workspaceId=${this.activeWorkspaceId}></fc-learning-card>

        <!-- ROW 3: Configuration memory -->
        <fc-config-memory
          .workspaceId=${this.activeWorkspaceId}
        ></fc-config-memory>

        ${this._renderServiceColonies(cols)}

        <!-- Running colonies by workspace -->
        ${running.length > 0 ? html`
          <div class="section-header">\u25B6 Running</div>
        ` : nothing}
        ${cols.length === 0 ? html`
          <div class="empty-state" style="height:auto;padding:40px 20px">
            <div class="empty-icon">\u265B</div>
            <div class="empty-title">Ready to orchestrate</div>
            <div class="empty-desc">Describe a task below, or pick a template to spawn your first colony.</div>
            <fc-btn variant="primary" sm @click=${() => this.re('spawn-colony-request', null)}>+ Spawn Colony</fc-btn>
          </div>
        ` : this.tree.map(ws => {
          const wsCols = allColonies([ws]).filter(c => c.status === 'running');
          if (wsCols.length === 0) return nothing;
          return html`
            <div class="ws-section">
              <div class="ws-header">
                <div class="s-label" style="margin-bottom:0"><span style="color:var(--v-accent)">\u25A3</span> ${ws.name}</div>
                <fc-pill color="var(--v-fg-dim)" sm>${(ws as any).config?.strategy ?? 'stigmergic'}</fc-pill>
              </div>
              <div class="colony-grid">
                ${wsCols.map(c => this.renderColonyCard(c as Colony))}
              </div>
            </div>`;
        })}

        <!-- ROW 3: Recent completions -->
        ${recentCompleted.length > 0 ? html`
          <div class="section-header">\u2713 Recent Completions</div>
          <div class="recent-grid">
            ${recentCompleted.map(c => this.renderColonyCard(c as Colony))}
          </div>
        ` : nothing}
      </div>
      <div class="chat-column ${this.chatExpanded ? 'expanded' : ''}">
        <div class="chat-actions">
          <fc-btn variant="ghost" sm @click=${() => { this.chatExpanded = !this.chatExpanded; }}>
            ${this.chatExpanded ? '\u25C0 Dashboard' : 'Ask the Queen \u25B6'}
          </fc-btn>
        </div>
        ${this.chatExpanded ? this._renderCompactHeader(cols, running, totalCost) : nothing}
        <fc-queen-chat .threads=${this.queenThreads} .activeThreadId=${this.activeQT}
          .runningColonies=${this._runningColonies}></fc-queen-chat>
      </div>`;
  }

  private renderColonyCard(c: Colony) {
    const sk = c.skillsExtracted ?? 0;
    const convHistory = (c as any).convergenceHistory as number[] | undefined;
    const agents = c.agents ?? [];
    const providers = [...new Set(agents.map(a => providerOf(a.model)))];
    const outcome = this._outcomeMap.get(c.id);
    const prod = c.productiveCalls ?? 0;
    const obs = c.observationCalls ?? 0;
    const totalCalls = prod + obs;
    const accessed = c.entriesAccessed ?? 0;
    return html`
      <div class="glass clickable colony-card" @click=${() => this.re('navigate', c.id)}>
        <div class="col-header">
          <fc-dot .status=${c.status ?? 'pending'} .size=${5}></fc-dot>
          <span class="col-name">${colonyName(c)}</span>
          <fc-quality-dot .quality=${c.qualityScore > 0 ? c.qualityScore : null}></fc-quality-dot>
          ${this._completionPill(c)}
          ${totalCalls > 0 ? html`<span class="outcome-badge ${prod > 0 ? 'outcome-quality' : 'outcome-spinning'}" title="${prod} productive / ${totalCalls} total tool calls">${prod}/${totalCalls} prod</span>` : nothing}
          ${accessed > 0 ? html`<span class="knowledge-badge" title="Knowledge-assisted: ${accessed} entries accessed">\u2726 assisted</span>` : nothing}
          ${sk > 0 ? html`<span class="knowledge-badge" title="${sk} knowledge extracted">${sk} extracted</span>` : nothing}
          ${outcome && c.status === 'completed' ? html`
            ${outcome.quality_score > 0 ? html`<span class="outcome-badge outcome-quality">${(outcome.quality_score * 100).toFixed(0)}%</span>` : nothing}
            <span class="outcome-badge outcome-cost">$${outcome.total_cost.toFixed(2)}</span>
            ${outcome.entries_extracted > 0 ? html`<span class="knowledge-badge">${outcome.entries_extracted} entries</span>` : nothing}
          ` : nothing}
        </div>
        ${c.displayName ? html`<div class="col-id" title="${c.id}">${c.id}</div>` : nothing}
        ${c.task ? html`<div class="col-task">${c.task}</div>` : nothing}
        <div class="col-meta">
          <span>R${c.round ?? 0}/${c.maxRounds ?? 0}</span>
          <span>${agents.length} agents</span>
          ${c.convergence > 0 ? html`
            <span style="color:${c.convergence > 0.8 ? 'var(--v-success)' : 'var(--v-fg-muted)'}">conv ${(c.convergence * 100).toFixed(0)}%</span>
            <fc-sparkline .data=${convHistory ?? []} .width=${50} .height=${14}></fc-sparkline>
          ` : nothing}
          <span style="color:${this._budgetColor((c as any).cost ?? 0, (c as any).budgetLimit ?? 0)}">$${((c as any).cost ?? 0).toFixed(2)}</span>
          <span class="provider-dots">
            ${providers.map(p => html`<span class="provider-dot" style="background:${providerColor(p === 'llama-cpp' ? 'llama-cpp/' : p === 'anthropic' ? 'anthropic/' : p === 'gemini' ? 'gemini/' : null)}" title="${p}"></span>`)}
          </span>
        </div>
        ${c.maxRounds > 0 && c.round > 0 ? html`
          <div class="progress"><div class="progress-fill" style="width:${(c.round / c.maxRounds) * 100}%;background:${c.status === 'completed' ? 'var(--v-success)' : 'var(--v-accent)'}"></div></div>
        ` : nothing}
      </div>`;
  }

  private _renderServiceColonies(cols: Colony[]) {
    const services = cols.filter(c => (c as Colony & { serviceType?: string }).serviceType != null);
    if (services.length === 0) return nothing;
    return html`
      <div class="service-section">
        <div class="ws-header">
          <div class="s-label" style="margin-bottom:0"><span style="color:var(--v-service)">\u25C6</span> Service Colonies</div>
          <fc-pill color="var(--v-service)" sm>${services.length} active</fc-pill>
        </div>
        <div class="colony-grid">
          ${services.map(c => this._renderServiceCard(c))}
        </div>
      </div>`;
  }

  private _renderServiceCard(c: Colony) {
    const sType = (c as Colony & { serviceType?: string }).serviceType ?? 'service';
    return html`
      <div class="glass clickable service-card" @click=${() => this.re('navigate', c.id)}>
        <div class="col-header">
          <span class="service-icon">\u25C6</span>
          <span class="col-name">${colonyName(c)}</span>
          <fc-pill color="var(--v-service)" sm>${sType}</fc-pill>
        </div>
        ${c.task ? html`<div class="col-task">${c.task}</div>` : nothing}
        <div class="col-meta">
          <span class="service-type-label">${sType}</span>
          <span>${(c.agents ?? []).length} agents idle</span>
          <span style="color:var(--v-service)">\u25C6 ready</span>
        </div>
      </div>`;
  }

  private get activeWorkspaceId(): string {
    return this.tree[0]?.id ?? '';
  }

  private get _isDemoWorkspace(): boolean {
    const name = this.tree[0]?.name ?? '';
    return name.toLowerCase().includes('demo');
  }

  private get _runningColonies(): { id: string; name: string }[] {
    return allColonies(this.tree)
      .filter(c => c.status === 'running')
      .map(c => ({ id: c.id, name: colonyName(c) }));
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('tree')) {
      const wsId = this.activeWorkspaceId;
      if (wsId && wsId !== this._fedWorkspaceId) {
        this._fedWorkspaceId = wsId;
        void this._fetchFederation(wsId);
      }
      if (wsId && wsId !== this._outcomesWorkspaceId) {
        this._outcomesWorkspaceId = wsId;
        void this._fetchOutcomes(wsId);
      }
    }
  }

  private async _fetchFederation(wsId: string) {
    this._fedFailed = false;
    try {
      const res = await fetch(`/api/v1/federation/status?workspace=${encodeURIComponent(wsId)}`);
      if (res.ok) {
        const data = await res.json();
        this._fedPeers = (data.peers ?? []).map((p: Record<string, unknown>) => ({
          instanceId: p.instance_id as string ?? '',
          trustScore: p.trust_score as number ?? 0,
          lastSync: p.last_sync as string ?? '',
          eventsPending: p.events_pending as number ?? 0,
        }));
      } else {
        this._fedFailed = true;
      }
    } catch { this._fedFailed = true; }
    this._fedLoaded = true;
  }

  private async _fetchOutcomes(wsId: string) {
    this._outcomesFailed = false;
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/outcomes?period=24h`);
      if (res.ok) {
        const data = await res.json();
        this._outcomeSummary = data.summary as OutcomeSummary;
        const map = new Map<string, ColonyOutcomeData>();
        for (const o of data.outcomes ?? []) {
          map.set(o.colony_id, {
            colony_id: o.colony_id,
            quality_score: o.quality_score ?? 0,
            total_cost: o.total_cost ?? 0,
            entries_extracted: o.entries_extracted ?? 0,
            maintenance_source: o.maintenance_source ?? null,
          });
        }
        this._outcomeMap = map;
      } else {
        this._outcomesFailed = true;
      }
    } catch { this._outcomesFailed = true; }
  }

  private _getMaintenancePolicy(): { autonomyLevel: string; maxColonies: number; dailyBudget: number } {
    const ws = this.tree[0] as any;
    const raw = ws?.config?.maintenance_policy;
    if (!raw) return { autonomyLevel: 'suggest', maxColonies: 2, dailyBudget: 1.0 };
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return {
      autonomyLevel: parsed.autonomy_level ?? 'suggest',
      maxColonies: parsed.max_maintenance_colonies ?? 2,
      dailyBudget: parsed.daily_maintenance_budget ?? 1.0,
    };
  }

  private _renderKnowledgePulse() {
    const s = this._outcomeSummary;
    const kb = this.skillBankStats;
    return html`
      <div class="glass posture-card">
        <span class="posture-label">Knowledge Pulse</span>
        <span class="posture-value">${kb.total} entries</span>
        <span class="posture-detail">
          conf ${(kb.avgConfidence * 100).toFixed(0)}%${s ? html`
            \u00B7 ${s.total_extracted} extracted
            \u00B7 quality ${(s.avg_quality * 100).toFixed(0)}%` : this._outcomesFailed ? html`
            \u00B7 <span style="color:var(--v-fg-dim)">outcomes unavailable</span>` : nothing}
        </span>
      </div>`;
  }

  private _renderMaintenancePosture() {
    const policy = this._getMaintenancePolicy();
    const cols = allColonies(this.tree);
    const maintenanceCols = cols.filter(c => ((c as any).tags ?? []).includes?.('maintenance') || (c.task ?? '').toLowerCase().includes('maintenance'));
    const activeCount = maintenanceCols.filter(c => c.status === 'running').length;
    const levelClass = `autonomy-${policy.autonomyLevel}`;
    const spent = this._outcomeSummary?.maintenance_spend ?? 0;
    return html`
      <div class="glass posture-card">
        <span class="posture-label">Maintenance</span>
        <div>
          <span class="posture-autonomy ${levelClass}">${policy.autonomyLevel.replace('_', ' ')}</span>
        </div>
        <span class="posture-detail">${activeCount} active \u00B7 $${spent.toFixed(2)}/$${policy.dailyBudget.toFixed(2)}</span>
      </div>`;
  }

  private _renderFederationSummary() {
    if (!this._fedLoaded) {
      return html`<div class="glass posture-card">
        <span class="posture-label">Federation</span>
        <span class="posture-detail" style="color:var(--v-fg-muted)">Loading\u2026</span>
      </div>`;
    }
    if (this._fedFailed) {
      return html`<div class="glass posture-card" style="opacity:0.6">
        <span class="posture-label">Federation</span>
        <span class="posture-detail" style="color:var(--v-fg-dim)">Unavailable</span>
      </div>`;
    }
    if (this._fedPeers.length === 0) {
      return html`<div class="glass posture-card">
        <span class="posture-label">Federation</span>
        <span class="posture-detail">No peers configured</span>
      </div>`;
    }
    const avgTrust = this._fedPeers.reduce((s, p) => s + p.trustScore, 0) / this._fedPeers.length;
    const totalPending = this._fedPeers.reduce((s, p) => s + p.eventsPending, 0);
    const lastSync = this._fedPeers.reduce((latest, p) => p.lastSync > latest ? p.lastSync : latest, '');
    const syncLabel = lastSync ? new Date(lastSync).toLocaleTimeString() : '\u2014';
    return html`<div class="glass posture-card">
      <span class="posture-label">Federation</span>
      <span class="posture-value">${this._fedPeers.length} peer${this._fedPeers.length !== 1 ? 's' : ''}</span>
      <span class="posture-detail">trust ${(avgTrust * 100).toFixed(0)}% \u00B7 ${totalPending} pending \u00B7 sync ${syncLabel}</span>
    </div>`;
  }

  /** Render compact Active Plans summary from queenThreads with parallel plans. */
  private _renderActivePlans() {
    const plans = this.queenThreads
      .filter(qt => qt.active_plan && qt.parallel_groups && qt.parallel_groups.length > 0)
      .map(qt => {
        const groups = qt.parallel_groups!;
        const totalGroups = groups.length;
        const threadNode = this.tree.flatMap(ws => ws.children ?? []).find(th => th.id === qt.id);
        const threadColonies = threadNode?.children ?? [];
        const colonyStatusMap = new Map<string, string>();
        for (const c of threadColonies) {
          colonyStatusMap.set(c.id, c.status ?? 'pending');
        }
        const taskMap = new Map<string, Record<string, string>>();
        if (qt.active_plan && Array.isArray((qt.active_plan as any).tasks)) {
          for (const t of (qt.active_plan as any).tasks) {
            taskMap.set(t.task_id, t);
          }
        }
        let completedGroups = 0;
        let runningCount = 0;
        for (const group of groups) {
          let groupDone = true;
          for (const taskId of group) {
            const taskData = taskMap.get(taskId);
            const colonyId = taskData?.colony_id;
            const status = colonyId ? colonyStatusMap.get(colonyId) : undefined;
            if (status === 'running') runningCount++;
            if (status !== 'completed') groupDone = false;
          }
          if (groupDone && group.length > 0) completedGroups++;
        }
        return { threadId: qt.id, threadName: qt.name, completedGroups, totalGroups, runningCount };
      });

    if (plans.length === 0) return nothing;

    return html`
      <div class="active-plans">
        <div class="section-title">\u25E8 Active Plans</div>
        <div class="plan-cards">
          ${plans.map(p => html`
            <div class="plan-card" @click=${() => this.re('navigate', p.threadId)}>
              <div class="plan-header">
                <span class="plan-thread-name">${p.threadName}</span>
                <span class="plan-groups">${p.completedGroups}/${p.totalGroups} groups</span>
                ${p.runningCount > 0 ? html`
                  <span class="plan-running">\u25CF ${p.runningCount} running</span>
                ` : nothing}
              </div>
              <div class="plan-group-bar">
                ${Array.from({length: p.totalGroups}, (_, i) => html`
                  <div class="group-segment ${i < p.completedGroups ? 'done' : i === p.completedGroups && p.runningCount > 0 ? 'active' : 'pending'}"></div>
                `)}
              </div>
            </div>
          `)}
        </div>
      </div>
    `;
  }

  /** Wave 39 1B: tri-state completion pill for colony cards */
  private _completionPill(c: Colony) {
    if (c.status === 'completed') {
      if ((c as any).validatorVerdict === 'pass') {
        return html`<fc-pill color="var(--v-success)" sm>\u2713 validated</fc-pill>`;
      }
      return html`<fc-pill color="var(--v-warn)" sm>\u25CB unvalidated</fc-pill>`;
    }
    if (c.status === 'failed' || c.status === 'killed') {
      return html`<fc-pill color="var(--v-danger)" sm>\u25A0 stalled</fc-pill>`;
    }
    return nothing;
  }

  private _budgetColor(cost: number, limit: number): string {
    if (limit <= 0) return 'var(--v-fg-dim)';
    const remaining = (limit - cost) / limit;
    if (remaining >= 0.70) return 'var(--v-success)';
    if (remaining >= 0.30) return 'var(--v-warn)';
    if (remaining >= 0.10) return 'var(--v-accent)';
    return 'var(--v-danger)';
  }

  private _renderProviderCard(label: string, endpoint: CloudEndpoint | undefined, color: string) {
    if (!endpoint || endpoint.status !== 'connected' || endpoint.limit <= 0) {
      return html`
        <div class="s-label" style="margin-bottom:6px">${label}</div>
        <div style="font-family:var(--f-mono);font-size:12px;color:var(--v-fg-muted)">
          ${endpoint?.status === 'no_key' ? 'No key configured' : 'Not active'}
        </div>
      `;
    }
    return html`<fc-meter label=${label} .value=${endpoint.spend} .max=${endpoint.limit} unit="$" color=${color}></fc-meter>`;
  }

  /** Wave 49: compact always-visible status header for chat-first mode. */
  private _renderCompactHeader(_cols: TreeNode[], running: TreeNode[], totalCost: number) {
    const plansCount = this.queenThreads.filter(qt =>
      qt.active_plan && qt.parallel_groups && qt.parallel_groups.length > 0
    ).length;
    return html`
      <div class="compact-header">
        <div class="ch-stat">
          <fc-dot status="running" .size=${4}></fc-dot>
          <span class="ch-val">${running.length}</span> active
        </div>
        <span class="ch-sep"></span>
        <div class="ch-stat">
          <span class="ch-accent">${formatCost(totalCost)}</span> spent
        </div>
        ${plansCount > 0 ? html`
          <span class="ch-sep"></span>
          <div class="ch-stat">
            <span class="ch-val">${plansCount}</span> plan${plansCount !== 1 ? 's' : ''}
          </div>
        ` : nothing}
        ${this.skillBankStats.total > 0 ? html`
          <span class="ch-sep"></span>
          <div class="ch-stat">
            <span class="ch-val">${this.skillBankStats.total}</span> knowledge
          </div>
        ` : nothing}
      </div>
    `;
  }

  private re(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-overview': FcQueenOverview; }
}
