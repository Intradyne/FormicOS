/**
 * Wave 71.5 Track 3A: Queen journal panel.
 * Fetches from GET /api/v1/workspaces/{id}/queen-journal and renders
 * the Queen's operational log as a scannable timeline.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import './atoms.js';

interface JournalEntry {
  timestamp: string;
  heading: string;
  body: string;
}

interface JournalData {
  exists: boolean;
  entries: JournalEntry[];
}

@customElement('fc-queen-journal-panel')
export class FcQueenJournalPanel extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .entries {
      display: flex; flex-direction: column; gap: 2px;
    }

    .entry {
      padding: 8px 10px;
      border-left: 2px solid var(--v-border);
      transition: border-color 0.15s;
    }
    .entry:hover {
      border-left-color: var(--v-accent);
    }

    .entry-header {
      display: flex; align-items: baseline; gap: 8px;
      margin-bottom: 3px;
    }
    .entry-ts {
      font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-dim);
      white-space: nowrap;
    }
    .entry-heading {
      font-family: var(--f-mono); font-size: 10.5px; font-weight: 600;
      color: var(--v-fg); overflow: hidden; text-overflow: ellipsis;
    }
    .entry-body {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
      line-height: 1.5; white-space: pre-wrap; word-break: break-word;
    }

    .controls {
      display: flex; gap: 8px; margin-top: 8px;
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

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: String }) workspaceId = '';
  @state() private _data: JournalData | null = null;
  @state() private _error = '';
  @state() private _limit = 10;

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
        `/api/v1/workspaces/${this.workspaceId}/queen-journal`,
      );
      if (!resp.ok) {
        this._error = `HTTP ${resp.status}`;
        return;
      }
      this._data = await resp.json() as JournalData;
      this._error = '';
    } catch {
      this._error = 'Failed to fetch journal';
    }
  }

  private _formatTs(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch {
      return iso;
    }
  }

  private _showMore() {
    this._limit += 10;
  }

  render() {
    if (this._error) {
      return html`<div class="error-text">${this._error}</div>`;
    }
    if (!this._data) {
      return html`<div class="empty-state">Loading journal\u2026</div>`;
    }

    const entries = this._data.entries ?? [];
    if (entries.length === 0) {
      return html`
        <div class="empty-state">
          No journal entries yet.<br>
          <span class="empty-hint">
            The Queen records operational decisions and session boundaries here
            as work progresses.
          </span>
        </div>
      `;
    }

    const visible = entries.slice(0, this._limit);
    const hasMore = entries.length > this._limit;

    return html`
      <div class="entries">
        ${visible.map(e => html`
          <div class="entry">
            <div class="entry-header">
              <span class="entry-ts">${this._formatTs(e.timestamp)}</span>
              <span class="entry-heading">${e.heading}</span>
            </div>
            ${e.body ? html`
              <div class="entry-body">${e.body}</div>
            ` : nothing}
          </div>
        `)}
      </div>
      <div class="controls">
        <button class="btn-sm" @click=${() => void this._fetch()}>
          Refresh
        </button>
        ${hasMore ? html`
          <button class="btn-sm" @click=${this._showMore}>
            Show more (${entries.length - this._limit} remaining)
          </button>
        ` : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-queen-journal-panel': FcQueenJournalPanel;
  }
}
