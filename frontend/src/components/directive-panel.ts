import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

/**
 * Operator directive panel — send typed directives to running colonies (Wave 35 C1).
 *
 * Visible when colonies are running. Allows operators to steer colony behavior
 * mid-execution via context_update, priority_shift, constraint_add, or strategy_change.
 */
@customElement('fc-directive-panel')
export class FcDirectivePanel extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; padding: 12px; }
    .panel-title { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); margin-bottom: 10px; }
    .form-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
    label { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); min-width: 60px; }
    select {
      font-size: 11px; font-family: var(--f-mono); padding: 4px 8px; border-radius: 6px;
      border: 1px solid var(--v-border); background: var(--v-recessed); color: var(--v-fg);
      outline: none;
    }
    select:focus { border-color: rgba(232,88,26,0.3); }
    .priority-toggle {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .priority-toggle.urgent { background: rgba(240,100,100,0.15); border-color: rgba(240,100,100,0.3); color: #F06464; }
    textarea {
      width: 100%; min-height: 60px; font-size: 11px; font-family: var(--f-mono);
      padding: 6px 8px; border-radius: 6px; border: 1px solid var(--v-border);
      background: var(--v-recessed); color: var(--v-fg); resize: vertical; outline: none;
    }
    textarea:focus { border-color: rgba(232,88,26,0.3); }
    .send-btn {
      font-size: 10px; font-family: var(--f-mono); padding: 4px 14px; border-radius: 6px;
      cursor: pointer; border: 1px solid rgba(232,88,26,0.3); background: rgba(232,88,26,0.08);
      color: var(--v-accent); transition: all 0.15s;
    }
    .send-btn:hover { background: rgba(232,88,26,0.15); }
    .send-btn:disabled { opacity: 0.4; cursor: default; }
  `];

  @state() private _directiveType = 'context_update';
  @state() private _priority = 'normal';
  @state() private _content = '';
  @state() private _sending = false;

  /** Colony ID must be set by parent component. */
  @state() colonyId = '';

  render() {
    return html`
      <div class="panel-title">Send Directive</div>
      <div class="form-row">
        <label>Type</label>
        <select @change=${(ev: Event) => { this._directiveType = (ev.target as HTMLSelectElement).value; }}>
          <option value="context_update">Context Update</option>
          <option value="priority_shift">Priority Shift</option>
          <option value="constraint_add">Constraint</option>
          <option value="strategy_change">Strategy Change</option>
        </select>
      </div>
      <div class="form-row">
        <label>Priority</label>
        <button class="priority-toggle ${this._priority === 'urgent' ? 'urgent' : ''}"
          @click=${() => { this._priority = this._priority === 'normal' ? 'urgent' : 'normal'; }}>
          ${this._priority}
        </button>
      </div>
      <textarea
        placeholder="Directive content..."
        .value=${this._content}
        @input=${(ev: Event) => { this._content = (ev.target as HTMLTextAreaElement).value; }}
      ></textarea>
      <div class="form-row" style="margin-top:6px">
        <button class="send-btn"
          ?disabled=${!this._content.trim() || !this.colonyId || this._sending}
          @click=${() => void this._send()}>
          ${this._sending ? 'Sending...' : 'Send'}
        </button>
      </div>
    `;
  }

  private async _send() {
    if (!this._content.trim() || !this.colonyId) return;
    this._sending = true;
    try {
      this.dispatchEvent(new CustomEvent('directive-send', {
        bubbles: true, composed: true,
        detail: {
          colony_id: this.colonyId,
          message: this._content,
          directive_type: this._directiveType,
          directive_priority: this._priority,
        },
      }));
      this._content = '';
    } finally {
      this._sending = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-directive-panel': FcDirectivePanel; }
}
