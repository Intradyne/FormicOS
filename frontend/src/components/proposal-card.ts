/**
 * Wave 61 Track 2: Proposal card for Queen's propose_plan tool output.
 *
 * Renders structured proposal data as an interactive card with option
 * selection, questions, and recommendation display. Emits proposal-action
 * events for confirm/adjust flows.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { ProposalData, ProposalOption } from '../types.js';
import './atoms.js';

@customElement('fc-proposal-card')
export class FcProposalCard extends LitElement {
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
    .summary {
      font-family: var(--f-display);
      font-size: 13px;
      font-weight: 700;
      color: var(--v-fg);
      line-height: 1.4;
      margin-bottom: 12px;
      letter-spacing: -0.02em;
    }
    .options { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
    .option {
      border: 1px solid var(--v-border);
      border-radius: 10px;
      background: rgba(255,255,255,0.02);
      padding: 10px 12px;
      transition: border-color 0.15s, background 0.15s;
      cursor: default;
    }
    .option:hover {
      border-color: rgba(232,88,26,0.25);
      background: rgba(255,255,255,0.05);
    }
    .option-header {
      font-family: var(--f-mono);
      font-size: 11px;
      font-weight: 700;
      color: var(--v-accent);
      letter-spacing: 0.03em;
      margin-bottom: 4px;
    }
    .option-desc {
      font-size: 12px;
      line-height: 1.5;
      color: var(--v-fg);
      margin-bottom: 8px;
    }
    .option-footer {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 9.5px;
      font-family: var(--f-mono);
      padding: 2px 7px;
      border-radius: 5px;
      font-weight: 600;
    }
    .badge-colonies {
      background: rgba(91,156,245,0.1);
      color: var(--v-blue);
      border: 1px solid rgba(91,156,245,0.15);
    }
    .badge-cost-free {
      background: rgba(45,212,168,0.1);
      color: var(--v-success);
      border: 1px solid rgba(45,212,168,0.15);
    }
    .badge-cost-paid {
      background: rgba(245,183,49,0.1);
      color: var(--v-warn);
      border: 1px solid rgba(245,183,49,0.15);
    }
    .option-actions { margin-left: auto; }

    .questions {
      margin-bottom: 12px;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(91,156,245,0.03);
      border: 1px solid rgba(91,156,245,0.1);
    }
    .questions-header {
      font-size: 10px;
      font-family: var(--f-mono);
      font-weight: 600;
      color: var(--v-fg-dim);
      margin-bottom: 6px;
      letter-spacing: 0.04em;
    }
    .questions ul {
      margin: 0;
      padding-left: 16px;
      list-style-type: disc;
    }
    .questions li {
      font-size: 11.5px;
      line-height: 1.5;
      color: var(--v-fg-muted);
      margin-bottom: 2px;
    }

    .recommendation {
      margin-bottom: 12px;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(167,139,250,0.04);
      border: 1px solid rgba(167,139,250,0.14);
    }
    .rec-header {
      font-size: 10px;
      font-family: var(--f-mono);
      font-weight: 600;
      color: rgba(167,139,250,0.8);
      margin-bottom: 4px;
      letter-spacing: 0.04em;
    }
    .rec-text {
      font-size: 12px;
      line-height: 1.5;
      color: var(--v-fg);
    }

    .bottom-actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 4px;
    }
  `];

  @property({ type: Object }) proposal: ProposalData | null = null;

  render() {
    const p = this.proposal;
    if (!p) return nothing;

    return html`
      <div class="card">
        <div class="summary">${p.summary}</div>

        <div class="options">
          ${p.options.map(opt => this._renderOption(opt))}
        </div>

        ${p.questions && p.questions.length > 0 ? html`
          <div class="questions">
            <div class="questions-header">These questions might help refine the plan:</div>
            <ul>
              ${p.questions.map(q => html`<li>${q}</li>`)}
            </ul>
          </div>
        ` : nothing}

        ${p.recommendation ? html`
          <div class="recommendation">
            <div class="rec-header">Recommendation</div>
            <div class="rec-text">${p.recommendation}</div>
          </div>
        ` : nothing}

        <div class="bottom-actions">
          <fc-btn variant="ghost" sm @click=${this._adjust}>Let me adjust</fc-btn>
        </div>
      </div>
    `;
  }

  private _renderOption(opt: ProposalOption) {
    const isFree = opt.estimated_cost?.toLowerCase().includes('free');
    return html`
      <div class="option">
        <div class="option-header">${opt.label}</div>
        <div class="option-desc">${opt.description}</div>
        <div class="option-footer">
          ${opt.colonies != null ? html`
            <span class="badge badge-colonies">${opt.colonies} ${opt.colonies === 1 ? 'colony' : 'colonies'}</span>
          ` : nothing}
          ${opt.estimated_cost ? html`
            <span class="badge ${isFree ? 'badge-cost-free' : 'badge-cost-paid'}">${opt.estimated_cost}</span>
          ` : nothing}
          <span class="option-actions">
            <fc-btn variant="primary" sm @click=${() => this._confirm(opt)}>Go ahead</fc-btn>
          </span>
        </div>
      </div>
    `;
  }

  private _confirm(opt: ProposalOption) {
    this.dispatchEvent(new CustomEvent('proposal-action', {
      detail: {
        action: 'confirm',
        message: `Go ahead: ${opt.description}`,
      },
      bubbles: true, composed: true,
    }));
  }

  private _adjust() {
    this.dispatchEvent(new CustomEvent('proposal-action', {
      detail: {
        action: 'adjust',
        message: `Regarding the plan "${this.proposal?.summary}": `,
      },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-proposal-card': FcProposalCard; }
}
