import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { TemplateInfo } from '../types.js';
import './atoms.js';

@customElement('fc-template-browser')
export class FcTemplateBrowser extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 860px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .template-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .template-card { padding: 14px; cursor: pointer; }
    .card-top { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
    .card-name { font-family: var(--f-display); font-size: 14px; font-weight: 600; color: var(--v-fg); }
    .card-uses { font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-muted); margin-left: auto; font-feature-settings: 'tnum'; }
    .card-desc { font-size: 10.5px; color: var(--v-fg-muted); line-height: 1.4; margin-bottom: 8px; }
    .card-castes { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
    .caste-entry { display: flex; align-items: center; gap: 3px; }
    .caste-icon { font-size: 11px; }
    .caste-name { font-size: 9px; color: var(--v-fg-muted); }
    .card-bottom { display: flex; gap: 4px; align-items: center; }
    .card-spec { margin-left: auto; font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-muted); font-feature-settings: 'tnum'; }
    .source-link { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); cursor: pointer; }
    .source-link:hover { color: var(--v-accent); }
    .empty-state {
      padding: 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px;
    }
    .loading { padding: 16px; text-align: center; color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); }
    .card-actions {
      display: flex; gap: 4px; margin-top: 8px; padding-top: 6px;
      border-top: 1px solid var(--v-border);
    }
    .card-action {
      font-size: 8px; font-family: var(--f-mono); padding: 2px 7px;
      border-radius: 5px; cursor: pointer; color: var(--v-fg-dim);
      border: 1px solid var(--v-border); background: transparent;
      transition: all 0.15s; text-transform: uppercase; letter-spacing: 0.06em;
    }
    .card-action:hover {
      border-color: var(--v-border-hover); color: var(--v-fg-muted);
    }
    .title-actions { margin-left: auto; }
    .tag-chip {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px;
      border-radius: 5px; background: rgba(163,130,250,0.1); color: #A78BFA;
    }
    .tags-row { display: flex; gap: 3px; margin-bottom: 4px; flex-wrap: wrap; }
  `];

  // Caste display mapping — mirrors the prototype's CASTES array
  private static readonly CASTE_ICONS: Record<string, { icon: string; color: string; name: string }> = {
    queen: { icon: '\u265B', color: '#E8581A', name: 'Queen' },
    coder: { icon: '</>', color: '#2DD4A8', name: 'Coder' },
    reviewer: { icon: '\u2713', color: '#A78BFA', name: 'Reviewer' },
    researcher: { icon: '\u25CE', color: '#5B9CF5', name: 'Researcher' },
    archivist: { icon: '\u29EB', color: '#F5B731', name: 'Archivist' },
  };

  @property({ type: Boolean }) expanded = false;
  @state() private templates: TemplateInfo[] = [];
  @state() private loading = true;

  connectedCallback() {
    super.connectedCallback();
    void this.fetchTemplates();
  }

  private async fetchTemplates() {
    this.loading = true;
    try {
      const resp = await fetch('/api/v1/templates');
      if (resp.ok) {
        const data = await resp.json();
        this.templates = (data as any[]).map(t => ({
          id: t.template_id ?? t.templateId ?? t.id,
          name: t.name,
          description: t.description ?? '',
          castes: (t.castes ?? t.caste_names ?? t.casteNames ?? []).map((c: any) =>
            typeof c === 'string' ? { caste: c, tier: 'standard', count: 1 } : c
          ),
          strategy: t.strategy ?? 'stigmergic',
          budgetLimit: t.budget_limit ?? t.budgetLimit ?? undefined,
          maxRounds: t.max_rounds ?? t.maxRounds ?? undefined,
          sourceColonyId: t.source_colony_id ?? t.sourceColonyId ?? null,
          useCount: t.use_count ?? t.useCount ?? 0,
          tags: t.tags ?? [],
          version: t.version ?? 1,
        }));
      } else {
        this.templates = [];
      }
    } catch {
      this.templates = [];
    }
    this.loading = false;
  }

  refresh() {
    void this.fetchTemplates();
  }

  render() {
    return html`
      <div class="title-row">
        <h2><fc-gradient-text>Colony Templates</fc-gradient-text></h2>
        ${!this.loading ? html`<fc-pill color="var(--v-fg-dim)">${this.templates.length}</fc-pill>` : nothing}
        <div class="title-actions">
          <fc-btn variant="primary" sm @click=${() => this._fireNew()}>+ New Template</fc-btn>
        </div>
      </div>
      ${this.loading
        ? html`<div class="loading">Loading templates\u2026</div>`
        : this.templates.length === 0
          ? html`<div class="glass empty-state">No templates yet. Create one here or save a completed colony as a starting point.</div>`
          : html`<div class="template-grid">${this.templates.map(t => this.renderTemplate(t))}</div>`}
    `;
  }

  private renderTemplate(t: TemplateInfo) {
    const budget = t.budgetLimit != null ? `$${t.budgetLimit.toFixed(2)}` : '';
    const rounds = t.maxRounds != null ? `${t.maxRounds}R` : '';
    const spec = [budget, rounds, t.strategy].filter(Boolean).join(' \u00B7 ');

    return html`
      <div class="glass clickable template-card" @click=${() => this.selectTemplate(t)}>
        <div class="card-top">
          <span class="card-name">${t.name}</span>
          <span class="card-uses">${t.useCount} uses</span>
        </div>
        ${t.description ? html`<div class="card-desc">${t.description}</div>` : nothing}
        <div class="card-castes">
          ${t.castes.map(s => {
            const cn = s.caste;
            const info = FcTemplateBrowser.CASTE_ICONS[cn];
            return info ? html`
              <div class="caste-entry">
                <span class="caste-icon" style="filter:drop-shadow(0 0 2px ${info.color}30)">${info.icon}</span>
                <span class="caste-name">${info.name}</span>
              </div>
            ` : html`<fc-pill color="var(--v-fg-dim)" sm>${cn}</fc-pill>`;
          })}
        </div>
        ${(t.tags?.length ?? 0) > 0 ? html`
          <div class="tags-row">
            ${t.tags!.map(tag => html`<span class="tag-chip">${tag}</span>`)}
          </div>` : nothing}
        <div class="card-bottom">
          ${t.sourceColonyId ? html`
            <span class="source-link" @click=${(e: Event) => { e.stopPropagation(); this.navigateToSource(t.sourceColonyId!); }}
              title="Navigate to source colony">\u2192 source</span>
          ` : nothing}
          ${spec ? html`<span class="card-spec">${spec}</span>` : nothing}
        </div>
        <div class="card-actions">
          <span class="card-action" @click=${(e: Event) => { e.stopPropagation(); this._fireEdit(t); }}>Edit</span>
          <span class="card-action" @click=${(e: Event) => { e.stopPropagation(); this._fireDuplicate(t); }}>Duplicate</span>
        </div>
      </div>`;
  }

  private selectTemplate(t: TemplateInfo) {
    this.dispatchEvent(new CustomEvent('select-template', {
      detail: t,
      bubbles: true,
      composed: true,
    }));
  }

  private navigateToSource(colonyId: string) {
    this.dispatchEvent(new CustomEvent('navigate', {
      detail: colonyId,
      bubbles: true,
      composed: true,
    }));
  }

  private _fireNew() {
    this.dispatchEvent(new CustomEvent('new-template', {
      bubbles: true, composed: true,
    }));
  }

  private _fireEdit(t: TemplateInfo) {
    this.dispatchEvent(new CustomEvent('edit-template', {
      detail: t, bubbles: true, composed: true,
    }));
  }

  private _fireDuplicate(t: TemplateInfo) {
    this.dispatchEvent(new CustomEvent('duplicate-template', {
      detail: t, bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-template-browser': FcTemplateBrowser; }
}
