import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { ProtocolStatus, RuntimeConfig, SkillBankStats, TreeNode } from '../types.js';
import type { RetrievalTiming, RetrievalCounts } from './retrieval-diagnostics.js';
import './atoms.js';
import './retrieval-diagnostics.js';

@customElement('fc-settings-view')
export class FcSettingsView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; max-width: 580px; overflow: auto; height: 100%; }
    h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin-bottom: 18px; }
    .section { margin-bottom: 16px; }
    .desc { font-size: 10.5px; font-family: var(--f-mono); color: var(--v-fg-muted); margin-bottom: 8px; }
    .strat-desc { font-size: 10.5px; color: var(--v-fg-muted); margin-bottom: 8px; line-height: 1.4; }
    .pills { display: flex; gap: 6px; }
    .proto-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--v-border); }
    .proto-name { font-family: var(--f-mono); font-size: 10.5px; font-weight: 600; color: var(--v-fg); width: 50px; }
    .proto-desc { font-size: 10px; color: var(--v-fg-muted); }
    .control-row {
      display: flex; align-items: center; gap: 10px; padding: 8px 0;
      border-bottom: 1px solid var(--v-border);
    }
    .control-row:last-child { border-bottom: none; }
    .control-label {
      font-family: var(--f-mono); font-size: 10.5px; font-weight: 600;
      color: var(--v-fg); flex: 1;
    }
    .control-hint { font-size: 9px; color: var(--v-fg-dim); font-family: var(--f-mono); }
    .control-row select, .control-row input {
      padding: 4px 8px; background: var(--v-surface); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono); font-size: 11px;
      outline: none; transition: border-color 0.15s;
    }
    .control-row select:focus, .control-row input:focus { border-color: rgba(232,88,26,0.3); }
    .control-row input[type="number"] { width: 80px; text-align: right; }
    .control-row input[type="range"] { width: 120px; accent-color: var(--v-accent); }
    .save-row { display: flex; justify-content: flex-end; margin-top: 8px; gap: 6px; align-items: center; }
    .save-msg { font-size: 9px; font-family: var(--f-mono); color: var(--v-success); }
  `];

  @property({ type: Object }) protocolStatus: ProtocolStatus | null = null;
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @property({ type: Object }) skillBankStats: SkillBankStats | null = null;
  @property({ type: Array }) tree: TreeNode[] = [];

  private _snapshotTime = Date.now();
  @state() private _editStrategy: 'stigmergic' | 'sequential' = 'stigmergic';
  @state() private _editMaxRounds = 25;
  @state() private _editBudget = 1.0;
  @state() private _editConvergence = 0.95;
  @state() private _editAutonomy: 'suggest' | 'auto_notify' | 'autonomous' = 'suggest';
  @state() private _saving = false;
  @state() private _saveMsg = '';
  @state() private _controlsDirty = false;
  @state() private _diagTiming: RetrievalTiming | null = null;
  @state() private _diagCounts: RetrievalCounts | null = null;
  @state() private _diagEmbedModel = '';
  @state() private _diagEmbedDim = 0;
  @state() private _diagSearchMode = '';

  connectedCallback() {
    super.connectedCallback();
    void this._fetchDiagnostics();
    this._syncFromConfig();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('runtimeConfig') && !this._controlsDirty) {
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
    return this.tree[0]?.id ?? '';
  }

  private async _saveSettings() {
    const wsId = this._workspaceId;
    if (!wsId) return;
    this._saving = true;
    this._saveMsg = '';
    try {
      const changes = [
        { dimension: 'governance.max_rounds_per_colony', original: {}, overridden: { value: this._editMaxRounds }, reason: 'operator settings panel' },
        { dimension: 'governance.default_budget_per_colony', original: {}, overridden: { value: this._editBudget }, reason: 'operator settings panel' },
        { dimension: 'governance.convergence_threshold', original: {}, overridden: { value: this._editConvergence }, reason: 'operator settings panel' },
        { dimension: 'routing.default_strategy', original: {}, overridden: { value: this._editStrategy }, reason: 'operator settings panel' },
      ];
      for (const change of changes) {
        await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/config-overrides`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(change),
        });
      }
      this._saveMsg = 'Saved';
      this._controlsDirty = false;
      setTimeout(() => { this._saveMsg = ''; }, 2000);
    } catch {
      this._saveMsg = 'Error saving';
    }
    this._saving = false;
  }

  private async _fetchDiagnostics() {
    try {
      const resp = await fetch('/api/v1/retrieval-diagnostics');
      if (!resp.ok) return;
      const data = await resp.json();
      const t = data.timing ?? {};
      this._diagTiming = {
        embedMs: 0,
        denseMs: t.vectorMs ?? 0,
        bm25Ms: 0,
        graphMs: t.graphMs ?? 0,
        fusionMs: 0,
        totalMs: t.totalMs ?? 0,
      };
      this._diagCounts = data.counts ?? null;
      const emb = data.embedding ?? {};
      this._diagEmbedModel = emb.model ?? '';
      this._diagEmbedDim = emb.dimensions ?? 0;
      this._diagSearchMode = data.searchMode ?? '';
    } catch {
      // Diagnostics are best-effort; fail silently
    }
  }

  render() {
    const strategy = this.runtimeConfig?.routing?.defaultStrategy ?? 'stigmergic';
    const aguiStatus = this.protocolStatus?.agui?.status ?? 'inactive';
    const a2aStatus = this.protocolStatus?.a2a?.status ?? 'inactive';
    const mcpProto = this.protocolStatus?.mcp;
    const aguiProto = this.protocolStatus?.agui;
    const a2aProto = this.protocolStatus?.a2a;
    const mcpDesc = mcpProto?.transport
      ? `${mcpProto.transport} \u00B7 ${mcpProto.endpoint ?? '/mcp'} \u00B7 ${mcpProto.tools ?? 0} tools`
      : `${mcpProto?.tools ?? 0} tools exposed`;
    const aguiDesc = aguiStatus === 'active'
      ? `SSE ${aguiProto?.semantics ?? ''} \u00B7 ${aguiProto?.endpoint ?? ''} \u00B7 ${aguiProto?.events ?? 0} event types`
      : 'Inactive';
    const a2aDesc = a2aStatus === 'inactive'
      ? (a2aProto?.note ?? 'Inactive')
      : `REST ${a2aProto?.semantics ?? 'poll/result'} \u00B7 ${a2aProto?.endpoint ?? '/a2a/tasks'}`;
    const protocols = [
      { n: 'MCP', d: mcpDesc, s: mcpProto?.status ?? 'inactive' },
      { n: 'AG-UI', d: aguiDesc, s: aguiStatus },
      { n: 'A2A', d: a2aDesc, s: a2aStatus },
    ];

    return html`
      <h2>Settings</h2>

      <div class="section">
        <fc-retrieval-diagnostics
          .embeddingModel=${this._diagEmbedModel}
          .embeddingDim=${this._diagEmbedDim}
          .searchMode=${this._diagSearchMode}
          .timing=${this._diagTiming}
          .counts=${this._diagCounts}
        ></fc-retrieval-diagnostics>
      </div>

      <div class="section">
        <div class="s-label">Event Store</div>
        <div class="glass" style="padding:12px">
          <div class="desc">Single SQLite \u00B7 WAL mode \u00B7 append-only</div>
        </div>
      </div>

      <div class="section">
        <div class="s-label">Colony Governance</div>
        <div class="glass" style="padding:12px">
          <div class="control-row">
            <div>
              <div class="control-label">Default Strategy</div>
              <div class="control-hint">Coordination mode for new colonies</div>
            </div>
            <select .value=${this._editStrategy} @change=${(e: Event) => {
              this._editStrategy = (e.target as HTMLSelectElement).value as 'stigmergic' | 'sequential';
              this._controlsDirty = true;
            }}>
              <option value="stigmergic">stigmergic</option>
              <option value="sequential">sequential</option>
            </select>
          </div>
          <div class="control-row">
            <div>
              <div class="control-label">Max Rounds per Colony</div>
              <div class="control-hint">Hard cap on iteration rounds</div>
            </div>
            <input type="number" min="1" max="50" .value=${String(this._editMaxRounds)} @input=${(e: Event) => {
              this._editMaxRounds = Math.max(1, Math.min(50, parseInt((e.target as HTMLInputElement).value, 10) || 25));
              this._controlsDirty = true;
            }}>
          </div>
          <div class="control-row">
            <div>
              <div class="control-label">Default Budget per Colony</div>
              <div class="control-hint">USD spend cap per colony</div>
            </div>
            <input type="number" min="0.01" max="100" step="0.10" .value=${String(this._editBudget)} @input=${(e: Event) => {
              this._editBudget = Math.max(0.01, parseFloat((e.target as HTMLInputElement).value) || 1.0);
              this._controlsDirty = true;
            }}>
          </div>
          <div class="control-row">
            <div>
              <div class="control-label">Convergence Threshold</div>
              <div class="control-hint">${this._editConvergence.toFixed(2)}</div>
            </div>
            <input type="range" min="0.80" max="1.00" step="0.01" .value=${String(this._editConvergence)} @input=${(e: Event) => {
              this._editConvergence = parseFloat((e.target as HTMLInputElement).value) || 0.95;
              this._controlsDirty = true;
            }}>
          </div>
          ${this._controlsDirty ? html`
            <div class="save-row">
              ${this._saveMsg ? html`<span class="save-msg">${this._saveMsg}</span>` : nothing}
              <fc-btn variant="primary" sm ?disabled=${this._saving} @click=${() => void this._saveSettings()}>
                ${this._saving ? 'Saving\u2026' : 'Save Changes'}
              </fc-btn>
            </div>` : nothing}
        </div>
      </div>

      <div class="section">
        <div class="s-label" style="display:flex;align-items:center;gap:8px">
          Protocols
          <span style="font-weight:400;font-size:8px;color:var(--v-fg-dim);letter-spacing:0">Snapshot data \u2014 refreshes on reconnect</span>
        </div>
        <div class="glass" style="padding:12px">
          ${protocols.map(p => html`
            <div class="proto-row">
              <fc-dot .status=${p.s === 'active' ? 'loaded' : 'pending'} .size=${4}></fc-dot>
              <span class="proto-name">${p.n}</span>
              <span class="proto-desc">${p.d}</span>
              <fc-pill color="var(--v-fg-dim)" sm style="margin-left:auto">${p.s}</fc-pill>
            </div>
          `)}
        </div>
      </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-settings-view': FcSettingsView; }
}
