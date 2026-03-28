/**
 * Wave 71.5 Track 2: Operations Inbox.
 *
 * Operator inbox for reviewing, approving, and rejecting queued actions.
 * Renders by action status and kind — not hardcoded to any single action type.
 * New action kinds (continuation, sync, knowledge-review) slot in without
 * changing the component shape.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface ActionRecord {
  action_id: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  status: string;
  kind: string;
  source_category: string;
  source_ref: string;
  title: string;
  detail: string;
  rationale: string;
  payload: Record<string, unknown>;
  thread_id: string;
  estimated_cost: number;
  blast_radius: number;
  confidence: number;
  requires_approval: boolean;
  executed_at: string;
  operator_reason: string;
}

interface ActionsResponse {
  actions: ActionRecord[];
  total: number;
  counts_by_status: Record<string, number>;
  counts_by_kind: Record<string, number>;
}

@customElement('fc-operations-inbox')
export class FcOperationsInbox extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }

    .inbox-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 12px;
    }
    .inbox-title {
      font-family: var(--f-display); font-size: 13px; font-weight: 600;
      color: var(--v-fg); letter-spacing: 0.04em;
    }
    .status-counts {
      display: flex; gap: 8px; align-items: center;
    }
    .count-badge {
      font-size: 9px; font-family: var(--f-mono); font-weight: 600;
      padding: 2px 6px; border-radius: 4px; letter-spacing: 0.04em;
    }
    .count-pending {
      background: rgba(232,88,26,0.12); color: var(--v-accent);
      border: 1px solid rgba(232,88,26,0.25);
    }
    .count-executed {
      background: rgba(45,212,168,0.08); color: var(--v-success, #2DD4A8);
      border: 1px solid rgba(45,212,168,0.15);
    }
    .count-rejected {
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim);
      border: 1px solid var(--v-border);
    }

    .section { margin-bottom: 16px; }
    .section-label {
      font-family: var(--f-display); font-size: 10px; font-weight: 600;
      color: var(--v-fg-muted); text-transform: uppercase; letter-spacing: 0.08em;
      margin-bottom: 8px; padding-left: 2px;
    }

    .action-list { display: flex; flex-direction: column; gap: 6px; }

    .action-card {
      padding: 10px 12px; transition: border-color 0.15s;
    }
    .action-card:hover { border-color: rgba(232,88,26,0.2); }
    .action-card.pending { border-left: 3px solid var(--v-accent); }
    .action-card.executed { border-left: 3px solid var(--v-success, #2DD4A8); opacity: 0.8; }
    .action-card.rejected { border-left: 3px solid var(--v-fg-dim); opacity: 0.7; }
    .action-card.self_rejected { border-left: 3px solid var(--v-fg-dim); opacity: 0.6; }

    .action-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
    .action-title {
      font-family: var(--f-display); font-size: 12px; font-weight: 600;
      color: var(--v-fg); flex: 1; min-width: 0; word-break: break-word;
    }
    .kind-chip {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      padding: 1px 5px; border-radius: 4px; text-transform: uppercase;
      letter-spacing: 0.04em; background: rgba(167,139,250,0.1);
      color: #A78BFA; border: 1px solid rgba(167,139,250,0.2);
    }
    .kind-maintenance { background: rgba(245,183,49,0.1); color: var(--v-warn, #F5B731); border-color: rgba(245,183,49,0.2); }
    .kind-continuation { background: rgba(96,196,255,0.1); color: #60C4FF; border-color: rgba(96,196,255,0.2); }
    .kind-knowledge { background: rgba(167,139,250,0.1); color: #A78BFA; border-color: rgba(167,139,250,0.2); }
    .kind-workflow { background: rgba(45,212,168,0.1); color: var(--v-success, #2DD4A8); border-color: rgba(45,212,168,0.2); }
    .kind-procedure { background: rgba(232,88,26,0.1); color: var(--v-accent); border-color: rgba(232,88,26,0.2); }

    .action-rationale {
      font-size: 11px; font-family: var(--f-body); color: var(--v-fg-muted);
      line-height: 1.4; margin-bottom: 6px; max-height: 40px; overflow: hidden;
    }

    .action-meta {
      display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .meta-item { display: flex; align-items: center; gap: 3px; }

    /* Blast radius — follows proposal-card visual language */
    .br-indicator { display: inline-flex; align-items: center; gap: 3px; }
    .br-dot { width: 6px; height: 6px; border-radius: 50%; }
    .br-low .br-dot { background: var(--v-success, #2DD4A8); }
    .br-medium .br-dot { background: var(--v-warn, #F5B731); }
    .br-high .br-dot { background: var(--v-danger, #F06464); }

    .action-controls { display: flex; gap: 6px; margin-top: 8px; align-items: center; }
    .btn-approve, .btn-reject {
      font-size: 10px; font-family: var(--f-mono); font-weight: 600;
      padding: 4px 10px; border-radius: 4px; cursor: pointer;
      border: 1px solid transparent; transition: all 0.15s;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    .btn-approve {
      background: rgba(45,212,168,0.12); color: var(--v-success, #2DD4A8);
      border-color: rgba(45,212,168,0.25);
    }
    .btn-approve:hover { background: rgba(45,212,168,0.2); }
    .btn-reject {
      background: rgba(240,100,100,0.08); color: var(--v-danger, #F06464);
      border-color: rgba(240,100,100,0.15);
    }
    .btn-reject:hover { background: rgba(240,100,100,0.16); }

    .reject-input {
      flex: 1; font-size: 10px; font-family: var(--f-mono);
      background: rgba(255,255,255,0.03); color: var(--v-fg);
      border: 1px solid var(--v-border); border-radius: 4px;
      padding: 4px 8px; outline: none;
    }
    .reject-input:focus { border-color: var(--v-accent); }
    .reject-input::placeholder { color: var(--v-fg-dim); }

    .status-pill {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      padding: 1px 5px; border-radius: 4px; text-transform: uppercase;
    }
    .pill-executed { background: rgba(45,212,168,0.1); color: var(--v-success); }
    .pill-rejected { background: rgba(240,100,100,0.08); color: var(--v-danger, #F06464); }
    .pill-self_rejected { background: rgba(255,255,255,0.04); color: var(--v-fg-dim); }
    .pill-approved { background: rgba(167,139,250,0.1); color: #A78BFA; }
    .pill-failed { background: rgba(240,100,100,0.12); color: var(--v-danger); }

    .operator-reason {
      font-size: 10px; font-family: var(--f-body); color: var(--v-fg-dim);
      font-style: italic; margin-top: 4px;
    }

    .timestamp {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }

    .empty-state {
      padding: 24px; text-align: center; color: var(--v-fg-muted);
      font-size: 12px; font-family: var(--f-body);
    }

    .loading { padding: 20px; text-align: center; color: var(--v-fg-dim); font-size: 11px; }
  `];

  @property() workspaceId = '';

  @state() private _data: ActionsResponse | null = null;
  @state() private _loading = true;
  @state() private _rejectingId = '';
  @state() private _rejectReason = '';

  override connectedCallback() {
    super.connectedCallback();
    this._fetch();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    this._loading = true;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/operations/actions?limit=200`,
      );
      if (resp.ok) {
        this._data = await resp.json() as ActionsResponse;
      }
    } catch { /* endpoint unavailable */ }
    this._loading = false;
  }

  private async _approve(actionId: string) {
    await fetch(
      `/api/v1/workspaces/${this.workspaceId}/operations/actions/${actionId}/approve`,
      { method: 'POST' },
    );
    await this._fetch();
  }

  private async _reject(actionId: string) {
    await fetch(
      `/api/v1/workspaces/${this.workspaceId}/operations/actions/${actionId}/reject`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: this._rejectReason }),
      },
    );
    this._rejectingId = '';
    this._rejectReason = '';
    await this._fetch();
  }

  private _brLevel(score: number): 'low' | 'medium' | 'high' {
    if (score >= 0.6) return 'high';
    if (score >= 0.3) return 'medium';
    return 'low';
  }

  private _brLabel(score: number): string {
    if (score >= 0.6) return 'High';
    if (score >= 0.3) return 'Medium';
    return 'Low';
  }

  private _kindClass(kind: string): string {
    if (kind === 'maintenance') return 'kind-maintenance';
    if (kind === 'continuation') return 'kind-continuation';
    if (kind === 'knowledge_review') return 'kind-knowledge';
    if (kind === 'workflow_template') return 'kind-workflow';
    if (kind === 'procedure_suggestion') return 'kind-procedure';
    return '';
  }

  private _formatTime(iso: string): string {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }

  private _isPending(a: ActionRecord): boolean {
    return a.status === 'pending_review' || a.status === 'approved';
  }

  private _isHistory(a: ActionRecord): boolean {
    return a.status === 'executed' || a.status === 'failed';
  }

  private _isDeferred(a: ActionRecord): boolean {
    return a.status === 'rejected' || a.status === 'self_rejected';
  }

  private _renderCard(a: ActionRecord) {
    if (a.kind === 'knowledge_review') return this._renderReviewCard(a);
    const isPending = this._isPending(a);
    const statusClass = a.status.replace('pending_review', 'pending');

    return html`
      <div class="glass action-card ${statusClass}">
        <div class="action-top">
          <span class="action-title">${a.title}</span>
          <span class="kind-chip ${this._kindClass(a.kind)}">${a.kind}</span>
          ${!isPending ? html`
            <span class="status-pill pill-${a.status}">${a.status.replace('_', ' ')}</span>
          ` : nothing}
        </div>

        ${a.rationale ? html`
          <div class="action-rationale">${a.rationale}</div>
        ` : nothing}

        <div class="action-meta">
          ${a.source_category ? html`
            <span class="meta-item">${a.source_category}</span>
          ` : nothing}

          ${a.blast_radius > 0 ? html`
            <span class="meta-item br-indicator br-${this._brLevel(a.blast_radius)}">
              <span class="br-dot"></span>
              ${this._brLabel(a.blast_radius)} risk
            </span>
          ` : nothing}

          ${a.estimated_cost > 0 ? html`
            <span class="meta-item">$${a.estimated_cost.toFixed(2)}</span>
          ` : nothing}

          ${a.confidence > 0 ? html`
            <span class="meta-item">${(a.confidence * 100).toFixed(0)}% conf</span>
          ` : nothing}

          ${a.thread_id ? html`
            <span class="meta-item">\u2192 ${a.thread_id.slice(0, 12)}</span>
          ` : nothing}

          <span class="timestamp">${this._formatTime(a.created_at)}</span>

          ${a.executed_at ? html`
            <span class="timestamp">exec ${this._formatTime(a.executed_at)}</span>
          ` : nothing}
        </div>

        ${a.operator_reason ? html`
          <div class="operator-reason">"${a.operator_reason}"</div>
        ` : nothing}

        ${isPending && a.status === 'pending_review' ? html`
          <div class="action-controls">
            <button class="btn-approve" @click=${() => this._approve(a.action_id)}>\u2713 Approve</button>
            ${this._rejectingId === a.action_id ? html`
              <input class="reject-input"
                placeholder="Reason (optional)"
                .value=${this._rejectReason}
                @input=${(e: InputEvent) => { this._rejectReason = (e.target as HTMLInputElement).value; }}
                @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this._reject(a.action_id); }}
              />
              <button class="btn-reject" @click=${() => this._reject(a.action_id)}>\u2717 Confirm</button>
            ` : html`
              <button class="btn-reject" @click=${() => { this._rejectingId = a.action_id; }}>\u2717 Reject</button>
            `}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderReviewCard(a: ActionRecord) {
    const isPending = this._isPending(a);
    const statusClass = a.status.replace('pending_review', 'pending');
    const p = a.payload as Record<string, unknown>;
    const entryTitle = (p.title as string) || '';
    const preview = (p.content_preview as string) || '';
    const reason = (p.review_reason as string) || '';
    const conf = p.confidence as number ?? 0;
    const accessCount = p.access_count as number ?? 0;
    const failCount = p.failure_count as number ?? 0;
    const failRate = p.failure_rate as number ?? 0;
    const entryId = (p.entry_id as string) || '';

    return html`
      <div class="glass action-card ${statusClass}">
        <div class="action-top">
          <span class="action-title">${entryTitle || a.title}</span>
          <span class="kind-chip kind-knowledge">review</span>
          <span class="kind-chip" style="background:rgba(255,255,255,0.04);color:var(--v-fg-dim);border-color:var(--v-border)">${reason.replace(/_/g, ' ')}</span>
          ${!isPending ? html`
            <span class="status-pill pill-${a.status}">${a.status.replace('_', ' ')}</span>
          ` : nothing}
        </div>

        ${preview ? html`
          <div class="action-rationale">${preview}</div>
        ` : nothing}

        <div class="action-meta">
          <span class="meta-item">${(conf * 100).toFixed(0)}% conf</span>
          ${accessCount > 0 ? html`
            <span class="meta-item">${accessCount} accesses</span>
          ` : nothing}
          ${failCount > 0 ? html`
            <span class="meta-item" style="color:var(--v-danger)">${failCount} failures (${(failRate * 100).toFixed(0)}%)</span>
          ` : nothing}
          <span class="timestamp">${this._formatTime(a.created_at)}</span>
        </div>

        ${a.operator_reason ? html`
          <div class="operator-reason">"${a.operator_reason}"</div>
        ` : nothing}

        ${isPending && a.status === 'pending_review' ? html`
          <div class="action-controls">
            <button class="btn-approve" @click=${() => this._reviewAction(a.action_id, 'confirm')}>\u2713 Confirm</button>
            ${entryId ? html`
              <button class="btn-approve" style="background:rgba(167,139,250,0.12);color:#A78BFA;border-color:rgba(167,139,250,0.25)"
                @click=${() => window.open(`/api/v1/knowledge/${entryId}`, '_blank')}>Edit</button>
            ` : nothing}
            <button class="btn-reject" @click=${() => this._reviewAction(a.action_id, 'invalidate')}>\u2717 Invalidate</button>
          </div>
        ` : nothing}
      </div>
    `;
  }

  private async _reviewAction(actionId: string, decision: 'confirm' | 'invalidate') {
    await fetch(
      `/api/v1/workspaces/${this.workspaceId}/operations/actions/${actionId}/review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      },
    );
    await this._fetch();
  }

  render() {
    if (this._loading) {
      return html`<div class="loading">Loading actions...</div>`;
    }

    if (!this._data || this._data.total === 0) {
      return html`<div class="empty-state">No queued actions. The system is idle.</div>`;
    }

    const all = this._data.actions;
    const pending = all.filter(a => this._isPending(a));
    const recent = all.filter(a => this._isHistory(a));
    const deferred = all.filter(a => this._isDeferred(a));

    const pendingCount = (this._data.counts_by_status['pending_review'] ?? 0)
      + (this._data.counts_by_status['approved'] ?? 0);
    const executedCount = this._data.counts_by_status['executed'] ?? 0;
    const rejectedCount = (this._data.counts_by_status['rejected'] ?? 0)
      + (this._data.counts_by_status['self_rejected'] ?? 0);

    return html`
      <div class="inbox-header">
        <span class="inbox-title">Action Queue</span>
        <div class="status-counts">
          ${pendingCount > 0 ? html`
            <span class="count-badge count-pending">${pendingCount} pending</span>
          ` : nothing}
          ${executedCount > 0 ? html`
            <span class="count-badge count-executed">${executedCount} executed</span>
          ` : nothing}
          ${rejectedCount > 0 ? html`
            <span class="count-badge count-rejected">${rejectedCount} deferred</span>
          ` : nothing}
        </div>
      </div>

      ${pending.length > 0 ? html`
        <div class="section">
          <div class="section-label">Pending Review</div>
          <div class="action-list">
            ${pending.map(a => this._renderCard(a))}
          </div>
        </div>
      ` : nothing}

      ${recent.length > 0 ? html`
        <div class="section">
          <div class="section-label">Recent Automatic Actions</div>
          <div class="action-list">
            ${recent.map(a => this._renderCard(a))}
          </div>
        </div>
      ` : nothing}

      ${deferred.length > 0 ? html`
        <div class="section">
          <div class="section-label">Deferred / Self-Rejected</div>
          <div class="action-list">
            ${deferred.map(a => this._renderCard(a))}
          </div>
        </div>
      ` : nothing}
    `;
  }
}
