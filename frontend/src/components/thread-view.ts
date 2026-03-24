import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { colonyName, providerColor } from '../helpers.js';
import { store } from '../state/store.js';
import type { TreeNode, MergeEdge, Colony, QueenThread, WorkflowStepPreview } from '../types.js';
import './atoms.js';
import './colony-creator.js';
import './workflow-view.js';
import './thread-timeline.js';

@customElement('fc-thread-view')
export class FcThreadView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; }
    .header { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
    .header h2 { font-family: var(--f-display); font-size: 18px; font-weight: 700; color: var(--v-fg); margin: 0; cursor: pointer; }
    .header h2:hover { color: var(--v-accent); }
    .rename-input { font-family: var(--f-display); font-size: 18px; font-weight: 700; color: var(--v-fg); background: transparent; border: 1px solid var(--v-accent); border-radius: 4px; padding: 0 4px; outline: none; }
    .actions { margin-left: auto; display: flex; gap: 5px; }
    .merge-hint {
      padding: 6px 12px; background: var(--v-accent-muted); border-radius: 7px;
      border: 1px solid rgba(232,88,26,0.12); margin-bottom: 12px;
      font-size: 11px; color: var(--v-accent); font-family: var(--f-body);
    }
    .colony-list { display: flex; flex-direction: column; gap: 8px; padding-left: 30px; position: relative; }
    .colony-card { cursor: pointer; padding: 14px; }
    .colony-card.merge-mode { cursor: crosshair; }
    .merge-svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
    .card-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
    .card-name { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .card-meta {
      font-size: 10.5px; font-family: var(--f-mono); color: var(--v-fg-muted);
      font-feature-settings: 'tnum'; margin-left: auto;
    }
    .card-task { font-size: 11px; color: var(--v-fg-muted); line-height: 1.4; margin-bottom: 6px; }
    .card-bottom { display: flex; gap: 8px; align-items: center; }
    .provider-dots { display: flex; gap: 2px; align-items: center; }
    .provider-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; }
    .workflow-section {
      padding: 10px 14px; margin-bottom: 10px; border-radius: 8px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
    }
    .workflow-goal {
      font-size: 12px; color: var(--v-fg); line-height: 1.4; margin-bottom: 6px;
      font-family: var(--f-body);
    }
    .workflow-checklist { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
    .checklist-item {
      font-size: 10px; font-family: var(--f-mono); padding: 2px 7px; border-radius: 6px;
      border: 1px solid var(--v-border); color: var(--v-fg-dim);
    }
    .checklist-item.done { color: #2DD4A8; border-color: rgba(45,212,168,0.3); background: rgba(45,212,168,0.06); }
    .checklist-item.missing { color: var(--v-fg-dim); }
    .workflow-counts {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      font-feature-settings: 'tnum';
    }
    .status-badge {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 7px; border-radius: 6px;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .status-badge.active { background: rgba(91,156,245,0.12); color: #5B9CF5; border: 1px solid rgba(91,156,245,0.25); }
    .status-badge.completed { background: rgba(45,212,168,0.12); color: #2DD4A8; border: 1px solid rgba(45,212,168,0.25); }
    .status-badge.archived { background: rgba(107,107,118,0.12); color: #6B6B76; border: 1px solid rgba(107,107,118,0.25); }
    .step-timeline { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
    .step-row {
      display: flex; align-items: center; gap: 8px; padding: 5px 8px; border-radius: 6px;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border: 1px solid var(--v-border); background: transparent;
    }
    .step-index { font-size: 9px; color: var(--v-fg-dim); min-width: 18px; text-align: center; }
    .step-desc { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .step-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 6px; border-radius: 4px;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .step-badge.pending { background: rgba(107,107,118,0.12); color: #6B6B76; }
    .step-badge.running { background: rgba(91,156,245,0.12); color: #5B9CF5; animation: pulse 1.5s infinite; }
    .step-badge.completed { background: rgba(45,212,168,0.12); color: #2DD4A8; }
    .step-badge.failed { background: rgba(240,100,100,0.12); color: #F06464; }
    .step-badge.skipped { background: rgba(107,107,118,0.08); color: #6B6B76; opacity: 0.6; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .step-colony-link { font-size: 9px; color: var(--v-accent); cursor: pointer; text-decoration: none; }
    .step-colony-link:hover { text-decoration: underline; }
    .step-summary { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 4px; }
    .timeline-section {
      margin-top: 10px; padding: 10px 14px; border-radius: 8px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
    }
    .timeline-toggle {
      display: flex; align-items: center; gap: 6px; cursor: pointer;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
      user-select: none;
    }
    .timeline-toggle:hover { color: var(--v-fg); }
    .timeline-toggle .arrow { transition: transform 0.2s; }
    .timeline-toggle .arrow.open { transform: rotate(90deg); }
  `];

  @property({ type: Object }) thread: TreeNode | null = null;
  @property({ type: Object }) threadData: QueenThread | null = null;
  @property() parentWsName = '';
  @property({ type: Array }) merges: MergeEdge[] = [];
  @state() private mergeMode: string | null = null;
  @state() private showSpawnForm = false;
  @state() private editingName = false;
  @state() private draftName = '';
  @state() private timelineOpen = false;
  private _unsub?: () => void;

  private get colonies(): TreeNode[] { return this.thread?.children ?? []; }
  private get activeMerges(): MergeEdge[] { return this.merges.filter(m => m.active); }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe(() => this._syncThreadData());
    this._syncThreadData();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  /** Derive threadData from the store's queenThreads when not passed externally. */
  private _syncThreadData() {
    if (!this.thread) return;
    const qt = store.state.queenThreads.find(t => t.id === this.thread!.id);
    if (qt) this.threadData = qt;
  }

  /** Check whether this thread has an active parallel plan for DAG rendering. */
  private get _hasPlan(): boolean {
    const td = this.threadData;
    return !!(td?.active_plan && td?.parallel_groups && td.parallel_groups.length > 0);
  }

  render() {
    if (!this.thread) return nothing;
    const cols = this.colonies;
    if (cols.length === 0) return html`
      <div class="header">
        <span style="font-size:12px;color:var(--v-blue)">\u25B7</span>
        ${this.editingName
          ? html`<input class="rename-input" .value=${this.draftName}
              @input=${(e: Event) => { this.draftName = (e.target as HTMLInputElement).value; }}
              @keydown=${this._renameKeydown}
              @blur=${this._commitRename}>`
          : html`<h2 @dblclick=${this._startRename} title="Double-click to rename">${this.thread.name}</h2>`}
        <div class="actions">
          <fc-btn variant="primary" sm @click=${this._toggleSpawn}>+ Spawn Colony</fc-btn>
        </div>
      </div>
      ${this._renderWorkflowProgress()}
      ${this.showSpawnForm ? html`
        <fc-colony-creator
          @spawn-colony=${(e: CustomEvent) => {
            this.dispatchEvent(new CustomEvent('spawn-colony', {
              detail: { threadId: this.thread!.id, ...e.detail },
              bubbles: true, composed: true,
            }));
            this.showSpawnForm = false;
          }}
          @cancel=${() => { this.showSpawnForm = false; }}
        ></fc-colony-creator>` : nothing}
      <div class="empty-state">
        <div class="empty-icon">\u2B21</div>
        <div class="empty-title">No colonies yet</div>
        <div class="empty-desc">Spawn a colony to get started, or ask the Queen</div>
      </div>`;
    return html`
      <div class="header">
        <span style="font-size:12px;color:var(--v-blue)">\u25B7</span>
        ${this.editingName
          ? html`<input class="rename-input" .value=${this.draftName}
              @input=${(e: Event) => { this.draftName = (e.target as HTMLInputElement).value; }}
              @keydown=${this._renameKeydown}
              @blur=${this._commitRename}>`
          : html`<h2 @dblclick=${this._startRename} title="Double-click to rename">${this.thread.name}</h2>`}
        <fc-pill color="var(--v-fg-muted)" sm>${cols.length} colonies</fc-pill>
        ${this.parentWsName ? html`<fc-pill color="var(--v-accent)" sm>\u25A3 ${this.parentWsName}</fc-pill>` : nothing}
        <div class="actions">
          <fc-btn variant="primary" sm @click=${this._toggleSpawn}>+ Spawn Colony</fc-btn>
          <fc-btn variant="merge" sm @click=${this._toggleMerge}>${this.mergeMode ? 'Cancel Merge' : '\u2295 Merge'}</fc-btn>
          <fc-btn variant="secondary" sm @click=${this._broadcast}>\u2297 Broadcast</fc-btn>
        </div>
      </div>
      ${this._renderWorkflowProgress()}
      ${this.mergeMode ? html`<div class="merge-hint">
        ${this.mergeMode === 'picking'
          ? 'Click a SOURCE colony to begin merge'
          : `Now click the TARGET colony to complete merge from ${this.mergeMode}`}
      </div>` : nothing}
      ${this.showSpawnForm ? html`
        <fc-colony-creator
          @spawn-colony=${(e: CustomEvent) => {
            this.dispatchEvent(new CustomEvent('spawn-colony', {
              detail: { threadId: this.thread!.id, ...e.detail },
              bubbles: true, composed: true,
            }));
            this.showSpawnForm = false;
          }}
          @cancel=${() => { this.showSpawnForm = false; }}
        ></fc-colony-creator>` : nothing}
      ${this._renderTimeline()}
      <div style="position:relative;padding-top:8px">
        ${this.activeMerges.length > 0 ? html`
          <svg class="merge-svg" style="height:${cols.length * 90}px">
            <defs>
              <marker id="mergeArr" viewBox="0 0 10 6" refX="10" refY="3"
                markerWidth="6" markerHeight="4" orient="auto">
                <path d="M0,0 L10,3 L0,6" fill="var(--v-secondary)"/>
              </marker>
            </defs>
            ${this.activeMerges.map(m => {
              const fi = cols.findIndex(c => c.id === m.from);
              const ti = cols.findIndex(c => c.id === m.to);
              if (fi < 0 || ti < 0) return nothing;
              const y1 = fi * 90 + 45, y2 = ti * 90 + 45;
              return html`<g>
                <path d="M 20 ${y1} C -20 ${y1}, -20 ${y2}, 20 ${y2}"
                  stroke="var(--v-secondary)" stroke-width="1.5" fill="none" opacity="0.5"
                  marker-end="url(#mergeArr)" stroke-dasharray="4 2"/>
                <text x="-8" y="${(y1 + y2) / 2 + 3}" fill="var(--v-secondary)" font-size="7"
                  font-family="var(--f-mono)" text-anchor="middle" opacity="0.6">MERGE</text>
              </g>`;
            })}
          </svg>` : nothing}
        <div class="colony-list">
          ${cols.map(c => this._renderColonyCard(c as Colony))}
        </div>
      </div>`;
  }

  private _renderWorkflowProgress() {
    const t = this.threadData;
    if (!t?.goal && !this._hasPlan) return nothing;

    // B1: If thread has an active parallel plan, render DAG view
    if (this._hasPlan) {
      return html`
        <fc-workflow-view
          .plan=${t!.active_plan}
          .parallelGroups=${t!.parallel_groups!}
          .reasoning=${t!.plan_reasoning ?? ''}
          .knowledgeGaps=${t!.plan_knowledge_gaps ?? []}
          .estimatedCost=${t!.plan_estimated_cost ?? 0}
          .colonies=${this.colonies as Colony[]}
          @navigate=${(e: CustomEvent) => this.dispatchEvent(new CustomEvent('navigate', { detail: e.detail, bubbles: true, composed: true }))}
          @edit-plan=${(e: CustomEvent) => this._handleEditPlan(e)}
        ></fc-workflow-view>`;
    }

    // Fallback: legacy simple workflow rendering for threads without plans
    return this._renderLegacyWorkflowProgress();
  }

  /** Legacy workflow rendering for threads without a parallel plan. */
  private _renderLegacyWorkflowProgress() {
    const t = this.threadData;
    if (!t?.goal) return nothing;
    const arts = t.artifactTypesProduced ?? {};
    const status = t.status ?? 'active';
    const completed = t.completedColonyCount ?? 0;
    const total = t.colonyCount ?? 0;
    const failed = t.failedColonyCount ?? 0;
    const canComplete = status === 'active' && completed > 0;
    return html`
      <div class="workflow-section">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
          <span class="status-badge ${status}">${status}</span>
          <span style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">Workflow</span>
        </div>
        <div class="workflow-goal">${t.goal}</div>
        ${(t.expectedOutputs?.length ?? 0) > 0 ? html`
          <div class="workflow-checklist">
            ${t.expectedOutputs!.map(out => {
              const count = arts[out] ?? 0;
              const done = count > 0;
              return html`<span class="checklist-item ${done ? 'done' : 'missing'}">${done ? '\u2713' : '\u25CB'} ${out} (${count})</span>`;
            })}
          </div>` : nothing}
        <div class="workflow-counts">
          ${completed}/${total} colonies completed${failed > 0 ? html` \u00B7 <span style="color:#F06464">${failed} failed</span>` : nothing}
        </div>
        ${this._renderStepTimeline()}
        ${canComplete ? html`
          <fc-btn variant="primary" sm style="margin-top:6px"
            @click=${this._completeThread}>Complete Thread</fc-btn>` : nothing}
      </div>`;
  }

  private _renderStepTimeline() {
    const steps = this.threadData?.workflow_steps;
    if (!steps || steps.length === 0) return nothing;
    const completed = steps.filter(s => s.status === 'completed').length;
    return html`
      <div class="step-summary">Steps: ${completed}/${steps.length} completed</div>
      <div class="step-timeline">
        ${steps.map(s => html`
          <div class="step-row">
            <span class="step-index">${s.step_index + 1}</span>
            <span class="step-badge ${s.status}">${s.status}</span>
            <span class="step-desc" title="${s.description}">${s.description}</span>
            ${s.colony_id ? html`
              <span class="step-colony-link"
                @click=${(e: Event) => { e.stopPropagation(); this.dispatchEvent(new CustomEvent('navigate', { detail: s.colony_id, bubbles: true, composed: true })); }}
              >${s.colony_id.slice(0, 8)}</span>
            ` : nothing}
          </div>
        `)}
      </div>`;
  }

  private async _handleEditPlan(e: CustomEvent) {
    const plan = e.detail;
    if (!plan || !this.threadData?.workspaceId) return;
    const workspaceId = this.threadData.workspaceId;
    try {
      await fetch(
        `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/config-overrides`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            suggestion_category: 'delegation_plan',
            original_config: plan,
            overridden_config: plan,
            reason: 'operator_edit_before_launch',
          }),
        },
      );
      this.dispatchEvent(new CustomEvent('edit-plan', {
        detail: { workspaceId, plan },
        bubbles: true, composed: true,
      }));
    } catch {
      // Silently fail — the override was best-effort
    }
  }

  private _completeThread() {
    if (!this.thread) return;
    this.dispatchEvent(new CustomEvent('complete-thread', {
      detail: { threadId: this.thread.id },
      bubbles: true, composed: true,
    }));
  }

  private _renderTimeline() {
    return html`
      <div class="timeline-section">
        <div class="timeline-toggle" @click=${() => { this.timelineOpen = !this.timelineOpen; }}>
          <span class="arrow ${this.timelineOpen ? 'open' : ''}">\u25B6</span>
          Thread Timeline
        </div>
        ${this.timelineOpen ? html`
          <fc-thread-timeline
            .thread=${this.thread}
            .threadData=${this.threadData}
            @navigate=${(e: CustomEvent) => this.dispatchEvent(new CustomEvent('navigate', { detail: e.detail, bubbles: true, composed: true }))}
            @navigate-knowledge=${(e: CustomEvent) => this.dispatchEvent(new CustomEvent('navigate-knowledge', { detail: e.detail, bubbles: true, composed: true }))}
          ></fc-thread-timeline>
        ` : nothing}
      </div>
    `;
  }

  private _renderColonyCard(c: Colony) {
    const hasMergeTo = this.activeMerges.some(m => m.to === c.id);
    const hasMergeFrom = this.activeMerges.some(m => m.from === c.id);
    const borderColor = hasMergeTo ? 'var(--v-secondary)' : hasMergeFrom ? 'rgba(61,214,245,0.25)' : 'transparent';
    const convHistory = (c as Colony & { convergenceHistory?: number[] }).convergenceHistory;
    const providers = this._uniqueProviders(c);

    return html`
      <div class="glass clickable colony-card ${this.mergeMode ? 'merge-mode' : ''}"
        style="border-left:3px solid ${borderColor}"
        @click=${() => this._handleColonyClick(c.id)}>
        <div class="card-header">
          <fc-dot .status=${c.status ?? 'pending'} .size=${6}></fc-dot>
          <span class="card-name">${colonyName(c)}</span>
          ${c.qualityScore > 0 ? html`<fc-quality-dot .quality=${c.qualityScore}></fc-quality-dot>` : nothing}
          <fc-pill color="var(--v-fg-muted)" sm>${c.strategy ?? 'stigmergic'}</fc-pill>
          ${providers.length > 0 ? html`
            <div class="provider-dots">
              ${providers.map(model => html`
                <span class="provider-dot" style="background:${providerColor(model)}" title="${model}"></span>
              `)}
            </div>` : nothing}
          <span class="card-meta">
            R${c.round ?? 0}/${c.maxRounds ?? 0} \u00B7 ${c.agents?.length ?? 0} agents \u00B7 $${(c.cost ?? 0).toFixed(2)}
          </span>
          ${hasMergeTo ? html`<fc-pill color="var(--v-secondary)" sm>\u2190 merge in</fc-pill>` : nothing}
          ${hasMergeFrom ? html`<fc-pill color="var(--v-secondary)" sm>\u2192 merge out</fc-pill>` : nothing}
        </div>
        ${c.task ? html`<div class="card-task">${c.task}</div>` : nothing}
        <div class="card-bottom">
          ${c.convergence > 0 ? html`
            <div style="flex:1"><fc-meter label="Convergence" .value=${c.convergence} .max=${1}
              .color=${c.convergence > 0.8 ? '#2DD4A8' : '#E8581A'}></fc-meter></div>` : nothing}
          ${convHistory && convHistory.length > 1 ? html`
            <fc-sparkline .data=${convHistory} .width=${60} .height=${16}
              .color=${(c.convergence ?? 0) > 0.8 ? '#2DD4A8' : '#E8581A'}></fc-sparkline>` : nothing}
          ${c.defense ? html`<fc-defense-gauge .score=${c.defense.composite}></fc-defense-gauge>` : nothing}
          <div style="display:flex;gap:3px;margin-left:auto">
            ${this.activeMerges.filter(m => m.to === c.id).map(m => html`
              <fc-btn variant="danger" sm @click=${(e: Event) => { e.stopPropagation(); this._pruneMerge(m.id); }}>\u2715 Prune</fc-btn>
            `)}
          </div>
        </div>
      </div>`;
  }

  /** Get unique provider prefixes from colony agents. */
  private _uniqueProviders(c: Colony): string[] {
    const agents = c.agents ?? [];
    const seen = new Set<string>();
    for (const a of agents) {
      const prefix = a.model.split('/')[0];
      if (!seen.has(prefix)) seen.add(prefix);
    }
    return [...seen].map(p => `${p}/`);
  }

  private _handleColonyClick(id: string) {
    if (this.mergeMode === 'picking') {
      this.mergeMode = id;
    } else if (this.mergeMode && this.mergeMode !== 'picking') {
      this.dispatchEvent(new CustomEvent('create-merge', {
        detail: { from: this.mergeMode, to: id },
        bubbles: true, composed: true,
      }));
      this.mergeMode = null;
    } else {
      this.dispatchEvent(new CustomEvent('navigate', { detail: id, bubbles: true, composed: true }));
    }
  }

  private _toggleMerge() { this.mergeMode = this.mergeMode ? null : 'picking'; }
  private _toggleSpawn() { this.showSpawnForm = !this.showSpawnForm; }

  private _broadcast() {
    this.dispatchEvent(new CustomEvent('broadcast', { detail: this.thread?.id, bubbles: true, composed: true }));
  }

  private _startRename() {
    this.draftName = this.thread?.name ?? '';
    this.editingName = true;
    this.updateComplete.then(() => {
      this.shadowRoot?.querySelector<HTMLInputElement>('.rename-input')?.focus();
    });
  }

  private _renameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); }
    if (e.key === 'Escape') { this.editingName = false; }
  }

  private _commitRename() {
    const name = this.draftName.trim();
    this.editingName = false;
    if (name && this.thread && name !== this.thread.name) {
      this.dispatchEvent(new CustomEvent('rename-thread', {
        detail: { threadId: this.thread.id, name },
        bubbles: true, composed: true,
      }));
    }
  }

  private _pruneMerge(id: string) {
    this.dispatchEvent(new CustomEvent('prune-merge', { detail: id, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-thread-view': FcThreadView; }
}
