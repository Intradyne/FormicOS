/**
 * Wave 71.5 Track 3C: Operations summary card.
 * Fetches from GET /api/v1/workspaces/{id}/operations/summary and renders
 * a compact at-a-glance orientation for the operator.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import './atoms.js';

interface ContinuationCandidate {
  thread_id: string;
  description: string;
  ready_for_autonomy: boolean;
  blocked_reason: string;
  priority: string;
}

interface SyncIssue {
  type: string;
  description: string;
}

interface ProgressItem {
  type: string;
  description: string;
}

interface OperationsSummary {
  workspace_id: string;
  pending_review_count: number;
  active_milestone_count: number;
  stalled_thread_count: number;
  last_operator_activity_at: string | null;
  idle_for_minutes: number | null;
  operator_active: boolean;
  continuation_candidates: ContinuationCandidate[];
  sync_issues: SyncIssue[];
  recent_progress: ProgressItem[];
}

@customElement('fc-operations-summary-card')
export class FcOperationsSummaryCard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .counts {
      display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;
    }
    .count-chip {
      font-family: var(--f-mono); font-size: 10px; font-weight: 600;
      padding: 3px 9px; border-radius: 5px;
      border: 1px solid var(--v-border);
      color: var(--v-fg-muted); background: rgba(255,255,255,0.02);
    }
    .count-chip-warn {
      border-color: rgba(245,183,49,0.25); color: var(--v-warn);
      background: rgba(245,183,49,0.04);
    }
    .count-chip-danger {
      border-color: rgba(240,100,100,0.25); color: var(--v-danger);
      background: rgba(240,100,100,0.04);
    }
    .count-chip-ok {
      border-color: rgba(45,212,168,0.25); color: var(--v-success);
      background: rgba(45,212,168,0.04);
    }

    .operator-status {
      font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-dim);
      margin-bottom: 10px;
    }
    .status-dot {
      display: inline-block; width: 6px; height: 6px; border-radius: 50%;
      margin-right: 5px;
    }
    .dot-active { background: var(--v-success); }
    .dot-idle { background: var(--v-fg-dim); }

    .section-label {
      font-family: var(--f-mono); font-size: 9px; font-weight: 600;
      color: var(--v-fg-dim); letter-spacing: 0.04em;
      margin: 10px 0 4px;
    }

    .item-row {
      display: flex; align-items: baseline; gap: 6px;
      padding: 3px 0;
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
    }
    .item-tag {
      font-size: 8px; font-weight: 700; padding: 1px 5px;
      border-radius: 3px; white-space: nowrap;
    }
    .tag-ready {
      color: var(--v-success);
      background: rgba(45,212,168,0.08);
    }
    .tag-blocked {
      color: var(--v-warn);
      background: rgba(245,183,49,0.08);
    }
    .tag-issue {
      color: var(--v-danger);
      background: rgba(240,100,100,0.08);
    }
    .tag-progress {
      color: var(--v-blue);
      background: rgba(91,156,245,0.08);
    }

    .empty-state {
      font-family: var(--f-mono); font-size: 10.5px; color: var(--v-fg-dim);
      padding: 16px 0; text-align: center; line-height: 1.7;
    }
    .empty-hint {
      font-size: 9.5px; color: var(--v-fg-dim); opacity: 0.7;
    }

    .error-text {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-danger);
    }

    .controls {
      margin-top: 8px;
    }
    .btn-sm {
      font-family: var(--f-mono); font-size: 9px; font-weight: 600;
      color: var(--v-fg-dim); background: rgba(255,255,255,0.03);
      border: 1px solid var(--v-border); border-radius: 5px;
      padding: 4px 10px; cursor: pointer;
      transition: border-color 0.15s, color 0.15s;
    }
    .btn-sm:hover {
      border-color: var(--v-border-hover); color: var(--v-fg-muted);
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: String }) workspaceId = '';
  @state() private _data: OperationsSummary | null = null;
  @state() private _error = '';

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/operations/summary`,
      );
      if (!resp.ok) {
        this._error = `HTTP ${resp.status}`;
        return;
      }
      this._data = await resp.json() as OperationsSummary;
      this._error = '';
    } catch {
      this._error = 'Failed to fetch operations summary';
    }
  }

  render() {
    if (this._error) {
      return html`<div class="error-text">${this._error}</div>`;
    }
    if (!this._data) {
      return html`<div class="empty-state">Loading operations summary\u2026</div>`;
    }

    const d = this._data;
    const hasAny = d.pending_review_count > 0
      || d.active_milestone_count > 0
      || d.stalled_thread_count > 0
      || d.continuation_candidates.length > 0
      || d.sync_issues.length > 0
      || d.recent_progress.length > 0;

    if (!hasAny) {
      return html`
        <div class="empty-state">
          Nothing in the operational loop right now.<br>
          <span class="empty-hint">
            Counts, continuations, and sync issues will appear here as work
            progresses.
          </span>
        </div>
      `;
    }

    return html`
      ${this._renderCounts(d)}
      ${this._renderOperatorStatus(d)}
      ${this._renderCandidates(d.continuation_candidates)}
      ${this._renderSyncIssues(d.sync_issues)}
      ${this._renderProgress(d.recent_progress)}
      <div class="controls">
        <button class="btn-sm" @click=${() => void this._fetch()}>
          Refresh
        </button>
      </div>
    `;
  }

  private _renderCounts(d: OperationsSummary) {
    return html`
      <div class="counts">
        ${d.pending_review_count > 0 ? html`
          <span class="count-chip count-chip-warn">
            ${d.pending_review_count} pending review
          </span>
        ` : nothing}
        ${d.active_milestone_count > 0 ? html`
          <span class="count-chip count-chip-ok">
            ${d.active_milestone_count} active milestone${d.active_milestone_count !== 1 ? 's' : ''}
          </span>
        ` : nothing}
        ${d.stalled_thread_count > 0 ? html`
          <span class="count-chip count-chip-danger">
            ${d.stalled_thread_count} stalled thread${d.stalled_thread_count !== 1 ? 's' : ''}
          </span>
        ` : nothing}
      </div>
    `;
  }

  private _renderOperatorStatus(d: OperationsSummary) {
    if (d.idle_for_minutes === null) return nothing;
    const active = d.operator_active;
    const label = active
      ? 'Operator active'
      : `Operator idle ${d.idle_for_minutes}m`;
    return html`
      <div class="operator-status">
        <span class="status-dot ${active ? 'dot-active' : 'dot-idle'}"></span>
        ${label}
      </div>
    `;
  }

  private _renderCandidates(candidates: ContinuationCandidate[]) {
    if (candidates.length === 0) return nothing;
    return html`
      <div class="section-label">CONTINUATIONS</div>
      ${candidates.slice(0, 3).map(c => html`
        <div class="item-row">
          <span class="item-tag ${c.ready_for_autonomy ? 'tag-ready' : 'tag-blocked'}">
            ${c.ready_for_autonomy ? 'READY' : 'BLOCKED'}
          </span>
          <span>${c.description}</span>
        </div>
      `)}
    `;
  }

  private _renderSyncIssues(issues: SyncIssue[]) {
    if (issues.length === 0) return nothing;
    return html`
      <div class="section-label">SYNC ISSUES</div>
      ${issues.slice(0, 3).map(i => html`
        <div class="item-row">
          <span class="item-tag tag-issue">SYNC</span>
          <span>${i.description}</span>
        </div>
      `)}
    `;
  }

  private _renderProgress(progress: ProgressItem[]) {
    if (progress.length === 0) return nothing;
    return html`
      <div class="section-label">RECENT PROGRESS</div>
      ${progress.slice(0, 3).map(p => html`
        <div class="item-row">
          <span class="item-tag tag-progress">
            ${p.type === 'milestone_completed' ? 'MILESTONE' : 'THREAD'}
          </span>
          <span>${p.description}</span>
        </div>
      `)}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-operations-summary-card': FcOperationsSummaryCard;
  }
}
