import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { WorkflowStepItem } from '../types.js';

@customElement('fc-workflow-editor')
export class FcWorkflowEditor extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
    .title {
      font-family: var(--f-display); font-size: 14px; font-weight: 700;
      color: var(--v-fg); letter-spacing: -0.03em;
    }
    .count-badge {
      font-size: 9px; font-family: var(--f-mono); font-weight: 600;
      padding: 1px 6px; border-radius: 6px;
      background: rgba(163,130,250,0.15); color: var(--v-purple);
    }
    .step-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
    .step-row {
      display: flex; align-items: center; gap: 8px; padding: 8px 10px;
      border-radius: 8px; background: var(--v-glass);
      border: 1px solid var(--v-border); font-size: 11px; font-family: var(--f-mono);
    }
    .step-index {
      font-size: 10px; font-weight: 700; color: var(--v-fg-dim);
      min-width: 18px; text-align: center; font-feature-settings: 'tnum';
    }
    .step-desc { flex: 1; color: var(--v-fg-muted); line-height: 1.4; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .step-desc.skipped { text-decoration: line-through; }
    .status-pill {
      font-size: 8px; font-weight: 600; text-transform: uppercase;
      padding: 1px 6px; border-radius: 4px; letter-spacing: 0.06em; white-space: nowrap;
    }
    .status-pending { background: rgba(107,107,118,0.12); color: var(--v-fg-dim); }
    .status-in_progress { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .status-completed { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .status-skipped { background: rgba(240,100,100,0.12); color: var(--v-danger); }
    .step-actions { display: flex; gap: 4px; }
    .icon-btn {
      background: none; border: 1px solid var(--v-border); border-radius: 4px;
      color: var(--v-fg-dim); cursor: pointer; padding: 2px 5px; font-size: 10px;
      font-family: var(--f-mono); transition: color 0.15s, border-color 0.15s;
    }
    .icon-btn:hover { color: var(--v-fg); border-color: var(--v-border-hover); }
    .icon-btn.danger:hover { color: var(--v-danger); border-color: var(--v-danger); }
    .edit-input {
      flex: 1; background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 4px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px; padding: 4px 6px; outline: none;
    }
    .edit-input:focus { border-color: var(--v-accent); }
    .add-row { display: flex; gap: 6px; align-items: center; }
    .add-input {
      flex: 1; background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-body);
      font-size: 11px; padding: 6px 10px; outline: none;
    }
    .add-input:focus { border-color: var(--v-accent); }
    .add-input::placeholder { color: var(--v-fg-dim); }
    .add-btn {
      background: var(--v-accent); color: var(--v-fg-on-accent); border: none;
      border-radius: 6px; padding: 6px 14px; font-size: 10px; font-family: var(--f-mono);
      font-weight: 700; cursor: pointer; text-transform: uppercase; letter-spacing: 0.06em;
    }
    .add-btn:disabled { opacity: 0.4; cursor: default; }
    .loading-msg { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); padding: 12px; }
    .empty-msg { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); padding: 8px 0; }
  `];

  @property() workspaceId = '';
  @property() threadId = '';

  @state() private _steps: WorkflowStepItem[] = [];
  @state() private _loading = false;
  @state() private _newDescription = '';
  @state() private _editingIndex = -1;
  @state() private _editText = '';

  private _fetchedKey = '';

  override connectedCallback() {
    super.connectedCallback();
    void this._fetchSteps();
  }

  override updated(changed: Map<string, unknown>) {
    const key = `${this.workspaceId}::${this.threadId}`;
    if ((changed.has('workspaceId') || changed.has('threadId')) && key !== this._fetchedKey) {
      this._fetchedKey = key;
      void this._fetchSteps();
    }
  }

  private async _fetchSteps() {
    if (!this.workspaceId || !this.threadId) return;
    this._loading = true;
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/threads/${encodeURIComponent(this.threadId)}/steps`,
      );
      if (res.ok) {
        const data = await res.json() as { steps: WorkflowStepItem[] };
        this._steps = data.steps;
      }
    } catch { /* swallow */ }
    this._loading = false;
  }

  private async _addStep() {
    const desc = this._newDescription.trim();
    if (!desc || !this.workspaceId || !this.threadId) return;
    await fetch(
      `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/threads/${encodeURIComponent(this.threadId)}/steps`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ description: desc }) },
    );
    this._newDescription = '';
    void this._fetchSteps();
  }

  private async _updateStep(index: number, payload: Record<string, unknown>) {
    if (!this.workspaceId || !this.threadId) return;
    await fetch(
      `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/threads/${encodeURIComponent(this.threadId)}/steps/${index}`,
      { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    );
    this._editingIndex = -1;
    void this._fetchSteps();
  }

  private async _deleteStep(index: number) {
    if (!this.workspaceId || !this.threadId) return;
    await fetch(
      `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/threads/${encodeURIComponent(this.threadId)}/steps/${index}`,
      { method: 'DELETE' },
    );
    void this._fetchSteps();
  }

  private _startEdit(step: WorkflowStepItem) {
    this._editingIndex = step.step_index;
    this._editText = step.description;
  }

  private _commitEdit(index: number) {
    const desc = this._editText.trim();
    if (desc) void this._updateStep(index, { description: desc });
    else this._editingIndex = -1;
  }

  render() {
    if (this._loading && this._steps.length === 0) return html`<div class="loading-msg">Loading steps...</div>`;

    return html`
      <div class="header">
        <span class="title">Workflow Steps</span>
        ${this._steps.length > 0 ? html`<span class="count-badge">${this._steps.length}</span>` : nothing}
      </div>

      ${this._steps.length === 0 && !this._loading
        ? html`<div class="empty-msg">No steps defined yet.</div>`
        : html`<div class="step-list">${this._steps.map(s => this._renderStep(s))}</div>`}

      <div class="add-row">
        <input
          class="add-input"
          placeholder="Add a step..."
          .value=${this._newDescription}
          @input=${(e: InputEvent) => { this._newDescription = (e.target as HTMLInputElement).value; }}
          @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') void this._addStep(); }}
        />
        <button class="add-btn" ?disabled=${!this._newDescription.trim()} @click=${() => void this._addStep()}>Add</button>
      </div>
    `;
  }

  private _renderStep(step: WorkflowStepItem) {
    const editing = this._editingIndex === step.step_index;
    const statusCls = `status-pill status-${step.status}`;
    const descCls = step.status === 'skipped' ? 'step-desc skipped' : 'step-desc';

    return html`
      <div class="step-row">
        <span class="step-index">${step.step_index}</span>
        ${editing
          ? html`
            <input
              class="edit-input"
              .value=${this._editText}
              @input=${(e: InputEvent) => { this._editText = (e.target as HTMLInputElement).value; }}
              @keydown=${(e: KeyboardEvent) => {
                if (e.key === 'Enter') this._commitEdit(step.step_index);
                if (e.key === 'Escape') { this._editingIndex = -1; }
              }}
            />`
          : html`<span class=${descCls}>${step.description}</span>`}
        <span class=${statusCls}>${step.status.replace('_', ' ')}</span>
        <span class="step-actions">
          <button class="icon-btn" title="Edit" @click=${() => this._startEdit(step)}>&#9998;</button>
          <button class="icon-btn danger" title="Delete" @click=${() => void this._deleteStep(step.step_index)}>&#10005;</button>
        </span>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-workflow-editor': FcWorkflowEditor;
  }
}
