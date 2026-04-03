/**
 * Wave 72 Track 10A: Settings — writable-first restructure.
 *
 * Sections: Workspace, Governance, Budgeting & Autonomy, Model Defaults,
 * Integrations. Read-only diagnostics collapse into a toggled section.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type {
  ProtocolStatus, RuntimeConfig, SkillBankStats, TreeNode,
  AddonSummary, ModelRegistryEntry,
} from '../types.js';
import type { RetrievalTiming, RetrievalCounts } from './retrieval-diagnostics.js';
import './atoms.js';
import './retrieval-diagnostics.js';
import './system-overview.js';
import './autonomy-card.js';
import './mcp-servers-card.js';

interface MaintenancePolicyData {
  autonomy_level: string;
  auto_actions: string[];
  max_maintenance_colonies: number;
  daily_maintenance_budget: number;
}

@customElement('fc-settings-view')
export class FcSettingsView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host {
      display: block; max-width: 640px; overflow-y: auto; height: 100%;
      padding: 0 4px 24px;
    }
    h2 {
      font-family: var(--f-display); font-size: 20px; font-weight: 700;
      color: var(--v-fg); margin: 0 0 6px;
    }
    .subtitle {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-dim);
      margin-bottom: 14px;
    }

    /* --- Card sections --- */
    .settings-card {
      background: var(--v-surface);
      border: 1px solid var(--v-border);
      border-radius: 10px;
      padding: 16px 20px;
      margin-bottom: 12px;
    }
    .settings-card h3 {
      font-family: var(--f-display); font-size: 13px; font-weight: 600;
      color: var(--v-fg); margin: 0 0 12px;
    }

    /* --- Shared control styles --- */
    .control-row {
      display: flex; align-items: center; gap: 10px; padding: 7px 0;
      border-bottom: 1px solid var(--v-border);
    }
    .control-row:last-child { border-bottom: none; }
    .control-label {
      font-family: var(--f-mono); font-size: 10.5px; font-weight: 600;
      color: var(--v-fg); flex: 1;
    }
    .control-hint {
      font-size: 9px; color: var(--v-fg-dim); font-family: var(--f-mono);
    }
    .control-row select, .control-row input {
      padding: 4px 8px; background: var(--v-surface);
      border: 1px solid var(--v-border); border-radius: 6px;
      color: var(--v-fg); font-family: var(--f-mono); font-size: 11px;
      outline: none; transition: border-color 0.15s;
    }
    .control-row select:focus, .control-row input:focus {
      border-color: rgba(232,88,26,0.3);
    }
    .control-row input[type="number"] { width: 80px; text-align: right; }
    .control-row input[type="range"] {
      width: 120px; accent-color: var(--v-accent);
    }

    /* --- Inline save indicator --- */
    .save-indicator {
      color: var(--v-success); font-size: 12px;
      opacity: 0; transition: opacity 0.15s;
      margin-left: 6px;
    }
    .save-indicator[visible] { opacity: 1; }

    /* --- Validation error --- */
    .field-error {
      font-size: 10px; font-family: var(--f-mono);
      color: var(--v-danger); margin-top: 2px;
    }

    /* --- Read-only label --- */
    .read-only-label {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      font-style: italic; margin-top: 4px;
    }

    /* --- Tag pills --- */
    .tag-pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
    .tag-pill {
      padding: 2px 8px; border-radius: 999px; font-size: 10px;
      font-family: var(--f-mono); background: var(--v-accent-muted);
      color: var(--v-fg-muted); border: 1px solid var(--v-border);
    }

    /* --- Caste grid --- */
    .caste-grid {
      display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;
      margin-top: 8px;
    }
    .caste-cell {
      text-align: center; padding: 8px 4px; border-radius: 8px;
      border: 1px solid var(--v-border); background: var(--v-recessed);
    }
    .caste-name {
      font-size: 9px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.06em; margin-bottom: 4px;
    }
    .caste-model {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      word-break: break-all;
    }

    /* --- Empty text --- */
    .empty-text {
      font-size: 10.5px; font-family: var(--f-mono);
      color: var(--v-fg-dim); font-style: italic;
    }

    /* --- Diagnostics toggle --- */
    .diag-toggle {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-dim);
      cursor: pointer; padding: 8px 0; display: flex; align-items: center; gap: 6px;
      transition: color 0.15s;
    }
    .diag-toggle:hover { color: var(--v-fg-muted); }

    /* --- Protocol row --- */
    .proto-row {
      display: flex; align-items: center; gap: 8px; padding: 5px 0;
      border-bottom: 1px solid var(--v-border);
    }
    .proto-row:last-child { border-bottom: none; }
    .proto-name {
      font-family: var(--f-mono); font-size: 10.5px; font-weight: 600;
      color: var(--v-fg); width: 50px;
    }
    .proto-detail {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-left: 4px;
    }
    .proto-desc { font-size: 10px; color: var(--v-fg-muted); }

    /* --- Addon summary --- */
    .addon-row {
      display: flex; align-items: center; gap: 8px; padding: 6px 0;
      border-bottom: 1px solid var(--v-border);
    }
    .addon-row:last-child { border-bottom: none; }
    .addon-name {
      font-size: 11px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg);
    }
    .addon-desc {
      font-size: 10px; color: var(--v-fg-dim); flex: 1;
    }
    .addon-meta {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { transition: none !important; animation: none !important; }
    }
  `];

  @property({ type: Object }) protocolStatus: ProtocolStatus | null = null;
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @property({ type: Object }) skillBankStats: SkillBankStats | null = null;
  @property({ type: Array }) tree: TreeNode[] = [];
  @property({ type: Array }) addons: AddonSummary[] = [];
  @property({ type: String }) activeWorkspaceId = '';

  @state() private _editStrategy: 'stigmergic' | 'sequential' = 'stigmergic';
  @state() private _editMaxRounds = 25;
  @state() private _editBudget = 1.0;
  @state() private _editConvergence = 0.95;
  @state() private _savedFields = new Set<string>();
  @state() private _fieldErrors = new Map<string, string>();
  @state() private _diagTiming: RetrievalTiming | null = null;
  @state() private _diagCounts: RetrievalCounts | null = null;
  @state() private _diagEmbedModel = '';
  @state() private _diagEmbedDim = 0;
  @state() private _diagSearchMode = '';
  @state() private _knowledgeTotal = 0;
  @state() private _showDiagnostics = false;

  // Wave 81: project binding + code index status
  @state() private _bindingBound = false;
  @state() private _bindingRoot = '';
  @state() private _bindingMode = '';
  @state() private _indexStatus = '';
  @state() private _indexChunks = 0;
  @state() private _indexLastTime = '';
  @state() private _indexReindexing = false;

  // Maintenance policy state
  @state() private _policyLoaded = false;
  @state() private _policyLevel = 'suggest';
  @state() private _policyBudget = 1.0;
  @state() private _policyMaxColonies = 2;
  @state() private _policySaving = false;
  @state() private _policySaved = false;

  private _saveTimeouts = new Map<string, number>();

  connectedCallback() {
    super.connectedCallback();
    void this._fetchDiagnostics();
    void this._fetchKnowledgeSummary();
    void this._fetchMaintenancePolicy();
    void this._fetchProjectBinding();
    this._syncFromConfig();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('runtimeConfig')) {
      this._syncFromConfig();
    }
  }

  private _syncFromConfig() {
    const gov = this.runtimeConfig?.governance;
    const routing = this.runtimeConfig?.routing;
    if (gov) {
      this._editMaxRounds = gov.maxRoundsPerColony;
      this._editBudget = gov.defaultBudgetPerColony;
      this._editConvergence = gov.convergenceThreshold;
    }
    if (routing) {
      this._editStrategy = routing.defaultStrategy as 'stigmergic' | 'sequential';
    }
  }

  private get _workspaceId(): string {
    return this.activeWorkspaceId || this.tree[0]?.id || '';
  }

  private get _activeWorkspace() {
    const id = this._workspaceId;
    return this.tree.find(ws => ws.id === id) ?? this.tree[0];
  }

  // --- Instant save per field ---

  private _onControlChange(field: string, value: unknown) {
    const error = this._validate(field, value);
    if (error) {
      const next = new Map(this._fieldErrors);
      next.set(field, error);
      this._fieldErrors = next;
      return;
    }
    if (this._fieldErrors.has(field)) {
      const next = new Map(this._fieldErrors);
      next.delete(field);
      this._fieldErrors = next;
    }
    const existing = this._saveTimeouts.get(field);
    if (existing) clearTimeout(existing);
    this._saveTimeouts.set(field, window.setTimeout(() => {
      void this._saveField(field, value);
    }, 500));
  }

  private _validate(field: string, value: unknown): string | null {
    const num = Number(value);
    switch (field) {
      case 'governance.default_budget_per_colony':
        if (isNaN(num) || num <= 0) return 'Must be a positive number';
        break;
      case 'governance.max_rounds_per_colony':
        if (isNaN(num) || num < 1 || num > 50) return 'Must be 1\u201350';
        break;
      case 'governance.convergence_threshold':
        if (isNaN(num) || num < 0.80 || num > 1.00) return '0.80\u20131.00';
        break;
    }
    return null;
  }

  private async _saveField(field: string, value: unknown) {
    const wsId = this._workspaceId;
    if (!wsId) return;
    try {
      await fetch(
        `/api/v1/workspaces/${encodeURIComponent(wsId)}/config-overrides`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dimension: field,
            original: {},
            overridden: { value },
            reason: 'operator settings panel',
          }),
        },
      );
      this._showSaveIndicator(field);
    } catch {
      // Save errors are silent
    }
  }

  private _showSaveIndicator(field: string) {
    const next = new Set(this._savedFields);
    next.add(field);
    this._savedFields = next;
    setTimeout(() => {
      const rm = new Set(this._savedFields);
      rm.delete(field);
      this._savedFields = rm;
    }, 1500);
  }

  // --- Maintenance policy ---

  private async _fetchMaintenancePolicy() {
    const wsId = this._workspaceId;
    if (!wsId) return;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(wsId)}/maintenance-policy`,
      );
      if (!resp.ok) return;
      const data = await resp.json() as MaintenancePolicyData;
      this._policyLevel = data.autonomy_level ?? 'suggest';
      this._policyBudget = data.daily_maintenance_budget ?? 1.0;
      this._policyMaxColonies = data.max_maintenance_colonies ?? 2;
      this._policyLoaded = true;
    } catch {
      // best-effort
    }
  }

  private async _saveMaintenancePolicy() {
    const wsId = this._workspaceId;
    if (!wsId) return;
    this._policySaving = true;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(wsId)}/maintenance-policy`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            autonomy_level: this._policyLevel,
            daily_maintenance_budget: this._policyBudget,
            max_maintenance_colonies: this._policyMaxColonies,
          }),
        },
      );
      if (resp.ok) {
        this._policySaved = true;
        setTimeout(() => { this._policySaved = false; }, 2000);
      }
    } catch {
      // best-effort
    }
    this._policySaving = false;
  }

  // --- Data fetching ---

  private async _fetchDiagnostics() {
    try {
      const resp = await fetch('/api/v1/retrieval-diagnostics');
      if (!resp.ok) return;
      const data = await resp.json();
      const t = data.timing ?? {};
      this._diagTiming = {
        embedMs: 0, denseMs: t.vectorMs ?? 0, bm25Ms: 0,
        graphMs: t.graphMs ?? 0, fusionMs: 0, totalMs: t.totalMs ?? 0,
      };
      this._diagCounts = data.counts ?? null;
      const emb = data.embedding ?? {};
      this._diagEmbedModel = emb.model ?? '';
      this._diagEmbedDim = emb.dimensions ?? 0;
      this._diagSearchMode = data.searchMode ?? '';
    } catch {
      // best-effort
    }
  }

  private async _fetchKnowledgeSummary() {
    try {
      const wsId = this._workspaceId;
      if (!wsId) return;
      const resp = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(wsId)}/knowledge?limit=1`,
      );
      if (!resp.ok) return;
      const data = await resp.json();
      this._knowledgeTotal = data.total ?? 0;
    } catch {
      // best-effort
    }
  }

  // --- Helpers ---

  private get _taxonomyTags(): string[] {
    const ws = this._activeWorkspace;
    if (!ws) return [];
    const cfg = (ws as unknown as { config?: Record<string, string> }).config;
    const raw = cfg?.taxonomy_tags;
    if (!raw) return [];
    try { return JSON.parse(raw); } catch { return []; }
  }

  private get _casteDefaults(): Record<string, string> {
    const d = this.runtimeConfig?.models?.defaults;
    if (!d) return {};
    return {
      queen: d.queen, coder: d.coder, reviewer: d.reviewer,
      researcher: d.researcher, archivist: d.archivist,
    };
  }

  // --- Render ---

  render() {
    return html`
      <h2>Settings</h2>
      <div class="subtitle">Operator controls and workspace configuration</div>

      ${this._renderIdentityCard()}
      ${this._renderProjectBindingCard()}
      ${this._renderGovernanceCard()}
      ${this._renderBudgetingCard()}
      ${this._renderModelDefaultsCard()}
      ${this._renderIntegrationsCard()}
      ${this._renderDiagnosticsToggle()}
    `;
  }

  // --- Card 1: Workspace Identity ---

  private _renderIdentityCard() {
    const wsName = this._activeWorkspace?.name ?? 'No workspace';
    const tags = this._taxonomyTags;

    return html`
      <div class="settings-card">
        <h3>Workspace</h3>
        <div class="control-row">
          <div>
            <div class="control-label">${wsName}</div>
            <div class="control-hint">Workspace name</div>
          </div>
        </div>
        <div style="padding:7px 0">
          <div class="control-label" style="margin-bottom:4px">Tags</div>
          ${tags.length > 0
            ? html`<div class="tag-pills">
                ${tags.map(t => html`<span class="tag-pill">${t}</span>`)}
              </div>`
            : html`<div class="empty-text">No tags yet</div>`
          }
          <div class="read-only-label">Set via Queen \u00B7 set_workspace_tags</div>
        </div>
      </div>
    `;
  }

  // --- Card 2: Colony Governance (editable, instant save) ---

  private _renderGovernanceCard() {
    return html`
      <div class="settings-card">
        <h3>Governance</h3>
        <div class="control-row">
          <div>
            <div class="control-label">Default Strategy</div>
            <div class="control-hint">Coordination mode for new colonies</div>
          </div>
          <select .value=${this._editStrategy} @change=${(e: Event) => {
            const v = (e.target as HTMLSelectElement).value as
              'stigmergic' | 'sequential';
            this._editStrategy = v;
            this._onControlChange('routing.default_strategy', v);
          }}>
            <option value="stigmergic">stigmergic</option>
            <option value="sequential">sequential</option>
          </select>
          <span class="save-indicator"
            ?visible=${this._savedFields.has('routing.default_strategy')}
          >\u2713</span>
        </div>

        <div class="control-row">
          <div>
            <div class="control-label">Max Rounds per Colony</div>
            <div class="control-hint">Hard cap on iteration rounds (1\u201350)</div>
            ${this._fieldErrors.has('governance.max_rounds_per_colony')
              ? html`<div class="field-error">
                  ${this._fieldErrors.get('governance.max_rounds_per_colony')}
                </div>` : nothing}
          </div>
          <input type="number" min="1" max="50"
            .value=${String(this._editMaxRounds)}
            @input=${(e: Event) => {
              const v = parseInt(
                (e.target as HTMLInputElement).value, 10,
              ) || 25;
              this._editMaxRounds = v;
              this._onControlChange(
                'governance.max_rounds_per_colony', v,
              );
            }}>
          <span class="save-indicator"
            ?visible=${this._savedFields.has('governance.max_rounds_per_colony')}
          >\u2713</span>
        </div>

        <div class="control-row">
          <div>
            <div class="control-label">Default Budget per Colony</div>
            <div class="control-hint">USD spend cap per colony</div>
            ${this._fieldErrors.has('governance.default_budget_per_colony')
              ? html`<div class="field-error">
                  ${this._fieldErrors.get('governance.default_budget_per_colony')}
                </div>` : nothing}
          </div>
          <input type="number" min="0.01" max="100" step="0.10"
            .value=${String(this._editBudget)}
            @input=${(e: Event) => {
              const v = parseFloat(
                (e.target as HTMLInputElement).value,
              ) || 1.0;
              this._editBudget = v;
              this._onControlChange(
                'governance.default_budget_per_colony', v,
              );
            }}>
          <span class="save-indicator"
            ?visible=${this._savedFields.has('governance.default_budget_per_colony')}
          >\u2713</span>
        </div>

        <div class="control-row">
          <div>
            <div class="control-label">Convergence Threshold</div>
            <div class="control-hint">${this._editConvergence.toFixed(2)}</div>
            ${this._fieldErrors.has('governance.convergence_threshold')
              ? html`<div class="field-error">
                  ${this._fieldErrors.get('governance.convergence_threshold')}
                </div>` : nothing}
          </div>
          <input type="range" min="0.80" max="1.00" step="0.01"
            .value=${String(this._editConvergence)}
            @input=${(e: Event) => {
              const v = parseFloat(
                (e.target as HTMLInputElement).value,
              ) || 0.95;
              this._editConvergence = v;
              this._onControlChange(
                'governance.convergence_threshold', v,
              );
            }}>
          <span class="save-indicator"
            ?visible=${this._savedFields.has('governance.convergence_threshold')}
          >\u2713</span>
        </div>
      </div>
    `;
  }

  // --- Card 3: Budgeting & Autonomy ---

  private _renderBudgetingCard() {
    const wsId = this._workspaceId;
    if (!wsId) return nothing;

    return html`
      <div class="settings-card">
        <h3>Budgeting & Autonomy</h3>

        <div class="control-row">
          <div>
            <div class="control-label">Autonomy Level</div>
            <div class="control-hint">How much the system can do on its own</div>
          </div>
          <select .value=${this._policyLevel} @change=${(e: Event) => {
            this._policyLevel = (e.target as HTMLSelectElement).value;
          }}>
            <option value="suggest">suggest</option>
            <option value="auto_notify">auto_notify</option>
            <option value="autonomous">autonomous</option>
          </select>
        </div>

        <div class="control-row">
          <div>
            <div class="control-label">Daily Maintenance Budget</div>
            <div class="control-hint">USD cap for autonomous work per day</div>
          </div>
          <input type="number" min="0.10" max="100" step="0.10"
            .value=${String(this._policyBudget)}
            @input=${(e: Event) => {
              this._policyBudget = parseFloat(
                (e.target as HTMLInputElement).value,
              ) || 1.0;
            }}>
        </div>

        <div class="control-row">
          <div>
            <div class="control-label">Max Maintenance Colonies</div>
            <div class="control-hint">Concurrent maintenance colony limit</div>
          </div>
          <input type="number" min="0" max="10"
            .value=${String(this._policyMaxColonies)}
            @input=${(e: Event) => {
              this._policyMaxColonies = parseInt(
                (e.target as HTMLInputElement).value, 10,
              ) || 2;
            }}>
        </div>

        <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
          <fc-btn variant="primary" sm
            ?disabled=${this._policySaving}
            @click=${() => void this._saveMaintenancePolicy()}>
            ${this._policySaving ? 'Saving\u2026' : 'Save Policy'}
          </fc-btn>
          ${this._policySaved ? html`
            <span style="font-family:var(--f-mono);font-size:10px;color:var(--v-success)">
              \u2713 Saved
            </span>
          ` : nothing}
        </div>

        <div style="margin-top:12px">
          <fc-autonomy-card .workspaceId=${wsId}></fc-autonomy-card>
        </div>
      </div>
    `;
  }

  // --- Card 4: Model Defaults ---

  private _renderModelDefaultsCard() {
    const castes = this._casteDefaults;

    return html`
      <div class="settings-card">
        <h3>Model Defaults</h3>
        ${Object.keys(castes).length > 0 ? html`
          <div class="caste-grid">
            ${Object.entries(castes).map(([caste, model]) => html`
              <div class="caste-cell">
                <div class="caste-name">${caste}</div>
                <div class="caste-model">${model || '\u2014'}</div>
              </div>
            `)}
          </div>
          <div class="read-only-label">
            Managed by caste recipes. Full admin in the Models tab.
          </div>
        ` : html`
          <div class="empty-text">Model configuration not available</div>
        `}
      </div>
    `;
  }

  // --- Card 5: Integrations ---

  private _renderIntegrationsCard() {
    return html`
      <div class="settings-card">
        <h3>Integrations</h3>
        <fc-mcp-servers-card></fc-mcp-servers-card>
        ${this._renderProtocolsSummary()}
        ${this._renderAddonsSummary()}
      </div>
    `;
  }

  private _renderProtocolsSummary() {
    const mcpProto = this.protocolStatus?.mcp;
    const aguiProto = this.protocolStatus?.agui;
    const a2aProto = this.protocolStatus?.a2a;

    const mcpStatus = mcpProto?.status ?? 'inactive';
    const aguiStatus = aguiProto?.status ?? 'inactive';
    const a2aStatus = a2aProto?.status ?? 'inactive';

    return html`
      <div style="margin-top:12px">
        <div style="font-family:var(--f-mono);font-size:9px;font-weight:600;color:var(--v-fg-dim);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px">
          Protocols
        </div>
        <div class="proto-row">
          <fc-dot .status=${mcpStatus === 'active' ? 'loaded' : 'pending'}
            .size=${4}></fc-dot>
          <span class="proto-name">MCP</span>
          <span class="proto-detail">${(mcpProto as any)?.tools ?? 0} tools</span>
          <fc-pill color="var(--v-fg-dim)" sm
            style="margin-left:auto">${mcpStatus}</fc-pill>
        </div>
        <div class="proto-row">
          <fc-dot .status=${aguiStatus === 'active' ? 'loaded' : 'pending'}
            .size=${4}></fc-dot>
          <span class="proto-name">AG-UI</span>
          <span class="proto-detail">${aguiStatus === 'active'
            ? `${(aguiProto as any)?.events ?? 0} events` : ''}</span>
          <fc-pill color="var(--v-fg-dim)" sm
            style="margin-left:auto">${aguiStatus}</fc-pill>
        </div>
        <div class="proto-row">
          <fc-dot .status=${a2aStatus === 'active' ? 'loaded' : 'pending'}
            .size=${4}></fc-dot>
          <span class="proto-name">A2A</span>
          <span class="proto-detail">${a2aStatus === 'active'
            ? `${(a2aProto as any)?.semantics ?? ''} ${(a2aProto as any)?.endpoint ?? ''}`.trim()
            : ''}</span>
          <fc-pill color="var(--v-fg-dim)" sm
            style="margin-left:auto">${a2aStatus}</fc-pill>
        </div>
      </div>
    `;
  }

  private _renderAddonsSummary() {
    const addons = this.addons;
    if (addons.length === 0) return nothing;

    return html`
      <div style="margin-top:12px">
        <div style="font-family:var(--f-mono);font-size:9px;font-weight:600;color:var(--v-fg-dim);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px">
          Addons
        </div>
        ${addons.map(a => html`
          <div class="addon-row">
            <fc-dot .status=${a.status === 'healthy' ? 'loaded'
              : a.status === 'degraded' ? 'pending' : 'error'}
              .size=${4}></fc-dot>
            <span class="addon-name">${a.name}</span>
            <span class="addon-desc">${a.description}</span>
            <span class="addon-meta">
              ${a.tools.length} tool${a.tools.length !== 1 ? 's' : ''}
            </span>
          </div>
        `)}
      </div>
    `;
  }

  // --- Card: Project Binding + Code Index (Wave 81) ---

  private async _fetchProjectBinding() {
    const wsId = this.activeWorkspaceId;
    if (!wsId) return;
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/project-binding`);
      if (res.ok) {
        const data = await res.json() as Record<string, unknown>;
        this._bindingBound = !!data.bound;
        this._bindingRoot = (data.project_root as string) ?? '';
        this._bindingMode = (data.binding_mode as string) ?? 'env';
        const idx = data.code_index as Record<string, unknown> | undefined;
        if (idx) {
          this._indexStatus = (idx.status as string) ?? 'unavailable';
          this._indexChunks = (idx.chunks_indexed as number) ?? 0;
          this._indexLastTime = (idx.last_indexed_at as string) ?? '';
        }
      } else {
        this._bindingBound = false;
      }
    } catch {
      this._bindingBound = false;
    }
  }

  private async _triggerReindex() {
    const wsId = this.activeWorkspaceId;
    if (!wsId) return;
    this._indexReindexing = true;
    try {
      await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/reindex`, { method: 'POST' });
      await this._fetchProjectBinding();
    } finally {
      this._indexReindexing = false;
    }
  }

  private _renderProjectBindingCard() {
    return html`
      <div class="settings-card">
        <h3>Project Binding</h3>
        <div class="control-row">
          <div>
            <div class="control-label">
              ${this._bindingBound
                ? html`<span style="color:var(--v-success)">\u2713 Bound</span>`
                : html`<span style="color:var(--v-fg-dim)">\u2014 Not bound</span>`}
            </div>
            <div class="control-hint">
              ${this._bindingBound
                ? html`Project root: <code style="font-size:10px">${this._bindingRoot}</code> (${this._bindingMode})`
                : 'Set PROJECT_DIR to bind a project root'}
            </div>
          </div>
        </div>
        ${this._bindingBound ? html`
          <div class="control-row" style="margin-top:8px">
            <div>
              <div class="control-label">Code Index</div>
              <div class="control-hint">
                ${this._indexStatus === 'ready'
                  ? html`${this._indexChunks} chunks indexed${this._indexLastTime ? html` \u00B7 last: ${this._indexLastTime}` : nothing}`
                  : this._indexStatus === 'indexing'
                    ? 'Indexing in progress...'
                    : this._indexStatus === 'unavailable'
                      ? 'Index unavailable'
                      : 'Not indexed yet'}
              </div>
            </div>
            <fc-btn variant="ghost" sm
              ?disabled=${this._indexReindexing}
              @click=${() => void this._triggerReindex()}>
              ${this._indexReindexing ? 'Reindexing...' : 'Reindex'}
            </fc-btn>
          </div>
        ` : nothing}
      </div>
    `;
  }

  // --- Diagnostics (collapsed) ---

  private _renderDiagnosticsToggle() {
    return html`
      <div class="diag-toggle" @click=${() => { this._showDiagnostics = !this._showDiagnostics; }}>
        <span>${this._showDiagnostics ? '\u25BC' : '\u25B6'}</span>
        <span>Diagnostics & System Info</span>
      </div>
      ${this._showDiagnostics ? html`
        <fc-system-overview
          .runtimeConfig=${this.runtimeConfig}
          .addons=${this.addons}
          .knowledgeTotal=${this._knowledgeTotal}
          .domainCount=${0}
        ></fc-system-overview>

        <div class="settings-card">
          <h3>Retrieval Diagnostics</h3>
          <fc-retrieval-diagnostics
            .embeddingModel=${this._diagEmbedModel}
            .embeddingDim=${this._diagEmbedDim}
            .searchMode=${this._diagSearchMode}
            .timing=${this._diagTiming}
            .counts=${this._diagCounts}
          ></fc-retrieval-diagnostics>
        </div>
      ` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-settings-view': FcSettingsView; }
}
