import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { providerOf, providerColor, formatVram } from '../helpers.js';
import type { LocalModel, CloudEndpoint, CasteDefinition, RuntimeConfig, ModelRegistryEntry, VramInfo } from '../types.js';
import type { CasteRecipePayload } from './caste-editor.js';
import './atoms.js';

@customElement('fc-model-registry')
export class FcModelRegistry extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 860px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .sub { font-size: 10.5px; color: var(--v-fg-muted); margin: 0 0 18px; }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; margin-bottom: 18px; }
    .stat-sub { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .model-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
    .model-card { padding: 0; overflow: hidden; }
    .model-main { padding: 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; }
    .model-info { flex: 1; }
    .model-name { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .model-meta { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); display: flex; gap: 10px; font-feature-settings: 'tnum'; }
    .model-detail { border-top: 1px solid var(--v-border); padding: 12px; background: var(--v-recessed); }
    .detail-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .detail-label { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 2px; font-weight: 600; }
    .detail-value { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg); font-feature-settings: 'tnum'; }
    .ep-card { padding: 12px; }
    .ep-header { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; }
    .ep-name { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .ep-spend { margin-left: auto; font-family: var(--f-mono); font-size: 9.5px; color: var(--v-fg-muted); font-feature-settings: 'tnum'; }
    .ep-note {
      margin-left: 6px; font-size: 10px; color: var(--v-fg-dim);
      font-family: var(--f-mono);
    }
    .models-pills { display: flex; gap: 3px; flex-wrap: wrap; }
    .cascade-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
    .cascade-item { text-align: center; padding: 7px; background: var(--v-void); border-radius: 7px; }
    .cascade-icon { font-size: 13px; margin-bottom: 3px; }
    .cascade-name { font-size: 10px; font-family: var(--f-display); font-weight: 600; color: var(--v-fg); margin-bottom: 1px; }
    .cascade-model { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); word-break: break-all; display: flex; align-items: center; justify-content: center; gap: 2px; }
    .provider-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
    .policy-card { padding: 0; overflow: hidden; }
    .policy-main { padding: 10px 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; }
    .policy-info { flex: 1; }
    .policy-addr { font-family: var(--f-mono); font-size: 12px; font-weight: 600; color: var(--v-fg); }
    .policy-meta { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); display: flex; gap: 10px; font-feature-settings: 'tnum'; }
    .policy-detail { border-top: 1px solid var(--v-border); padding: 12px; background: var(--v-recessed); }
    .policy-field { margin-bottom: 10px; }
    .policy-field:last-child { margin-bottom: 0; }
    .policy-field label {
      display: block; font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 3px;
    }
    .policy-field input {
      width: 100%; box-sizing: border-box; padding: 5px 8px;
      background: var(--v-surface); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono);
      font-size: 11px; outline: none; transition: border-color 0.15s;
    }
    .policy-field input:focus { border-color: rgba(232,88,26,0.3); }
    .policy-field .hint { font-size: 8px; color: var(--v-fg-dim); font-family: var(--f-mono); margin-top: 2px; }
    .policy-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 10px; }
    .policy-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .provider-group { margin-bottom: 8px; }
    .provider-header {
      display: flex; align-items: center; gap: 8px; padding: 8px 12px;
      cursor: pointer; border-radius: 8px; transition: background 0.15s;
    }
    .provider-header:hover { background: rgba(255,255,255,0.02); }
    .provider-name {
      font-family: var(--f-display); font-size: 13px; font-weight: 700; color: var(--v-fg);
    }
    .provider-summary {
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-left: auto; display: flex; gap: 10px; align-items: center;
    }
    .provider-models { padding: 0 6px 6px; }
    .provider-group.dimmed { opacity: 0.5; }
    .provider-group.dimmed .provider-header { cursor: default; }
  `];

  @property({ type: Array }) localModels: LocalModel[] = [];
  @property({ type: Array }) cloudEndpoints: CloudEndpoint[] = [];
  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @state() private expanded: string | null = null;
  @state() private policyExpanded: string | null = null;
  @state() private providerExpanded: Set<string> = new Set();
  @state() private recipes: Record<string, CasteRecipePayload> = {};
  @state() private saving = false;
  @state() private _lastRefreshed: number = 0;
  private _refreshTimer?: ReturnType<typeof setInterval>;

  // Inline edit state for policy fields
  @state() private editMaxOutput = 0;
  @state() private editTimeMul = 1.0;
  @state() private editToolMul = 1.0;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchRecipes();
    this._lastRefreshed = Date.now();
    // Periodic refresh every 60s to keep model/protocol state fresh
    this._refreshTimer = setInterval(() => {
      this._lastRefreshed = Date.now();
      void this._fetchRecipes();
    }, 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._refreshTimer) clearInterval(this._refreshTimer);
  }

  private _freshnessLabel(): string {
    if (!this._lastRefreshed) return '';
    const ago = Math.floor((Date.now() - this._lastRefreshed) / 1000);
    if (ago < 5) return 'just now';
    if (ago < 60) return `${ago}s ago`;
    return `${Math.floor(ago / 60)}m ago`;
  }

  render() {
    const knownVram = this.localModels.filter(m => m.vram != null);
    const totalVramUsed = knownVram.reduce((a, m) => a + (m.vram?.usedMb ?? 0), 0);
    const totalVramTotal = knownVram.reduce((a, m) => a + (m.vram?.totalMb ?? 0), 0);
    const vramKnown = knownVram.length > 0;
    const connected = this.cloudEndpoints.filter(c => c.status === 'connected');
    const defaults = this.runtimeConfig?.models?.defaults;
    const registry = this.runtimeConfig?.models?.registry ?? [];
    const totalSlots = this.localModels.reduce((a, m) => a + m.slotsTotal, 0);
    const idleSlots = this.localModels.reduce((a, m) => a + m.slotsIdle, 0);

    return html`
      <div class="title-row">
        <h2><fc-gradient-text>Model Registry</fc-gradient-text></h2>
        <span style="margin-left:auto;font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim)">Updated ${this._freshnessLabel()}</span>
      </div>
      <p class="sub"><span style="font-family:var(--f-mono);color:var(--v-fg)">provider/model-name</span> \u00B7 nullable cascade: thread \u2192 workspace \u2192 system</p>

      <div class="summary-grid">
        ${totalSlots > 0 ? html`<div class="glass" style="padding:10px">
          <fc-meter label="Slot Utilization" .value=${totalSlots - idleSlots} .max=${totalSlots} unit=" slots" color="#A78BFA"></fc-meter>
          <div class="stat-sub">${idleSlots}/${totalSlots} idle \u00B7 llama.cpp</div>
        </div>` : nothing}
        ${vramKnown ? html`<div class="glass" style="padding:10px">
          <fc-meter label="GPU VRAM" .value=${totalVramUsed} .max=${totalVramTotal} unit=" MiB" color="#A78BFA"></fc-meter>
          <div class="stat-sub">${formatVram(totalVramUsed)} / ${formatVram(totalVramTotal)} used</div>
        </div>` : nothing}
        ${connected.filter(c => c.spend > 0 || c.limit > 0).map(c => html`
          <div class="glass" style="padding:10px">
            <fc-meter label="${c.provider}" .value=${c.spend} .max=${c.limit} unit="$" color="var(--v-secondary)"></fc-meter>
            <div class="stat-sub">daily cap $${c.limit.toFixed(2)}</div>
          </div>
        `)}
      </div>

      <div class="s-label">Model Policy</div>
      <div class="model-list">
        ${this._renderGroupedRegistry(registry)}
      </div>

      <div class="s-label">Local Models</div>
      <div class="model-list">
        ${this.localModels.map(m => {
          const exp = this.expanded === m.id;
          const slotsLabel = m.slotsTotal > 0
            ? `${m.slotsIdle}/${m.slotsTotal} idle`
            : '\u2014';
          return html`
            <div class="glass model-card">
              <div class="model-main" @click=${() => { this.expanded = exp ? null : m.id; }}>
                <fc-dot .status=${m.status} .size=${7}></fc-dot>
                <div class="model-info">
                  <div style="display:flex;align-items:center;gap:6px;margin-bottom:1px">
                    <span class="model-name">${m.name}</span>
                    <fc-pill color="var(--v-success)" sm>${m.status}</fc-pill>
                  </div>
                  <div class="model-meta">
                    <span><span class="provider-dot" style="background:${providerColor(m.name)}"></span> ${m.provider}/${m.id}</span>
                    <span>ctx ${m.configuredCtx && m.configuredCtx !== m.ctx ? `${m.ctx.toLocaleString()} effective (${m.configuredCtx.toLocaleString()} configured)` : m.ctx.toLocaleString()}</span>
                    <span>slots ${slotsLabel}</span>
                    ${m.vram != null
                      ? html`<span style="color:var(--v-purple)">${formatVram(m.vram.usedMb)} / ${formatVram(m.vram.totalMb)}</span>`
                      : nothing}
                  </div>
                </div>
                <fc-btn variant="ghost" sm>${exp ? '\u25B2' : '\u25BC'}</fc-btn>
              </div>
              ${exp ? html`
                <div class="model-detail">
                  <div class="detail-grid">
                    ${[
                      { l: 'Slots', v: m.slotsTotal > 0 ? `${m.slotsIdle} idle / ${m.slotsProcessing} busy / ${m.slotsTotal} total` : 'unavailable' },
                      { l: 'Context', v: m.configuredCtx && m.configuredCtx !== m.ctx ? `${m.ctx.toLocaleString()} effective (configured ${m.configuredCtx.toLocaleString()}). Reduced by llama.cpp auto-sizing to fit model + KV cache in available VRAM. Increase GPU memory or reduce model size to recover headroom.` : m.maxCtx.toLocaleString() },
                      { l: 'Backend', v: m.backend },
                      { l: 'VRAM', v: m.vram != null ? `${formatVram(m.vram.usedMb)} / ${formatVram(m.vram.totalMb)}` : 'no probe source' },
                    ].map(({ l, v }) => html`<div><div class="detail-label">${l}</div><div class="detail-value">${v}</div></div>`)}
                  </div>
                  ${m.slotDetails && m.slotDetails.length > 0 ? html`
                    <div style="margin-top:10px">
                      <div class="detail-label" style="margin-bottom:4px">Slot Details</div>
                      ${m.slotDetails.map(s => html`
                        <div style="font-size:9.5px;font-family:var(--f-mono);color:var(--v-fg-dim);display:flex;gap:12px;padding:2px 0">
                          <span>slot ${s.id}</span>
                          <span>${s.state === 0 ? 'idle' : 'processing'}</span>
                          <span>ctx ${s.nCtx.toLocaleString()}</span>
                          <span>${s.promptTokens} prompt tokens</span>
                        </div>
                      `)}
                    </div>
                  ` : nothing}
                </div>` : nothing}
            </div>`;
        })}
      </div>

      <div class="s-label">Cloud Endpoints</div>
      <div class="model-list">
        ${this.cloudEndpoints.map(c => html`
          <div class="glass ep-card">
            <div class="ep-header">
              <fc-dot .status=${c.status} .size=${6}></fc-dot>
              <span class="ep-name">${c.provider}</span>
              <fc-pill .color=${c.status === 'connected' ? 'var(--v-success)' : c.status === 'cooldown' ? 'var(--v-warn)' : 'var(--v-danger)'} sm>${c.status}</fc-pill>
              ${c.status === 'no_key'
                ? html`<span class="ep-note">Set ${c.provider.toUpperCase()}_API_KEY in .env and restart FormicOS</span>`
                : c.status === 'cooldown'
                ? html`<span class="ep-note">Provider in cooldown after repeated failures</span>`
                : nothing}
              ${c.status === 'connected'
                ? (c.spend === 0 && c.limit === 0
                  ? html`<span class="ep-spend" style="color:var(--v-fg-dim)">spend not tracked</span>`
                  : html`<span class="ep-spend">$${c.spend.toFixed(2)} / $${c.limit.toFixed(2)}</span>`)
                : nothing}
            </div>
            <div class="models-pills">${c.models.map(m => html`<fc-pill .color=${c.status === 'connected' ? 'var(--v-fg)' : 'var(--v-fg-dim)'} sm>${m}</fc-pill>`)}</div>
            ${c.status === 'connected' && (c.spend > 0 || c.limit > 0)
              ? html`<div style="margin-top:8px"><fc-meter label="Daily" .value=${c.spend} .max=${c.limit} unit="$" color="var(--v-secondary)"></fc-meter></div>`
              : c.status === 'connected'
              ? html`<div style="margin-top:8px;font-size:9.5px;font-family:var(--f-mono);color:var(--v-fg-dim)">Spend tracking not configured</div>`
              : nothing}
          </div>
        `)}
      </div>

      ${defaults && this.castes.length > 0 ? html`
        <div class="s-label">Default Routing Cascade</div>
        <div class="glass" style="padding:12px">
          <div class="cascade-grid">
            ${this.castes.map(c => {
              const model = (defaults as any)[c.id] ?? 'unset';
              const recipe = this.recipes[c.id];
              return html`
              <div class="cascade-item" style="border:1px solid ${c.color}12">
                <div class="cascade-icon" style="filter:drop-shadow(0 0 3px ${c.color}25)">${c.icon}</div>
                <div class="cascade-name">${c.name}</div>
                <div class="cascade-model">
                  <span class="provider-dot" style="background:${providerColor(model)}"></span>${model}
                </div>
                ${recipe?.tier_models ? html`
                  <div style="margin-top:6px;display:flex;flex-direction:column;gap:3px">
                    ${['flash', 'light', 'standard', 'heavy'].map(tier => {
                      const tierModel = recipe.tier_models[tier] || '\u21B3 cascade';
                      return html`
                        <div style="font-size:8.5px;font-family:var(--f-mono);color:var(--v-fg-dim);display:flex;justify-content:space-between;gap:6px">
                          <span style="text-transform:capitalize">${tier}</span>
                          <span style="color:${recipe.tier_models[tier] ? 'var(--v-fg-muted)' : 'var(--v-fg-dim)'}">${tierModel}</span>
                        </div>
                      `;
                    })}
                  </div>
                ` : nothing}
              </div>`;
            })}
          </div>
        </div>` : nothing}`;
  }

  private _renderGroupedRegistry(registry: ModelRegistryEntry[]) {
    const groups = new Map<string, ModelRegistryEntry[]>();
    for (const m of registry) {
      const provider = providerOf(m.address);
      const list = groups.get(provider) ?? [];
      list.push(m);
      groups.set(provider, list);
    }
    return [...groups.entries()].map(([provider, models]) => {
      const expanded = this.providerExpanded.has(provider);
      const hasKey = models.some(m => m.status === 'available' || m.status === 'loaded');
      const dimmed = !hasKey;
      const statusLabel = hasKey ? 'connected' : 'no_key';
      return html`
        <div class="glass provider-group ${dimmed ? 'dimmed' : ''}">
          <div class="provider-header" @click=${() => { if (!dimmed) this._toggleProvider(provider); }}>
            <span class="provider-dot" style="background:${providerColor(provider + '/x')}"></span>
            <span class="provider-name">${provider}</span>
            <fc-pill .color=${hasKey ? 'var(--v-success)' : 'var(--v-fg-dim)'} sm>${statusLabel}</fc-pill>
            <span class="provider-summary">
              <span>${models.length} model${models.length > 1 ? 's' : ''}</span>
            </span>
            ${!dimmed ? html`<span style="font-size:10px;color:var(--v-fg-dim)">${expanded ? '\u25B2' : '\u25BC'}</span>` : nothing}
          </div>
          ${expanded ? html`
            <div class="provider-models">
              ${models.map(m => this._renderPolicyCard(m))}
            </div>` : nothing}
        </div>`;
    });
  }

  private _toggleProvider(provider: string) {
    const next = new Set(this.providerExpanded);
    if (next.has(provider)) next.delete(provider);
    else next.add(provider);
    this.providerExpanded = next;
  }

  private _renderPolicyCard(m: ModelRegistryEntry) {
    const exp = this.policyExpanded === m.address;
    const primaryLabel = this._policyPrimaryLabel(m);
    return html`
      <div class="glass policy-card">
        <div class="policy-main" @click=${() => this._expandPolicy(m)}>
          <span class="provider-dot" style="background:${providerColor(m.address)}"></span>
          <div class="policy-info">
            <div class="policy-addr">${primaryLabel}</div>
            <div class="policy-meta">
              <span>${m.address}</span>
              <span>${m.provider}</span>
              <span>ctx ${m.contextWindow.toLocaleString()}</span>
              <span>out ${m.maxOutputTokens.toLocaleString()}</span>
              <span>time \u00D7${m.timeMultiplier}</span>
              <span>tools \u00D7${m.toolCallMultiplier}</span>
              <fc-pill .color=${m.status === 'available' || m.status === 'loaded' ? 'var(--v-success)' : m.status === 'no_key' ? 'var(--v-warn)' : 'var(--v-fg-dim)'} sm>${m.status}</fc-pill>
            </div>
          </div>
          <fc-btn variant="ghost" sm>${exp ? '\u25B2' : '\u25BC'}</fc-btn>
        </div>
        ${exp ? html`
          <div class="policy-detail">
            <div class="detail-grid" style="margin-bottom:12px">
              <div><div class="detail-label">Context Window</div><div class="detail-value">${m.contextWindow.toLocaleString()}</div></div>
              <div><div class="detail-label">Tools</div><div class="detail-value">${m.supportsTools ? 'yes' : 'no'}</div></div>
              <div><div class="detail-label">Provider</div><div class="detail-value">${m.provider}</div></div>
            </div>
            <div class="policy-row">
              <div class="policy-field">
                <label>Max Output Tokens</label>
                <input type="number" min="256" max="131072"
                  .value=${String(this.editMaxOutput)}
                  @input=${(e: Event) => {
                    this.editMaxOutput = parseInt((e.target as HTMLInputElement).value, 10) || 4096;
                  }}>
                <div class="hint">Hard cap on LLM output per request</div>
              </div>
              <div class="policy-field">
                <label>Time Multiplier</label>
                <input type="number" step="0.1" min="0.1" max="10"
                  .value=${String(this.editTimeMul)}
                  @input=${(e: Event) => {
                    this.editTimeMul = parseFloat((e.target as HTMLInputElement).value) || 1.0;
                  }}>
                <div class="hint">\u00D7 caste base execution time</div>
              </div>
              <div class="policy-field">
                <label>Tool Call Multiplier</label>
                <input type="number" step="0.1" min="0.1" max="10"
                  .value=${String(this.editToolMul)}
                  @input=${(e: Event) => {
                    this.editToolMul = parseFloat((e.target as HTMLInputElement).value) || 1.0;
                  }}>
                <div class="hint">\u00D7 caste base tool calls/iteration</div>
              </div>
            </div>
            <div class="policy-actions">
              <fc-btn variant="secondary" sm
                @click=${() => { this.policyExpanded = null; }}>Cancel</fc-btn>
              <fc-btn variant="primary" sm
                ?disabled=${this.saving}
                @click=${() => this._savePolicy(m.address)}>
                ${this.saving ? 'Saving\u2026' : 'Save Policy'}
              </fc-btn>
            </div>
          </div>` : nothing}
      </div>`;
  }

  private _policyPrimaryLabel(m: ModelRegistryEntry): string {
    if (m.provider === 'llama-cpp' || m.provider === 'ollama' || m.provider === 'local') {
      const local = this.localModels.find(lm => `${lm.provider}/${lm.id}` === m.address);
      if (local?.name) return local.name;
    }
    return m.address.includes('/') ? m.address.split('/').slice(1).join('/') : m.address;
  }

  private _expandPolicy(m: ModelRegistryEntry) {
    if (this.policyExpanded === m.address) {
      this.policyExpanded = null;
      return;
    }
    this.editMaxOutput = m.maxOutputTokens;
    this.editTimeMul = m.timeMultiplier;
    this.editToolMul = m.toolCallMultiplier;
    this.policyExpanded = m.address;
  }

  private async _savePolicy(address: string) {
    this.saving = true;
    try {
      const resp = await fetch(`/api/v1/models/${encodeURIComponent(address)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_output_tokens: this.editMaxOutput,
          time_multiplier: this.editTimeMul,
          tool_call_multiplier: this.editToolMul,
        }),
      });
      if (resp.ok) {
        this.policyExpanded = null;
        this.dispatchEvent(
          new CustomEvent('policy-saved', { bubbles: true, composed: true }),
        );
      }
    } catch { /* best-effort */ }
    this.saving = false;
  }

  private async _fetchRecipes() {
    try {
      const resp = await fetch('/api/v1/castes');
      if (resp.ok) {
        this.recipes = await resp.json();
      }
    } catch {
      this.recipes = {};
    }
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-model-registry': FcModelRegistry; }
}
