/**
 * Wave 83 Track D: Plan Workbench shell.
 *
 * Composes the Track C editor, Track A validation, comparison sidebar,
 * and save-pattern actions into one coherent operator surface.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type {
  PreviewCardMeta,
  PlanValidationResult,
  SavedPlanPattern,
  PlanningSignals,
} from '../types.js';
import './fc-plan-editor.js';
import './fc-plan-comparison.js';
import './atoms.js';

@customElement('fc-plan-workbench')
export class FcPlanWorkbench extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    .header {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 16px; border-bottom: 1px solid var(--v-border);
      flex-shrink: 0;
    }
    .header h2 {
      font-family: var(--f-display); font-size: 16px; font-weight: 700;
      color: var(--v-fg); margin: 0; flex: 1;
    }
    .body {
      display: flex; flex: 1; min-height: 0; overflow: hidden;
    }
    .editor-col {
      flex: 1; min-width: 0; overflow: auto; padding: 12px 16px;
    }
    .sidebar {
      width: 280px; flex-shrink: 0; overflow: auto;
      padding: 12px; border-left: 1px solid var(--v-border);
    }
    .validation-bar {
      padding: 8px 16px; border-bottom: 1px solid var(--v-border);
      font-size: 10px; font-family: var(--f-mono); flex-shrink: 0;
    }
    .validation-bar.valid { background: rgba(45,212,168,0.04); color: var(--v-success); }
    .validation-bar.invalid { background: rgba(248,113,113,0.04); color: var(--v-danger); }
    .validation-bar.pending { color: var(--v-fg-dim); }
    .error-list, .warning-list {
      margin: 4px 0 0; padding: 0; list-style: none;
    }
    .error-list li { color: var(--v-danger); margin: 2px 0; }
    .warning-list li { color: var(--v-accent); margin: 2px 0; }
    .actions {
      display: flex; gap: 8px; padding: 12px 16px;
      border-top: 1px solid var(--v-border); flex-shrink: 0;
      justify-content: flex-end;
    }
    .signals-section {
      margin-bottom: 12px; padding: 8px 10px; border-radius: 6px;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.03);
    }
    .signal-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 4px;
    }
    .signal-row {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      margin-bottom: 2px;
    }
    .signal-tag {
      font-size: 9px; padding: 1px 5px; border-radius: 3px;
      background: rgba(99,102,241,0.1); color: #8b8cf6;
    }
    .save-name {
      font-size: 11px; font-family: var(--f-mono); padding: 4px 8px;
      border: 1px solid var(--v-border); border-radius: 5px;
      background: transparent; color: var(--v-fg); width: 100%;
      outline: none; margin-bottom: 6px;
    }
    .save-name::placeholder { color: var(--v-fg-dim); }
  `];

  @property({ type: Object }) preview: PreviewCardMeta | null = null;
  @property() workspaceId = '';
  @property() threadId = '';

  @state() private _editorPreview: PreviewCardMeta | null = null;
  @state() private _editedPreview: PreviewCardMeta | null = null;
  @state() private _validation: PlanValidationResult | null = null;
  @state() private _validating = false;
  @state() private _showSave = false;
  @state() private _saveName = '';
  @state() private _saving = false;

  connectedCallback() {
    super.connectedCallback();
    this._resetFromPreview();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('preview')) {
      this._resetFromPreview();
    }
  }

  private _resetFromPreview() {
    const p = this.preview;
    if (!p) return;
    const base = JSON.parse(JSON.stringify(p)) as PreviewCardMeta;
    this._editorPreview = base;
    this._editedPreview = base;
    this._validation = null;
    this._showSave = false;
    void this._validate(base);
  }

  private _buildPreview(): PreviewCardMeta {
    return this._editedPreview ?? this._editorPreview ?? this.preview ?? {} as PreviewCardMeta;
  }

  private _applyPattern(e: CustomEvent) {
    const pattern = e.detail as SavedPlanPattern;
    if (!pattern?.task_previews?.length) return;
    const groups = (pattern.groups ?? []).map(group => {
      if (Array.isArray(group)) {
        return { taskIds: [...group], tasks: [] };
      }
      return {
        taskIds: [...(group.taskIds ?? [])],
        tasks: [...(group.tasks ?? [])],
      };
    });
    const nextPreview: PreviewCardMeta = {
      ...(this.preview ?? {} as PreviewCardMeta),
      taskPreviews: pattern.task_previews.map(t => ({ ...t })),
      groups,
      totalPlannedTasks: pattern.task_previews.length,
    };
    this._editorPreview = nextPreview;
    this._editedPreview = nextPreview;
    void this._validate(nextPreview);
  }

  private async _validate(previewOverride?: PreviewCardMeta | null) {
    this._validating = true;
    const preview = previewOverride ?? this._buildPreview();
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/validate-reviewed-plan`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ preview }),
        },
      ).catch(() => null);
      if (resp?.ok) {
        this._validation = await resp.json() as PlanValidationResult;
      }
    } catch {
      // degrade gracefully
    }
    this._validating = false;
  }

  private _dispatch(previewOverride?: PreviewCardMeta) {
    const preview = previewOverride ?? this._buildPreview();
    this.dispatchEvent(new CustomEvent('workbench-dispatch', {
      detail: { preview, threadId: this.threadId, workspaceId: this.workspaceId },
      bubbles: true, composed: true,
    }));
  }

  private async _savePattern() {
    if (!this._saveName.trim()) return;
    this._saving = true;
    const currentPreview = this._buildPreview();
    try {
      await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/plan-patterns`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: this._saveName.trim(),
            description: currentPreview.task ?? '',
            task_previews: currentPreview.taskPreviews ?? [],
            groups: currentPreview.groups ?? [],
            thread_id: this.threadId,
            planner_model: currentPreview.plannerModel ?? '',
            source_query: currentPreview.task ?? '',
            created_from: 'reviewed_plan',
          }),
        },
      );
      this._showSave = false;
      this._saveName = '';
    } catch {
      // degrade gracefully
    }
    this._saving = false;
  }

  private _close() {
    this.dispatchEvent(new CustomEvent('workbench-close', {
      bubbles: true, composed: true,
    }));
  }

  render() {
    if (!this.preview) {
      return html`<div style="padding:20px;color:var(--v-fg-dim)">No plan to edit.</div>`;
    }

    const signals = this._buildPreview().planningSignals ?? this.preview.planningSignals;

    return html`
      <div class="header">
        <h2>Plan Workbench</h2>
        ${this.preview.plannerModel ? html`
          <span style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">
            Planner: ${this.preview.plannerModel.split('/').pop()}
          </span>
        ` : nothing}
        <fc-btn variant="ghost" sm @click=${this._close}>Close</fc-btn>
      </div>

      ${this._renderValidationBar()}

      <div class="body">
        <div class="editor-col">
          <fc-plan-editor
            .original=${this._editorPreview ?? this.preview}
            .errors=${this._validation?.errors ?? []}
            .warnings=${this._validation?.warnings ?? []}
            @plan-edited=${(e: CustomEvent) => {
              this._editedPreview = e.detail as PreviewCardMeta;
            }}
            @validate-plan=${(e: CustomEvent) => {
              const nextPreview = e.detail as PreviewCardMeta;
              this._editedPreview = nextPreview;
              void this._validate(nextPreview);
            }}
            @plan-confirm=${(e: CustomEvent) => {
              const nextPreview = e.detail as PreviewCardMeta;
              this._editedPreview = nextPreview;
              this._dispatch(nextPreview);
            }}
            @plan-cancel=${() => this._close()}
          ></fc-plan-editor>
        </div>

        <div class="sidebar">
          ${signals ? this._renderSignals(signals) : nothing}

          <fc-plan-comparison
            .workspaceId=${this.workspaceId}
            .currentPlan=${this._buildPreview()}
            @apply-pattern=${this._applyPattern}
          ></fc-plan-comparison>

          ${this._showSave ? html`
            <div style="margin-top:12px">
              <div class="signal-label">Save as Pattern</div>
              <input class="save-name" type="text"
                placeholder="Pattern name..."
                .value=${this._saveName}
                @input=${(e: Event) => { this._saveName = (e.target as HTMLInputElement).value; }}
              />
              <div style="display:flex;gap:6px">
                <fc-btn variant="primary" sm ?disabled=${this._saving || !this._saveName.trim()} @click=${() => void this._savePattern()}>
                  ${this._saving ? 'Saving...' : 'Save'}
                </fc-btn>
                <fc-btn variant="ghost" sm @click=${() => { this._showSave = false; }}>Cancel</fc-btn>
              </div>
            </div>
          ` : nothing}
        </div>
      </div>

      <div class="actions">
        <fc-btn variant="ghost" sm @click=${() => { this._showSave = true; }}>Save Pattern</fc-btn>
        <fc-btn variant="ghost" sm @click=${this._close}>Close</fc-btn>
      </div>
    `;
  }

  private _renderValidationBar() {
    if (this._validating) {
      return html`<div class="validation-bar pending">Validating...</div>`;
    }
    if (!this._validation) {
      return html`<div class="validation-bar pending">Validation pending</div>`;
    }
    const v = this._validation;
    if (v.valid) {
      return html`
        <div class="validation-bar valid">
          Plan valid${v.warnings.length > 0 ? ` (${v.warnings.length} warning${v.warnings.length > 1 ? 's' : ''})` : ''}
          ${v.warnings.length > 0 ? html`
            <ul class="warning-list">${v.warnings.map(w => html`<li>${w}</li>`)}</ul>
          ` : nothing}
        </div>
      `;
    }
    return html`
      <div class="validation-bar invalid">
        ${v.errors.length} error${v.errors.length > 1 ? 's' : ''}
        <ul class="error-list">${v.errors.map(e => html`<li>${e}</li>`)}</ul>
        ${v.warnings.length > 0 ? html`
          <ul class="warning-list">${v.warnings.map(w => html`<li>${w}</li>`)}</ul>
        ` : nothing}
      </div>
    `;
  }

  private _renderSignals(s: PlanningSignals) {
    const hasContent = (s.patterns?.length ?? 0) > 0
      || s.playbook || s.capability
      || (s.previous_plans?.length ?? 0) > 0;
    if (!hasContent) return nothing;

    return html`
      <div class="signals-section">
        <div class="signal-label">Why this plan</div>
        ${s.patterns?.length ? html`
          <div class="signal-row">
            Patterns: ${s.patterns.map(p => html`
              <span class="signal-tag">${p.title} (q=${p.quality})</span>
            `)}
          </div>
        ` : nothing}
        ${s.playbook ? html`
          <div class="signal-row">Playbook: ${s.playbook.hint}</div>
        ` : nothing}
        ${s.capability ? html`
          <div class="signal-row">Worker: ${s.capability.summary ?? s.capability.short_name}</div>
        ` : nothing}
        ${(s.previous_plans?.length ?? 0) > 0 ? html`
          <div class="signal-row">Prior plans: ${s.previous_plans!.length} similar</div>
        ` : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-plan-workbench': FcPlanWorkbench; }
}
