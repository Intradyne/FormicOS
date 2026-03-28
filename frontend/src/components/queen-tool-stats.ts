/**
 * Wave 74 Track 4d: Queen tool usage stats.
 * Compact table showing session tool call counts from
 * GET /api/v1/queen-tool-stats.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';

interface ToolStat {
  name: string;
  count: number;
  last_status: string;
}

@customElement('fc-queen-tool-stats')
export class FcQueenToolStats extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
    }
    .title {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase;
    }
    .total {
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

    .tool-grid {
      display: grid; grid-template-columns: 1fr auto;
      gap: 1px 12px; align-items: center;
    }

    .tool-name {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }

    .tool-count {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg);
      font-weight: 600; font-feature-settings: 'tnum';
      text-align: right;
    }

    .empty {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-dim);
      padding: 6px 0;
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @state() private _stats: ToolStat[] = [];
  @state() private _loaded = false;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  private async _fetch() {
    try {
      const resp = await fetch('/api/v1/queen-tool-stats');
      if (!resp.ok) return;
      const data = await resp.json();
      this._stats = (data.tools ?? []) as ToolStat[];
    } catch { /* silent */ }
    this._loaded = true;
  }

  render() {
    if (!this._loaded || this._stats.length === 0) return nothing;

    const totalCalls = this._stats.reduce((s, t) => s + t.count, 0);

    return html`
      <div class="header">
        <span class="title">\u2699 Tool Usage</span>
        <span class="total">${totalCalls} calls</span>
        <button class="refresh-btn" @click=${() => void this._fetch()}>\u21BB</button>
      </div>
      <div class="tool-grid">
        ${this._stats.map(t => html`
          <span class="tool-name">${t.name}</span>
          <span class="tool-count">${t.count}</span>
        `)}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-queen-tool-stats': FcQueenToolStats;
  }
}
