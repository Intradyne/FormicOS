import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { allColonies, formatCost } from '../helpers.js';
import type { TreeNode, ApprovalRequest, QueenThread, LocalModel, CasteDefinition, SkillBankStats, CloudEndpoint, RuntimeConfig } from '../types.js';
import './atoms.js';
import './queen-chat.js';
import './approval-queue.js';
import './proactive-briefing.js';
import './demo-guide.js';
import './budget-panel.js';
import './project-plan-card.js';
import './queen-display-board.js';
import './queen-tool-stats.js';
import './queen-continuations.js';
import './queen-autonomy-card.js';
import './queen-budget-viz.js';
import './queen-overrides.js';
import './operating-procedures-editor.js';
import './queen-journal-panel.js';

@customElement('fc-queen-overview')
export class FcQueenOverview extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; gap: 16px; height: 100%; overflow: hidden; }
    .main { flex: 1; min-height: 0; overflow: auto; padding-right: 4px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
    .title-row h1 { font-family: var(--f-display); font-size: 22px; font-weight: 700; color: var(--v-fg); letter-spacing: -0.04em; margin: 0; }
    .title-icon { font-size: 22px; filter: drop-shadow(0 0 8px var(--v-accent-glow)); }
    .subtitle { font-size: 11px; color: var(--v-fg-muted); margin: 0 0 14px; }
    .health-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
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

  render() {
    const cols = allColonies(this.tree);
    const running = cols.filter(c => c.status === 'running');
    const totalCost = cols.reduce((a, c) => a + ((c as any).cost ?? 0), 0);
    const totalTok = cols.reduce((a, c) => a + ((c as any).agents ?? []).reduce((b: number, ag: any) => b + (ag.tokens ?? 0), 0), 0);

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

        <!-- Display board: prioritized observations -->
        <fc-queen-display-board
          .workspaceId=${this.activeWorkspaceId}
        ></fc-queen-display-board>

        <!-- Proactive briefing -->
        <fc-proactive-briefing
          .workspaceId=${this.activeWorkspaceId}
        ></fc-proactive-briefing>

        ${this._isDemoWorkspace ? html`
          <fc-demo-guide
            .workspaceId=${this.activeWorkspaceId}
            .tree=${this.tree}
          ></fc-demo-guide>
        ` : nothing}

        <!-- Budget control panel -->
        <fc-budget-panel .workspaceId=${this.activeWorkspaceId}></fc-budget-panel>

        <!-- Project plan card -->
        <fc-project-plan-card .workspaceId=${this.activeWorkspaceId}></fc-project-plan-card>

        ${this.approvals.length > 0 ? html`
          <fc-approval-queue .approvals=${this.approvals}
            @approve=${(e: CustomEvent) => this.re('approve', e.detail)}
            @deny=${(e: CustomEvent) => this.re('deny', e.detail)}
          ></fc-approval-queue>` : nothing}

        ${this._renderActivePlans()}

        <!-- Continuations + Autonomy row -->
        <div class="health-grid">
          <fc-queen-continuations .workspaceId=${this.activeWorkspaceId}></fc-queen-continuations>
          <fc-queen-autonomy-card .workspaceId=${this.activeWorkspaceId}></fc-queen-autonomy-card>
        </div>

        <!-- Operating procedures editor (elevated from Operations view) -->
        <fc-operating-procedures-editor .workspaceId=${this.activeWorkspaceId}></fc-operating-procedures-editor>

        <!-- Budget viz + Overrides row -->
        <div class="health-grid">
          <fc-queen-budget-viz></fc-queen-budget-viz>
          <fc-queen-overrides .workspaceId=${this.activeWorkspaceId} .workspace=${this.tree[0] ?? null}></fc-queen-overrides>
        </div>

        <!-- Tool usage stats -->
        <fc-queen-tool-stats></fc-queen-tool-stats>

        <!-- Queen journal -->
        <fc-queen-journal-panel .workspaceId=${this.activeWorkspaceId}></fc-queen-journal-panel>
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
      .map(c => ({ id: c.id, name: c.name }));
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
