/**
 * Wave 63: Edit proposal card for Queen's edit_file tool output.
 *
 * Renders a unified diff with syntax-colored lines, file path header,
 * reason text, and apply/reject action buttons. Emits edit-apply and
 * edit-reject events for operator decision flow.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { EditProposalMeta } from '../types.js';

@customElement('fc-edit-proposal')
export class FcEditProposal extends LitElement {
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
    .file-header {
      display: flex;
      align-items: center;
      gap: 6px;
      font-family: var(--f-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--v-accent);
      letter-spacing: 0.02em;
      margin-bottom: 10px;
    }
    .file-icon {
      font-size: 13px;
      opacity: 0.7;
    }
    .diff-block {
      background: var(--v-recessed);
      border: 1px solid var(--v-border);
      border-radius: 8px;
      padding: 8px 10px;
      margin-bottom: 10px;
      overflow-x: auto;
      font-family: var(--f-mono);
      font-size: 11px;
      line-height: 1.6;
      white-space: pre;
    }
    .line-del {
      background: rgba(248,81,73,0.10);
      color: var(--v-danger);
    }
    .line-add {
      background: rgba(45,212,168,0.10);
      color: var(--v-success);
    }
    .line-hunk {
      color: var(--v-fg-dim);
      font-style: italic;
    }
    .line-ctx {
      color: var(--v-fg-muted);
    }
    .reason {
      font-size: 12px;
      line-height: 1.5;
      color: var(--v-fg);
      margin-bottom: 12px;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .btn {
      font-family: var(--f-mono);
      font-size: 11px;
      font-weight: 600;
      padding: 5px 14px;
      border-radius: 7px;
      border: 1px solid transparent;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    .btn-apply {
      background: rgba(45,212,168,0.12);
      color: var(--v-success);
      border-color: rgba(45,212,168,0.2);
    }
    .btn-apply:hover {
      background: rgba(45,212,168,0.22);
      border-color: rgba(45,212,168,0.35);
    }
    .btn-reject {
      background: rgba(248,81,73,0.10);
      color: var(--v-danger);
      border-color: rgba(248,81,73,0.18);
    }
    .btn-reject:hover {
      background: rgba(248,81,73,0.20);
      border-color: rgba(248,81,73,0.32);
    }
  `];

  @property({ type: Object }) proposal: EditProposalMeta | null = null;

  render() {
    const p = this.proposal;
    if (!p) return nothing;

    const lines = p.diff.split('\n');

    return html`
      <div class="card">
        <div class="file-header">
          <span class="file-icon">&#128196;</span>
          <span>${p.filePath}</span>
        </div>

        <div class="diff-block">${lines.map(l => {
          const cls = l.startsWith('-') ? 'line-del'
            : l.startsWith('+') ? 'line-add'
            : l.startsWith('@@') ? 'line-hunk'
            : 'line-ctx';
          return html`<div class="${cls}">${l}</div>`;
        })}</div>

        <div class="reason">${p.reason}</div>

        <div class="actions">
          <button class="btn btn-reject" @click=${this._reject}>Reject</button>
          <button class="btn btn-apply" @click=${this._apply}>Apply</button>
        </div>
      </div>
    `;
  }

  private _apply() {
    const p = this.proposal;
    if (!p) return;
    this.dispatchEvent(new CustomEvent('edit-apply', {
      detail: { filePath: p.filePath, diff: p.diff, colonyId: p.colonyId },
      bubbles: true, composed: true,
    }));
  }

  private _reject() {
    const p = this.proposal;
    if (!p) return;
    this.dispatchEvent(new CustomEvent('edit-reject', {
      detail: { filePath: p.filePath, colonyId: p.colonyId },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-edit-proposal': FcEditProposal; }
}
