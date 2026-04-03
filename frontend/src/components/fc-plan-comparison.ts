/**
 * Wave 83 Track D: Plan comparison panel.
 *
 * Shows planning history summaries and saved patterns alongside the
 * current reviewed plan. Lets the operator compare, inspect, and apply
 * a saved pattern as the editor starting shape.
 *
 * Consumes:
 * - GET /api/v1/workspaces/{id}/planning-history (summary-only)
 * - GET /api/v1/workspaces/{id}/plan-patterns (full saved patterns)
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type {
  PlanningHistoryEntry,
  SavedPlanPattern,
  PreviewCardMeta,
} from '../types.js';

@customElement('fc-plan-comparison')
export class FcPlanComparison extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .panel {
      border: 1px solid var(--v-border);
      border-radius: 8px;
      background: rgba(255,255,255,0.02);
      padding: 10px 12px;
    }
    .section-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 6px;
    }
    .entry {
      display: flex; align-items: center; gap: 8px;
      padding: 5px 8px; border-radius: 5px; margin-bottom: 3px;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04);
      cursor: pointer; font-size: 10px; font-family: var(--f-mono);
      color: var(--v-fg-muted); transition: border-color 0.15s;
    }
    .entry:hover { border-color: var(--v-border-hover); color: var(--v-fg); }
    .entry-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .entry-meta { color: var(--v-fg-dim); font-size: 9px; flex-shrink: 0; }
    .entry-badge {
      font-size: 8px; padding: 1px 5px; border-radius: 3px;
      background: rgba(99,102,241,0.1); color: #8b8cf6;
    }
    .entry-badge.saved { background: rgba(45,212,168,0.1); color: var(--v-success); }
    .apply-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px;
      border-radius: 4px; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); cursor: pointer;
    }
    .apply-btn:hover { border-color: var(--v-accent); color: var(--v-accent); }
    .empty { font-size: 10px; color: var(--v-fg-dim); font-family: var(--f-mono); padding: 8px 0; }
    .detail-panel {
      margin-top: 8px; padding: 8px 10px; border-radius: 6px;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.03);
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .detail-task {
      padding: 3px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
    }
    .detail-task:last-child { border-bottom: none; }
  `];

  @property() workspaceId = '';
  @property({ type: Object }) currentPlan: PreviewCardMeta | null = null;

  @state() private _history: PlanningHistoryEntry[] = [];
  @state() private _patterns: SavedPlanPattern[] = [];
  @state() private _selectedPattern: SavedPlanPattern | null = null;
  @state() private _loading = false;

  connectedCallback() {
    super.connectedCallback();
    void this._loadData();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._loadData();
    }
  }

  private async _loadData() {
    if (!this.workspaceId) return;
    this._loading = true;
    const wsId = encodeURIComponent(this.workspaceId);
    const query = (this.currentPlan?.task ?? '').trim();
    try {
      const [histRes, patRes] = await Promise.all([
        query
          ? fetch(`/api/v1/workspaces/${wsId}/planning-history?top_k=5&query=${encodeURIComponent(query)}`)
          : Promise.resolve(null),
        fetch(`/api/v1/workspaces/${wsId}/plan-patterns`).catch(() => null),
      ]);
      if (histRes?.ok) {
        const data = await histRes.json() as { plans?: PlanningHistoryEntry[] };
        this._history = data.plans ?? [];
      } else {
        this._history = [];
      }
      if (patRes?.ok) {
        const data = await patRes.json() as { patterns?: SavedPlanPattern[] };
        this._patterns = data.patterns ?? [];
      }
    } catch { /* degrade gracefully */ }
    this._loading = false;
  }

  render() {
    if (this._loading) {
      return html`<div class="panel"><div class="empty">Loading compare data...</div></div>`;
    }

    return html`
      <div class="panel">
        ${this._patterns.length > 0 ? html`
          <div class="section-label">Saved Patterns</div>
          ${this._patterns.map(p => html`
            <div class="entry" @click=${() => { this._selectedPattern = this._selectedPattern?.pattern_id === p.pattern_id ? null : p; }}>
              <span class="entry-badge saved">saved</span>
              <span class="entry-name" title=${p.description}>${p.name}</span>
              <span class="entry-meta">${p.task_previews?.length ?? 0} tasks, ${p.groups?.length ?? 0} groups</span>
              <button class="apply-btn" @click=${(e: Event) => { e.stopPropagation(); this._applyPattern(p); }}>Apply</button>
            </div>
          `)}
          ${this._selectedPattern ? this._renderPatternDetail(this._selectedPattern) : nothing}
        ` : nothing}

        ${this._history.length > 0 ? html`
          <div class="section-label" style="margin-top:${this._patterns.length > 0 ? '10px' : '0'}">Planning History</div>
          ${this._history.map(h => html`
            <div class="entry" title=${h.evidence}>
              <span class="entry-badge">${h.evidence_type === 'summary_history' ? 'summary' : 'history'}</span>
              <span class="entry-name">${h.strategy}</span>
              <span class="entry-meta">n=${h.count} \u00B7 q=${(h.avg_quality * 100).toFixed(0)}% \u00B7 sr=${(h.success_rate * 100).toFixed(0)}%</span>
            </div>
          `)}
          <div class="detail-panel" style="margin-top:6px">
            Historical compare is summary-only for legacy runs. Saved patterns carry reusable DAG structure.
          </div>
        ` : nothing}

        ${this._patterns.length === 0 && this._history.length === 0 ? html`
          <div class="empty">No saved patterns or planning history yet.</div>
        ` : nothing}
      </div>
    `;
  }

  private _renderPatternDetail(p: SavedPlanPattern) {
    return html`
      <div class="detail-panel">
        <div style="font-weight:600;margin-bottom:4px">${p.name}</div>
        <div style="color:var(--v-fg-dim);margin-bottom:6px">${p.description}</div>
        ${p.task_previews?.map(t => html`
          <div class="detail-task">
            <span style="color:var(--v-accent)">${t.caste}</span>
            ${t.task}
            ${t.target_files?.length ? html`<span style="color:var(--v-fg-dim)"> [${t.target_files.join(', ')}]</span>` : nothing}
          </div>
        `) ?? nothing}
        <div style="margin-top:6px;color:var(--v-fg-dim);font-size:9px">
          Created: ${p.created_at} \u00B7 From: ${p.created_from} \u00B7 Model: ${p.planner_model}
        </div>
      </div>
    `;
  }

  private _applyPattern(p: SavedPlanPattern) {
    this.dispatchEvent(new CustomEvent('apply-pattern', {
      detail: p,
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-plan-comparison': FcPlanComparison; }
}
