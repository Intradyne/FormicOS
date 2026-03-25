/**
 * Parallel colony result aggregation card.
 * Renders a DAG plan summary with colony status badges and cost totals.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { ParallelResultMeta, ParallelColonyResult } from '../types.js';

const _statusIcon = (s: string) =>
  s === 'completed' ? '\u2713' : s === 'failed' ? '\u2717' : '\u25CB';

const _statusClass = (s: string) =>
  s === 'completed' ? 'ok' : s === 'failed' ? 'err' : 'run';

@customElement('fc-parallel-result')
export class FcParallelResult extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .card {
      border: 1px solid var(--v-border);
      border-radius: 12px;
      background: rgba(255,255,255,0.04);
      padding: 14px 16px;
      font-family: var(--f-body);
      color: var(--v-fg);
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
    }
    .icon {
      font-size: 14px;
      color: var(--v-accent);
    }
    .plan-summary {
      font-family: var(--f-display);
      font-size: 13px;
      font-weight: 700;
      color: var(--v-fg);
      letter-spacing: -0.02em;
      line-height: 1.4;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }
    .badge {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 10px;
      border: 1px solid var(--v-border);
      border-radius: 8px;
      background: rgba(255,255,255,0.02);
      cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .badge:hover {
      border-color: rgba(232,88,26,0.25);
      background: rgba(255,255,255,0.05);
    }
    .status { font-size: 13px; font-weight: 700; line-height: 1; }
    .status.ok  { color: var(--v-success); }
    .status.err { color: var(--v-danger); }
    .status.run { color: var(--v-fg-muted); }
    .badge-label {
      flex: 1;
      font-size: 11px;
      font-family: var(--f-mono);
      color: var(--v-fg);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .badge-cost {
      font-size: 9.5px;
      font-family: var(--f-mono);
      color: var(--v-fg-dim);
      white-space: nowrap;
    }
    .footer {
      display: flex;
      gap: 16px;
      font-size: 10px;
      font-family: var(--f-mono);
      color: var(--v-fg-muted);
      letter-spacing: 0.03em;
    }
  `];

  @property({ type: Object }) result: ParallelResultMeta | null = null;

  render() {
    const r = this.result;
    if (!r) return nothing;
    return html`
      <div class="card">
        <div class="header">
          <span class="icon">\u2263</span>
          <span class="plan-summary">${r.planSummary}</span>
        </div>
        <div class="grid">
          ${r.colonies.map(c => this._badge(c))}
        </div>
        <div class="footer">
          <span>Cost \u00A0$${r.totalCost.toFixed(4)}</span>
          <span>${(r.durationMs / 1000).toFixed(1)}s</span>
        </div>
      </div>
    `;
  }

  private _badge(c: ParallelColonyResult) {
    const label = c.displayName ?? c.task.slice(0, 32);
    return html`
      <div class="badge" @click=${() => this._nav(c.colonyId)}>
        <span class="status ${_statusClass(c.status)}">${_statusIcon(c.status)}</span>
        <span class="badge-label" title=${c.task}>${label}</span>
        <span class="badge-cost">$${c.cost.toFixed(4)}</span>
      </div>
    `;
  }

  private _nav(colonyId: string) {
    this.dispatchEvent(new CustomEvent('result-navigate', {
      detail: { target: 'colony', colonyId },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-parallel-result': FcParallelResult; }
}
