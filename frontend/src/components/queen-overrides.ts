/**
 * Wave 74 Team C: Queen behavioral override forms.
 * Workspace-scoped overrides injected into Queen context via WorkspaceConfigChanged.
 * Mount contract: see Track 1e in wave_74/team_c_prompt.md.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

/** Known Queen tool names — derived from queen_tools.py tool_specs(). */
const QUEEN_TOOLS = [
  'spawn_colony', 'spawn_parallel', 'approve_config_change', 'get_status',
  'kill_colony', 'list_templates', 'inspect_template', 'inspect_colony',
  'read_workspace_files', 'suggest_config_change', 'redirect_colony',
  'escalate_colony', 'read_colony_output', 'memory_search',
  'write_workspace_file', 'queen_note', 'set_thread_goal', 'complete_thread',
  'archive_thread', 'query_service', 'define_workflow_steps', 'propose_plan',
  'mark_plan_step', 'query_outcomes', 'analyze_colony', 'query_briefing',
  'search_codebase', 'run_command', 'edit_file', 'run_tests', 'delete_file',
  'retry_colony', 'batch_command', 'summarize_thread', 'draft_document',
  'list_addons', 'trigger_addon', 'set_workspace_tags',
  'propose_project_milestone', 'complete_project_milestone',
  'check_autonomy_budget',
] as const;

@customElement('fc-queen-overrides')
export class FcQueenOverrides extends LitElement {

  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .section {
      margin-bottom: 16px; padding: 12px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 8px;
    }
    .section-title {
      font-size: 10px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.08em; text-transform: uppercase;
      margin: 0 0 8px;
    }
    .section-desc {
      font-size: 10px; color: var(--v-fg-muted); margin: 0 0 8px; line-height: 1.4;
    }
    .tool-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 4px 8px;
    }
    .tool-check {
      display: flex; align-items: center; gap: 4px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      cursor: pointer;
    }
    .tool-check input { accent-color: var(--v-accent, #e8581a); cursor: pointer; }
    .tool-check.disabled-tool { color: var(--v-fg-muted); text-decoration: line-through; }
    textarea, .json-editor {
      width: 100%; box-sizing: border-box; padding: 8px 10px;
      background: var(--v-bg); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px; outline: none; resize: vertical; min-height: 60px;
    }
    textarea:focus, .json-editor:focus { border-color: rgba(232,88,26,0.3); }
    .json-error {
      font-size: 9px; color: var(--v-danger, #ef4444); margin-top: 4px;
      font-family: var(--f-mono);
    }
    .save-row {
      display: flex; justify-content: flex-end; margin-top: 8px; gap: 6px;
    }
    .save-btn {
      font-size: 10px; font-family: var(--f-mono); padding: 4px 12px;
      border-radius: 4px; border: 1px solid var(--v-border); cursor: pointer;
      background: var(--v-accent, #e8581a); color: #fff; font-weight: 600;
    }
    .save-btn:hover { opacity: 0.85; }
    .save-btn[disabled] { opacity: 0.4; cursor: not-allowed; }
    .disabled-count {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-muted);
      margin-bottom: 6px;
    }
  `];

  @property() workspaceId = '';
  @property({ type: Object }) workspace: any = null;  // eslint-disable-line @typescript-eslint/no-explicit-any

  @state() private _disabledTools: string[] = [];
  @state() private _customRules = '';
  @state() private _teamCompJson = '';
  @state() private _teamCompError = '';
  @state() private _roundBudgetJson = '';
  @state() private _roundBudgetError = '';
  @state() private _initialized = false;

  override willUpdate() {
    if (!this._initialized && this.workspace?.config) {
      this._loadFromConfig(this.workspace.config);
      this._initialized = true;
    }
  }

  private _loadFromConfig(cfg: Record<string, unknown>) {
    // Disabled tools
    const dt = cfg['queen.disabled_tools'];
    if (dt) {
      try {
        const parsed = typeof dt === 'string' ? JSON.parse(dt) : dt;
        if (Array.isArray(parsed)) this._disabledTools = parsed;
      } catch { /* ignore parse errors */ }
    }
    // Custom rules
    const cr = cfg['queen.custom_rules'];
    if (cr) {
      try {
        this._customRules = typeof cr === 'string'
          ? (cr.startsWith('"') ? JSON.parse(cr) : cr) : String(cr);
      } catch { this._customRules = String(cr); }
    }
    // Team composition
    const tc = cfg['queen.team_composition'];
    if (tc) {
      try {
        const obj = typeof tc === 'string' ? JSON.parse(tc) : tc;
        this._teamCompJson = JSON.stringify(obj, null, 2);
      } catch { this._teamCompJson = String(tc); }
    }
    // Round budget
    const rb = cfg['queen.round_budget'];
    if (rb) {
      try {
        const obj = typeof rb === 'string' ? JSON.parse(rb) : rb;
        this._roundBudgetJson = JSON.stringify(obj, null, 2);
      } catch { this._roundBudgetJson = String(rb); }
    }
  }

  private _emitConfig(field: string, value: string) {
    this.dispatchEvent(new CustomEvent('update-config', {
      detail: { field, value },
      bubbles: true,
      composed: true,
    }));
  }

  // ── Disabled tools ──

  private _toggleTool(name: string) {
    if (this._disabledTools.includes(name)) {
      this._disabledTools = this._disabledTools.filter(t => t !== name);
    } else {
      this._disabledTools = [...this._disabledTools, name];
    }
  }

  private _saveDisabledTools() {
    this._emitConfig('queen.disabled_tools', JSON.stringify(this._disabledTools));
  }

  // ── Custom rules ──

  private _saveCustomRules() {
    this._emitConfig('queen.custom_rules', JSON.stringify(this._customRules));
  }

  // ── Team composition ──

  private _onTeamCompInput(value: string) {
    this._teamCompJson = value;
    if (!value.trim()) { this._teamCompError = ''; return; }
    try { JSON.parse(value); this._teamCompError = ''; }
    catch { this._teamCompError = 'Invalid JSON'; }
  }

  private _saveTeamComp() {
    if (this._teamCompError) return;
    this._emitConfig('queen.team_composition', this._teamCompJson.trim() || '{}');
  }

  // ── Round budget ──

  private _onRoundBudgetInput(value: string) {
    this._roundBudgetJson = value;
    if (!value.trim()) { this._roundBudgetError = ''; return; }
    try { JSON.parse(value); this._roundBudgetError = ''; }
    catch { this._roundBudgetError = 'Invalid JSON'; }
  }

  private _saveRoundBudget() {
    if (this._roundBudgetError) return;
    this._emitConfig('queen.round_budget', this._roundBudgetJson.trim() || '{}');
  }

  // ── Render ──

  override render() {
    return html`
      ${this._renderDisabledTools()}
      ${this._renderCustomRules()}
      ${this._renderTeamComp()}
      ${this._renderRoundBudget()}
    `;
  }

  private _renderDisabledTools() {
    const disabled = this._disabledTools;
    return html`
      <div class="section">
        <div class="section-title">Disabled Tools</div>
        <p class="section-desc">
          Checked tools will require operator confirmation before the Queen can use them.
        </p>
        ${disabled.length > 0 ? html`
          <div class="disabled-count">${disabled.length} tool${disabled.length !== 1 ? 's' : ''} disabled</div>
        ` : nothing}
        <div class="tool-grid">
          ${QUEEN_TOOLS.map(name => html`
            <label class="tool-check ${disabled.includes(name) ? 'disabled-tool' : ''}">
              <input type="checkbox"
                .checked=${disabled.includes(name)}
                @change=${() => this._toggleTool(name)}>
              ${name}
            </label>
          `)}
        </div>
        <div class="save-row">
          <button class="save-btn" @click=${this._saveDisabledTools}>Save</button>
        </div>
      </div>
    `;
  }

  private _renderCustomRules() {
    return html`
      <div class="section">
        <div class="section-title">Custom Rules</div>
        <p class="section-desc">
          Free-text behavioral guidance injected into the Queen's context.
          Use for workspace-specific instructions, priorities, or constraints.
        </p>
        <textarea
          .value=${this._customRules}
          placeholder="e.g. Always use sequential strategy for database migrations..."
          @input=${(e: Event) => { this._customRules = (e.target as HTMLTextAreaElement).value; }}
        ></textarea>
        <div class="save-row">
          <button class="save-btn" @click=${this._saveCustomRules}>Save</button>
        </div>
      </div>
    `;
  }

  private _renderTeamComp() {
    return html`
      <div class="section">
        <div class="section-title">Team Composition Overrides</div>
        <p class="section-desc">
          JSON mapping task types to team shapes. Overrides the Queen's default team suggestions.
        </p>
        <textarea class="json-editor"
          .value=${this._teamCompJson}
          placeholder='{"code_simple": "coder / sequential", "research": "researcher + archivist / sequential"}'
          @input=${(e: Event) => this._onTeamCompInput((e.target as HTMLTextAreaElement).value)}
        ></textarea>
        ${this._teamCompError ? html`<div class="json-error">${this._teamCompError}</div>` : nothing}
        <div class="save-row">
          <button class="save-btn" ?disabled=${!!this._teamCompError} @click=${this._saveTeamComp}>Save</button>
        </div>
      </div>
    `;
  }

  private _renderRoundBudget() {
    return html`
      <div class="section">
        <div class="section-title">Round / Budget Overrides</div>
        <p class="section-desc">
          JSON mapping complexity tiers to round and budget limits.
        </p>
        <textarea class="json-editor"
          .value=${this._roundBudgetJson}
          placeholder='{"simple": {"rounds": 4, "budget": 1.5}, "standard": {"rounds": 8, "budget": 2.5}}'
          @input=${(e: Event) => this._onRoundBudgetInput((e.target as HTMLTextAreaElement).value)}
        ></textarea>
        ${this._roundBudgetError ? html`<div class="json-error">${this._roundBudgetError}</div>` : nothing}
        <div class="save-row">
          <button class="save-btn" ?disabled=${!!this._roundBudgetError} @click=${this._saveRoundBudget}>Save</button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-overrides': FcQueenOverrides; }
}
