/**
 * Wave 82 Track D: Parallel plan preview with why-this-plan signals
 * and minimal operator correction before dispatch.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type {
  PreviewCardMeta,
  DelegationTaskPreview,
  PlanningSignals,
} from '../types.js';
import './fc-plan-editor.js';

@customElement('fc-parallel-preview')
export class FcParallelPreview extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .preview {
      padding: 12px 14px; border-radius: 10px;
      background: var(--v-glass); border: 1px solid var(--v-border);
      backdrop-filter: blur(14px);
    }
    .header {
      font-family: var(--f-display); font-size: 14px; font-weight: 700;
      color: var(--v-fg); margin-bottom: 8px;
    }
    .meta-row {
      display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .meta-item strong { color: var(--v-fg); }
    .group-section { margin-bottom: 10px; }
    .group-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.5px; margin-bottom: 4px;
    }
    .task-row {
      display: flex; align-items: flex-start; gap: 8px; padding: 6px 10px;
      border-radius: 6px; margin-bottom: 3px;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04);
    }
    .task-caste {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px;
      border-radius: 3px; background: rgba(232,88,26,0.1);
      color: var(--v-accent); flex-shrink: 0;
    }
    .task-text {
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      flex: 1; min-width: 0;
    }
    .task-text textarea {
      width: 100%; border: none; background: transparent; color: var(--v-fg);
      font-family: var(--f-mono); font-size: 11px; resize: none;
      outline: none; padding: 0; min-height: 18px;
    }
    .task-files {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px;
    }
    .task-file {
      padding: 1px 5px; border-radius: 3px;
      background: rgba(255,255,255,0.04); cursor: default;
    }
    .signals-section {
      margin-top: 10px; padding: 8px 10px; border-radius: 6px;
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
    .actions {
      display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end;
    }
    .btn {
      font-size: 10px; font-family: var(--f-mono); padding: 5px 14px;
      border-radius: 5px; border: 1px solid var(--v-border); cursor: pointer;
    }
    .btn-confirm {
      background: var(--v-accent); color: #fff; border-color: var(--v-accent);
      font-weight: 600;
    }
    .btn-confirm:hover { opacity: 0.85; }
    .btn-cancel {
      background: transparent; color: var(--v-fg-dim);
    }
    .btn-cancel:hover { color: var(--v-fg); }
  `];

  @property({ type: Object }) preview: PreviewCardMeta | null = null;

  // Editable task texts for minimal correction
  @state() private _editedTasks = new Map<string, string>();
  @state() private _editorOpen = false;

  render() {
    const p = this.preview;
    if (!p || !p.groups?.length) return nothing;

    if (this._editorOpen) {
      return html`
        <fc-plan-editor
          .original=${p}
          @plan-confirm=${(e: CustomEvent) => {
            this._editorOpen = false;
            this.dispatchEvent(new CustomEvent('plan-confirm', {
              detail: e.detail, bubbles: true, composed: true,
            }));
          }}
          @plan-cancel=${() => { this._editorOpen = false; }}
        ></fc-plan-editor>
      `;
    }

    const tasks = p.taskPreviews ?? [];
    const taskMap = new Map(tasks.map(t => [t.task_id, t]));
    const signals = p.planningSignals;

    return html`
      <div class="preview">
        <div class="header">Parallel Plan Preview</div>
        <div class="meta-row">
          <span>Strategy: <strong>${p.strategy}</strong></span>
          <span>Tasks: <strong>${p.totalPlannedTasks ?? tasks.length}</strong></span>
          <span>Groups: <strong>${p.groups.length}</strong></span>
          ${p.estimatedCost ? html`
            <span>Est: <strong>$${p.estimatedCost.toFixed(2)}</strong></span>
          ` : nothing}
          ${p.plannerModel ? html`
            <span>Planner: <strong>${p.plannerModel.split('/').pop()}</strong></span>
          ` : nothing}
        </div>

        ${p.groups.map((g, gi) => html`
          <div class="group-section">
            <div class="group-label">
              Group ${gi + 1}${gi > 0 ? ' (after group ' + gi + ')' : ' (first)'}
            </div>
            ${g.taskIds.map(tid => {
              const task = taskMap.get(tid);
              const taskText = this._editedTasks.get(tid) ?? task?.task ?? g.tasks?.[g.taskIds.indexOf(tid)] ?? tid;
              return html`
                <div class="task-row">
                  <span class="task-caste">${task?.caste ?? 'coder'}</span>
                  <div class="task-text">
                    <textarea rows="1"
                      .value=${taskText}
                      @input=${(e: Event) => {
                        this._editedTasks.set(tid, (e.target as HTMLTextAreaElement).value);
                        this._editedTasks = new Map(this._editedTasks);
                      }}
                    ></textarea>
                    ${task?.target_files?.length ? html`
                      <div class="task-files">
                        ${task.target_files.map(f => html`
                          <span class="task-file" title=${f}>${f.split('/').pop()}</span>
                        `)}
                      </div>
                    ` : nothing}
                    ${task?.expected_outputs?.length ? html`
                      <div class="task-files">
                        ${task.expected_outputs.map(o => html`
                          <span class="task-file" style="color:var(--v-success)">${o}</span>
                        `)}
                      </div>
                    ` : nothing}
                  </div>
                </div>
              `;
            })}
          </div>
        `)}

        ${signals ? this._renderSignals(signals) : nothing}

        <div class="actions">
          <button class="btn btn-cancel" @click=${this._cancel}>Reject</button>
          <button class="btn btn-cancel" @click=${this._openWorkbench}>Open Workbench</button>
          <button class="btn btn-confirm" @click=${this._confirm}>Dispatch Plan</button>
        </div>
      </div>
    `;
  }

  private _renderSignals(s: PlanningSignals) {
    const hasContent = (s.patterns?.length ?? 0) > 0
      || s.playbook || s.capability || s.coupling
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
          <div class="signal-row">
            Worker: ${s.capability.summary ?? s.capability.short_name}
          </div>
        ` : nothing}
        ${(s.previous_plans?.length ?? 0) > 0 ? html`
          <div class="signal-row">
            Prior plans: ${s.previous_plans!.length} similar
            ${s.previous_plans!.slice(0, 2).map(pp => html`
              <span class="signal-tag">${(pp as Record<string, string>).evidence ?? ''}</span>
            `)}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _confirm() {
    const p = this.preview;
    if (!p) return;

    // Apply edits to tasks
    const editedPreview = { ...p };
    if (editedPreview.taskPreviews) {
      editedPreview.taskPreviews = editedPreview.taskPreviews.map(t => {
        const edited = this._editedTasks.get(t.task_id);
        return edited ? { ...t, task: edited } : t;
      });
    }

    this.dispatchEvent(new CustomEvent('plan-confirm', {
      detail: editedPreview,
      bubbles: true, composed: true,
    }));
  }

  private _cancel() {
    this.dispatchEvent(new CustomEvent('plan-cancel', {
      detail: this.preview,
      bubbles: true, composed: true,
    }));
  }

  /** Wave 83 Track D: open the full workbench for deeper editing. */
  private _openWorkbench() {
    this.dispatchEvent(new CustomEvent('plan-open-workbench', {
      detail: this.preview,
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-parallel-preview': FcParallelPreview;
  }
}
