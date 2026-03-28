import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { allColonies } from '../state/store.js';
import { providerColor } from '../helpers.js';
import type { TreeNode, CasteDefinition, RuntimeConfig } from '../types.js';
import './atoms.js';

@customElement('fc-workspace-config')
export class FcWorkspaceConfig extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 860px; }
    .header { display: flex; align-items: center; gap: 7px; margin-bottom: 16px; }
    .header h2 { font-family: var(--f-display); font-size: 18px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .meta { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted); margin-left: auto; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
    .inherit-note { font-size: 9.5px; color: var(--v-fg-dim); margin-bottom: 10px; line-height: 1.4; }
    .caste-row { display: flex; align-items: center; gap: 6px; padding: 5px 0; border-bottom: 1px solid var(--v-border); }
    .caste-icon { font-size: 10px; }
    .caste-name { font-size: 10.5px; color: var(--v-fg); width: 70px; }
    .caste-model { font-family: var(--f-mono); font-size: 10px; flex: 1; }
    .edit-input {
      background: var(--v-void); border: 1px solid var(--v-border); border-radius: 4px;
      color: var(--v-fg); font-family: var(--f-mono); font-size: 10px; padding: 3px 8px;
      outline: none; flex: 1; min-width: 0;
    }
    .edit-input:focus { border-color: rgba(232,88,26,0.25); }
    .gov-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
    .gov-label { font-size: 7.5px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 2px; font-weight: 600; }
    .gov-value { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg); }
    .thread-card { padding: 12px; margin-bottom: 6px; }
    .thread-row { display: flex; align-items: center; gap: 5px; }
    .thread-name { font-family: var(--f-display); font-size: 12.5px; font-weight: 600; color: var(--v-fg); }
    .thread-count { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-muted); margin-left: auto; }
  `];

  @property({ type: Object }) workspace: (TreeNode & { config?: any }) | null = null;
  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @state() private editingGov = false;
  @state() private govStrategy = '';
  @state() private govBudget = '';

  render() {
    const ws = this.workspace;
    if (!ws) return nothing;
    const cols = allColonies([ws]);
    const totalCost = cols.reduce((a, c) => a + ((c as any).cost ?? 0), 0);
    const cfg = ws.config ?? {};
    const systemBudget = this.runtimeConfig?.governance?.defaultBudgetPerColony ?? 0;
    const budgetCap = cfg.budget ?? systemBudget;

    return html`
      <div class="header">
        <span style="font-size:14px;color:var(--v-accent)">\u25A3</span>
        <h2>${ws.name}</h2>
        <fc-pill color="var(--v-fg-dim)" sm>${cfg.strategy ?? 'stigmergic'}</fc-pill>
        <span class="meta">${cols.length} colonies \u00B7 $${totalCost.toFixed(2)}</span>
      </div>

      <div class="grid">
        <div class="glass" style="padding:14px">
          <div class="s-label">Model Cascade Overrides</div>
          <div class="inherit-note">Choose a model to override the system cascade for this workspace. Select <span style="font-family:var(--f-mono);color:var(--v-fg)">Default</span> to inherit system routing.</div>
          ${this.castes.filter(c => c.id !== 'queen').map(c => {
            const val = cfg[`${c.id}Model`] ?? cfg[`${c.id}_model`] ?? null;
            const systemDefault = (this.runtimeConfig?.models?.defaults as Record<string, string> | undefined)?.[c.id] ?? '';
            const models = this._modelOptions(val);
            return html`
              <div class="caste-row">
                <span class="caste-icon" style="filter:drop-shadow(0 0 2px ${c.color}25)">${c.icon}</span>
                <span class="caste-name">${c.name}</span>
                <select class="edit-input" .value=${val ?? ''}
                  @change=${(ev: Event) => {
                    this.saveModelEdit(
                      c.id,
                      (ev.target as HTMLSelectElement).value,
                    );
                  }}>
                  <option value="">Default${systemDefault ? ` (${systemDefault})` : ''}</option>
                  ${models.map(model => html`
                    <option value=${model}>${model}</option>
                  `)}
                </select>
                ${val ? html`
                  <span class="caste-model" style="color:var(--v-fg)">
                    <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:${providerColor(val)};margin-right:4px"></span>${val}
                  </span>
                  <fc-pill .color=${c.color} sm>override</fc-pill>
                ` : html`
                  <span class="caste-model" style="color:var(--v-fg-dim)">using system default</span>
                `}
              </div>`;
          })}
        </div>

        <div class="glass" style="padding:14px">
          <div class="s-label">Governance & Budget</div>
          <fc-meter label="Budget Used" .value=${totalCost} .max=${budgetCap} unit="$" color="#E8581A"></fc-meter>
          <div class="gov-grid">
            ${[
              { l: 'Strategy', v: cfg.strategy ?? 'stigmergic' },
              { l: 'Budget Limit', v: cfg.budget != null ? `$${cfg.budget.toFixed(2)}` : budgetCap > 0 ? `$${budgetCap.toFixed(2)} (system)` : 'n/a' },
              { l: 'Max Rounds', v: `${this.runtimeConfig?.governance?.maxRoundsPerColony ?? 25} (system)` },
              { l: 'Convergence \u03B8', v: `${this.runtimeConfig?.governance?.convergenceThreshold ?? 0.95}` },
            ].map(({ l, v }) => html`<div><div class="gov-label">${l}</div><div class="gov-value">${v}</div></div>`)}
          </div>
          ${this.editingGov ? html`
            <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px">
                <span class="gov-label" style="margin:0;width:60px">Strategy</span>
                <select style="background:var(--v-void);border:1px solid var(--v-border);border-radius:4px;color:var(--v-fg);font-family:var(--f-mono);font-size:10px;padding:3px 6px"
                  .value=${this.govStrategy} @change=${(ev: Event) => { this.govStrategy = (ev.target as HTMLSelectElement).value; }}>
                  <option value="stigmergic">stigmergic</option>
                  <option value="sequential">sequential</option>
                </select>
              </div>
              <div style="display:flex;align-items:center;gap:6px">
                <span class="gov-label" style="margin:0;width:60px">Budget</span>
                <input class="edit-input" style="width:80px" .value=${this.govBudget}
                  @input=${(ev: InputEvent) => { this.govBudget = (ev.target as HTMLInputElement).value; }}/>
              </div>
              <div style="display:flex;gap:5px">
                <fc-btn sm @click=${this.saveGovEdit}>Save</fc-btn>
                <fc-btn variant="ghost" sm @click=${() => { this.editingGov = false; }}>Cancel</fc-btn>
              </div>
            </div>
          ` : html`
            <div style="margin-top:10px;display:flex;gap:5px">
              <fc-btn variant="secondary" sm @click=${() => { this.editingGov = true; this.govStrategy = cfg.strategy ?? 'stigmergic'; this.govBudget = cfg.budget != null ? `${cfg.budget}` : ''; }}>Edit Config</fc-btn>
              <fc-btn variant="danger" sm @click=${() => this.fire('update-config', { field: 'budget', value: 0 })}>Reset Budget</fc-btn>
            </div>
          `}
        </div>
      </div>

      ${this._renderColonyCards(cols)}

      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <div class="s-label" style="margin:0">Threads</div>
        <fc-btn variant="primary" sm @click=${() => this.fire('spawn-colony-request', null)}>+ New Colony</fc-btn>
      </div>
      ${(ws.children ?? []).map(th => html`
        <div class="glass clickable thread-card" @click=${() => this.fire('navigate', th.id)}>
          <div class="thread-row">
            <span style="color:var(--v-blue);font-size:10px">\u25B7</span>
            <span class="thread-name">${th.name}</span>
            <span class="thread-count">${(th.children ?? []).length} colonies</span>
          </div>
        </div>
      `)}

      ${(() => {
        const completed = cols.filter(c => c.status === 'completed' || c.status === 'done');
        return completed.length > 0 ? html`
          <div class="s-label" style="margin-top:14px">Recent Completions</div>
          ${completed.slice(0, 4).map(c => html`
            <div class="glass clickable" style="padding:6px 10px;margin-bottom:4px;font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)"
              @click=${() => this.fire('navigate', c.id)}>
              ${c.name} \u2014 ${c.status}
            </div>
          `)}
        ` : nothing;
      })()}

      ${cfg.description ? html`
        <div class="s-label" style="margin-top:16px">Description</div>
        <div class="glass" style="padding:10px;font-size:11px;font-family:var(--f-mono);color:var(--v-fg-dim);line-height:1.5">${cfg.description}</div>
      ` : nothing}

      <div style="display:flex;gap:12px;margin-top:16px">
        <div class="glass clickable" style="padding:10px 14px;flex:1;text-align:center" @click=${() => this.fire('navigate-tab', 'knowledge')}>
          <div class="gov-label">Knowledge</div>
          <div style="font-size:12px;color:var(--v-fg)">\u2139 Browse</div>
        </div>
        <div class="glass clickable" style="padding:10px 14px;flex:1;text-align:center" @click=${() => this.fire('navigate-tab', 'playbook')}>
          <div class="gov-label">Playbook</div>
          <div style="font-size:12px;color:var(--v-fg)">\u25B6 Templates</div>
        </div>
        <div class="glass clickable" style="padding:10px 14px;flex:1;text-align:center" @click=${() => this.fire('navigate-tab', 'operations')}>
          <div class="gov-label">Operations</div>
          <div style="font-size:12px;color:var(--v-fg)">\u2699 Manage</div>
        </div>
      </div>`;
  }

  private _renderColonyCards(cols: ReturnType<typeof allColonies>) {
    const running = cols.filter(c => c.status === 'running');
    if (running.length === 0) return nothing;
    return html`
      <div class="s-label">Active Colonies</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-bottom:14px">
        ${running.map(c => html`
          <div class="glass clickable" style="padding:8px 10px" @click=${() => this.fire('navigate', c.id)}>
            <div style="display:flex;align-items:center;gap:5px">
              <span style="width:6px;height:6px;border-radius:50%;background:var(--v-green, #22c55e)"></span>
              <span style="font-size:10.5px;font-family:var(--f-mono);color:var(--v-fg);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</span>
            </div>
            <div style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim);margin-top:2px">${c.status} \u00B7 R${(c as any).rounds ?? 0}</div>
          </div>
        `)}
      </div>
    `;
  }

  private _modelOptions(current: string | null): string[] {
    const registry = this.runtimeConfig?.models?.registry ?? [];
    const options = registry
      .map(model => model.address)
      .filter((address): address is string => Boolean(address));
    if (current && !options.includes(current)) {
      options.push(current);
    }
    return [...new Set(options)].sort((a, b) => a.localeCompare(b));
  }

  private saveModelEdit(casteId: string, value: string) {
    this.fire('update-config', {
      field: `${casteId}_model`,
      value: value || null,
    });
  }

  private saveGovEdit() {
    if (this.govStrategy) this.fire('update-config', { field: 'strategy', value: this.govStrategy });
    const budget = parseFloat(this.govBudget);
    if (!isNaN(budget)) this.fire('update-config', { field: 'budget', value: budget });
    this.editingGov = false;
  }

  private fire(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-workspace-config': FcWorkspaceConfig; }
}
