/**
 * Wave 66 T1 + Wave 72.5 T3-T5: Addons management view.
 * Two-column layout: sidebar list with status dots, detail panel.
 * Interactive: tool "Try It" forms, inline config editing, error retry.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { store } from '../state/store.js';
import type { AddonSummary, AddonToolSummary, AddonConfigParam } from '../types.js';
import './atoms.js';

const STATUS_COLORS: Record<string, string> = {
  healthy: '#2DD4A8',
  degraded: '#F5B731',
  error: '#E8581A',
};

@customElement('fc-addons-view')
export class FcAddonsView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; height: 100%; gap: 0; overflow: hidden; }
    .sidebar {
      width: 220px; min-width: 180px; border-right: 1px solid var(--v-border);
      overflow-y: auto; padding: 12px 0;
    }
    .sidebar-item {
      display: flex; align-items: center; gap: 8px; padding: 8px 16px;
      cursor: pointer; font-size: 12px; font-family: var(--f-mono);
      color: var(--v-fg-dim); transition: background 0.1s;
    }
    .sidebar-item:hover { background: rgba(232,88,26,0.04); }
    .sidebar-item.active { background: rgba(232,88,26,0.08); color: var(--v-fg); }
    .status-dot {
      width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    }
    .detail {
      flex: 1; overflow-y: auto; padding: 20px 24px; max-width: 700px;
    }
    .detail h2 {
      font-family: var(--f-display); font-size: 20px; font-weight: 700;
      color: var(--v-fg); margin: 0 0 4px;
    }
    .detail .version {
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 12px;
    }
    .detail .desc {
      font-size: 13px; color: var(--v-fg-dim); margin-bottom: 20px;
      line-height: 1.5;
    }
    .section-title {
      font-size: 10px; font-family: var(--f-mono); text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--v-fg-dim); margin: 16px 0 8px;
    }
    table {
      width: 100%; border-collapse: collapse; font-size: 12px;
      font-family: var(--f-mono);
    }
    th {
      text-align: left; font-weight: 600; color: var(--v-fg-dim);
      padding: 4px 8px; border-bottom: 1px solid var(--v-border);
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
    }
    td {
      padding: 6px 8px; border-bottom: 1px solid var(--v-border-dim, rgba(255,255,255,0.04));
      color: var(--v-fg);
    }
    .trigger-btn {
      font-size: 10px; font-family: var(--f-mono); padding: 2px 10px;
      border-radius: 6px; cursor: pointer; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-accent); transition: all 0.15s;
    }
    .trigger-btn:hover { background: rgba(232,88,26,0.08); }
    .trigger-btn:disabled { opacity: 0.4; cursor: default; }
    .empty {
      display: flex; align-items: center; justify-content: center;
      height: 100%; color: var(--v-fg-dim); font-size: 13px;
      font-family: var(--f-mono);
    }

    /* Track 5: error card */
    .error-card {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 12px; border-radius: 8px;
      background: rgba(232,88,26,0.06); border: 1px solid rgba(232,88,26,0.15);
      margin-bottom: 12px;
    }
    .error-text {
      font-size: 11px; color: #E8581A; font-family: var(--f-mono); flex: 1;
    }

    /* Track 3: try form */
    .try-form {
      padding: 12px; background: rgba(6,6,12,0.5); border-radius: 8px;
      margin: 4px 0;
    }
    .try-field { margin-bottom: 8px; }
    .try-field label {
      display: block; font-size: 10px; font-family: var(--f-mono);
      color: var(--v-fg-dim); margin-bottom: 2px;
    }
    .try-field input, .try-field textarea {
      width: 100%; box-sizing: border-box; padding: 5px 8px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px;
    }
    .try-field .hint {
      font-size: 10px; color: var(--v-fg-dim); opacity: 0.6; margin-top: 2px;
    }
    .try-result {
      margin-top: 8px; padding: 8px; background: var(--v-recessed);
      border-radius: 6px; font-family: var(--f-mono); font-size: 11px;
      white-space: pre-wrap; word-break: break-word; color: var(--v-fg);
      max-height: 200px; overflow-y: auto;
    }

    /* Track 4: config form */
    .config-form { margin-top: 8px; }
    .config-field { margin-bottom: 10px; }
    .config-field label {
      display: block; font-size: 10px; font-family: var(--f-mono);
      color: var(--v-fg-dim); margin-bottom: 2px;
    }
    .config-field input, .config-field select, .config-field textarea {
      width: 100%; box-sizing: border-box; padding: 5px 8px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px;
    }
    .config-field input[type="checkbox"] {
      width: auto; margin-right: 6px;
    }
    .config-saved {
      font-size: 10px; color: #2DD4A8; font-family: var(--f-mono);
      margin-left: 8px;
    }

    /* Wave 73 Track 2: search filter */
    .addon-search {
      width: 100%; box-sizing: border-box; padding: 6px 10px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px; outline: none; margin: 0 16px 8px; width: calc(100% - 32px);
    }
    .addon-search:focus { border-color: rgba(232,88,26,0.3); }
    .addon-search::placeholder { color: var(--v-fg-dim); }

    /* Wave 73 Track 3: health summary */
    .health-summary {
      display: flex; gap: 12px; padding: 8px 12px;
      font-family: var(--f-mono); font-size: 10px;
      color: var(--v-fg-dim); margin-bottom: 12px;
      border-bottom: 1px solid var(--v-border);
    }
    .health-stat { display: flex; align-items: center; gap: 3px; }
    .health-stat.warn { color: var(--v-warn, #f59e0b); }
    .health-stat.error { color: var(--v-danger, #ef4444); }
  `];

  @state() private _selected: string | null = null;
  @state() private _addons: AddonSummary[] = [];
  @state() private _searchQuery = '';
  @state() private _triggerStatus: string = '';

  // Track 3: Try It state
  @state() private _tryingTool: string | null = null;
  @state() private _tryInputs: Record<string, any> = {};
  @state() private _tryResult: string = '';
  @state() private _tryLoading = false;

  // Track 4: Config state
  @state() private _configValues: Record<string, any> = {};
  @state() private _configLoading = false;
  @state() private _configSaving = false;
  @state() private _configSaved = false;
  @state() private _lastConfigAddon: string = '';

  private _unsub?: () => void;

  connectedCallback(): void {
    super.connectedCallback();
    this._unsub = store.subscribe(() => {
      this._addons = store.state.addons;
      this.requestUpdate();
    });
    this._addons = store.state.addons;
    if (this._addons.length > 0 && !this._selected) {
      this._selected = this._addons[0].name;
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._unsub?.();
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has('_selected') && this._selected) {
      const addon = this._selectedAddon;
      if (addon && addon.config?.length > 0 && this._lastConfigAddon !== addon.name) {
        this._lastConfigAddon = addon.name;
        this._fetchConfig(addon.name);
      }
      // Reset try state on addon change
      this._tryingTool = null;
      this._tryResult = '';
      this._tryInputs = {};
    }
  }

  private get _selectedAddon(): AddonSummary | undefined {
    return this._addons.find(a => a.name === this._selected);
  }

  render() {
    if (this._addons.length === 0) {
      return html`<div class="empty">No addons installed</div>`;
    }
    const q = this._searchQuery.toLowerCase();
    const filtered = q
      ? this._addons.filter(a =>
          a.name.toLowerCase().includes(q)
          || a.description.toLowerCase().includes(q))
      : this._addons;

    return html`
      <div class="sidebar">
        <input class="addon-search" type="text" placeholder="Filter addons..."
          .value=${this._searchQuery}
          @input=${(e: Event) => { this._searchQuery = (e.target as HTMLInputElement).value; }}>
        ${filtered.map(a => html`
          <div
            class="sidebar-item ${this._selected === a.name ? 'active' : ''}"
            @click=${() => { this._selected = a.name; }}
          >
            <span class="status-dot" style="background:${STATUS_COLORS[a.status] ?? '#888'}"></span>
            ${a.name}
            ${a.disabled ? html`<span style="font-size:9px;color:var(--v-fg-dim);margin-left:auto">off</span>` : nothing}
          </div>
        `)}
      </div>
      <div class="detail">
        ${this._renderHealthSummary(this._addons)}
        ${this._selectedAddon ? this._renderDetail(this._selectedAddon) : nothing}
      </div>
    `;
  }

  private _renderHealthSummary(addons: AddonSummary[]) {
    const total = addons.length;
    const disabled = addons.filter(a => a.disabled).length;
    const errored = addons.filter(a => a.status === 'error').length;
    const totalTools = addons.reduce((sum, a) => sum + a.tools.length, 0);
    const totalCalls = addons.reduce(
      (sum, a) => sum + a.tools.reduce((s, t) => s + t.callCount, 0), 0,
    );
    return html`
      <div class="health-summary">
        <span class="health-stat">${total} addons</span>
        <span class="health-stat">${totalTools} tools</span>
        <span class="health-stat">${totalCalls} calls</span>
        ${disabled > 0
          ? html`<span class="health-stat warn">${disabled} disabled</span>`
          : nothing}
        ${errored > 0
          ? html`<span class="health-stat error">${errored} errors</span>`
          : nothing}
      </div>
    `;
  }

  private _renderDetail(addon: AddonSummary) {
    return html`
      <h2>${addon.name}</h2>
      <div class="version">v${addon.version || '0.0.0'}
        <span class="status-dot" style="background:${STATUS_COLORS[addon.status] ?? '#888'};display:inline-block;vertical-align:middle;margin-left:8px"></span>
        ${addon.status}
      </div>
      ${addon.description ? html`<div class="desc">${addon.description}</div>` : nothing}

      <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;font-family:var(--f-mono);color:var(--v-fg-dim)">
          <input type="checkbox"
            .checked=${!addon.disabled}
            @change=${async (e: Event) => {
              const enabled = (e.target as HTMLInputElement).checked;
              try {
                await fetch(`/api/v1/addons/${addon.name}/toggle`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    disabled: !enabled,
                    workspace_id: store.state.tree?.[0]?.id ?? '',
                  }),
                });
              } catch { /* best-effort */ }
            }}>
          ${addon.disabled ? 'Disabled' : 'Enabled'}
        </label>
      </div>

      ${addon.lastError ? html`
        <div class="error-card">
          <span class="error-text">${addon.lastError}</span>
          <button class="trigger-btn" @click=${() => this._fireTrigger(addon.name)}>Retry</button>
        </div>
      ` : nothing}

      ${addon.tools.length > 0 ? html`
        <div class="section-title">Tools</div>
        <table>
          <tr><th>Name</th><th>Description</th><th>Calls</th><th></th></tr>
          ${addon.tools.map(t => html`
            <tr>
              <td>${t.name}</td>
              <td style="color:var(--v-fg-dim)">${t.description}</td>
              <td>${t.callCount}</td>
              <td>
                <button class="trigger-btn"
                  @click=${() => {
                    if (this._tryingTool === t.name) {
                      this._tryingTool = null;
                    } else {
                      this._tryingTool = t.name;
                      this._tryResult = '';
                      this._tryInputs = {};
                    }
                  }}>
                  ${this._tryingTool === t.name ? 'Close' : 'Try'}
                </button>
              </td>
            </tr>
            ${this._tryingTool === t.name ? html`
              <tr><td colspan="4">${this._renderTryForm(addon, t)}</td></tr>
            ` : nothing}
          `)}
        </table>
      ` : nothing}

      ${addon.handlers.length > 0 ? html`
        <div class="section-title">Event Handlers</div>
        <table>
          <tr><th>Event</th><th>Last Fired</th><th>Errors</th></tr>
          ${addon.handlers.map(h => html`
            <tr>
              <td>${h.event}</td>
              <td style="color:var(--v-fg-dim)">${h.lastFired ?? 'never'}</td>
              <td>${h.errorCount > 0
                ? html`<span class="error-text">${h.errorCount}</span>`
                : '0'}</td>
            </tr>
          `)}
        </table>
      ` : nothing}

      ${addon.triggers.length > 0 ? html`
        <div class="section-title">Triggers</div>
        <table>
          <tr><th>Type</th><th>Schedule</th><th></th></tr>
          ${addon.triggers.map(t => html`
            <tr>
              <td>${t.type}</td>
              <td style="color:var(--v-fg-dim)">${t.schedule || '-'}</td>
              <td>${t.type === 'manual' ? html`
                <button
                  class="trigger-btn"
                  @click=${() => this._fireTrigger(addon.name)}
                >Trigger Now</button>
              ` : nothing}</td>
            </tr>
          `)}
        </table>
      ` : nothing}

      ${this._triggerStatus ? html`
        <div style="margin-top:12px;font-size:11px;font-family:var(--f-mono);color:var(--v-fg-dim)">
          ${this._triggerStatus}
        </div>
      ` : nothing}

      ${this._renderConfigSection(addon)}
    `;
  }

  // ---- Track 3: Try It form ----

  private _renderTryForm(addon: AddonSummary, tool: AddonToolSummary) {
    const props = tool.parameters?.properties as Record<string, any> | undefined;
    const hasProps = props && Object.keys(props).length > 0;

    return html`
      <div class="try-form">
        ${hasProps ? Object.entries(props!).map(([key, schema]) => html`
          <div class="try-field">
            <label>${key}</label>
            ${this._renderParamInput(key, schema as Record<string, any>)}
            ${(schema as any)?.description
              ? html`<div class="hint">${(schema as any).description}</div>`
              : nothing}
          </div>
        `) : html`<div style="font-size:11px;color:var(--v-fg-dim);margin-bottom:8px">
          No parameters — runs with empty inputs.
        </div>`}
        <button class="trigger-btn" ?disabled=${this._tryLoading}
          @click=${() => this._runTryTool(addon, tool)}>
          ${this._tryLoading ? 'Running...' : 'Run'}
        </button>
        ${this._tryResult ? html`
          <div class="try-result">${this._tryResult}</div>
        ` : nothing}
      </div>
    `;
  }

  private _renderParamInput(key: string, schema: Record<string, any>) {
    const type = schema?.type ?? 'string';
    const val = this._tryInputs[key] ?? '';

    if (type === 'boolean') {
      return html`<input type="checkbox" .checked=${!!val}
        @change=${(e: Event) => {
          this._tryInputs = { ...this._tryInputs, [key]: (e.target as HTMLInputElement).checked };
        }}>`;
    }
    if (type === 'integer' || type === 'number') {
      return html`<input type="number" .value=${String(val)}
        @input=${(e: Event) => {
          this._tryInputs = { ...this._tryInputs, [key]: Number((e.target as HTMLInputElement).value) };
        }}>`;
    }
    if (type === 'array' || type === 'object') {
      return html`<textarea rows="3" .value=${typeof val === 'string' ? val : JSON.stringify(val, null, 2)}
        placeholder="Enter JSON"
        @input=${(e: Event) => {
          const raw = (e.target as HTMLTextAreaElement).value;
          try { this._tryInputs = { ...this._tryInputs, [key]: JSON.parse(raw) }; }
          catch { this._tryInputs = { ...this._tryInputs, [key]: raw }; }
        }}></textarea>`;
    }
    // Default: string
    return html`<input type="text" .value=${String(val)}
      @input=${(e: Event) => {
        this._tryInputs = { ...this._tryInputs, [key]: (e.target as HTMLInputElement).value };
      }}>`;
  }

  private async _runTryTool(addon: AddonSummary, tool: AddonToolSummary) {
    this._tryLoading = true;
    this._tryResult = '';
    try {
      const resp = await fetch(`/api/v1/addons/${addon.name}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          handler: tool.handler,
          inputs: this._tryInputs,
          workspace_id: store.state.tree?.[0]?.id ?? '',
        }),
      });
      const data = await resp.json();
      this._tryResult = resp.ok
        ? (data.result ?? 'ok')
        : `Error: ${data.error ?? resp.statusText}`;
    } catch (e) {
      this._tryResult = `Error: ${e}`;
    }
    this._tryLoading = false;
  }

  // ---- Track 4: Config editing ----

  private _renderConfigSection(addon: AddonSummary) {
    if (!addon.config || addon.config.length === 0) return nothing;
    return html`
      <div class="section-title">Configuration</div>
      <div class="config-form">
        ${addon.config.map(c => this._renderConfigField(c))}
        <button class="trigger-btn" ?disabled=${this._configSaving}
          @click=${() => this._saveConfig(addon.name)}>
          ${this._configSaving ? 'Saving...' : 'Save Config'}
        </button>
        ${this._configSaved ? html`<span class="config-saved">Saved</span>` : nothing}
      </div>
    `;
  }

  private _renderConfigField(param: AddonConfigParam) {
    const label = param.label || param.key;
    const val = this._configValues[param.key] ?? param.default;

    if (param.type === 'boolean') {
      return html`
        <div class="config-field">
          <label>
            <input type="checkbox" .checked=${!!val}
              @change=${(e: Event) => {
                this._configValues = { ...this._configValues, [param.key]: (e.target as HTMLInputElement).checked };
              }}>
            ${label}
          </label>
        </div>`;
    }
    if (param.type === 'select') {
      return html`
        <div class="config-field">
          <label>${label}</label>
          <select .value=${String(val ?? '')}
            @change=${(e: Event) => {
              this._configValues = { ...this._configValues, [param.key]: (e.target as HTMLSelectElement).value };
            }}>
            ${(param.options ?? []).map(o => html`
              <option value=${o} ?selected=${o === String(val)}>${o}</option>
            `)}
          </select>
        </div>`;
    }
    if (param.type === 'integer') {
      return html`
        <div class="config-field">
          <label>${label}</label>
          <input type="number" .value=${String(val ?? '')}
            @input=${(e: Event) => {
              this._configValues = { ...this._configValues, [param.key]: Number((e.target as HTMLInputElement).value) };
            }}>
        </div>`;
    }
    if (param.type === 'cron') {
      return html`
        <div class="config-field">
          <label>${label}</label>
          <input type="text" .value=${String(val ?? '')} placeholder="0 3 * * *"
            @input=${(e: Event) => {
              this._configValues = { ...this._configValues, [param.key]: (e.target as HTMLInputElement).value };
            }}>
        </div>`;
    }
    // Default: string
    return html`
      <div class="config-field">
        <label>${label}</label>
        <input type="text" .value=${String(val ?? '')}
          @input=${(e: Event) => {
            this._configValues = { ...this._configValues, [param.key]: (e.target as HTMLInputElement).value };
          }}>
      </div>`;
  }

  private async _fetchConfig(addonName: string) {
    this._configLoading = true;
    this._configValues = {};
    try {
      const wsId = store.state.tree?.[0]?.id ?? '';
      const resp = await fetch(
        `/api/v1/addons/${addonName}/config?workspace_id=${encodeURIComponent(wsId)}`,
      );
      if (resp.ok) {
        const data = await resp.json();
        this._configValues = data.values ?? {};
      }
    } catch { /* ignore */ }
    this._configLoading = false;
  }

  private async _saveConfig(addonName: string) {
    this._configSaving = true;
    this._configSaved = false;
    try {
      await fetch(`/api/v1/addons/${addonName}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: store.state.tree?.[0]?.id ?? '',
          values: this._configValues,
        }),
      });
      this._configSaved = true;
      setTimeout(() => { this._configSaved = false; }, 2000);
    } catch { /* ignore */ }
    this._configSaving = false;
  }

  // ---- Trigger Now ----

  private async _fireTrigger(addonName: string) {
    this._triggerStatus = 'Triggering...';
    try {
      const addon = this._addons.find(a => a.name === addonName);
      const manualTrigger = addon?.triggers.find(t => t.type === 'manual');
      const resp = await fetch(`/api/v1/addons/${addonName}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          handler: manualTrigger?.handler ?? '',
          workspace_id: store.state.tree?.[0]?.id ?? '',
        }),
      });
      const data = await resp.json();
      if (resp.ok) {
        this._triggerStatus = `Triggered: ${data.result ?? 'ok'}`;
      } else {
        this._triggerStatus = `Error: ${data.error ?? resp.statusText}`;
      }
    } catch (e) {
      this._triggerStatus = `Error: ${e}`;
    }
  }
}
