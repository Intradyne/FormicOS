/**
 * Wave 49: Queen chat — the primary conversational orchestration surface.
 *
 * Renders structured preview/result cards inline when metadata is present.
 * Distinguishes ask vs notify messages visually.
 * Falls back to plain text when structured metadata is absent.
 * Stays Queen-thread-first — not a raw event feed.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state, query } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import { timeAgo } from '../helpers.js';
import type { QueenThread, QueenChatMessage, EventKind, PreviewCardMeta, ResultCardMeta } from '../types.js';
import './atoms.js';
import './directive-panel.js';
import './fc-preview-card.js';
import './fc-result-card.js';

const kindColor: Record<string, string> = {
  spawn: '#2DD4A8', merge: '#3DD6F5', metric: '#A78BFA', route: '#F5B731', pheromone: '#E8581A',
};

/** Heuristic fallback: detect ask-like messages when backend intent is absent. */
function inferIntent(m: QueenChatMessage): 'ask' | 'notify' | undefined {
  if (m.intent) return m.intent;
  if (m.role !== 'queen') return undefined;
  // Simple heuristic: messages ending with '?' are ask-like
  const trimmed = m.text.trim();
  if (trimmed.endsWith('?')) return 'ask';
  return undefined;
}

@customElement('fc-queen-chat')
export class FcQueenChat extends LitElement {
  static styles = [voidTokens, css`
    :host {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      background: var(--v-surface);
      border-radius: 10px;
      border: 1px solid var(--v-border);
      overflow: hidden;
    }
    .tabs { display: flex; align-items: center; border-bottom: 1px solid var(--v-border); padding: 0 4px; min-height: 36px; overflow: auto; gap: 0; }
    .tabs .icon { font-size: 11px; color: var(--v-accent); padding: 0 8px; flex-shrink: 0; filter: drop-shadow(0 0 3px rgba(232,88,26,0.16)); }
    .tab { padding: 7px 10px; cursor: pointer; font-size: 11.5px; font-family: var(--f-body); font-weight: 500; white-space: nowrap;
      color: var(--v-fg-dim); border-bottom: 2px solid transparent; transition: all 0.15s; }
    .tab.active { color: var(--v-fg); border-bottom-color: var(--v-accent); }
    .add-tab {
      padding: 7px 10px; cursor: pointer; font-size: 13px; color: var(--v-accent);
      margin-left: auto; flex-shrink: 0; background: var(--v-accent-muted);
      border-left: 1px solid var(--v-border); font-weight: 700;
    }
    .add-tab:hover { color: var(--v-accent-bright); }
    .messages {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      overscroll-behavior: contain;
      padding: 8px 0;
    }
    .event-row { display: flex; align-items: center; gap: 5px; padding: 2px 12px; font-size: 10px; }
    .event-dot { width: 3px; height: 3px; border-radius: 50%; flex-shrink: 0; }
    .event-ts { font-family: var(--f-mono); font-size: 8.5px; color: var(--v-fg-dim); font-feature-settings: 'tnum'; }
    .event-text { color: var(--v-fg-dim); font-size: 10px; }

    /* Message bubbles */
    .msg { padding: 6px 12px; }
    .msg-header { display: flex; align-items: center; gap: 5px; margin-bottom: 2px; }
    .msg-role { font-family: var(--f-mono); font-size: 8px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    .msg-ts { font-family: var(--f-mono); font-size: 7.5px; color: var(--v-fg-dim); font-feature-settings: 'tnum'; }
    .msg-body { font-size: 12px; line-height: 1.55; }

    /* Wave 49: Ask/Notify visual distinction */
    .msg.intent-ask {
      border-left: 2px solid var(--v-accent);
      background: rgba(232,88,26,0.025);
      padding-left: 10px;
    }
    .msg.intent-notify {
      opacity: 0.78;
    }
    .ask-badge {
      font-size: 7.5px; font-family: var(--f-mono); padding: 1px 5px;
      border-radius: 3px; background: rgba(232,88,26,0.1); color: var(--v-accent);
      font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    }

    /* Card container */
    .card-wrap { padding: 6px 12px; }

    .thinking { padding: 6px 12px; display: flex; align-items: center; gap: 6px; }
    .thinking-dots { display: flex; gap: 3px; }
    .thinking-dots span {
      width: 4px; height: 4px; border-radius: 50%; background: var(--v-accent);
      opacity: 0.4; animation: think 1.4s ease-in-out infinite;
    }
    .thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
    .thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes think { 0%,100%{opacity:0.2} 50%{opacity:0.8} }
    .thinking-label { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.06em; }
    .input-row { padding: 6px 8px; border-top: 1px solid var(--v-border); display: flex; gap: 5px; }
    input {
      flex: 1; background: var(--v-void); border: 1px solid var(--v-border); border-radius: 999px;
      color: var(--v-fg); font-family: var(--f-body); font-size: 12px; padding: 7px 14px; outline: none;
      transition: border-color 0.2s;
    }
    input:focus { border-color: rgba(232,88,26,0.25); }
    .empty-hint { text-align: center; font-size: 11px; color: var(--v-fg-dim); }
    .pin-btn { cursor: pointer; font-size: 9px; color: var(--v-fg-dim); opacity: 0; transition: opacity 0.15s; padding: 1px 4px; border-radius: 3px; }
    .pin-btn:hover { color: var(--v-accent); background: var(--v-accent-muted); }
    .msg:hover .pin-btn { opacity: 1; }
    .directive-toggle {
      display: flex; align-items: center; gap: 6px; padding: 4px 8px;
      border-top: 1px solid var(--v-border); cursor: pointer;
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      transition: color 0.15s;
    }
    .directive-toggle:hover { color: var(--v-accent); }
    .directive-toggle .dt-icon { font-size: 10px; }
    .directive-colony-select {
      font-size: 10px; font-family: var(--f-mono); padding: 2px 6px; border-radius: 4px;
      border: 1px solid var(--v-border); background: var(--v-recessed); color: var(--v-fg);
      outline: none; margin-left: auto;
    }
  `];

  @property({ type: Array }) threads: QueenThread[] = [];
  @property() activeThreadId = '';
  @property({ type: Array }) runningColonies: { id: string; name: string }[] = [];
  @state() private input = '';
  @state() private _queenPending = false;
  @state() private _directiveOpen = false;
  @state() private _directiveTargetId = '';
  /** Track which preview cards have been confirmed/cancelled (by message index). */
  @state() private _confirmedPreviews = new Set<number>();
  @state() private _cancelledPreviews = new Set<number>();
  @query('.messages') private messagesEl!: HTMLElement;

  private get activeThread(): QueenThread | undefined {
    return this.threads.find(t => t.id === this.activeThreadId) ?? this.threads[0];
  }

  updated() {
    if (this.messagesEl) this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    if (this._queenPending) {
      const msgs = this.activeThread?.messages;
      if (msgs && msgs.length > 0 && msgs[msgs.length - 1].role === 'queen') {
        this._queenPending = false;
      }
    }
  }

  render() {
    const active = this.activeThread;
    return html`
      <div class="tabs">
        <span class="icon">\u265B</span>
        ${this.threads.map(t => html`
          <div class="tab ${t.id === active?.id ? 'active' : ''}" @click=${() => this.switchThread(t.id)}>${t.name}</div>
        `)}
        <div class="add-tab" @click=${this.newThread}>+</div>
      </div>
      <div class="messages">
        ${!active?.messages.length ? html`
          <div class="empty-hint" style="padding:24px 16px">Ask me anything \u2014 describe a task and I\u2019ll propose a plan</div>
        ` : nothing}
        ${active?.messages.map((m, idx) => this._renderMessage(m, idx))}
      </div>
      ${this._queenPending ? html`
        <div class="thinking">
          <span style="font-size:8px;color:var(--v-accent)">\u265B</span>
          <div class="thinking-dots"><span></span><span></span><span></span></div>
          <span class="thinking-label">Queen is thinking\u2026</span>
        </div>` : nothing}
      ${this.runningColonies.length > 0 ? html`
        <div class="directive-toggle" @click=${() => { this._directiveOpen = !this._directiveOpen; }}>
          <span class="dt-icon">\u2192</span>
          <span>${this._directiveOpen ? 'Hide Directive' : 'Send Directive'}</span>
          ${this._directiveOpen && this.runningColonies.length > 1 ? html`
            <select class="directive-colony-select"
              @click=${(e: Event) => e.stopPropagation()}
              @change=${(e: Event) => { this._directiveTargetId = (e.target as HTMLSelectElement).value; }}>
              ${this.runningColonies.map(c => html`<option value=${c.id} ?selected=${c.id === this._directiveTargetId}>${c.name}</option>`)}
            </select>` : nothing}
        </div>
        ${this._directiveOpen ? html`
          <fc-directive-panel
            .colonyId=${this._directiveTargetId || this.runningColonies[0]?.id || ''}
            @directive-send=${this._onDirectiveSend}
          ></fc-directive-panel>` : nothing}
      ` : nothing}
      <div class="input-row">
        <input .value=${this.input} placeholder="Describe a task or ask the Queen..."
          @input=${(e: InputEvent) => { this.input = (e.target as HTMLInputElement).value; }}
          @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this.sendMessage(); }}/>
        <fc-btn sm @click=${this.sendMessage}>Send</fc-btn>
      </div>`;
  }

  private _renderMessage(m: QueenChatMessage, idx: number) {
    // Event rows
    if (m.role === 'event') {
      return html`<div class="event-row">
        <span class="event-dot" style="background:${kindColor[m.kind as string] ?? '#3A3A44'};box-shadow:0 0 5px ${kindColor[m.kind as string] ?? '#3A3A44'}35"></span>
        <span class="event-ts">${timeAgo(m.ts)}</span>
        <span class="event-text">${m.text}</span>
      </div>`;
    }

    // Wave 49: render structured cards when metadata says so
    const renderType = m.render;
    if (renderType === 'preview_card' && m.meta) {
      const preview = m.meta as unknown as PreviewCardMeta;
      return html`
        <div class="msg">
          <div class="msg-header">
            <span style="font-size:8px;color:var(--v-accent)">\u265B</span>
            <span class="msg-role" style="color:var(--v-accent)">Queen</span>
            <span class="msg-ts">${timeAgo(m.ts)}</span>
          </div>
          ${m.text ? html`<div class="msg-body" style="color:var(--v-fg);padding-left:14px;margin-bottom:8px">${m.text}</div>` : nothing}
        </div>
        <div class="card-wrap">
          <fc-preview-card
            .preview=${preview}
            ?confirmed=${this._confirmedPreviews.has(idx)}
            ?cancelled=${this._cancelledPreviews.has(idx)}
            @preview-confirm=${(e: CustomEvent) => this._handlePreviewConfirm(e, idx)}
            @preview-cancel=${() => this._handlePreviewCancel(idx)}
            @preview-open-editor=${this._handleOpenEditor}
          ></fc-preview-card>
        </div>`;
    }

    if (renderType === 'result_card' && m.meta) {
      const result = m.meta as unknown as ResultCardMeta;
      return html`
        <div class="msg">
          <div class="msg-header">
            <span style="font-size:8px;color:var(--v-accent)">\u265B</span>
            <span class="msg-role" style="color:var(--v-accent)">Queen</span>
            <span class="msg-ts">${timeAgo(m.ts)}</span>
          </div>
          ${m.text ? html`<div class="msg-body" style="color:var(--v-fg);padding-left:14px;margin-bottom:8px">${m.text}</div>` : nothing}
        </div>
        <div class="card-wrap">
          <fc-result-card
            .result=${result}
            @result-navigate=${this._handleResultNavigate}
          ></fc-result-card>
        </div>`;
    }

    // Standard text message with ask/notify distinction
    const intent = inferIntent(m);
    const intentClass = intent === 'ask' ? 'intent-ask' : intent === 'notify' ? 'intent-notify' : '';

    return html`<div class="msg ${intentClass}">
      <div class="msg-header">
        ${m.role === 'queen' ? html`<span style="font-size:8px;color:var(--v-accent)">\u265B</span>` : nothing}
        <span class="msg-role" style="color:${m.role === 'queen' ? 'var(--v-accent)' : 'var(--v-fg-dim)'}">${m.role === 'queen' ? 'Queen' : 'Operator'}</span>
        <span class="msg-ts">${timeAgo(m.ts)}</span>
        ${(m as QueenChatMessage & { parsed?: boolean }).parsed ? html`<fc-pill color="var(--v-warn)" sm>parsed from intent</fc-pill>` : nothing}
        ${intent === 'ask' ? html`<span class="ask-badge">needs input</span>` : nothing}
        ${m.role === 'queen' ? html`<span class="pin-btn" title="Save as preference" @click=${() => this._saveAsPreference(m.text)}>&#x1F4CC;</span>` : nothing}
      </div>
      <div class="msg-body" style="color:${m.role === 'queen' ? 'var(--v-fg)' : 'rgba(237,237,240,0.8)'};padding-left:${m.role === 'queen' ? 14 : 0}px">${m.text}</div>
    </div>`;
  }

  private _handlePreviewConfirm(e: CustomEvent, idx: number) {
    this._confirmedPreviews = new Set([...this._confirmedPreviews, idx]);
    this.dispatchEvent(new CustomEvent('confirm-preview', {
      detail: e.detail,
      bubbles: true, composed: true,
    }));
  }

  private _handlePreviewCancel(idx: number) {
    this._cancelledPreviews = new Set([...this._cancelledPreviews, idx]);
    this.dispatchEvent(new CustomEvent('cancel-preview', {
      bubbles: true, composed: true,
    }));
  }

  private _handleOpenEditor(e: CustomEvent) {
    this.dispatchEvent(new CustomEvent('open-colony-editor', {
      detail: e.detail,
      bubbles: true, composed: true,
    }));
  }

  private _handleResultNavigate(e: CustomEvent) {
    const d = e.detail as { target: string; colonyId: string; threadId?: string };
    if (d.target === 'colony' || d.target === 'audit') {
      this.dispatchEvent(new CustomEvent('navigate', {
        detail: d.colonyId,
        bubbles: true, composed: true,
      }));
    } else if (d.target === 'timeline' && d.threadId) {
      this.dispatchEvent(new CustomEvent('navigate', {
        detail: d.threadId,
        bubbles: true, composed: true,
      }));
    }
  }

  private switchThread(id: string) {
    // Reset card states when switching threads
    this._confirmedPreviews = new Set();
    this._cancelledPreviews = new Set();
    this.dispatchEvent(new CustomEvent('switch-thread', { detail: id, bubbles: true, composed: true }));
  }

  private newThread() {
    this.dispatchEvent(new CustomEvent('new-thread', { bubbles: true, composed: true }));
  }

  private _saveAsPreference(content: string) {
    this.dispatchEvent(new CustomEvent('save-queen-note', {
      detail: { threadId: this.activeThread?.id, content: content.slice(0, 500) },
      bubbles: true, composed: true,
    }));
  }

  private _onDirectiveSend(e: CustomEvent) {
    const d = e.detail as { colony_id: string; message: string; directive_type: string; directive_priority: string };
    this.dispatchEvent(new CustomEvent('send-colony-message', {
      detail: {
        colonyId: d.colony_id,
        message: d.message,
        directive_type: d.directive_type,
        directive_priority: d.directive_priority,
      },
      bubbles: true, composed: true,
    }));
  }

  private sendMessage() {
    if (!this.input.trim() || !this.activeThread) return;
    this.dispatchEvent(new CustomEvent('send-message', {
      detail: { threadId: this.activeThread.id, content: this.input.trim() },
      bubbles: true, composed: true,
    }));
    this.input = '';
    this._queenPending = true;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-chat': FcQueenChat; }
}
