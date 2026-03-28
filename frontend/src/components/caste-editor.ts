import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { RuntimeConfig } from '../types.js';
import './atoms.js';

/** Matches CasteRecipe from the backend (model_override omitted — deprecated). */
export interface CasteRecipePayload {
  name: string;
  description: string;
  system_prompt: string;
  temperature: number;
  tools: string[];
  max_tokens: number;
  max_iterations: number;
  max_execution_time_s: number;
  base_tool_calls_per_iteration: number;
  tier_models: Record<string, string>;
}

const TIERS = ['flash', 'light', 'standard', 'heavy'] as const;

const KNOWN_TOOLS = [
  'memory_search', 'memory_write', 'code_execute',
  'spawn_colony', 'get_status', 'kill_colony',
];

@customElement('fc-caste-editor')
export class FcCasteEditor extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .editor-title {
      font-family: var(--f-display); font-size: 18px; font-weight: 700;
      color: var(--v-fg); margin: 0 0 16px;
    }
    .field { margin-bottom: 12px; }
    .field-label {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); letter-spacing: 0.14em;
      text-transform: uppercase; margin-bottom: 4px;
    }
    input, textarea, select {
      width: 100%; box-sizing: border-box; padding: 7px 10px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 7px; color: var(--v-fg); font-family: var(--f-body);
      font-size: 12px; outline: none; transition: border-color 0.15s;
    }
    input:focus, textarea:focus, select:focus {
      border-color: rgba(232,88,26,0.3);
    }
    textarea { resize: vertical; min-height: 80px; font-family: var(--f-mono); font-size: 11px; }
    .inline-row { display: flex; gap: 10px; }
    .inline-row .field { flex: 1; }
    .inline-three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .tools-list { display: flex; flex-wrap: wrap; gap: 4px; }
    .tool-chip {
      display: flex; align-items: center; gap: 3px; padding: 2px 8px;
      border-radius: 6px; font-size: 9px; font-family: var(--f-mono);
      cursor: pointer; transition: all 0.15s; user-select: none;
      border: 1px solid var(--v-border); color: var(--v-fg-dim);
    }
    .tool-chip.active {
      background: rgba(45,212,168,0.08); border-color: rgba(45,212,168,0.2);
      color: var(--v-success);
    }
    .tier-row {
      display: flex; align-items: center; gap: 8px; padding: 5px 0;
      border-bottom: 1px solid var(--v-border);
    }
    .tier-label {
      font-size: 10px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-muted); width: 65px; text-transform: capitalize;
    }
    .tier-input {
      flex: 1; padding: 4px 8px; font-size: 10px; font-family: var(--f-mono);
    }
    .tier-hint {
      font-size: 8px; color: var(--v-fg-dim); font-family: var(--f-mono);
    }
    .actions {
      display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;
    }
    .caste-id-note {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 12px;
    }
  `];

  @property({ type: String }) casteId = '';
  @property({ type: Object }) recipe: CasteRecipePayload | null = null;
  @property({ type: Boolean }) isNew = false;
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;

  @state() private _id = '';
  @state() private name = '';
  @state() private description = '';
  @state() private systemPrompt = '';
  @state() private temperature = 0.0;
  @state() private tools: string[] = [];
  @state() private maxTokens = 8192;
  @state() private maxIterations = 5;
  @state() private maxExecutionTimeS = 120;
  @state() private baseToolCalls = 10;
  @state() private tierModels: Record<string, string> = {};
  @state() private saving = false;

  connectedCallback() {
    super.connectedCallback();
    this._populate();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('recipe') || changed.has('casteId')) {
      this._populate();
    }
  }

  private _populate() {
    const r = this.recipe;
    if (r) {
      this._id = this.casteId;
      this.name = r.name;
      this.description = r.description;
      this.systemPrompt = r.system_prompt;
      this.temperature = r.temperature;
      this.tools = [...r.tools];
      this.maxTokens = r.max_tokens;
      this.maxIterations = r.max_iterations;
      this.maxExecutionTimeS = r.max_execution_time_s;
      this.baseToolCalls = r.base_tool_calls_per_iteration ?? 10;
      this.tierModels = { ...r.tier_models };
    } else {
      this._id = '';
      this.name = '';
      this.description = '';
      this.systemPrompt = '';
      this.temperature = 0.0;
      this.tools = [];
      this.maxTokens = 8192;
      this.maxIterations = 5;
      this.maxExecutionTimeS = 120;
      this.baseToolCalls = 10;
      this.tierModels = {};
    }
  }

  render() {
    const title = this.isNew ? 'New Caste' : `Edit ${this.name || 'Caste'}`;
    const casteKey = this.isNew ? this._id : this.casteId;
    const defaults = this.runtimeConfig?.models?.defaults as Record<string, string> | undefined;
    const cascadeDefault = casteKey ? defaults?.[casteKey] ?? '' : '';
    const availableModels = this._availableModels();

    return html`
      <div class="editor-title">
        <fc-gradient-text>${title}</fc-gradient-text>
      </div>

      ${this.isNew ? html`
        <div class="field">
          <div class="field-label">Caste ID (lowercase, no spaces)</div>
          <input type="text" .value=${this._id} placeholder="e.g. debugger"
            @input=${(e: Event) => {
              this._id = (e.target as HTMLInputElement).value
                .toLowerCase().replace(/[^a-z0-9_]/g, '');
            }}>
        </div>
      ` : html`
        <div class="caste-id-note">caste: ${this.casteId}</div>
      `}

      <div class="inline-row">
        <div class="field">
          <div class="field-label">Name</div>
          <input type="text" .value=${this.name} placeholder="Display name"
            @input=${(e: Event) => {
              this.name = (e.target as HTMLInputElement).value;
            }}>
        </div>
        <div class="field">
          <div class="field-label">Temperature</div>
          <input type="number" step="0.1" min="0" max="2"
            .value=${String(this.temperature)}
            @input=${(e: Event) => {
              this.temperature =
                parseFloat((e.target as HTMLInputElement).value) || 0;
            }}>
        </div>
      </div>

      <div class="field">
        <div class="field-label">Description</div>
        <input type="text" .value=${this.description}
          @input=${(e: Event) => {
            this.description = (e.target as HTMLInputElement).value;
          }}>
      </div>

      <div class="field">
        <div class="field-label">System Prompt</div>
        <textarea rows="6" .value=${this.systemPrompt}
          @input=${(e: Event) => {
            this.systemPrompt = (e.target as HTMLTextAreaElement).value;
          }}></textarea>
      </div>

      <div class="field">
        <div class="field-label">Tools</div>
        <div class="tools-list">
          ${KNOWN_TOOLS.map(t => html`
            <span class="tool-chip ${this.tools.includes(t) ? 'active' : ''}"
              @click=${() => this._toggleTool(t)}>${t}</span>
          `)}
        </div>
      </div>

      <div class="inline-three">
        <div class="field">
          <div class="field-label">Max Iterations</div>
          <input type="number" min="1" max="50"
            .value=${String(this.maxIterations)}
            @input=${(e: Event) => {
              this.maxIterations =
                parseInt((e.target as HTMLInputElement).value, 10) || 5;
            }}>
        </div>
        <div class="field">
          <div class="field-label">Base Time (s)</div>
          <input type="number" min="10" max="600"
            .value=${String(this.maxExecutionTimeS)}
            @input=${(e: Event) => {
              this.maxExecutionTimeS =
                parseInt((e.target as HTMLInputElement).value, 10) || 120;
            }}>
          <div class="tier-hint">\u00D7 model time multiplier at runtime</div>
        </div>
        <div class="field">
          <div class="field-label">Base Tool Calls</div>
          <input type="number" min="1" max="100"
            .value=${String(this.baseToolCalls)}
            @input=${(e: Event) => {
              this.baseToolCalls =
                parseInt((e.target as HTMLInputElement).value, 10) || 10;
            }}>
          <div class="tier-hint">\u00D7 model tool multiplier at runtime</div>
        </div>
      </div>

      <div class="field">
        <div class="field-label">Max Tokens (context assembly)</div>
        <input type="number" min="256" max="32768"
          .value=${String(this.maxTokens)}
          @input=${(e: Event) => {
            this.maxTokens =
              parseInt((e.target as HTMLInputElement).value, 10) || 8192;
          }}>
        <div class="tier-hint">Legacy fallback for context assembly. Output cap is set per model in the Models tab.</div>
      </div>

      <div class="field">
        <div class="field-label">Tier Model Defaults</div>
        <div class="tier-hint">
          Recipe defaults per tier. Blank = uses workspace or system cascade.
          Explicit colony assignments always take priority.
        </div>
        ${TIERS.map(tier => html`
          <div class="tier-row">
            <span class="tier-label">${tier}</span>
            <select class="tier-input"
              .value=${this.tierModels[tier] ?? ''}
              @change=${(e: Event) => {
                const val = (e.target as HTMLSelectElement).value.trim();
                this.tierModels = { ...this.tierModels };
                if (val) {
                  this.tierModels[tier] = val;
                } else {
                  delete this.tierModels[tier];
                }
              }}>
              <option value="">Use cascade${cascadeDefault ? ` (${cascadeDefault})` : ''}</option>
              ${availableModels.map(model => html`
                <option value=${model}>${model}</option>
              `)}
            </select>
          </div>
        `)}
        ${cascadeDefault ? html`
          <div class="tier-hint" style="margin-top:8px">
            Cascade default for this caste: ${cascadeDefault}
          </div>
        ` : nothing}
      </div>

      <div class="field">
        <div class="field-label">Available Models</div>
        <div class="tools-list" style="margin-top:6px">
          ${availableModels.map(model => html`
            <span class="tool-chip active" style="cursor:default">${model}</span>
          `)}
          ${availableModels.length === 0 ? html`
            <span class="tier-hint">No models found in runtime config.</span>
          ` : nothing}
        </div>
      </div>

      <div class="actions">
        <fc-btn variant="secondary" sm
          @click=${() => this._fire('cancel', null)}>Cancel</fc-btn>
        <fc-btn variant="primary" sm
          ?disabled=${this.saving || !this.name.trim() || (this.isNew && !this._id)}
          @click=${() => this._save()}>
          ${this.saving ? 'Saving\u2026' : this.isNew ? 'Create Caste' : 'Save Changes'}
        </fc-btn>
      </div>
    `;
  }

  private _toggleTool(tool: string) {
    if (this.tools.includes(tool)) {
      this.tools = this.tools.filter(t => t !== tool);
    } else {
      this.tools = [...this.tools, tool];
    }
  }

  private _availableModels(): string[] {
    const registry = this.runtimeConfig?.models?.registry ?? [];
    const _SELECTABLE = new Set(['available', 'loaded']);
    return [...new Set(
      registry
        .filter(model => !model.hidden && _SELECTABLE.has(model.status ?? 'available'))
        .map(model => model.address)
        .filter((address): address is string => Boolean(address)),
    )];
  }

  private async _save() {
    const id = this.isNew ? this._id : this.casteId;
    if (!id || !this.name.trim()) return;
    this.saving = true;

    const body: CasteRecipePayload = {
      name: this.name.trim(),
      description: this.description.trim(),
      system_prompt: this.systemPrompt,
      temperature: this.temperature,
      tools: this.tools,
      max_tokens: this.maxTokens,
      max_iterations: this.maxIterations,
      max_execution_time_s: this.maxExecutionTimeS,
      base_tool_calls_per_iteration: this.baseToolCalls,
      tier_models: this.tierModels,
    };

    try {
      const resp = await fetch(`/api/v1/castes/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        this._fire('saved', { id, recipe: await resp.json() });
      }
    } catch { /* best-effort */ }

    this.saving = false;
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(
      new CustomEvent(name, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-caste-editor': FcCasteEditor; }
}
