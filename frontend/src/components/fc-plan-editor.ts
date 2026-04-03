/**
 * Wave 83 Track C: DAG plan editor.
 *
 * Edits the same preview/plan contract that spawn_parallel consumes.
 * No shadow plan format — mutations operate on taskPreviews + groups.
 *
 * Emits:
 *   plan-edited   — detail: edited PreviewCardMeta (after each mutation)
 *   plan-confirm  — detail: final edited PreviewCardMeta (dispatch)
 *   plan-cancel   — detail: original preview
 *   validate-plan — detail: current edited state (debounced, for backend validation)
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { PreviewCardMeta, DelegationTaskPreview } from '../types.js';

interface GroupState {
  taskIds: string[];
  tasks: string[];
}

@customElement('fc-plan-editor')
export class FcPlanEditor extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .editor {
      padding: 12px 14px; border-radius: 10px;
      background: var(--v-glass); border: 1px solid var(--v-border);
      backdrop-filter: blur(14px);
    }
    .header {
      font-family: var(--f-display); font-size: 14px; font-weight: 700;
      color: var(--v-fg); margin-bottom: 4px;
    }
    .subtitle {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 10px;
    }
    .group-section {
      margin-bottom: 10px; padding: 8px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.06);
      background: rgba(255,255,255,0.01);
    }
    .group-header {
      display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    }
    .group-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.5px; flex: 1;
    }
    .group-actions { display: flex; gap: 4px; }
    .task-card {
      padding: 8px 10px; border-radius: 6px; margin-bottom: 4px;
      background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04);
    }
    .task-card.edited { border-color: var(--v-accent); }
    .task-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .task-caste {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px;
      border-radius: 3px; background: rgba(232,88,26,0.1);
      color: var(--v-accent); flex-shrink: 0;
    }
    .task-id {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); flex-shrink: 0;
    }
    .task-actions { display: flex; gap: 3px; margin-left: auto; }
    textarea {
      width: 100%; border: 1px solid rgba(255,255,255,0.06); background: rgba(0,0,0,0.2);
      color: var(--v-fg); font-family: var(--f-mono); font-size: 11px; resize: vertical;
      outline: none; padding: 4px 6px; border-radius: 4px; min-height: 28px;
    }
    textarea:focus { border-color: var(--v-accent); }
    .file-section { margin-top: 4px; }
    .file-label {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;
    }
    .file-pills { display: flex; gap: 3px; flex-wrap: wrap; }
    .file-pill {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px;
      border-radius: 3px; background: rgba(255,255,255,0.04);
      color: var(--v-fg-muted); cursor: grab; display: flex; align-items: center; gap: 3px;
    }
    .file-pill.output { color: var(--v-success); }
    .file-remove {
      cursor: pointer; opacity: 0.5; font-size: 10px;
    }
    .file-remove:hover { opacity: 1; color: var(--v-error); }
    .deps-section { margin-top: 4px; }
    .dep-pill {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px;
      border-radius: 3px; background: rgba(99,102,241,0.1);
      color: #8b8cf6; display: inline-flex; align-items: center; gap: 3px;
      margin-right: 3px;
    }
    .mini-btn {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px;
      border-radius: 3px; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); cursor: pointer;
    }
    .mini-btn:hover { background: var(--v-accent); color: #fff; border-color: var(--v-accent); }
    .mini-btn.danger:hover { background: #ef4444; border-color: #ef4444; }
    .validation { margin-top: 8px; }
    .val-error {
      font-size: 10px; font-family: var(--f-mono); color: #ef4444;
      padding: 3px 8px; margin-bottom: 2px;
    }
    .val-warning {
      font-size: 10px; font-family: var(--f-mono); color: #f59e0b;
      padding: 3px 8px; margin-bottom: 2px;
    }
    .bar {
      display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end;
      align-items: center;
    }
    .change-count {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
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
    .btn-cancel { background: transparent; color: var(--v-fg-dim); }
    .btn-cancel:hover { color: var(--v-fg); }
    .btn-confirm:disabled { opacity: 0.4; cursor: not-allowed; }
    select {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 4px;
      border-radius: 3px; border: 1px solid var(--v-border);
      background: rgba(0,0,0,0.2); color: var(--v-fg-muted);
    }
  `];

  /** The original Queen-proposed preview (immutable reference). */
  @property({ type: Object }) original: PreviewCardMeta | null = null;

  /** Backend validation errors. */
  @property({ type: Array }) errors: string[] = [];

  /** Backend validation warnings. */
  @property({ type: Array }) warnings: string[] = [];

  // Editable state — deep-cloned from original on first load.
  @state() private _tasks: DelegationTaskPreview[] = [];
  @state() private _groups: GroupState[] = [];
  @state() private _reasoning = '';
  @state() private _nextTaskNum = 1;

  override updated(changed: Map<string, unknown>) {
    if (changed.has('original') && this.original) {
      this._initFromPreview(this.original);
    }
  }

  private _initFromPreview(p: PreviewCardMeta) {
    this._tasks = (p.taskPreviews ?? []).map(t => ({ ...t }));
    this._groups = (p.groups ?? []).map(g => ({ taskIds: [...g.taskIds], tasks: [...(g.tasks ?? [])] }));
    this._reasoning = (p as Record<string, unknown>).reasoning as string ?? '';
    this._nextTaskNum = this._tasks.length + 1;
  }

  /** Reset editor to original Queen proposal. */
  reset() {
    if (this.original) {
      this._initFromPreview(this.original);
      this._emitEdited();
    }
  }

  /** Get the current edited state as a PreviewCardMeta. */
  get editedPreview(): PreviewCardMeta {
    const p = this.original ?? {} as PreviewCardMeta;
    return {
      ...p,
      taskPreviews: this._tasks.map(t => ({ ...t })),
      groups: this._groups.map(g => ({ taskIds: [...g.taskIds], tasks: [...g.tasks] })),
      totalPlannedTasks: this._tasks.length,
    };
  }

  private _countChanges(): number {
    if (!this.original?.taskPreviews) return 0;
    const orig = new Map(this.original.taskPreviews.map(t => [t.task_id, t]));
    let n = 0;
    for (const t of this._tasks) {
      const o = orig.get(t.task_id);
      if (!o) { n++; continue; }
      if (t.task !== o.task) n++;
      if (JSON.stringify(t.target_files) !== JSON.stringify(o.target_files)) n++;
      if (JSON.stringify(t.expected_outputs) !== JSON.stringify(o.expected_outputs)) n++;
      if (JSON.stringify(t.depends_on) !== JSON.stringify(o.depends_on)) n++;
    }
    const origGroups = this.original.groups ?? [];
    if (JSON.stringify(this._groups.map(g => g.taskIds)) !== JSON.stringify(origGroups.map(g => g.taskIds))) n++;
    return n;
  }

  private _taskMap(): Map<string, DelegationTaskPreview> {
    return new Map(this._tasks.map(t => [t.task_id, t]));
  }

  // ── Mutations ──

  private _editTaskText(tid: string, text: string) {
    this._tasks = this._tasks.map(t => t.task_id === tid ? { ...t, task: text } : t);
    this._emitEdited();
  }

  private _editTaskCaste(tid: string, caste: string) {
    this._tasks = this._tasks.map(t => t.task_id === tid ? { ...t, caste } : t);
    this._emitEdited();
  }

  private _removeFile(tid: string, file: string, field: 'target_files' | 'expected_outputs') {
    this._tasks = this._tasks.map(t => {
      if (t.task_id !== tid) return t;
      return { ...t, [field]: (t[field] ?? []).filter(f => f !== file) };
    });
    this._emitEdited();
  }

  private _moveFile(fromTid: string, toTid: string, file: string, field: 'target_files' | 'expected_outputs') {
    this._tasks = this._tasks.map(t => {
      if (t.task_id === fromTid) return { ...t, [field]: (t[field] ?? []).filter(f => f !== file) };
      if (t.task_id === toTid) return { ...t, [field]: [...(t[field] ?? []), file] };
      return t;
    });
    this._emitEdited();
  }

  private _removeDep(tid: string, depId: string) {
    this._tasks = this._tasks.map(t =>
      t.task_id === tid ? { ...t, depends_on: (t.depends_on ?? []).filter(d => d !== depId) } : t,
    );
    this._emitEdited();
  }

  private _addDep(tid: string, depId: string) {
    if (tid === depId) return;
    this._tasks = this._tasks.map(t =>
      t.task_id === tid ? { ...t, depends_on: [...new Set([...(t.depends_on ?? []), depId])] } : t,
    );
    this._emitEdited();
  }

  private _splitTask(tid: string, groupIdx: number) {
    const task = this._tasks.find(t => t.task_id === tid);
    if (!task) return;
    const newId = `split-${this._nextTaskNum++}`;
    const newTask: DelegationTaskPreview = {
      task_id: newId,
      task: '(split from ' + tid + ')',
      caste: task.caste,
      depends_on: [...(task.depends_on ?? [])],
      target_files: [],
      expected_outputs: [],
    };
    this._tasks = [...this._tasks, newTask];
    this._groups = this._groups.map((g, gi) =>
      gi === groupIdx ? { ...g, taskIds: [...g.taskIds, newId], tasks: [...g.tasks, newTask.task] } : g,
    );
    this._emitEdited();
  }

  private _mergeTask(fromTid: string, intoTid: string) {
    const from = this._tasks.find(t => t.task_id === fromTid);
    const into = this._tasks.find(t => t.task_id === intoTid);
    if (!from || !into) return;
    // Merge text, files, deps
    const merged: DelegationTaskPreview = {
      ...into,
      task: into.task + '\n' + from.task,
      target_files: [...new Set([...(into.target_files ?? []), ...(from.target_files ?? [])])],
      expected_outputs: [...new Set([...(into.expected_outputs ?? []), ...(from.expected_outputs ?? [])])],
      depends_on: [...new Set([...(into.depends_on ?? []), ...(from.depends_on ?? [])].filter(d => d !== into.task_id && d !== fromTid))],
    };
    this._tasks = this._tasks.filter(t => t.task_id !== fromTid).map(t => t.task_id === intoTid ? merged : t);
    // Remove from groups
    this._groups = this._groups.map(g => ({
      ...g,
      taskIds: g.taskIds.filter(id => id !== fromTid),
      tasks: g.tasks.filter((_, i) => g.taskIds[i] !== fromTid),
    }));
    // Update deps that referenced the removed task
    this._tasks = this._tasks.map(t => ({
      ...t,
      depends_on: (t.depends_on ?? []).map(d => d === fromTid ? intoTid : d),
    }));
    this._emitEdited();
  }

  private _moveTaskToGroup(tid: string, fromGroup: number, toGroup: number) {
    if (fromGroup === toGroup) return;
    this._groups = this._groups.map((g, gi) => {
      if (gi === fromGroup) return { ...g, taskIds: g.taskIds.filter(id => id !== tid) };
      if (gi === toGroup) return { ...g, taskIds: [...g.taskIds, tid] };
      return g;
    });
    this._emitEdited();
  }

  private _moveGroupUp(idx: number) {
    if (idx <= 0) return;
    const gs = [...this._groups];
    [gs[idx - 1], gs[idx]] = [gs[idx], gs[idx - 1]];
    this._groups = gs;
    this._emitEdited();
  }

  private _moveGroupDown(idx: number) {
    if (idx >= this._groups.length - 1) return;
    const gs = [...this._groups];
    [gs[idx], gs[idx + 1]] = [gs[idx + 1], gs[idx]];
    this._groups = gs;
    this._emitEdited();
  }

  private _deleteTask(tid: string) {
    this._tasks = this._tasks.filter(t => t.task_id !== tid);
    this._groups = this._groups.map(g => ({
      ...g, taskIds: g.taskIds.filter(id => id !== tid),
    })).filter(g => g.taskIds.length > 0);
    // Clean deps
    this._tasks = this._tasks.map(t => ({
      ...t,
      depends_on: (t.depends_on ?? []).filter(d => d !== tid),
    }));
    this._emitEdited();
  }

  private _emitEdited() {
    this.requestUpdate();
    this.dispatchEvent(new CustomEvent('plan-edited', {
      detail: this.editedPreview, bubbles: true, composed: true,
    }));
    // Debounced validation request
    clearTimeout(this._valTimer);
    this._valTimer = window.setTimeout(() => {
      this.dispatchEvent(new CustomEvent('validate-plan', {
        detail: this.editedPreview, bubbles: true, composed: true,
      }));
    }, 500);
  }

  private _valTimer = 0;

  // ── Render ──

  render() {
    if (!this._tasks.length && !this._groups.length) return nothing;
    const tm = this._taskMap();
    const changes = this._countChanges();
    const hasErrors = this.errors.length > 0;

    return html`
      <div class="editor">
        <div class="header">Plan Editor</div>
        <div class="subtitle">
          ${this._tasks.length} tasks in ${this._groups.length} groups
          ${changes > 0 ? html` \u2014 <strong>${changes} edit${changes > 1 ? 's' : ''}</strong>` : nothing}
        </div>

        ${this._groups.map((g, gi) => this._renderGroup(g, gi, tm))}

        ${this.errors.length || this.warnings.length ? html`
          <div class="validation">
            ${this.errors.map(e => html`<div class="val-error">\u2717 ${e}</div>`)}
            ${this.warnings.map(w => html`<div class="val-warning">\u26A0 ${w}</div>`)}
          </div>
        ` : nothing}

        <div class="bar">
          ${changes > 0 ? html`
            <button class="mini-btn" @click=${() => this.reset()}>Reset</button>
            <span class="change-count">${changes} change${changes > 1 ? 's' : ''}</span>
          ` : nothing}
          <button class="btn btn-cancel" @click=${this._cancel}>Cancel</button>
          <button class="btn btn-confirm" ?disabled=${hasErrors} @click=${this._confirm}>
            ${hasErrors ? 'Fix Errors' : 'Dispatch Plan'}
          </button>
        </div>
      </div>
    `;
  }

  private _renderGroup(g: GroupState, gi: number, tm: Map<string, DelegationTaskPreview>) {
    return html`
      <div class="group-section">
        <div class="group-header">
          <div class="group-label">
            Group ${gi + 1}${gi === 0 ? ' (first)' : ` (after group ${gi})`}
          </div>
          <div class="group-actions">
            ${gi > 0 ? html`<button class="mini-btn" title="Move group up" @click=${() => this._moveGroupUp(gi)}>\u2191</button>` : nothing}
            ${gi < this._groups.length - 1 ? html`<button class="mini-btn" title="Move group down" @click=${() => this._moveGroupDown(gi)}>\u2193</button>` : nothing}
          </div>
        </div>
        ${g.taskIds.map(tid => this._renderTask(tid, gi, tm))}
      </div>
    `;
  }

  private _renderTask(tid: string, gi: number, tm: Map<string, DelegationTaskPreview>) {
    const task = tm.get(tid);
    if (!task) return nothing;

    const origTask = this.original?.taskPreviews?.find(t => t.task_id === tid);
    const isEdited = origTask && task.task !== origTask.task;
    const otherTids = this._tasks.filter(t => t.task_id !== tid).map(t => t.task_id);
    const sameGroupTids = this._groups[gi]?.taskIds.filter(id => id !== tid) ?? [];

    return html`
      <div class="task-card ${isEdited ? 'edited' : ''}">
        <div class="task-top">
          <span class="task-id">${tid}</span>
          <select .value=${task.caste} @change=${(e: Event) => this._editTaskCaste(tid, (e.target as HTMLSelectElement).value)}>
            <option value="coder">coder</option>
            <option value="reviewer">reviewer</option>
            <option value="researcher">researcher</option>
            <option value="archivist">archivist</option>
          </select>
          <div class="task-actions">
            <button class="mini-btn" title="Split task" @click=${() => this._splitTask(tid, gi)}>Split</button>
            ${sameGroupTids.length > 0 ? html`
              <select title="Merge into..." @change=${(e: Event) => {
                const target = (e.target as HTMLSelectElement).value;
                if (target) { this._mergeTask(tid, target); (e.target as HTMLSelectElement).value = ''; }
              }}>
                <option value="">Merge\u2026</option>
                ${sameGroupTids.map(id => html`<option value=${id}>${id}</option>`)}
              </select>
            ` : nothing}
            ${this._groups.length > 1 ? html`
              <select title="Move to group..." @change=${(e: Event) => {
                const target = parseInt((e.target as HTMLSelectElement).value, 10);
                if (!isNaN(target)) { this._moveTaskToGroup(tid, gi, target); (e.target as HTMLSelectElement).value = ''; }
              }}>
                <option value="">Move\u2026</option>
                ${this._groups.map((_g, i) => i !== gi ? html`<option value=${String(i)}>Group ${i + 1}</option>` : nothing)}
              </select>
            ` : nothing}
            <button class="mini-btn danger" title="Delete task" @click=${() => this._deleteTask(tid)}>\u00D7</button>
          </div>
        </div>

        <textarea rows="2"
          .value=${task.task}
          @input=${(e: Event) => this._editTaskText(tid, (e.target as HTMLTextAreaElement).value)}
        ></textarea>

        ${(task.target_files?.length ?? 0) > 0 ? html`
          <div class="file-section">
            <div class="file-label">Target files</div>
            <div class="file-pills">
              ${task.target_files!.map(f => html`
                <span class="file-pill">
                  ${f.split('/').pop()}
                  <span class="file-remove" @click=${() => this._removeFile(tid, f, 'target_files')}>\u00D7</span>
                </span>
              `)}
            </div>
          </div>
        ` : nothing}

        ${(task.expected_outputs?.length ?? 0) > 0 ? html`
          <div class="file-section">
            <div class="file-label">Expected outputs</div>
            <div class="file-pills">
              ${task.expected_outputs!.map(f => html`
                <span class="file-pill output">
                  ${f}
                  <span class="file-remove" @click=${() => this._removeFile(tid, f, 'expected_outputs')}>\u00D7</span>
                </span>
              `)}
            </div>
          </div>
        ` : nothing}

        ${(task.depends_on?.length ?? 0) > 0 ? html`
          <div class="deps-section">
            ${task.depends_on!.map(d => html`
              <span class="dep-pill">
                \u2190 ${d}
                <span class="file-remove" @click=${() => this._removeDep(tid, d)}>\u00D7</span>
              </span>
            `)}
          </div>
        ` : nothing}

        ${otherTids.length > 0 ? html`
          <select style="margin-top:4px" @change=${(e: Event) => {
            const dep = (e.target as HTMLSelectElement).value;
            if (dep) { this._addDep(tid, dep); (e.target as HTMLSelectElement).value = ''; }
          }}>
            <option value="">Add dependency\u2026</option>
            ${otherTids.filter(id => !(task.depends_on ?? []).includes(id)).map(id => html`
              <option value=${id}>${id}</option>
            `)}
          </select>
        ` : nothing}
      </div>
    `;
  }

  private _confirm() {
    this.dispatchEvent(new CustomEvent('plan-confirm', {
      detail: this.editedPreview, bubbles: true, composed: true,
    }));
  }

  private _cancel() {
    this.dispatchEvent(new CustomEvent('plan-cancel', {
      detail: this.original, bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-plan-editor': FcPlanEditor;
  }
}
