import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface ContinuationCandidate {
  thread_id: string;
  description: string;
  ready_for_autonomy: boolean;
  blocked_reason: string | null;
  priority: string;
}

@customElement('fc-queen-continuations')
export class FcQueenContinuations extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .empty { font-size: 10px; color: var(--v-fg-dim); font-family: var(--f-mono); }
    .candidate {
      padding: 8px 10px; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;
    }
    .desc {
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg);
      flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .blocked-reason {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-top: 2px;
    }
  `];

  @property() workspaceId = '';
  @state() private _candidates: ContinuationCandidate[] = [];
  @state() private _loading = false;
  private _timer: ReturnType<typeof setInterval> | null = null;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
    this._timer = setInterval(() => void this._fetch(), 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._timer) clearInterval(this._timer);
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    this._loading = true;
    try {
      const resp = await fetch(`/api/v1/workspaces/${this.workspaceId}/operations/summary`);
      if (resp.ok) {
        const data = await resp.json() as { continuation_candidates?: ContinuationCandidate[] };
        this._candidates = data.continuation_candidates ?? [];
      }
    } catch { /* silent */ }
    this._loading = false;
  }

  render() {
    return html`
      <div class="s-label">Continuations</div>
      ${this._candidates.length === 0 ? html`
        <div class="empty">${this._loading ? 'Loading...' : 'No pending continuations'}</div>
      ` : this._candidates.map(c => html`
        <div class="glass candidate">
          <span class="desc" title=${c.description}>${c.description.slice(0, 60)}</span>
          ${c.ready_for_autonomy
            ? html`<fc-pill color="var(--v-green, #22c55e)" sm>ready</fc-pill>`
            : html`<fc-pill color="var(--v-warning, #f59e0b)" sm title=${c.blocked_reason ?? ''}>blocked</fc-pill>`}
          <fc-pill color="var(--v-fg-dim)" sm>${c.priority}</fc-pill>
        </div>
        ${!c.ready_for_autonomy && c.blocked_reason ? html`
          <div class="blocked-reason">${c.blocked_reason}</div>
        ` : nothing}
      `)}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-continuations': FcQueenContinuations; }
}
