/**
 * Wave 49 Track B: Inline result card for Queen chat.
 *
 * Renders structured colony completion metadata from a Queen follow-up message.
 * Provides deep-link actions to colony detail, audit, and thread timeline.
 *
 * Does NOT fabricate data — requires structured `ResultCardMeta` payload.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { ResultCardMeta } from '../types.js';
import './atoms.js';

const STATUS_STYLE: Record<string, { color: string; icon: string; label: string }> = {
  completed: { color: 'var(--v-success)', icon: '\u2713', label: 'Completed' },
  failed:    { color: 'var(--v-danger)',  icon: '\u2717', label: 'Failed' },
  killed:    { color: 'var(--v-danger)',  icon: '\u25A0', label: 'Killed' },
  running:   { color: 'var(--v-accent)',  icon: '\u25B6', label: 'Running' },
};

@customElement('fc-result-card')
export class FcResultCard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .card {
      border: 1px solid var(--v-border);
      border-radius: 10px;
      background: rgba(255,255,255,0.015);
      padding: 12px 14px;
      font-family: var(--f-mono);
      font-size: 11.5px;
      color: var(--v-fg);
    }
    .card.success { border-color: rgba(45,212,168,0.18); background: rgba(45,212,168,0.02); }
    .card.failure { border-color: rgba(248,113,113,0.18); background: rgba(248,113,113,0.02); }
    .card-header {
      display: flex; align-items: center; gap: 6px;
      margin-bottom: 6px;
    }
    .status-icon { font-size: 11px; font-weight: 700; }
    .card-title {
      font-family: var(--f-display); font-size: 12px; font-weight: 700;
      letter-spacing: -0.02em; flex: 1;
    }
    .validator-badge {
      font-size: 8px; padding: 1px 6px; border-radius: 4px;
      font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    }
    .validator-pass { background: rgba(45,212,168,0.1); color: var(--v-success); }
    .validator-fail { background: rgba(248,113,113,0.1); color: var(--v-danger); }
    .task-text {
      font-size: 11px; font-family: var(--f-body); color: var(--v-fg-muted);
      line-height: 1.4; margin-bottom: 8px;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .meta-row {
      display: flex; gap: 12px; flex-wrap: wrap;
      font-size: 10px; color: var(--v-fg-muted);
      margin-bottom: 8px;
    }
    .meta-item { display: flex; gap: 3px; align-items: center; }
    .meta-value { color: var(--v-fg); font-weight: 600; }
    .actions {
      display: flex; gap: 6px; margin-top: 8px;
    }
    .link-btn {
      font-size: 9.5px; font-family: var(--f-mono); padding: 3px 8px;
      border-radius: 5px; cursor: pointer; border: 1px solid var(--v-border);
      background: rgba(255,255,255,0.02); color: var(--v-fg-dim);
      transition: all 0.15s; text-transform: uppercase; letter-spacing: 0.05em;
    }
    .link-btn:hover {
      border-color: var(--v-border-hover); color: var(--v-fg);
      background: rgba(255,255,255,0.04);
    }
  `];

  @property({ type: Object }) result: ResultCardMeta | null = null;

  render() {
    const r = this.result;
    if (!r) return nothing;

    const s = STATUS_STYLE[r.status] ?? STATUS_STYLE.completed;
    const isSuccess = r.status === 'completed';
    const isFailure = r.status === 'failed' || r.status === 'killed';

    return html`
      <div class="card ${isSuccess ? 'success' : isFailure ? 'failure' : ''}">
        <div class="card-header">
          <span class="status-icon" style="color:${s.color}">${s.icon}</span>
          <span class="card-title" style="color:${s.color}">
            ${r.displayName || s.label}
          </span>
          ${r.validatorVerdict ? html`
            <span class="validator-badge ${r.validatorVerdict === 'pass' ? 'validator-pass' : 'validator-fail'}">
              ${r.validatorVerdict}
            </span>
          ` : nothing}
        </div>

        <div class="task-text">${r.task}</div>

        <div class="meta-row">
          <div class="meta-item">
            Rounds: <span class="meta-value">${r.rounds}/${r.maxRounds}</span>
          </div>
          <div class="meta-item">
            Cost: <span class="meta-value" style="color:var(--v-accent)">$${r.cost.toFixed(2)}</span>
          </div>
          ${r.qualityScore != null && r.qualityScore > 0 ? html`
            <div class="meta-item">
              Quality: <span class="meta-value" style="color:var(--v-success)">${(r.qualityScore * 100).toFixed(0)}%</span>
            </div>
          ` : nothing}
          ${r.entriesExtracted != null && r.entriesExtracted > 0 ? html`
            <div class="meta-item">
              Knowledge: <span class="meta-value">${r.entriesExtracted} extracted</span>
            </div>
          ` : nothing}
        </div>

        <div class="actions">
          <span class="link-btn" @click=${() => this._nav('colony')}>Colony Detail</span>
          ${r.threadId ? html`
            <span class="link-btn" @click=${() => this._nav('timeline')}>Timeline</span>
          ` : nothing}
        </div>
      </div>
    `;
  }

  private _nav(target: 'colony' | 'audit' | 'timeline') {
    const r = this.result;
    if (!r) return;
    this.dispatchEvent(new CustomEvent('result-navigate', {
      detail: { target, colonyId: r.colonyId, threadId: r.threadId },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-result-card': FcResultCard; }
}
