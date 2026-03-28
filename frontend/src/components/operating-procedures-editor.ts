/**
 * Wave 71.5 Track 3B: Operating procedures editor.
 * Fetches from GET and saves via PUT to
 * /api/v1/workspaces/{id}/operating-procedures.
 *
 * Standing-policy surface for autonomy — the operator writes rules here
 * that the Queen reads every response.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import './atoms.js';

const EMPTY_TEMPLATE = `## Standing Procedures

### Autonomy
- Maintenance colonies may run automatically for low-risk knowledge health tasks.
- Any cost above $0.50 requires my approval.

### Style
- Keep commit messages concise.
- Prefer small, focused colonies over large multi-step ones.

### Priorities
- (Add your current priorities here)
`;

@customElement('fc-operating-procedures-editor')
export class FcOperatingProceduresEditor extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .editor-area {
      width: 100%; min-height: 180px; max-height: 400px;
      resize: vertical;
      font-family: var(--f-mono); font-size: 11px; line-height: 1.6;
      color: var(--v-fg); background: var(--v-recessed);
      border: 1px solid var(--v-border); border-radius: 6px;
      padding: 10px 12px;
      box-sizing: border-box;
      transition: border-color 0.15s;
    }
    .editor-area:focus {
      outline: none;
      border-color: var(--v-accent);
    }

    .controls {
      display: flex; align-items: center; gap: 8px; margin-top: 8px;
    }
    .btn-save {
      font-family: var(--f-mono); font-size: 10px; font-weight: 600;
      color: var(--v-fg-on-accent); background: var(--v-accent);
      border: none; border-radius: 5px;
      padding: 5px 14px; cursor: pointer;
      transition: background 0.15s;
    }
    .btn-save:hover { background: var(--v-accent-bright); }
    .btn-save:disabled {
      opacity: 0.4; cursor: default;
      background: var(--v-accent);
    }

    .btn-reset {
      font-family: var(--f-mono); font-size: 9px; font-weight: 600;
      color: var(--v-fg-dim); background: rgba(255,255,255,0.03);
      border: 1px solid var(--v-border); border-radius: 5px;
      padding: 4px 10px; cursor: pointer;
      transition: border-color 0.15s, color 0.15s;
    }
    .btn-reset:hover {
      border-color: var(--v-border-hover); color: var(--v-fg-muted);
    }

    .status-text {
      font-family: var(--f-mono); font-size: 9px;
      margin-left: auto;
    }
    .status-saved { color: var(--v-success); }
    .status-error { color: var(--v-danger); }
    .status-dirty { color: var(--v-warn); }

    .empty-state {
      font-family: var(--f-mono); font-size: 10.5px; color: var(--v-fg-dim);
      padding: 16px 0; text-align: center; line-height: 1.7;
    }
    .empty-hint {
      font-size: 9.5px; color: var(--v-fg-dim); opacity: 0.7;
    }

    .error-text {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-danger);
    }

    .use-template {
      font-family: var(--f-mono); font-size: 9px;
      color: var(--v-accent); background: none; border: none;
      cursor: pointer; text-decoration: underline;
      padding: 0; margin-top: 6px;
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: String }) workspaceId = '';
  @state() private _content = '';
  @state() private _savedContent = '';
  @state() private _loaded = false;
  @state() private _error = '';
  @state() private _saveStatus: 'idle' | 'saving' | 'saved' | 'error' = 'idle';

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/operating-procedures`,
      );
      if (!resp.ok) {
        this._error = `HTTP ${resp.status}`;
        return;
      }
      const data = await resp.json() as { exists: boolean; content: string };
      this._content = data.content ?? '';
      this._savedContent = this._content;
      this._loaded = true;
      this._error = '';
      this._saveStatus = 'idle';
    } catch {
      this._error = 'Failed to fetch procedures';
    }
  }

  private async _save() {
    if (!this.workspaceId) return;
    this._saveStatus = 'saving';
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/operating-procedures`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: this._content }),
        },
      );
      if (!resp.ok) {
        this._saveStatus = 'error';
        return;
      }
      this._savedContent = this._content;
      this._saveStatus = 'saved';
      // Clear "saved" indicator after a moment
      setTimeout(() => {
        if (this._saveStatus === 'saved') this._saveStatus = 'idle';
      }, 2000);
    } catch {
      this._saveStatus = 'error';
    }
  }

  private _onInput(e: InputEvent) {
    const target = e.target as HTMLTextAreaElement;
    this._content = target.value;
    if (this._saveStatus === 'saved' || this._saveStatus === 'error') {
      this._saveStatus = 'idle';
    }
  }

  private _useTemplate() {
    this._content = EMPTY_TEMPLATE;
  }

  private get _isDirty(): boolean {
    return this._content !== this._savedContent;
  }

  render() {
    if (this._error) {
      return html`<div class="error-text">${this._error}</div>`;
    }
    if (!this._loaded) {
      return html`<div class="empty-state">Loading procedures\u2026</div>`;
    }

    // Empty state — no procedures exist yet
    if (!this._content && !this._isDirty) {
      return html`
        <div class="empty-state">
          No operating procedures defined yet.<br>
          <span class="empty-hint">
            Procedures tell the Queen what rules to follow when acting
            autonomously. Write them in plain text or markdown.
          </span>
          <br>
          <button class="use-template" @click=${this._useTemplate}>
            Start from a template
          </button>
        </div>
      `;
    }

    return html`
      <textarea
        class="editor-area"
        .value=${this._content}
        @input=${this._onInput}
        spellcheck="false"
      ></textarea>
      <div class="controls">
        <button
          class="btn-save"
          ?disabled=${!this._isDirty || this._saveStatus === 'saving'}
          @click=${() => void this._save()}
        >
          ${this._saveStatus === 'saving' ? 'Saving\u2026' : 'Save'}
        </button>
        ${this._isDirty ? html`
          <button class="btn-reset" @click=${() => { this._content = this._savedContent; }}>
            Discard
          </button>
        ` : nothing}
        ${this._saveStatus === 'saved' ? html`
          <span class="status-text status-saved">Saved</span>
        ` : nothing}
        ${this._saveStatus === 'error' ? html`
          <span class="status-text status-error">Save failed</span>
        ` : nothing}
        ${this._isDirty && this._saveStatus === 'idle' ? html`
          <span class="status-text status-dirty">Unsaved changes</span>
        ` : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-operating-procedures-editor': FcOperatingProceduresEditor;
  }
}
