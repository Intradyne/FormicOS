import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state, query } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { timeAgo } from '../helpers.js';
import type { ChatSender, ColonyStatus } from '../types.js';
import './atoms.js';

/** Single colony chat message — matches ColonyChatMessage event shape. */
export interface ColonyChatEntry {
  sender: ChatSender;
  text: string;
  ts: string;
  /** For system events: spawn, merge, metric, pheromone, route, service, phase, governance, approval, complete */
  eventKind?: string;
  /** For service/colony messages: which colony sent it */
  sourceColony?: string;
}

const KIND_COLORS: Record<string, string> = {
  metric: 'var(--v-purple)',
  route: 'var(--v-warn)',
  pheromone: 'var(--v-accent)',
  merge: 'var(--v-secondary)',
  service: 'var(--v-service)',
  spawn: 'var(--v-success)',
  phase: 'var(--v-blue)',
  governance: 'var(--v-warn)',
  approval: 'var(--v-accent)',
  complete: 'var(--v-success)',
};

@customElement('fc-colony-chat')
export class FcColonyChat extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; flex-direction: column; overflow: hidden; }
    .header {
      display: flex; align-items: center; border-bottom: 1px solid var(--v-border);
      padding: 7px 10px; gap: 6px;
    }
    .header-icon { font-size: 10px; }
    .header-name {
      font-size: 10.5px; font-family: var(--f-display); font-weight: 600;
      color: var(--v-fg); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .messages { flex: 1; overflow: auto; padding: 4px 0; }
    .msg { padding: 4px 10px; }
    .msg.event { padding: 2px 10px; }

    /* Event row */
    .event-row { display: flex; align-items: center; gap: 4px; font-size: 9.5px; }
    .event-dot {
      width: 3px; height: 3px; border-radius: 50%; flex-shrink: 0;
    }
    .event-dot.service { border-radius: 1px; }
    .event-ts { font-family: var(--f-mono); font-size: 7.5px; color: var(--v-fg-dim); }
    .event-text { color: var(--v-fg-dim); font-size: 9.5px; }

    /* Colony/service inbound message */
    .colony-msg {
      background: var(--v-service-muted); border-radius: 6px; padding: 5px 8px;
      border: 1px solid rgba(34,211,238,0.08);
    }
    .colony-header { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; }
    .colony-icon { font-size: 7px; color: var(--v-service); }
    .colony-source {
      font-family: var(--f-mono); font-size: 7.5px; color: var(--v-service);
      font-weight: 600; letter-spacing: 0.06em;
    }
    .colony-body { font-size: 11px; line-height: 1.5; color: var(--v-fg); padding-left: 12px; }

    /* Operator / queen messages */
    .msg-header { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; }
    .msg-role {
      font-family: var(--f-mono); font-size: 7.5px; font-weight: 600;
      letter-spacing: 0.06em; text-transform: uppercase;
    }
    .msg-ts { font-family: var(--f-mono); font-size: 7px; color: var(--v-fg-dim); }
    .msg-body { font-size: 11.5px; line-height: 1.5; }
    .queen-icon { font-size: 7px; color: var(--v-accent); }

    /* Input bar */
    .input-bar {
      padding: 5px 8px; border-top: 1px solid var(--v-border);
      display: flex; gap: 5px;
    }
    .input-bar input {
      flex: 1; background: var(--v-void); border: 1px solid var(--v-border);
      border-radius: 999px; color: var(--v-fg); font-family: var(--f-body);
      font-size: 11px; padding: 6px 12px; outline: none;
      transition: border-color 0.15s;
    }
    .input-bar input:focus { border-color: rgba(232,88,26,0.25); }
  `];

  @property({ type: String }) colonyId = '';
  @property({ type: String }) colonyName = '';
  @property({ type: String }) status: ColonyStatus | 'service' = 'running';
  @property({ type: Array }) messages: ColonyChatEntry[] = [];

  @state() private _input = '';
  @query('.messages') private _scrollEl!: HTMLElement;

  updated(changed: Map<string, unknown>) {
    if (changed.has('messages')) {
      requestAnimationFrame(() => {
        this._scrollEl?.scrollTo({ top: this._scrollEl.scrollHeight, behavior: 'smooth' });
      });
    }
  }

  render() {
    const isService = this.status === 'service';
    const borderStyle = isService ? 'border-color: rgba(34,211,238,0.15)' : '';

    return html`
      <div class="header" style="${borderStyle}">
        <span class="header-icon" style="color:${isService ? 'var(--v-service)' : 'var(--v-accent)'}">
          ${isService ? '\u25C6' : '\u2B21'}
        </span>
        <span class="header-name">${this.colonyName || this.colonyId}</span>
        ${isService
          ? html`<fc-pill color="var(--v-service)" sm>service</fc-pill>`
          : html`<fc-pill color="var(--v-fg-dim)" sm>colony</fc-pill>`}
      </div>

      <div class="messages">
        ${this.messages.map(m => this._renderMessage(m))}
      </div>

      <div class="input-bar">
        <input
          .value=${this._input}
          @input=${(e: Event) => { this._input = (e.target as HTMLInputElement).value; }}
          @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this._send(); }}
          placeholder=${isService ? 'Message this service...' : 'Message this colony...'}
        />
        <fc-btn sm @click=${() => this._send()}>Send</fc-btn>
      </div>
    `;
  }

  private _renderMessage(m: ColonyChatEntry) {
    // System event — compact timeline row
    if (m.sender === 'system') {
      const dotColor = KIND_COLORS[m.eventKind ?? ''] ?? 'var(--v-fg-dim)';
      const isServiceKind = m.eventKind === 'service';
      return html`
        <div class="msg event">
          <div class="event-row">
            <span class="event-dot ${isServiceKind ? 'service' : ''}"
              style="background:${dotColor}"></span>
            <span class="event-ts">${timeAgo(m.ts)}</span>
            <span class="event-text">${m.text}</span>
          </div>
        </div>`;
    }

    // Service / colony inbound
    if (m.sender === 'service') {
      return html`
        <div class="msg">
          <div class="colony-msg">
            <div class="colony-header">
              <span class="colony-icon">\u2B21</span>
              <span class="colony-source">${m.sourceColony ?? 'service'}</span>
              <span class="msg-ts">${timeAgo(m.ts)}</span>
            </div>
            <div class="colony-body">${m.text}</div>
          </div>
        </div>`;
    }

    // Operator or queen
    const isQueen = m.sender === 'queen';
    return html`
      <div class="msg">
        <div class="msg-header">
          ${isQueen ? html`<span class="queen-icon">\u265B</span>` : nothing}
          <span class="msg-role" style="color:${isQueen ? 'var(--v-accent)' : 'var(--v-fg-dim)'}">
            ${isQueen ? 'Queen' : 'Operator'}
          </span>
          <span class="msg-ts">${timeAgo(m.ts)}</span>
        </div>
        <div class="msg-body" style="color:${isQueen ? 'var(--v-fg)' : 'rgba(237,237,240,0.8)'};padding-left:${isQueen ? '12px' : '0'}">
          ${m.text}
        </div>
      </div>`;
  }

  private _send() {
    const text = this._input.trim();
    if (!text) return;
    this._input = '';
    this.dispatchEvent(new CustomEvent('send-colony-message', {
      detail: { colonyId: this.colonyId, message: text },
      bubbles: true,
      composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-colony-chat': FcColonyChat; }
}
