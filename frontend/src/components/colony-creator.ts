import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { CasteDefinition, CasteSlot, SubcasteTier, TemplateInfo, SuggestTeamEntry, Colony } from '../types.js';
import './atoms.js';

/** Preview result from backend preview endpoint. */
interface PreviewResult {
  task: string;
  team: string;
  strategy: string;
  maxRounds: number;
  budgetLimit: number;
  estimatedCost: number;
  fastPath: boolean;
  targetFiles: string[];
  summary: string;
}

/** Tier metadata for display. */
const TIERS: Record<SubcasteTier, { label: string; icon: string; color: string; tag: string; costHint: string }> = {
  light:    { label: 'Light',    icon: '○', color: 'var(--v-success)',  tag: 'local-only',    costHint: 'free' },
  standard: { label: 'Standard', icon: '◐', color: 'var(--v-fg-muted)', tag: 'smart routing', costHint: '~$0.02/turn' },
  heavy:    { label: 'Heavy',    icon: '●', color: 'var(--v-accent)',   tag: 'cloud-only',    costHint: '~$0.08/turn' },
  flash:    { label: 'Flash',    icon: '◈', color: 'var(--v-blue)',     tag: 'fastest',       costHint: '~$0.01/turn' },
};
const TIER_ORDER: SubcasteTier[] = ['light', 'standard', 'heavy', 'flash'];

@customElement('fc-colony-creator')
export class FcColonyCreator extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }

    .steps { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; }
    .step-bar {
      width: 20px; height: 3px; border-radius: 2px;
      background: rgba(255,255,255,0.06); transition: background 0.2s;
    }
    .step-bar.active { background: var(--v-accent); }
    .step-bar.done { background: var(--v-success); }
    .step-label { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-left: 8px; }

    .objective-input {
      width: 100%; background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 8px; color: var(--v-fg); font-family: var(--f-body); font-size: 13px;
      padding: 10px 14px; outline: none; resize: vertical; min-height: 60px;
      line-height: 1.5; box-sizing: border-box;
    }
    .objective-input:focus { border-color: rgba(232,88,26,0.3); }
    .objective-input::placeholder { color: var(--v-fg-dim); }

    .suggest-loading { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); padding: 12px 0; text-align: center; }

    .caste-list { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
    .caste-row {
      display: flex; align-items: center; gap: 8px; padding: 8px 12px;
      border-radius: 8px; transition: all 0.2s;
    }
    .caste-row.active { border-color: rgba(255,255,255,0.08); }
    .caste-icon { font-size: 14px; width: 20px; text-align: center; flex-shrink: 0; }
    .caste-name { font-size: 12px; font-weight: 600; color: var(--v-fg); width: 80px; flex-shrink: 0; }
    .caste-reason { font-size: 9px; color: var(--v-fg-muted); flex: 1; }
    .caste-remove { cursor: pointer; font-size: 12px; color: var(--v-fg-dim); padding: 2px 6px; border-radius: 4px; }
    .caste-remove:hover { color: var(--v-danger); background: rgba(240,100,100,0.08); }
    .caste-inactive { opacity: 0.5; cursor: pointer; }
    .caste-inactive:hover { opacity: 0.8; }
    .caste-inactive .add-hint { font-size: 9px; color: var(--v-fg-dim); }

    .tier-pills { display: flex; gap: 3px; }
    .tier-pill {
      display: inline-flex; align-items: center; gap: 2px;
      padding: 1px 7px; border-radius: 999px;
      font-size: 8.5px; font-family: var(--f-mono); font-weight: 500;
      letter-spacing: 0.05em; cursor: pointer;
      border: 1px solid transparent; transition: all 0.15s;
    }
    .tier-pill:hover { opacity: 1; }
    .tier-pill.selected { border-color: currentColor; }

    .count-control {
      display: flex; align-items: center; gap: 3px;
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-dim);
      margin-left: auto;
    }
    .count-label {
      font-size: 8px; letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--v-fg-dim); margin-right: 2px;
    }
    .count-btn {
      width: 16px; height: 16px; border-radius: 4px; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); font-size: 10px; cursor: pointer;
      display: flex; align-items: center; justify-content: center; padding: 0;
    }
    .count-btn:hover { background: rgba(255,255,255,0.04); color: var(--v-fg); }
    .count-val { min-width: 14px; text-align: center; color: var(--v-fg); }

    .service-list { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
    .svc-chip {
      display: flex; align-items: center; gap: 4px; padding: 4px 8px;
      border-radius: 6px; cursor: pointer; font-size: 10px;
      transition: all 0.2s;
    }
    .svc-chip.attached { border-left: 3px solid var(--v-service); }
    .svc-icon { font-size: 10px; color: var(--v-service); }
    .svc-name { font-weight: 500; }

    .template-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 8px 0; }
    .tmpl-card { padding: 10px; cursor: pointer; }
    .tmpl-card.selected { border-color: rgba(232,88,26,0.3); background: rgba(232,88,26,0.03); }
    .tmpl-name { font-size: 11px; font-weight: 600; color: var(--v-fg); margin-bottom: 2px; }
    .tmpl-desc { font-size: 9px; color: var(--v-fg-muted); line-height: 1.3; }
    .tmpl-meta { display: flex; gap: 6px; margin-top: 4px; font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); align-items: center; }
    .tmpl-caste-icons { display: flex; gap: 3px; align-items: center; }

    .config-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin: 12px 0; }
    .config-input {
      width: 100%; background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 6px; color: var(--v-fg); font-family: var(--f-mono); font-size: 12px;
      padding: 6px 10px; outline: none; box-sizing: border-box;
    }
    .config-input:focus { border-color: rgba(232,88,26,0.3); }

    .launch-summary { padding: 14px; }
    .launch-row { display: flex; align-items: center; gap: 6px; padding: 3px 0; }
    .launch-meta {
      display: flex; gap: 12px; font-family: var(--f-mono); font-size: 10px;
      color: var(--v-fg-muted); border-top: 1px solid var(--v-border); padding-top: 8px; margin-top: 8px;
    }
    .from-template { font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 6px; background: rgba(232,88,26,0.08); color: var(--v-accent); }

    .actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }
    .section-label { margin: 12px 0 6px; }

    .strategy-pills { display: flex; gap: 4px; }
    .strategy-pill {
      padding: 2px 8px; border-radius: 999px; font-size: 9px;
      font-family: var(--f-mono); cursor: pointer; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); transition: all 0.15s;
    }
    .strategy-pill.active { color: var(--v-accent); border-color: var(--v-accent); background: rgba(232,88,26,0.05); }
  `];

  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: String }) initialObjective = '';
  @property({ type: String }) initialTemplateId = '';
  /** Available service colonies for attachment. */
  @property({ type: Array }) availableServices: Colony[] = [];
  @property({ type: Object }) governance: { defaultBudgetPerColony: number; maxRoundsPerColony: number } | null = null;
  /** Wave 79.5 B3: seed colony with output from a prior colony. */
  @property({ type: String }) initialInputFrom = '';
  @property({ type: Array }) initialTargetFiles: string[] = [];

  @state() private step: 1 | 2 | 3 | 4 = 1;
  @state() private objective = '';
  @state() private suggestions: SuggestTeamEntry[] = [];
  @state() private templates: TemplateInfo[] = [];
  @state() private selectedTemplate: TemplateInfo | null = null;
  @state() private team: CasteSlot[] = [
    { caste: 'coder', tier: 'standard', count: 1 },
    { caste: 'reviewer', tier: 'standard', count: 1 },
  ];
  @state() private attachedServices: string[] = [];
  @state() private budget = 0;
  @state() private maxRounds = 0;
  @state() private strategy: 'stigmergic' | 'sequential' = 'stigmergic';
  @state() private loadingSuggestions = false;
  @state() private launching = false;
  // Wave 79.5 A1: selected target files
  @state() private _selectedTargetFiles: string[] = [];
  @state() private previewData: PreviewResult | null = null;
  @state() private previewLoading = false;
  private _initialized = false;

  connectedCallback() {
    super.connectedCallback();
    this._applyGovernanceDefaults();
  }

  private _applyGovernanceDefaults() {
    if (this.governance) {
      if (!this.budget) this.budget = this.governance.defaultBudgetPerColony ?? 1.0;
      if (!this.maxRounds) this.maxRounds = this.governance.maxRoundsPerColony ?? 10;
    } else {
      if (!this.budget) this.budget = 1.0;
      if (!this.maxRounds) this.maxRounds = 10;
    }
  }

  updated(changed: Map<string, unknown>) {
    if (!this._initialized) {
      if (this.initialObjective) this.objective = this.initialObjective;
      if (this.initialTargetFiles.length) this._selectedTargetFiles = [...this.initialTargetFiles];
      this._initialized = true;
    }
    if (changed.has('governance') && this.governance) {
      this._applyGovernanceDefaults();
    }
    if (changed.has('templates' as never) && this.initialTemplateId && this.templates.length > 0 && !this.selectedTemplate) {
      const tmpl = this.templates.find(t => t.id === this.initialTemplateId);
      if (tmpl) this.applyTemplate(tmpl);
    }
  }

  render() {
    const stepLabels = ['Describe', 'Suggest', 'Configure', 'Launch'];
    return html`
      <div class="steps">
        ${[1, 2, 3, 4].map(s => html`
          <div class="step-bar ${this.step > s ? 'done' : this.step >= s ? 'active' : ''}"></div>
        `)}
        <span class="step-label">${stepLabels[this.step - 1]}</span>
      </div>
      ${this.step === 1 ? this._renderDescribe() : nothing}
      ${this.step === 2 ? this._renderSuggest() : nothing}
      ${this.step === 3 ? this._renderConfigure() : nothing}
      ${this.step === 4 ? this._renderLaunch() : nothing}
    `;
  }

  // -- Step 1: Describe ----------------------------------------------------

  private _renderDescribe() {
    return html`
      <div class="s-label">What should the colony accomplish?</div>
      <textarea class="objective-input" placeholder="Describe the objective — the Queen will recommend a team..."
        .value=${this.objective}
        @input=${(e: Event) => { this.objective = (e.target as HTMLTextAreaElement).value; }}
        @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey && this.objective.trim()) { e.preventDefault(); this._suggestTeam(); } }}
      ></textarea>

      ${this._selectedTargetFiles.length > 0 ? html`
        <div class="s-label section-label">Target Files</div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">
          ${this._selectedTargetFiles.map((f, i) => html`
            <span style="font-size:9px;font-family:var(--f-mono);padding:2px 8px;border-radius:4px;background:rgba(232,88,26,0.08);color:var(--v-accent);display:inline-flex;align-items:center;gap:4px">
              ${f.split('/').pop()}
              <span style="cursor:pointer;opacity:0.6" @click=${() => { this._selectedTargetFiles = this._selectedTargetFiles.filter((_, j) => j !== i); }}>\u00d7</span>
            </span>
          `)}
        </div>
      ` : nothing}

      ${this.templates.length > 0 ? html`
        <div class="s-label section-label">Or start from template</div>
        <div class="template-cards">
          ${this.templates.slice(0, 6).map(t => this._renderTemplateCard(t, () => {
            this.objective = t.description;
            this.applyTemplate(t);
            this.step = 3;
          }))}
        </div>
      ` : nothing}

      <div class="actions">
        <fc-btn variant="ghost" @click=${() => this.fire('cancel')}>Cancel</fc-btn>
        <fc-btn variant="primary" ?disabled=${!this.objective.trim()} @click=${() => this._suggestTeam()}>Suggest Team</fc-btn>
      </div>
    `;
  }

  // -- Step 2: Suggest -----------------------------------------------------

  private _renderSuggest() {
    if (this.loadingSuggestions) {
      return html`
        <div class="suggest-loading">Queen is analyzing the objective...</div>
        <div class="actions">
          <fc-btn variant="ghost" @click=${() => { this.step = 1; }}>Back</fc-btn>
        </div>
      `;
    }
    return html`
      <div class="s-label">Suggested Team</div>
      <div class="glass" style="padding:12px;margin-bottom:12px">
        ${this.suggestions.map(s => {
          const def = this.castes.find(d => d.id === s.caste);
          return html`
            <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--v-border)">
              <span style="font-size:13px">${def?.icon ?? '○'}</span>
              <span style="font-size:11px;color:var(--v-fg);font-weight:500;width:80px">${def?.name ?? s.caste}</span>
              <span style="font-size:9px;color:var(--v-fg-muted);flex:1">${s.reasoning}</span>
            </div>`;
        })}
      </div>

      ${this.templates.length > 0 ? html`
        <div class="s-label">Matching Templates</div>
        <div style="display:flex;gap:6px;margin-bottom:12px">
          ${this.templates.slice(0, 3).map(t => html`
            <div class="glass clickable" style="padding:8px;flex:1" @click=${() => { this.applyTemplate(t); this.step = 3; }}>
              <span style="font-size:10px;font-weight:600;color:var(--v-fg)">${t.name}</span>
            </div>
          `)}
        </div>
      ` : nothing}

      <div class="actions">
        <fc-btn variant="ghost" @click=${() => { this.step = 1; }}>Back</fc-btn>
        <fc-btn variant="primary" @click=${() => { this._applySuggestions(); this.step = 3; }}>Accept Suggestion</fc-btn>
        <fc-btn variant="secondary" @click=${() => { this.step = 3; }}>Configure Manually</fc-btn>
      </div>
    `;
  }

  // -- Step 3: Configure ---------------------------------------------------

  private _renderConfigure() {
    return html`
      <div class="s-label">Team — click caste to add/remove, click tier to change, use Count to scale</div>
      ${this.selectedTemplate ? html`<span class="from-template">from ${this.selectedTemplate.name}</span>` : nothing}

      <div class="caste-list">
        ${this.castes.filter(c => c.id !== 'queen').map(c => {
          const slot = this.team.find(t => t.caste === c.id);
          if (slot) {
            return html`
              <div class="glass caste-row active" style="background:${c.color}08;border-color:${c.color}25">
                <span class="caste-icon" style="filter:drop-shadow(0 0 3px ${c.color}40)">${c.icon}</span>
                <span class="caste-name" style="color:var(--v-fg)">${c.name}</span>
                <div class="tier-pills">
                  ${TIER_ORDER.map(k => {
                    const ti = TIERS[k];
                    return html`
                      <span class="tier-pill ${slot.tier === k ? 'selected' : ''}"
                        style="color:${ti.color};background:${slot.tier === k ? ti.color + '12' : 'transparent'}"
                        @click=${(e: Event) => { e.stopPropagation(); this._setTier(c.id, k); }}>
                        ${ti.icon} ${ti.label}
                      </span>`;
                  })}
                </div>
                <div class="count-control">
                  <span class="count-label">Count</span>
                  <button
                    class="count-btn"
                    title=${`Decrease ${c.name} count`}
                    aria-label=${`Decrease ${c.name} count`}
                    @click=${(e: Event) => { e.stopPropagation(); this._setCount(c.id, slot.count - 1); }}
                  >-</button>
                  <span class="count-val">${slot.count}</span>
                  <button
                    class="count-btn"
                    title=${`Increase ${c.name} count`}
                    aria-label=${`Increase ${c.name} count`}
                    @click=${(e: Event) => { e.stopPropagation(); this._setCount(c.id, slot.count + 1); }}
                  >+</button>
                </div>
                <span class="caste-remove" @click=${() => this._removeCaste(c.id)}>✕</span>
              </div>`;
          }
          return html`
            <div class="glass caste-row caste-inactive" @click=${() => this._addCaste(c.id)}>
              <span class="caste-icon">${c.icon}</span>
              <span class="caste-name" style="color:var(--v-fg-dim)">${c.name}</span>
              <span class="add-hint">click to add</span>
            </div>`;
        })}
      </div>

      ${this.availableServices.length > 0 ? html`
        <div class="s-label section-label">Attach Services (callable resources)</div>
        <div class="service-list">
          ${this.availableServices.map(s => {
            const attached = this.attachedServices.includes(s.id);
            return html`
              <div class="glass svc-chip ${attached ? 'attached' : ''}" @click=${() => this._toggleService(s.id)}>
                <span class="svc-icon">◆</span>
                <span class="svc-name" style="color:${attached ? 'var(--v-fg)' : 'var(--v-fg-muted)'}">${s.displayName ?? s.id}</span>
                ${attached ? html`<span style="font-size:8px;color:var(--v-service)">✓</span>` : nothing}
              </div>`;
          })}
        </div>
      ` : nothing}

      <div class="config-grid">
        <div>
          <div class="s-label">Budget ($)</div>
          <input class="config-input" type="number" step="0.5" min="0.25" max="20"
            .value=${String(this.budget)}
            @input=${(e: Event) => { this.budget = parseFloat((e.target as HTMLInputElement).value) || this.governance?.defaultBudgetPerColony || 1.0; }}>
        </div>
        <div>
          <div class="s-label">Max Rounds</div>
          <input class="config-input" type="number" min="1" max="50"
            .value=${String(this.maxRounds)}
            @input=${(e: Event) => { this.maxRounds = parseInt((e.target as HTMLInputElement).value) || this.governance?.maxRoundsPerColony || 10; }}>
        </div>
        <div>
          <div class="s-label">Strategy</div>
          <div class="strategy-pills">
            ${(['stigmergic', 'sequential'] as const).map(s => html`
              <span class="strategy-pill ${this.strategy === s ? 'active' : ''}"
                @click=${() => { this.strategy = s; }}>${s}</span>
            `)}
          </div>
        </div>
      </div>

      <div class="actions">
        <fc-btn variant="ghost" @click=${() => { this.step = this.suggestions.length > 0 ? 2 : 1; }}>Back</fc-btn>
        <fc-btn variant="primary" ?disabled=${this.team.length === 0} @click=${() => this._enterReview()}>Review</fc-btn>
      </div>
    `;
  }

  // -- Step 4: Launch summary (real preview truth) -------------------------

  private _renderLaunch() {
    const isFastPath = this.team.length === 1 && this.team[0].count === 1 && this.strategy === 'sequential';
    const totalAgents = this.team.reduce((s, t) => s + t.count, 0);

    return html`
      <div class="s-label">Review &amp; Confirm</div>
      ${this.previewLoading ? html`
        <div class="suggest-loading">Loading preview...</div>
      ` : nothing}
      <div class="glass launch-summary">
        <div style="font-size:12px;color:var(--v-fg);line-height:1.5;margin-bottom:10px">${this.objective}</div>

        <!-- Team shape -->
        <div class="s-label" style="margin-top:8px;margin-bottom:4px">Team (${totalAgents} agent${totalAgents > 1 ? 's' : ''})</div>
        <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px">
          ${this.team.map(slot => {
            const def = this.castes.find(d => d.id === slot.caste);
            const ti = TIERS[slot.tier];
            return html`
              <div class="launch-row">
                <span style="font-size:11px">${def?.icon ?? '\u25CB'}</span>
                <span style="font-size:10.5px;color:var(--v-fg)">${def?.name ?? slot.caste}</span>
                ${slot.count > 1 ? html`<span style="font-size:9px;color:var(--v-fg-dim)">\u00D7${slot.count}</span>` : nothing}
                <fc-pill color="${ti.color}" sm>${ti.icon} ${ti.label}</fc-pill>
                <span style="font-size:8px;color:var(--v-fg-dim)">${ti.costHint}</span>
              </div>`;
          })}
        </div>

        ${this.attachedServices.length > 0 ? html`
          <div style="margin-bottom:10px">
            <div class="s-label" style="margin-bottom:4px">Attached Services</div>
            ${this.attachedServices.map(id => {
              const svc = this.availableServices.find(s => s.id === id);
              return html`
                <div style="display:flex;align-items:center;gap:4px">
                  <span style="font-size:9px;color:var(--v-service)">\u25C6</span>
                  <span style="font-size:10px;color:var(--v-fg)">${svc?.displayName ?? id}</span>
                </div>`;
            })}
          </div>
        ` : nothing}

        <!-- Launch parameters -->
        <div class="launch-meta">
          <span>$${this.budget.toFixed(2)} budget</span>
          <span>${this.maxRounds} rounds max</span>
          <span>${this.strategy}</span>
          ${this.previewData?.estimatedCost
            ? html`<span style="color:var(--v-accent)">est. ~$${this.previewData.estimatedCost.toFixed(2)}</span>`
            : html`<span style="color:var(--v-fg-dim)">cost varies by model</span>`}
          ${this.selectedTemplate ? html`<span>tmpl: ${this.selectedTemplate.name}</span>` : nothing}
        </div>

        ${isFastPath ? html`
          <div style="margin-top:8px;padding:5px 8px;border-radius:6px;background:rgba(45,212,168,0.06);border:1px solid rgba(45,212,168,0.15);font-size:10px;font-family:var(--f-mono);color:var(--v-success)">
            \u26A1 fast_path eligible \u2014 single agent, skips pheromone/convergence overhead
          </div>
        ` : nothing}

        ${this.previewData?.summary ? html`
          <div style="margin-top:8px;padding:6px 8px;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid var(--v-border);font-size:10px;font-family:var(--f-mono);color:var(--v-fg-muted);white-space:pre-line">
            ${this.previewData.summary}
          </div>
        ` : nothing}
      </div>

      <div class="actions">
        <fc-btn variant="ghost" @click=${() => { this.step = 3; this.previewData = null; }}>Back</fc-btn>
        <fc-btn variant="primary" ?disabled=${this.launching} @click=${() => this._launch()}>
          ${this.launching ? 'Launching...' : 'Launch Colony'}
        </fc-btn>
      </div>
    `;
  }

  // -- Template card -------------------------------------------------------

  private _renderTemplateCard(t: TemplateInfo, onClick: () => void) {
    return html`
      <div class="glass tmpl-card clickable ${this.selectedTemplate?.id === t.id ? 'selected' : ''}"
        @click=${onClick}>
        <div class="tmpl-name">${t.name}</div>
        <div class="tmpl-desc">${t.description}</div>
        <div class="tmpl-meta">
          <span class="tmpl-caste-icons">
            ${t.castes.map(s => {
              const def = this.castes.find(d => d.id === s.caste);
              const ti = TIERS[s.tier] ?? TIERS.standard;
              return html`<span style="display:inline-flex;align-items:center;gap:1px">
                <span style="font-size:10px">${def?.icon ?? '○'}</span>
                <span style="font-size:7px;color:${ti.color}">${ti.icon}</span>
              </span>`;
            })}
          </span>
          <span>· ${t.useCount} uses</span>
        </div>
      </div>`;
  }

  // -- Preview -------------------------------------------------------------

  private async _enterReview() {
    this.step = 4;
    this.previewData = null;
    this.previewLoading = true;
    try {
      const res = await fetch('/api/v1/preview-colony', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: this.objective,
          castes: this.team,
          strategy: this.strategy,
          max_rounds: this.maxRounds,
          budget_limit: this.budget,
          target_files: this._selectedTargetFiles,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        this.previewData = {
          task: (data.task ?? this.objective) as string,
          team: (data.team ?? '') as string,
          strategy: (data.strategy ?? this.strategy) as string,
          maxRounds: (data.max_rounds ?? this.maxRounds) as number,
          budgetLimit: (data.budget_limit ?? this.budget) as number,
          estimatedCost: (data.estimated_cost ?? 0) as number,
          fastPath: (data.fast_path ?? false) as boolean,
          targetFiles: (data.target_files ?? []) as string[],
          summary: (data.summary ?? '') as string,
        };
      }
    } catch {
      // Backend preview not available — proceed with local estimates
    }
    this.previewLoading = false;
  }

  // -- Actions -------------------------------------------------------------

  private async _suggestTeam() {
    if (!this.objective.trim()) return;
    this.step = 2;
    this.loadingSuggestions = true;

    const [sugResp, tmplResp] = await Promise.allSettled([
      fetch('/api/v1/suggest-team', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: this.objective }),
      }),
      fetch('/api/v1/templates'),
    ]);

    if (sugResp.status === 'fulfilled' && sugResp.value.ok) {
      try {
        const data = await sugResp.value.json();
        const suggestions: SuggestTeamEntry[] = Array.isArray(data)
          ? data
          : Array.isArray(data?.castes) ? data.castes : [];
        if (suggestions.length > 0) {
          this.suggestions = suggestions;
        }
      } catch { /* keep defaults */ }
    }

    if (tmplResp.status === 'fulfilled' && tmplResp.value.ok) {
      try {
        const data = await tmplResp.value.json();
        if (Array.isArray(data)) {
          this.templates = data.map((t: Record<string, unknown>) => ({
            id: (t.template_id ?? t.templateId ?? t.id) as string,
            name: t.name as string,
            description: (t.description ?? '') as string,
            castes: ((t.castes ?? []) as any[]).map((c: any) =>
              typeof c === 'string' ? { caste: c, tier: 'standard' as SubcasteTier, count: 1 } : c
            ),
            strategy: (t.strategy ?? 'stigmergic') as 'stigmergic' | 'sequential',
            budgetLimit: (t.budget_limit ?? t.budgetLimit ?? undefined) as number | undefined,
            maxRounds: (t.max_rounds ?? t.maxRounds ?? undefined) as number | undefined,
            sourceColonyId: (t.source_colony_id ?? t.sourceColonyId ?? null) as string | null,
            useCount: (t.use_count ?? t.useCount ?? 0) as number,
          }));
        }
      } catch { /* no templates */ }
    }

    this.loadingSuggestions = false;
  }

  private _applySuggestions() {
    if (this.suggestions.length > 0) {
      this.team = this.suggestions.map(s => ({
        caste: s.caste,
        tier: 'standard' as SubcasteTier,
        count: 1,
      }));
    }
  }

  private applyTemplate(t: TemplateInfo) {
    this.selectedTemplate = t;
    this.team = t.castes.map(s => ({ ...s }));
    if (typeof t.budgetLimit === 'number' && Number.isFinite(t.budgetLimit)) {
      this.budget = t.budgetLimit;
    }
    if (typeof t.maxRounds === 'number' && Number.isFinite(t.maxRounds)) {
      this.maxRounds = t.maxRounds;
    }
    if (t.strategy) this.strategy = t.strategy;
  }

  private _addCaste(id: string) {
    if (!this.team.find(t => t.caste === id)) {
      this.team = [...this.team, { caste: id, tier: 'standard', count: 1 }];
    }
  }

  private _removeCaste(id: string) {
    this.team = this.team.filter(t => t.caste !== id);
  }

  private _setTier(caste: string, tier: SubcasteTier) {
    this.team = this.team.map(t => t.caste === caste ? { ...t, tier } : t);
  }

  private _setCount(caste: string, count: number) {
    if (count < 1) return;
    if (count > 5) return;
    this.team = this.team.map(t => t.caste === caste ? { ...t, count } : t);
  }

  private _toggleService(id: string) {
    this.attachedServices = this.attachedServices.includes(id)
      ? this.attachedServices.filter(x => x !== id)
      : [...this.attachedServices, id];
  }

  private _launch() {
    this.launching = true;
    const detail: Record<string, unknown> = {
      task: this.objective,
      castes: this.team,
      budgetLimit: this.budget,
      maxRounds: this.maxRounds,
      strategy: this.strategy,
      services: this.attachedServices,
    };
    if (this.selectedTemplate) {
      detail.templateId = this.selectedTemplate.id;
    }
    // Wave 79.5 B3: include file handoff context
    if (this.initialInputFrom) {
      detail.inputFrom = this.initialInputFrom;
    }
    if (this._selectedTargetFiles.length > 0) {
      detail.targetFiles = this._selectedTargetFiles;
    }
    this.fire('spawn-colony', detail);
  }

  private fire(name: string, detail?: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }

  /** Reset to step 1 for reuse. */
  reset() {
    this.step = 1;
    this.objective = '';
    this.suggestions = [];
    this.templates = [];
    this.selectedTemplate = null;
    this.team = [
      { caste: 'coder', tier: 'standard', count: 1 },
      { caste: 'reviewer', tier: 'standard', count: 1 },
    ];
    this.attachedServices = [];
    this.budget = this.governance?.defaultBudgetPerColony ?? 1.0;
    this.maxRounds = this.governance?.maxRoundsPerColony ?? 10;
    this.strategy = 'stigmergic';
    this.launching = false;
    this.previewData = null;
    this.previewLoading = false;
    this._initialized = false;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-colony-creator': FcColonyCreator; }
}
