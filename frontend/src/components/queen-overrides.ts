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
    .form-row {
      display: flex; gap: 8px; align-items: center; margin-bottom: 6px;
      flex-wrap: wrap;
    }
    .form-row select, .form-row input {
      font-size: 10px; font-family: var(--f-mono); padding: 4px 8px;
      border-radius: 4px; border: 1px solid var(--v-border);
      background: var(--v-bg); color: var(--v-fg); outline: none;
    }
    .form-row select:focus, .form-row input:focus { border-color: rgba(232,88,26,0.3); }
    .rule-list { margin-top: 8px; }
    .rule-item {
      display: flex; align-items: center; gap: 8px; padding: 4px 8px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      background: var(--v-bg); border-radius: 4px; margin-bottom: 3px;
    }
    .rule-item .rule-text { flex: 1; }
    .rule-del {
      cursor: pointer; color: var(--v-fg-dim); font-size: 12px;
      padding: 0 4px; border: none; background: none;
    }
    .rule-del:hover { color: var(--v-danger, #ef4444); }
    .caste-pills { display: flex; gap: 4px; flex-wrap: wrap; }
    .caste-pill {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px;
      border-radius: 10px; border: 1px solid var(--v-border); cursor: pointer;
      background: var(--v-bg); color: var(--v-fg-dim); user-select: none;
    }
    .caste-pill.active {
      background: rgba(232,88,26,0.15); border-color: var(--v-accent); color: var(--v-accent);
    }
  `];

  @property() workspaceId = '';
  @property({ type: Object }) workspace: any = null;  // eslint-disable-line @typescript-eslint/no-explicit-any

  @state() private _disabledTools: string[] = [];
  @state() private _customRules = '';
  // Team composition form state
  @state() private _teamRules: Array<{taskType: string; castes: string[]; strategy: string}> = [];
  @state() private _newTaskType = '';
  @state() private _newCastes: string[] = [];
  @state() private _newStrategy = 'sequential';
  // Round budget form state
  @state() private _budgetTiers: Array<{tier: string; rounds: number; budget: number}> = [];
  @state() private _newTier = 'simple';
  @state() private _newRounds = 8;
  @state() private _newBudget = 1.0;
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
    // Team composition → structured rules
    const tc = cfg['queen.team_composition'];
    if (tc) {
      try {
        const obj = typeof tc === 'string' ? JSON.parse(tc) : tc;
        if (typeof obj === 'object' && obj) {
          this._teamRules = Object.entries(obj as Record<string, string>).map(([taskType, value]) => {
            const parts = String(value).split(' / ');
            const strategy = parts[1]?.trim() || 'sequential';
            const castes = parts[0].split('+').map(c => c.trim()).filter(Boolean);
            return { taskType, castes, strategy };
          });
        }
      } catch { /* ignore */ }
    }
    // Round budget → structured tiers
    const rb = cfg['queen.round_budget'];
    if (rb) {
      try {
        const obj = typeof rb === 'string' ? JSON.parse(rb) : rb;
        if (typeof obj === 'object' && obj) {
          this._budgetTiers = Object.entries(obj as Record<string, {rounds?: number; budget?: number}>).map(
            ([tier, val]) => ({
              tier,
              rounds: typeof val === 'object' ? (val.rounds ?? 8) : 8,
              budget: typeof val === 'object' ? (val.budget ?? 1.0) : 1.0,
            }),
          );
        }
      } catch { /* ignore */ }
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

  // ── Team composition (structured) ──

  private _toggleNewCaste(caste: string) {
    if (this._newCastes.includes(caste)) {
      this._newCastes = this._newCastes.filter(c => c !== caste);
    } else {
      this._newCastes = [...this._newCastes, caste];
    }
  }

  private _addTeamRule() {
    const taskType = this._newTaskType.trim();
    if (!taskType || this._newCastes.length === 0) return;
    this._teamRules = [...this._teamRules, { taskType, castes: [...this._newCastes], strategy: this._newStrategy }];
    this._newTaskType = '';
    this._newCastes = [];
    this._newStrategy = 'sequential';
  }

  private _removeTeamRule(idx: number) {
    this._teamRules = this._teamRules.filter((_, i) => i !== idx);
  }

  private _saveTeamComp() {
    const obj: Record<string, string> = {};
    for (const rule of this._teamRules) {
      obj[rule.taskType] = `${rule.castes.join(' + ')} / ${rule.strategy}`;
    }
    this._emitConfig('queen.team_composition', JSON.stringify(obj));
  }

  // ── Round budget (structured) ──

  private _addBudgetTier() {
    const tier = this._newTier.trim();
    if (!tier) return;
    this._budgetTiers = [...this._budgetTiers, { tier, rounds: this._newRounds, budget: this._newBudget }];
    this._newTier = 'simple';
    this._newRounds = 8;
    this._newBudget = 1.0;
  }

  private _removeBudgetTier(idx: number) {
    this._budgetTiers = this._budgetTiers.filter((_, i) => i !== idx);
  }

  private _saveRoundBudget() {
    const obj: Record<string, {rounds: number; budget: number}> = {};
    for (const t of this._budgetTiers) obj[t.tier] = { rounds: t.rounds, budget: t.budget };
    this._emitConfig('queen.round_budget', JSON.stringify(obj));
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
    const TASK_TYPES = ['code_simple', 'code_complex', 'research', 'analysis', 'review', 'documentation'];
    const CASTES = ['coder', 'reviewer', 'researcher', 'archivist'];
    return html`
      <div class="section">
        <div class="section-title">Team Composition Overrides</div>
        <p class="section-desc">
          Map task types to team shapes. Overrides the Queen's default team suggestions.
        </p>
        <div class="form-row">
          <select .value=${this._newTaskType}
            @change=${(e: Event) => { this._newTaskType = (e.target as HTMLSelectElement).value; }}>
            <option value="">Task type...</option>
            ${TASK_TYPES.map(t => html`<option value=${t}>${t}</option>`)}
          </select>
          <input type="text" placeholder="or custom type" style="width:100px"
            .value=${this._newTaskType && !TASK_TYPES.includes(this._newTaskType) ? this._newTaskType : ''}
            @input=${(e: Event) => { this._newTaskType = (e.target as HTMLInputElement).value; }}>
          <div class="caste-pills">
            ${CASTES.map(c => html`
              <span class="caste-pill ${this._newCastes.includes(c) ? 'active' : ''}"
                @click=${() => this._toggleNewCaste(c)}>${c}</span>
            `)}
          </div>
          <select .value=${this._newStrategy}
            @change=${(e: Event) => { this._newStrategy = (e.target as HTMLSelectElement).value; }}>
            <option value="sequential">sequential</option>
            <option value="stigmergic">stigmergic</option>
          </select>
          <button class="save-btn" style="padding:3px 8px"
            ?disabled=${!this._newTaskType.trim() || this._newCastes.length === 0}
            @click=${this._addTeamRule}>Add</button>
        </div>
        ${this._teamRules.length > 0 ? html`
          <div class="rule-list">
            ${this._teamRules.map((rule, i) => html`
              <div class="rule-item">
                <span class="rule-text">${rule.taskType}: ${rule.castes.join(' + ')} / ${rule.strategy}</span>
                <button class="rule-del" @click=${() => this._removeTeamRule(i)}>\u00d7</button>
              </div>
            `)}
          </div>
        ` : nothing}
        <div class="save-row">
          <button class="save-btn" @click=${this._saveTeamComp}>Save</button>
        </div>
      </div>
    `;
  }

  private _renderRoundBudget() {
    const TIERS = ['simple', 'standard', 'complex', 'critical'];
    return html`
      <div class="section">
        <div class="section-title">Round / Budget Overrides</div>
        <p class="section-desc">
          Set per-tier round limits and dollar budgets.
        </p>
        <div class="form-row">
          <select .value=${this._newTier}
            @change=${(e: Event) => { this._newTier = (e.target as HTMLSelectElement).value; }}>
            ${TIERS.map(t => html`<option value=${t}>${t}</option>`)}
          </select>
          <input type="text" placeholder="or custom" style="width:80px"
            @input=${(e: Event) => { const v = (e.target as HTMLInputElement).value; if (v) this._newTier = v; }}>
          <label style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim)">Rounds:</label>
          <input type="number" min="1" max="50" style="width:50px"
            .value=${String(this._newRounds)}
            @input=${(e: Event) => { this._newRounds = parseInt((e.target as HTMLInputElement).value) || 8; }}>
          <label style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim)">Budget $:</label>
          <input type="number" min="0.10" max="100" step="0.10" style="width:60px"
            .value=${String(this._newBudget)}
            @input=${(e: Event) => { this._newBudget = parseFloat((e.target as HTMLInputElement).value) || 1.0; }}>
          <button class="save-btn" style="padding:3px 8px"
            ?disabled=${!this._newTier.trim()}
            @click=${this._addBudgetTier}>Add</button>
        </div>
        ${this._budgetTiers.length > 0 ? html`
          <div class="rule-list">
            ${this._budgetTiers.map((t, i) => html`
              <div class="rule-item">
                <span class="rule-text">${t.tier}: ${t.rounds} rounds, $${t.budget.toFixed(2)}</span>
                <button class="rule-del" @click=${() => this._removeBudgetTier(i)}>\u00d7</button>
              </div>
            `)}
          </div>
        ` : nothing}
        <div class="save-row">
          <button class="save-btn" @click=${this._saveRoundBudget}>Save</button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-overrides': FcQueenOverrides; }
}
