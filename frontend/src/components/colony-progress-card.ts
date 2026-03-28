/**
 * Wave 69 Track 1: Inline colony progress card for Queen chat.
 *
 * Subscribes to store updates for a specific colony and renders live progress
 * inline within the Queen chat. Transitions to a compact completed state
 * when the colony finishes.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import { store, findNode } from '../state/store.js';
import type { Colony, TreeNode } from '../types.js';

const STATUS_COLOR: Record<string, string> = {
  running:   'var(--v-accent)',
  completed: 'var(--v-success)',
  failed:    'var(--v-danger)',
  killed:    'var(--v-danger)',
  pending:   'var(--v-fg-dim)',
  queued:    'var(--v-fg-dim)',
};

@customElement('fc-colony-progress')
export class ColonyProgressCard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .card {
      border: 1px solid var(--v-border);
      border-radius: 10px;
      background: rgba(255,255,255,0.015);
      padding: 10px 12px;
      font-family: var(--f-mono);
      font-size: 10.5px;
      color: var(--v-fg);
      transition: border-color 0.15s, background 0.15s;
    }
    @media (prefers-reduced-motion: reduce) {
      .card { transition: none; }
    }
    .card.running { border-color: rgba(232,88,26,0.18); }
    .card.completed { border-color: rgba(45,212,168,0.18); background: rgba(45,212,168,0.02); }
    .card.failed { border-color: rgba(248,113,113,0.18); background: rgba(248,113,113,0.02); }
    .header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
    }
    .status-dot {
      width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
    }
    .task-label {
      font-family: var(--f-body); font-size: 11px; color: var(--v-fg-muted);
      flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .caste-badge {
      font-size: 8px; padding: 1px 5px; border-radius: 3px;
      background: var(--v-accent-muted); color: var(--v-accent);
      font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    }
    .progress-row {
      display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
    }
    .bar-track {
      flex: 1; height: 4px; border-radius: 2px;
      background: rgba(255,255,255,0.06);
      overflow: hidden;
    }
    .bar-fill {
      height: 100%; border-radius: 2px;
      background: var(--v-accent);
      transition: width 0.3s ease;
    }
    @media (prefers-reduced-motion: reduce) {
      .bar-fill { transition: none; }
    }
    .bar-label {
      font-size: 9px; color: var(--v-fg-dim); white-space: nowrap;
      font-feature-settings: 'tnum';
    }
    .meta-row {
      display: flex; gap: 10px; font-size: 9px; color: var(--v-fg-dim);
    }
    .meta-item { display: flex; gap: 3px; align-items: center; }
    .meta-val { color: var(--v-fg-muted); font-weight: 600; }
    .sparkline { flex-shrink: 0; }
    .compact {
      display: flex; align-items: center; gap: 8px;
    }
    .compact-status {
      font-size: 10px; font-weight: 700;
    }
    .compact-task {
      font-family: var(--f-body); font-size: 10.5px; color: var(--v-fg-muted);
      flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .compact-meta {
      font-size: 9px; color: var(--v-fg-dim); white-space: nowrap;
      font-feature-settings: 'tnum';
    }
  `];

  @property() colonyId = '';
  @property() task = '';
  private _unsub?: () => void;

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe(() => this.requestUpdate());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  render() {
    const node = findNode(store.state.tree, this.colonyId) as Colony | null;
    if (!node) return nothing;

    const status = node.status ?? 'pending';
    const isTerminal = status === 'completed' || status === 'failed' || status === 'killed';

    if (isTerminal) return this._renderCompact(node, status);
    return this._renderRunning(node, status);
  }

  private _renderRunning(c: Colony, status: string) {
    const round = c.round ?? 0;
    const maxRounds = c.maxRounds ?? 10;
    const pct = maxRounds > 0 ? Math.min(100, (round / maxRounds) * 100) : 0;
    const cost = c.cost ?? 0;
    const strategy = c.strategy ?? '';
    const caste = c.castes?.[0]?.caste ?? '';
    const history = c.convergenceHistory ?? [];
    const color = STATUS_COLOR[status] ?? 'var(--v-fg-dim)';

    return html`
      <div class="card running">
        <div class="header">
          <span class="status-dot" style="background:${color};box-shadow:0 0 6px ${color}"></span>
          <span class="task-label">${this.task || c.task || this.colonyId}</span>
          ${caste ? html`<span class="caste-badge">${caste}</span>` : nothing}
        </div>
        <div class="progress-row">
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct}%"></div>
          </div>
          <span class="bar-label">${round}/${maxRounds}</span>
          ${history.length >= 3 ? this._renderSparkline(history) : nothing}
        </div>
        <div class="meta-row">
          ${strategy ? html`<div class="meta-item">Strategy: <span class="meta-val">${strategy}</span></div>` : nothing}
          <div class="meta-item">Cost: <span class="meta-val" style="color:var(--v-accent)">$${cost.toFixed(2)}</span></div>
        </div>
      </div>
    `;
  }

  private _renderCompact(c: Colony, status: string) {
    const color = STATUS_COLOR[status] ?? 'var(--v-fg-dim)';
    const icon = status === 'completed' ? '\u2713' : '\u2717';
    const cost = c.cost ?? 0;
    const quality = c.qualityScore ?? 0;

    return html`
      <div class="card ${status}">
        <div class="compact">
          <span class="compact-status" style="color:${color}">${icon}</span>
          <span class="compact-task">${this.task || c.task || this.colonyId}</span>
          <span class="compact-meta">
            $${cost.toFixed(2)}
            ${quality > 0 ? html` · ${(quality * 100).toFixed(0)}%` : nothing}
          </span>
        </div>
      </div>
    `;
  }

  private _renderSparkline(history: number[]) {
    const recent = history.slice(-8);
    const w = 40;
    const h = 16;
    const max = Math.max(...recent, 0.01);
    const step = w / Math.max(recent.length - 1, 1);
    const points = recent.map((v, i) =>
      `${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`
    ).join(' ');

    return html`
      <svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
        <polyline
          points="${points}"
          fill="none"
          stroke="var(--v-accent)"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-colony-progress': ColonyProgressCard; }
}
