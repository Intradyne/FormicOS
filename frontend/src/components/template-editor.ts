import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { TemplateInfo, CasteSlot, CoordinationStrategy } from '../types.js';
import './atoms.js';

export type EditorMode = 'create' | 'edit' | 'duplicate';

const CASTE_OPTIONS = [
  { id: 'queen', icon: '\u265B', color: '#E8581A', name: 'Queen' },
  { id: 'coder', icon: '</>', color: '#2DD4A8', name: 'Coder' },
  { id: 'reviewer', icon: '\u2713', color: '#A78BFA', name: 'Reviewer' },
  { id: 'researcher', icon: '\u25CE', color: '#5B9CF5', name: 'Researcher' },
  { id: 'archivist', icon: '\u29EB', color: '#F5B731', name: 'Archivist' },
];

const TIER_OPTIONS: Array<{ id: string; label: string }> = [
  { id: 'flash', label: 'Flash' },
  { id: 'light', label: 'Light' },
  { id: 'standard', label: 'Standard' },
  { id: 'heavy', label: 'Heavy' },
];

@customElement('fc-template-editor')
export class FcTemplateEditor extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .editor-title {
      font-family: var(--f-display); font-size: 18px; font-weight: 700;
      color: var(--v-fg); margin: 0 0 16px;
    }
    .field { margin-bottom: 14px; }
    .field-label {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); letter-spacing: 0.14em;
      text-transform: uppercase; margin-bottom: 5px;
    }
    input, textarea, select {
      width: 100%; box-sizing: border-box; padding: 8px 10px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 7px; color: var(--v-fg); font-family: var(--f-body);
      font-size: 12px; outline: none; transition: border-color 0.15s;
    }
    input:focus, textarea:focus, select:focus {
      border-color: rgba(232,88,26,0.3);
    }
    textarea { resize: vertical; min-height: 50px; }
    select { cursor: pointer; appearance: none; }
    .inline-row { display: flex; gap: 10px; }
    .inline-row .field { flex: 1; }

    /* Castes editor */
    .castes-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
    .caste-row {
      display: flex; align-items: center; gap: 8px; padding: 6px 10px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 7px;
    }
    .caste-icon { font-size: 13px; width: 20px; text-align: center; }
    .caste-name {
      font-size: 11px; font-weight: 500; color: var(--v-fg); width: 80px;
    }
    .caste-tier {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .caste-count {
      width: 40px; text-align: center; padding: 3px 4px;
      font-size: 11px; font-family: var(--f-mono);
    }
    .caste-remove {
      margin-left: auto; cursor: pointer; color: var(--v-fg-dim);
      font-size: 12px; padding: 2px 6px; border-radius: 4px;
      transition: color 0.15s;
    }
    .caste-remove:hover { color: var(--v-danger); }
    .add-caste-row { display: flex; gap: 6px; align-items: center; }
    .add-caste-row select { width: auto; min-width: 100px; }

    /* Tags */
    .tags-row { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px; }
    .tag-chip {
      display: flex; align-items: center; gap: 3px; padding: 2px 8px;
      background: rgba(163,130,250,0.1); border: 1px solid rgba(163,130,250,0.15);
      border-radius: 6px; font-size: 9px; font-family: var(--f-mono); color: #A78BFA;
    }
    .tag-x {
      cursor: pointer; font-size: 10px; color: var(--v-fg-dim);
      margin-left: 2px;
    }
    .tag-x:hover { color: var(--v-danger); }
    .tag-input { width: 120px; padding: 3px 6px; font-size: 9px; }

    /* Actions */
    .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 18px; }
    .version-note {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-top: 8px;
    }
  `];

  @property({ type: String }) mode: EditorMode = 'create';
  @property({ type: Object }) template: TemplateInfo | null = null;
  @property({ type: Object }) governance: { defaultBudgetPerColony: number; maxRoundsPerColony: number } | null = null;

  @state() private name = '';
  @state() private description = '';
  @state() private castes: CasteSlot[] = [];
  @state() private strategy: CoordinationStrategy = 'stigmergic';
  @state() private budgetLimit = 0;
  @state() private maxRounds = 0;
  @state() private tags: string[] = [];
  @state() private tagInput = '';
  @state() private saving = false;

  // Preserved from source template in edit mode
  private _templateId = '';
  private _version = 1;
  private _sourceColonyId: string | null = null;

  connectedCallback() {
    super.connectedCallback();
    this._populateFromTemplate();
  }

  private get _defaultBudget(): number {
    return this.governance?.defaultBudgetPerColony ?? 1.0;
  }

  private get _defaultMaxRounds(): number {
    return this.governance?.maxRoundsPerColony ?? 5;
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('template') || changed.has('mode')) {
      this._populateFromTemplate();
    }
    if (changed.has('governance') && this.governance) {
      if (!this.budgetLimit) this.budgetLimit = this._defaultBudget;
      if (!this.maxRounds) this.maxRounds = this._defaultMaxRounds;
    }
  }

  private _populateFromTemplate() {
    const t = this.template;
    if (!t) {
      // Create mode defaults
      this.name = '';
      this.description = '';
      this.castes = [{ caste: 'coder', tier: 'standard', count: 1 }];
      this.strategy = 'stigmergic';
      this.budgetLimit = this._defaultBudget;
      this.maxRounds = this._defaultMaxRounds;
      this.tags = [];
      this._templateId = '';
      this._version = 1;
      this._sourceColonyId = null;
      return;
    }

    if (this.mode === 'duplicate') {
      this.name = `${t.name} (copy)`;
      this._templateId = ''; // new id for duplicates
      this._version = 1;
    } else {
      this.name = t.name;
      this._templateId = t.id;
      this._version = (t.version ?? 1) + (this.mode === 'edit' ? 1 : 0);
    }

    this.description = t.description;
    this.castes = t.castes.map(c => ({ ...c }));
    this.strategy = t.strategy;
    this.budgetLimit = t.budgetLimit ?? this._defaultBudget;
    this.maxRounds = t.maxRounds ?? this._defaultMaxRounds;
    this.tags = [...(t.tags ?? [])];
    this._sourceColonyId = t.sourceColonyId;
  }

  render() {
    const title = this.mode === 'create' ? 'New Template'
      : this.mode === 'edit' ? 'Edit Template'
      : 'Duplicate Template';

    return html`
      <div class="editor-title">
        <fc-gradient-text>${title}</fc-gradient-text>
      </div>

      <div class="field">
        <div class="field-label">Name</div>
        <input type="text" .value=${this.name} placeholder="e.g. Full-stack feature"
          @input=${(e: Event) => { this.name = (e.target as HTMLInputElement).value; }}>
      </div>

      <div class="field">
        <div class="field-label">Description</div>
        <textarea .value=${this.description} placeholder="What this template is for..."
          @input=${(e: Event) => {
            this.description = (e.target as HTMLTextAreaElement).value;
          }}></textarea>
      </div>

      <div class="field">
        <div class="field-label">Castes</div>
        <div class="castes-list">
          ${this.castes.map((slot, i) => this._renderCasteSlot(slot, i))}
        </div>
        ${this._renderAddCaste()}
      </div>

      <div class="inline-row">
        <div class="field">
          <div class="field-label">Strategy</div>
          <select .value=${this.strategy}
            @change=${(e: Event) => {
              this.strategy =
                (e.target as HTMLSelectElement).value as CoordinationStrategy;
            }}>
            <option value="stigmergic">Stigmergic</option>
            <option value="sequential">Sequential</option>
          </select>
        </div>
        <div class="field">
          <div class="field-label">Budget ($)</div>
          <input type="number" step="0.25" min="0.25" .value=${String(this.budgetLimit)}
            @input=${(e: Event) => {
              this.budgetLimit =
                parseFloat((e.target as HTMLInputElement).value) || 1.0;
            }}>
        </div>
        <div class="field">
          <div class="field-label">Max Rounds</div>
          <input type="number" min="1" max="50" .value=${String(this.maxRounds)}
            @input=${(e: Event) => {
              this.maxRounds =
                parseInt((e.target as HTMLInputElement).value, 10) || 5;
            }}>
        </div>
      </div>

      <div class="field">
        <div class="field-label">Tags</div>
        <div class="tags-row">
          ${this.tags.map((tag, i) => html`
            <span class="tag-chip">
              ${tag}
              <span class="tag-x"
                @click=${() => this._removeTag(i)}>\u2715</span>
            </span>
          `)}
        </div>
        <input class="tag-input" type="text" placeholder="Add tag + Enter"
          .value=${this.tagInput}
          @input=${(e: Event) => {
            this.tagInput = (e.target as HTMLInputElement).value;
          }}
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter') { e.preventDefault(); this._addTag(); }
          }}>
      </div>

      ${this.mode === 'edit' && this._templateId ? html`
        <div class="version-note">
          template_id: ${this._templateId} \u00B7
          version: ${this._version}
        </div>` : nothing}

      <div class="actions">
        <fc-btn variant="secondary" sm
          @click=${() => this._fire('cancel', null)}>Cancel</fc-btn>
        <fc-btn variant="primary" sm ?disabled=${this.saving || !this.name.trim()}
          @click=${() => this._save()}>
          ${this.saving ? 'Saving\u2026'
            : this.mode === 'edit' ? 'Save Changes'
            : this.mode === 'duplicate' ? 'Create Copy'
            : 'Create Template'}
        </fc-btn>
      </div>
    `;
  }

  private _renderCasteSlot(slot: CasteSlot, idx: number) {
    const info = CASTE_OPTIONS.find(c => c.id === slot.caste);
    return html`
      <div class="caste-row">
        <span class="caste-icon"
          style="color:${info?.color ?? 'var(--v-fg-dim)'}">${info?.icon ?? '\u2B22'}</span>
        <span class="caste-name">${info?.name ?? slot.caste}</span>
        <select class="caste-tier" .value=${slot.tier}
          @change=${(e: Event) => {
            this.castes = this.castes.map((s, i) =>
              i === idx
                ? { ...s, tier: (e.target as HTMLSelectElement).value as CasteSlot['tier'] }
                : s
            );
          }}>
          ${TIER_OPTIONS.map(t => html`
            <option value=${t.id} ?selected=${t.id === slot.tier}>${t.label}</option>
          `)}
        </select>
        <input type="number" class="caste-count" min="1" max="5"
          .value=${String(slot.count)}
          @input=${(e: Event) => {
            const val = parseInt((e.target as HTMLInputElement).value, 10) || 1;
            this.castes = this.castes.map((s, i) =>
              i === idx ? { ...s, count: val } : s
            );
          }}>
        <span class="caste-remove" @click=${() => {
          this.castes = this.castes.filter((_, i) => i !== idx);
        }}>\u2715</span>
      </div>`;
  }

  private _renderAddCaste() {
    const used = new Set(this.castes.map(c => c.caste));
    const available = CASTE_OPTIONS.filter(c => !used.has(c.id));
    if (available.length === 0) return nothing;
    return html`
      <div class="add-caste-row">
        <fc-btn variant="secondary" sm @click=${() => {
          if (available.length > 0) {
            this.castes = [
              ...this.castes,
              { caste: available[0].id, tier: 'standard', count: 1 },
            ];
          }
        }}>+ Add Caste</fc-btn>
      </div>`;
  }

  private _addTag() {
    const tag = this.tagInput.trim();
    if (tag && !this.tags.includes(tag)) {
      this.tags = [...this.tags, tag];
    }
    this.tagInput = '';
  }

  private _removeTag(idx: number) {
    this.tags = this.tags.filter((_, i) => i !== idx);
  }

  private async _save() {
    if (!this.name.trim() || this.castes.length === 0) return;
    this.saving = true;

    const body: Record<string, unknown> = {
      name: this.name.trim(),
      description: this.description.trim(),
      castes: this.castes,
      strategy: this.strategy,
      budget_limit: this.budgetLimit,
      max_rounds: this.maxRounds,
    };

    if (this.tags.length > 0) {
      body.tags = this.tags;
    }

    // Edit mode: preserve template_id and send incremented version
    if (this.mode === 'edit' && this._templateId) {
      body.template_id = this._templateId;
      body.version = this._version;
    }

    if (this._sourceColonyId && this.mode !== 'duplicate') {
      body.source_colony_id = this._sourceColonyId;
    }

    try {
      const resp = await fetch('/api/v1/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        this._fire('saved', await resp.json());
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
  interface HTMLElementTagNameMap { 'fc-template-editor': FcTemplateEditor; }
}
