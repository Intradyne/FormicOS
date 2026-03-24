import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { Colony } from '../types.js';
import './atoms.js';

/**
 * Renders a DAG visualization of a Queen's DelegationPlan.
 * Shows parallel groups as horizontal swim-lanes, tasks as cards,
 * dependency arrows between groups, live colony status, cost and
 * knowledge annotations.
 *
 * Supports a `compact` mode for embedding as mini-DAG in Active Plans.
 */
@customElement('fc-workflow-view')
export class FcWorkflowView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; margin-bottom: 10px; }

    /* ── Full DAG container ── */
    .dag-container {
      display: flex; flex-direction: column; gap: 0;
      padding: 12px 14px; border-radius: 8px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
    }
    .dag-header {
      display: flex; align-items: center; gap: 6px;
      font-family: var(--f-display); font-size: 12px; font-weight: 600;
      color: var(--v-fg); margin-bottom: 8px;
    }
    .dag-header-icon { font-size: 11px; color: var(--v-accent); }
    .cost-running {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-accent);
      margin-left: auto; font-feature-settings: 'tnum';
    }
    .cost-est {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-left: auto; font-feature-settings: 'tnum';
    }
    .progress-summary {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      font-feature-settings: 'tnum';
    }

    /* ── Collapsible reasoning ── */
    .reasoning-toggle {
      display: flex; align-items: center; gap: 4px; cursor: pointer;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 8px; user-select: none;
    }
    .reasoning-toggle:hover { color: var(--v-fg-muted); }
    .reasoning-arrow { font-size: 8px; transition: transform 0.15s; display: inline-block; }
    .reasoning-arrow.open { transform: rotate(90deg); }
    .reasoning-body {
      font-size: 10.5px; color: var(--v-fg-muted); line-height: 1.5;
      font-family: var(--f-body); margin-bottom: 10px; padding: 6px 10px;
      background: rgba(255,255,255,0.015); border-radius: 6px;
      border-left: 2px solid var(--v-accent-muted);
    }

    /* ── Group structure ── */
    .group-block { margin-bottom: 0; }
    .group-connector {
      display: flex; align-items: center; justify-content: center;
      padding: 6px 0; gap: 6px;
    }
    .connector-line {
      flex: 1; height: 1px; max-width: 50px;
      background: linear-gradient(90deg, transparent, var(--v-border-hover), transparent);
      transition: background 0.3s;
    }
    .connector-line.active {
      background: linear-gradient(90deg, transparent, var(--v-blue), transparent);
    }
    .connector-line.done {
      background: linear-gradient(90deg, transparent, var(--v-success), transparent);
    }
    .connector-arrow {
      font-size: 10px; color: var(--v-fg-dim); font-family: var(--f-mono);
      transition: color 0.3s;
    }
    .connector-arrow.active { color: var(--v-blue); }
    .connector-arrow.done { color: var(--v-success); }
    .group-header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
    }
    .group-label {
      font-size: 8px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.1em; text-transform: uppercase;
      padding: 2px 6px; border-radius: 4px;
      background: rgba(255,255,255,0.04); border: 1px solid var(--v-border);
      transition: border-color 0.3s, color 0.3s;
    }
    .group-label.all-done { border-color: rgba(45,212,168,0.3); color: var(--v-success); }
    .group-label.has-running { border-color: rgba(91,156,245,0.3); color: var(--v-blue); }
    .group-label.has-failed { border-color: rgba(240,100,100,0.3); color: var(--v-danger); }
    .group-parallel-hint {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); opacity: 0.6;
    }
    .group-meta {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
      font-feature-settings: 'tnum'; margin-left: auto;
    }
    .group-tasks {
      display: flex; gap: 6px; flex-wrap: wrap;
      padding-left: 4px;
    }

    /* ── Task cards with animated status ── */
    .task-card {
      padding: 8px 10px; border-radius: 6px; min-width: 100px; max-width: 240px;
      border: 1px solid var(--v-border); background: rgba(255,255,255,0.03);
      font-size: 10.5px; font-family: var(--f-mono); color: var(--v-fg);
      cursor: pointer;
      transition: border-color 0.3s, background 0.3s, transform 0.15s;
    }
    .task-card:hover { border-color: var(--v-border-hover); transform: translateY(-1px); }
    .task-card.status-running {
      border-color: rgba(91,156,245,0.35);
      background: rgba(91,156,245,0.04);
      animation: card-glow 2s ease-in-out infinite;
    }
    .task-card.status-completed {
      border-color: rgba(45,212,168,0.3);
      background: rgba(45,212,168,0.03);
    }
    .task-card.status-failed {
      border-color: rgba(240,100,100,0.3);
      background: rgba(240,100,100,0.03);
    }
    @keyframes card-glow {
      0%, 100% { box-shadow: 0 0 0 0 rgba(91,156,245,0); }
      50% { box-shadow: 0 0 8px 0 rgba(91,156,245,0.15); }
    }
    .task-top { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
    .task-id { font-weight: 600; font-size: 10px; }
    .task-caste {
      font-size: 8px; padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.06); color: var(--v-fg-dim);
      text-transform: uppercase; letter-spacing: 0.05em;
    }
    .status-dot {
      width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
      transition: background 0.3s;
    }
    .status-dot.pending { background: var(--v-fg-dim); }
    .status-dot.running { background: var(--v-blue); animation: pulse-dot 1.5s infinite; }
    .status-dot.completed { background: var(--v-success); }
    .status-dot.failed { background: var(--v-danger); }
    .status-dot.killed { background: var(--v-fg-dim); }
    @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    .task-desc {
      color: var(--v-fg-muted); font-size: 10px; line-height: 1.3;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .task-annotations {
      display: flex; gap: 6px; align-items: center; margin-top: 4px;
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      font-feature-settings: 'tnum';
    }
    .ann-cost { color: var(--v-fg-muted); }
    .ann-knowledge { color: var(--v-purple); }

    /* ── Running cost accumulator footer ── */
    .dag-footer {
      display: flex; align-items: center; gap: 8px; margin-top: 8px;
      padding-top: 6px; border-top: 1px solid var(--v-border);
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      font-feature-settings: 'tnum';
    }
    .edit-plan-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 6px;
      cursor: pointer; border: 1px solid rgba(232,88,26,0.25); background: rgba(232,88,26,0.06);
      color: var(--v-accent); margin-left: 6px; transition: all 0.15s;
    }
    .edit-plan-btn:hover { background: rgba(232,88,26,0.12); border-color: rgba(232,88,26,0.4); }
    .dag-footer .total-cost { color: var(--v-accent); font-weight: 600; }
    .dag-footer .total-knowledge { color: var(--v-purple); }

    /* ── Knowledge gaps ── */
    .knowledge-gaps {
      display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px;
    }
    .gap-badge {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px;
      border-radius: 4px; color: var(--v-warn);
      border: 1px solid rgba(245,183,49,0.3);
      background: rgba(245,183,49,0.06);
    }

    /* ── Compact mini-DAG mode ── */
    :host([compact]) .dag-container {
      padding: 6px 8px; border: none; background: none;
    }
    :host([compact]) .dag-header,
    :host([compact]) .reasoning-toggle,
    :host([compact]) .reasoning-body,
    :host([compact]) .knowledge-gaps,
    :host([compact]) .dag-footer { display: none; }
    :host([compact]) .group-block { margin-bottom: 0; }
    :host([compact]) .group-header { margin-bottom: 2px; }
    :host([compact]) .group-label { font-size: 7px; padding: 1px 4px; }
    :host([compact]) .group-parallel-hint { display: none; }
    :host([compact]) .group-meta { display: none; }
    :host([compact]) .group-connector { padding: 2px 0; }
    :host([compact]) .connector-line { max-width: 20px; }
    :host([compact]) .group-tasks { gap: 3px; padding-left: 2px; }
    :host([compact]) .task-card {
      padding: 3px 6px; min-width: 0; max-width: none;
      border-radius: 4px; font-size: 9px;
    }
    :host([compact]) .task-desc { display: none; }
    :host([compact]) .task-annotations { display: none; }
    :host([compact]) .task-caste { display: none; }
    :host([compact]) .task-id { font-size: 8px; }
    :host([compact]) .status-dot { width: 5px; height: 5px; }
  `];

  @property({ type: Array }) parallelGroups: string[][] = [];
  @property({ type: String }) reasoning = '';
  @property({ type: Array }) knowledgeGaps: string[] = [];
  @property({ type: Number }) estimatedCost = 0;
  @property({ type: Object }) plan: Record<string, unknown> | null = null;
  @property({ type: Array }) colonies: Colony[] = [];
  @property({ type: Boolean, reflect: true }) compact = false;
  @state() private _reasoningOpen = false;

  private _getTaskMap(): Map<string, { task_id: string; task: string; caste: string; colony_id?: string }> {
    const map = new Map<string, { task_id: string; task: string; caste: string; colony_id?: string }>();
    if (this.plan && Array.isArray((this.plan as Record<string, unknown>).tasks)) {
      for (const t of (this.plan as Record<string, unknown[]>).tasks as Array<Record<string, string>>) {
        map.set(t.task_id, t as unknown as { task_id: string; task: string; caste: string; colony_id?: string });
      }
    }
    return map;
  }

  /** Build a map from colony_id to Colony for live status lookups. */
  private _getColonyMap(): Map<string, Colony> {
    const map = new Map<string, Colony>();
    for (const c of this.colonies) {
      map.set(c.id, c);
    }
    return map;
  }

  /** Resolve the colony for a task — match by colony_id on the plan task or by task_id pattern. */
  private _colonyForTask(
    taskId: string,
    taskData: { colony_id?: string } | undefined,
    colonyMap: Map<string, Colony>,
  ): Colony | undefined {
    if (taskData?.colony_id) {
      return colonyMap.get(taskData.colony_id);
    }
    for (const c of this.colonies) {
      if (c.id === taskId || c.id.endsWith(taskId)) return c;
    }
    return undefined;
  }

  private _colonyStatus(colony: Colony | undefined): string {
    return colony?.status ?? 'pending';
  }

  /** Derive a readable group label from the dominant caste. */
  private _groupLabel(
    group: string[], idx: number,
    taskMap: Map<string, { task_id: string; task: string; caste: string; colony_id?: string }>,
  ): string {
    const castes = group.map(tid => taskMap.get(tid)?.caste).filter(Boolean) as string[];
    if (castes.length === 0) return `Phase ${idx + 1}`;
    const casteSet = [...new Set(castes)];
    if (casteSet.length === 1) {
      const labels: Record<string, string> = {
        researcher: 'Research', coder: 'Implementation',
        reviewer: 'Review', archivist: 'Synthesis',
      };
      return labels[casteSet[0]] ?? `Phase ${idx + 1}`;
    }
    if (casteSet.includes('researcher') && casteSet.includes('coder')) return 'Research + Build';
    if (casteSet.includes('coder') && casteSet.includes('reviewer')) return 'Build + Review';
    return `Phase ${idx + 1}`;
  }

  /** Compute group cost from resolved colonies. */
  private _groupCost(
    group: string[],
    taskMap: Map<string, { task_id: string; task: string; caste: string; colony_id?: string }>,
    colonyMap: Map<string, Colony>,
  ): number {
    return group.reduce((sum, tid) => {
      const colony = this._colonyForTask(tid, taskMap.get(tid), colonyMap);
      return sum + (colony?.cost ?? 0);
    }, 0);
  }

  render() {
    if (!this.parallelGroups.length) return nothing;

    const taskMap = this._getTaskMap();
    const colonyMap = this._getColonyMap();
    const totalTasks = this.parallelGroups.reduce((a, g) => a + g.length, 0);
    const completedTasks = this.parallelGroups.reduce((a, g) =>
      a + g.filter(tid => this._colonyStatus(this._colonyForTask(tid, taskMap.get(tid), colonyMap)) === 'completed').length, 0);
    const failedTasks = this.parallelGroups.reduce((a, g) =>
      a + g.filter(tid => this._colonyStatus(this._colonyForTask(tid, taskMap.get(tid), colonyMap)) === 'failed').length, 0);

    // Running cost accumulator
    const runningCost = this.parallelGroups.reduce((sum, g) => sum + this._groupCost(g, taskMap, colonyMap), 0);
    const totalKnowledge = this.parallelGroups.reduce((sum, g) =>
      sum + g.reduce((s, tid) => {
        const colony = this._colonyForTask(tid, taskMap.get(tid), colonyMap);
        return s + (colony?.skillsExtracted ?? 0);
      }, 0), 0);

    return html`
      <div class="dag-container">
        <div class="dag-header">
          <span class="dag-header-icon">\u25E8</span>
          Parallel Execution Plan
          ${completedTasks === 0 && totalTasks > 0 ? html`
            <button class="edit-plan-btn" @click=${(e: Event) => {
              e.stopPropagation();
              this.dispatchEvent(new CustomEvent('edit-plan', { detail: this.plan, bubbles: true, composed: true }));
            }}>Edit before launch</button>
          ` : nothing}
          <span class="progress-summary">
            ${completedTasks}/${totalTasks} tasks${failedTasks > 0 ? html` \u00B7 <span style="color:var(--v-danger)">${failedTasks} failed</span>` : nothing}
          </span>
          ${runningCost > 0 ? html`
            <span class="cost-running">$${runningCost.toFixed(2)}</span>
          ` : this.estimatedCost > 0 ? html`
            <span class="cost-est">est. ~$${this.estimatedCost.toFixed(2)}</span>
          ` : nothing}
        </div>

        ${this.reasoning ? html`
          <div class="reasoning-toggle" @click=${() => { this._reasoningOpen = !this._reasoningOpen; }}>
            <span class="reasoning-arrow ${this._reasoningOpen ? 'open' : ''}">\u25B6</span>
            Queen's reasoning
          </div>
          ${this._reasoningOpen ? html`
            <div class="reasoning-body">${this.reasoning}</div>
          ` : nothing}
        ` : nothing}

        ${this.parallelGroups.map((group, idx) => {
          const groupStatuses = group.map(tid => this._colonyStatus(this._colonyForTask(tid, taskMap.get(tid), colonyMap)));
          const allDone = groupStatuses.every(s => s === 'completed');
          const hasRunning = groupStatuses.some(s => s === 'running');
          const hasFailed = groupStatuses.some(s => s === 'failed');
          const labelClass = allDone ? 'all-done' : hasRunning ? 'has-running' : hasFailed ? 'has-failed' : '';
          const groupCost = this._groupCost(group, taskMap, colonyMap);
          // Connector status reflects the relationship between prev group and this one
          const prevStatuses = idx > 0
            ? this.parallelGroups[idx - 1].map(tid => this._colonyStatus(this._colonyForTask(tid, taskMap.get(tid), colonyMap)))
            : [];
          const prevDone = prevStatuses.every(s => s === 'completed');
          const connectorClass = prevDone && allDone ? 'done' : prevDone && (hasRunning || hasFailed) ? 'active' : '';

          return html`
            ${idx > 0 ? html`
              <div class="group-connector">
                <span class="connector-line ${connectorClass}"></span>
                <span class="connector-arrow ${connectorClass}">\u2193</span>
                <span class="connector-line ${connectorClass}"></span>
              </div>` : nothing}
            <div class="group-block">
              <div class="group-header">
                <span class="group-label ${labelClass}">${this._groupLabel(group, idx, taskMap)}</span>
                ${group.length > 1 ? html`<span class="group-parallel-hint">${group.length} parallel</span>` : nothing}
                ${groupCost > 0 ? html`<span class="group-meta">$${groupCost.toFixed(2)}</span>` : nothing}
              </div>
              <div class="group-tasks">
                ${group.map(taskId => this._renderTaskCard(taskId, taskMap, colonyMap))}
              </div>
            </div>
          `;
        })}

        ${this.knowledgeGaps.length ? html`
          <div class="knowledge-gaps">
            ${this.knowledgeGaps.map(gap => html`
              <span class="gap-badge">\u26A0 ${gap}</span>
            `)}
          </div>
        ` : nothing}

        ${runningCost > 0 || totalKnowledge > 0 ? html`
          <div class="dag-footer">
            ${runningCost > 0 ? html`<span>Total: <span class="total-cost">$${runningCost.toFixed(2)}</span>${this.estimatedCost > 0 ? html` / $${this.estimatedCost.toFixed(2)} est.` : nothing}</span>` : nothing}
            ${totalKnowledge > 0 ? html`<span class="total-knowledge">\u2726 ${totalKnowledge} entries extracted</span>` : nothing}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderTaskCard(
    taskId: string,
    taskMap: Map<string, { task_id: string; task: string; caste: string; colony_id?: string }>,
    colonyMap: Map<string, Colony>,
  ) {
    const task = taskMap.get(taskId);
    const colony = this._colonyForTask(taskId, task, colonyMap);
    const status = this._colonyStatus(colony);
    const cost = colony?.cost ?? 0;
    const knowledge = colony?.skillsExtracted ?? 0;

    return html`
      <div class="task-card status-${status}"
        @click=${() => { if (colony) this.dispatchEvent(new CustomEvent('navigate', { detail: colony.id, bubbles: true, composed: true })); }}
        title="${task?.task ?? taskId}">
        <div class="task-top">
          <span class="status-dot ${status}"></span>
          <span class="task-id">${taskId}</span>
          ${task?.caste ? html`<span class="task-caste">${task.caste}</span>` : nothing}
        </div>
        ${task ? html`
          <div class="task-desc">${task.task}</div>
        ` : nothing}
        ${status !== 'pending' ? html`
          <div class="task-annotations">
            ${cost > 0 ? html`<span class="ann-cost">$${cost.toFixed(2)}</span>` : nothing}
            ${knowledge > 0 ? html`<span class="ann-knowledge">\u2726 ${knowledge} entries</span>` : nothing}
          </div>
        ` : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-workflow-view': FcWorkflowView;
  }
}
