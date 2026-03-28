/**
 * Wave 74 Track 2: Queen display board.
 * Filters journal entries with display_board metadata and renders them
 * as a prioritized observation feed at the top of the Queen tab.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import './atoms.js';

interface BoardEntry {
  timestamp: string;
  heading: string;
  body: string;
  source: string;
  metadata: { display_board?: boolean; type?: string; priority?: string } | null;
}

interface JournalData {
  exists: boolean;
  entries: BoardEntry[];
  totalEntries?: number;
}

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'var(--v-danger)',
  attention: 'var(--v-warn)',
  normal: 'var(--v-fg-dim)',
};

const TYPE_ICONS: Record<string, string> = {
  status: '\u25CF',
  concern: '\u26A0',
  observation: '\u25C6',
  recommendation: '\u2192',
};

@customElement('fc-queen-display-board')
export class FcQueenDisplayBoard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .board {
      display: flex; flex-direction: column; gap: 3px;
      margin-bottom: 8px;
    }

    .board-entry {
      display: flex; align-items: flex-start; gap: 8px;
      padding: 6px 10px; border-radius: 5px;
      background: rgba(255,255,255,0.015);
      border-left: 2px solid var(--v-border);
      transition: border-color 0.15s;
    }
    .board-entry:hover { border-left-color: var(--v-accent); }

    .board-entry.priority-critical { border-left-color: var(--v-danger); }
    .board-entry.priority-attention { border-left-color: var(--v-warn); }

    .entry-icon {
      font-size: 10px; flex-shrink: 0; margin-top: 1px;
    }

    .entry-content { flex: 1; min-width: 0; }

    .entry-heading {
      font-family: var(--f-mono); font-size: 10px; font-weight: 600;
      color: var(--v-fg); overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap;
    }

    .entry-body {
      font-family: var(--f-mono); font-size: 9.5px; color: var(--v-fg-muted);
      line-height: 1.4; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap;
    }

    .entry-ts {
      font-family: var(--f-mono); font-size: 8px; color: var(--v-fg-dim);
      white-space: nowrap; flex-shrink: 0; margin-top: 2px;
    }

    .board-header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
    }
    .board-title {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase;
    }
    .board-count {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
      padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.04);
    }

    .refresh-btn {
      margin-left: auto;
      font-family: var(--f-mono); font-size: 8px; font-weight: 600;
      color: var(--v-fg-dim); background: none; border: none;
      cursor: pointer; padding: 2px 6px; border-radius: 3px;
      transition: color 0.15s;
    }
    .refresh-btn:hover { color: var(--v-fg-muted); }

    .empty-state {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-dim);
      padding: 8px 0;
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: String }) workspaceId = '';
  @state() private _entries: BoardEntry[] = [];
  @state() private _loaded = false;
  @state() private _error = false;

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
      if (!resp.ok) { this._error = true; return; }
      const data = await resp.json() as JournalData;
      // Filter to display_board entries only
      this._entries = (data.entries ?? []).filter(
        e => e.metadata?.display_board === true,
      );
      this._error = false;
    } catch {
      this._error = true;
    }
    this._loaded = true;
  }

  private _formatTs(ts: string): string {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch {
      return ts;
    }
  }

  private _parseHeading(heading: string): { type: string; priority: string; label: string } {
    // Format: "type:priority — label" e.g. "status:normal — Continuations ready"
    const match = heading.match(/^(\w+):(\w+)\s*[—-]\s*(.*)$/);
    if (match) {
      return { type: match[1], priority: match[2], label: match[3] };
    }
    return { type: 'observation', priority: 'normal', label: heading };
  }

  render() {
    if (!this._loaded) return nothing;
    if (this._error || this._entries.length === 0) return nothing;

    // Sort: critical first, then attention, then normal; within priority by recency (already sorted)
    const priorityOrder: Record<string, number> = { critical: 0, attention: 1, normal: 2 };
    const sorted = [...this._entries].sort((a, b) => {
      const pa = priorityOrder[a.metadata?.priority ?? 'normal'] ?? 2;
      const pb = priorityOrder[b.metadata?.priority ?? 'normal'] ?? 2;
      return pa - pb;
    });

    // Show at most 8 entries
    const visible = sorted.slice(0, 8);

    return html`
      <div class="board-header">
        <span class="board-title">\u25A3 Display Board</span>
        <span class="board-count">${this._entries.length}</span>
        <button class="refresh-btn" @click=${() => void this._fetch()}>\u21BB</button>
      </div>
      <div class="board">
        ${visible.map(e => {
          const parsed = this._parseHeading(e.heading);
          const icon = TYPE_ICONS[parsed.type] ?? '\u25CF';
          const color = PRIORITY_COLORS[parsed.priority] ?? 'var(--v-fg-dim)';
          return html`
            <div class="board-entry priority-${parsed.priority}">
              <span class="entry-icon" style="color:${color}">${icon}</span>
              <div class="entry-content">
                <div class="entry-heading">${parsed.label}</div>
                ${e.body ? html`<div class="entry-body">${e.body}</div>` : nothing}
              </div>
              <span class="entry-ts">${this._formatTs(e.timestamp)}</span>
            </div>
          `;
        })}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-queen-display-board': FcQueenDisplayBoard;
  }
}
