import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { ApprovalRequest } from '../types.js';
import './atoms.js';

@customElement('fc-approval-queue')
export class FcApprovalQueue extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; margin-bottom: 20px; }
    .item {
      padding: 12px; margin-bottom: 6px; display: flex; align-items: center; gap: 10px;
    }
    .bar { width: 3px; height: 28px; border-radius: 2px; background: var(--v-accent); flex-shrink: 0; }
    .info { flex: 1; }
    .type { font-size: 9px; font-family: var(--f-mono); color: var(--v-accent); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 1px; }
    .detail { font-size: 11.5px; color: var(--v-fg); }
    .colony-name { font-size: 9px; color: var(--v-fg-dim); }
    .actions { display: flex; gap: 4px; }
  `];

  @property({ type: Array }) approvals: ApprovalRequest[] = [];

  render() {
    return html`
      <div class="s-label">Pending Approvals</div>
      ${this.approvals.map(a => html`
        <div class="glass featured item">
          <div class="bar"></div>
          <div class="info">
            <div class="type">${a.type}</div>
            <div class="detail">${a.agent} \u2192 ${a.detail}</div>
            <div class="colony-name">${(a as any).colonyName ?? a.colony}</div>
          </div>
          <div class="actions">
            <fc-btn variant="success" sm @click=${() => this.fire('approve', a.id)}>Approve</fc-btn>
            <fc-btn variant="danger" sm @click=${() => this.fire('deny', a.id)}>Deny</fc-btn>
          </div>
        </div>
      `)}`;
  }

  private fire(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-approval-queue': FcApprovalQueue; }
}
