import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { providerColor } from '../helpers.js';
import type { CasteDefinition, TreeNode, RuntimeConfig } from '../types.js';
import type { CasteRecipePayload } from './caste-editor.js';
import './atoms.js';

@customElement('fc-castes-view')
export class FcCastesView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; gap: 14px; height: 100%; overflow: hidden; }
    .list {
      width: 150px; flex-shrink: 0; background: var(--v-surface); border-radius: 10px;
      border: 1px solid var(--v-border); overflow: hidden; display: flex; flex-direction: column;
    }
    .list-header {
      padding: 8px 12px; border-bottom: 1px solid var(--v-border);
      font-family: var(--f-display); font-size: 11px; font-weight: 600;
      color: var(--v-fg); display: flex; align-items: center; justify-content: space-between;
    }
    .list-items { flex: 1; overflow: auto; }
    .list-item {
      padding: 7px 12px; cursor: pointer; display: flex; align-items: center; gap: 6px;
      border-left: 2px solid transparent; transition: background 0.15s;
    }
    .list-item.active { border-left-color: var(--v-accent); }
    .list-icon { font-size: 11px; }
    .list-name { font-size: 10.5px; font-weight: 400; }
    .detail { flex: 1; overflow: auto; }
    .detail-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .detail-icon { font-size: 24px; }
    .detail-name { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .detail-desc { font-size: 11px; color: var(--v-fg-muted); margin-bottom: 16px; line-height: 1.4; }
    .default-box { padding: 12px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
    .provider-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
    .default-model { font-family: var(--f-mono); font-size: 11.5px; color: var(--v-fg); }
    .ws-row { display: flex; align-items: center; gap: 7px; padding: 4px 0; border-bottom: 1px solid var(--v-border); }
    .ws-icon { font-size: 9px; color: var(--v-accent); }
    .ws-name { font-size: 10.5px; color: var(--v-fg-muted); width: 120px; }
    .ws-model { font-family: var(--f-mono); font-size: 10px; }
    .tier-section { margin-top: 14px; }
    .tier-row {
      display: flex; align-items: center; gap: 8px; padding: 3px 0;
      font-size: 10px; font-family: var(--f-mono);
    }
    .tier-name { width: 65px; color: var(--v-fg-muted); text-transform: capitalize; }
    .tier-model { color: var(--v-fg); }
    .tier-inherit { color: var(--v-fg-dim); font-style: italic; }
    .recipe-meta {
      margin-top: 14px; font-size: 9.5px; font-family: var(--f-mono);
      color: var(--v-fg-dim); display: flex; gap: 12px; flex-wrap: wrap;
    }
    .edit-actions { margin-top: 12px; display: flex; gap: 6px; }
    .add-btn {
      font-size: 10px; cursor: pointer; color: var(--v-fg-dim);
      padding: 2px 6px; border-radius: 4px; transition: color 0.15s;
    }
    .add-btn:hover { color: var(--v-accent); }
  `];

  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: Array }) tree: TreeNode[] = [];
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @state() private selected = 'queen';
  @state() private recipes: Record<string, CasteRecipePayload> = {};

  connectedCallback() {
    super.connectedCallback();
    void this._fetchRecipes();
  }

  private async _fetchRecipes() {
    try {
      const resp = await fetch('/api/v1/castes');
      if (resp.ok) {
        this.recipes = await resp.json();
      }
    } catch { /* best-effort */ }
  }

  refresh() {
    void this._fetchRecipes();
  }

  render() {
    const c = this.castes.find(x => x.id === this.selected);
    const defaults = this.runtimeConfig?.models?.defaults as Record<string, string> | undefined;
    const recipe = this.recipes[this.selected];

    return html`
      <div class="list">
        <div class="list-header">
          Castes
          <span class="add-btn" title="New caste"
            @click=${() => this._fire('new-caste', null)}>+</span>
        </div>
        <div class="list-items">
          ${this.castes.map(x => html`
            <div class="list-item ${this.selected === x.id ? 'active' : ''}"
              style="background:${this.selected === x.id ? `${x.color}0C` : 'transparent'}"
              @click=${() => { this.selected = x.id; }}>
              <span class="list-icon"
                style="filter:${this.selected === x.id ? `drop-shadow(0 0 2px ${x.color}35)` : 'none'}">${x.icon}</span>
              <span class="list-name"
                style="color:${this.selected === x.id ? 'var(--v-fg)' : 'var(--v-fg-muted)'};font-weight:${this.selected === x.id ? 500 : 400}">${x.name}</span>
            </div>
          `)}
        </div>
      </div>
      ${c ? html`
        <div class="detail">
          <div class="detail-header">
            <span class="detail-icon" style="filter:drop-shadow(0 0 5px ${c.color}35)">${c.icon}</span>
            <h2 class="detail-name">${c.name}</h2>
          </div>
          <p class="detail-desc">${c.desc}</p>

          ${recipe ? html`
            <div class="recipe-meta">
              <span>temp: ${recipe.temperature}</span>
              <span>iterations: ${recipe.max_iterations}</span>
              <span>base time: ${recipe.max_execution_time_s}s</span>
              <span>base tools: ${recipe.base_tool_calls_per_iteration ?? 10}/iter</span>
              <span>tools: ${recipe.tools.join(', ') || 'none'}</span>
            </div>
          ` : nothing}

          <div class="s-label" style="margin-top:14px">Cascade Default</div>
          <div class="glass default-box">
            <span class="provider-dot" style="background:${providerColor(defaults?.[c.id])}"></span>
            <span class="default-model">${defaults?.[c.id] ?? 'unset'}</span>
          </div>

          ${recipe ? html`
            <div class="tier-section">
              <div class="s-label">Tier Model Defaults</div>
              <div class="glass" style="padding:12px">
                ${['flash', 'light', 'standard', 'heavy'].map(tier => {
                  const model = recipe.tier_models[tier];
                  const fallback = defaults?.[c.id];
                  return html`
                    <div class="tier-row">
                      <span class="tier-name">${tier}</span>
                      ${model
                        ? html`
                          <span class="provider-dot" style="background:${providerColor(model)}"></span>
                          <span class="tier-model">${model}</span>`
                        : html`<span class="tier-inherit">\u2192 ${fallback ?? 'unset'}</span>`
                      }
                    </div>`;
                })}
              </div>
            </div>
          ` : nothing}

          <div class="s-label" style="margin-top:14px">Workspace Overrides</div>
          <div class="glass" style="padding:12px">
            ${this.tree.length === 0 ? html`<div style="font-size:10px;color:var(--v-fg-dim);font-family:var(--f-mono)">No workspaces</div>` : nothing}
            ${this.tree.map(ws => {
              const cfg = (ws as any).config ?? {};
              const val = cfg[`${c.id}Model`] ?? cfg[`${c.id}_model`] ?? null;
              return html`
                <div class="ws-row">
                  <span class="ws-icon">\u25A3</span>
                  <span class="ws-name">${ws.name}</span>
                  <span class="ws-model" style="color:${val ? 'var(--v-fg)' : 'var(--v-fg-dim)'}">${val ?? 'default (inherit)'}</span>
                  ${val ? html`<fc-pill .color=${c.color} sm>override</fc-pill>` : nothing}
                </div>`;
            })}
          </div>

          <div class="edit-actions">
            <fc-btn variant="secondary" sm
              @click=${() => this._fire('edit-caste', { id: c.id, recipe })}
            >Edit Recipe</fc-btn>
          </div>
        </div>
      ` : nothing}`;
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(
      new CustomEvent(name, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-castes-view': FcCastesView; }
}
