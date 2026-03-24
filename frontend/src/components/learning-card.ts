import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface LearningSummary {
  learned_template_count: number;
  total_template_count: number;
  top_template: { id: string; name: string; use_count: number } | null;
  knowledge_entry_count: number;
  quality_trend: number[];
}

@customElement('fc-learning-card')
export class FcLearningCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .card { padding: 12px; }
    .card-header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 8px;
    }
    .card-title {
      font-family: var(--f-display); font-size: 12px; font-weight: 600;
      color: var(--v-fg); letter-spacing: -0.02em;
    }
    .card-icon { font-size: 12px; filter: drop-shadow(0 0 4px var(--v-accent-glow)); }
    .stat-row {
      display: flex; gap: 12px; font-size: 10px; font-family: var(--f-mono);
      color: var(--v-fg-muted); font-feature-settings: 'tnum'; flex-wrap: wrap;
    }
    .stat-val { color: var(--v-fg); font-weight: 600; }
    .top-tmpl {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-top: 6px; padding: 4px 8px; border-radius: 4px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
    }
    .tmpl-name { color: var(--v-accent); font-weight: 600; }
    .trend-bar {
      display: flex; align-items: flex-end; gap: 2px; height: 20px; margin-top: 6px;
    }
    .trend-col {
      flex: 1; min-width: 3px; max-width: 12px; border-radius: 1px 1px 0 0;
      transition: height 0.3s;
    }
    .empty-state {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      padding: 8px 0;
    }
  `];

  @property() workspaceId = '';
  @state() private summary: LearningSummary | null = null;
  @state() private failed = false;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) void this._fetch();
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/learning-summary`,
      );
      if (res.ok) {
        this.summary = await res.json();
        this.failed = false;
      } else {
        this.failed = true;
      }
    } catch {
      this.failed = true;
    }
  }

  render() {
    if (this.failed) {
      return html`<div class="glass card">
        <div class="card-header">
          <span class="card-icon">\u2726</span>
          <span class="card-title">Learning Loop</span>
        </div>
        <div class="empty-state">Unavailable</div>
      </div>`;
    }
    const s = this.summary;
    if (!s) return nothing;

    const isEmpty = s.learned_template_count === 0
      && s.knowledge_entry_count === 0
      && s.quality_trend.length === 0;

    return html`
      <div class="glass card">
        <div class="card-header">
          <span class="card-icon">\u2726</span>
          <span class="card-title">Learning Loop</span>
        </div>
        ${isEmpty
          ? html`<div class="empty-state">No learned templates or knowledge entries yet.</div>`
          : html`
            <div class="stat-row">
              <span><span class="stat-val">${s.learned_template_count}</span> learned templates</span>
              <span><span class="stat-val">${s.knowledge_entry_count}</span> entries</span>
            </div>
            ${s.top_template ? html`
              <div class="top-tmpl">
                Top: <span class="tmpl-name">${s.top_template.name}</span>
                \u00B7 ${s.top_template.use_count} uses
              </div>
            ` : nothing}
            ${s.quality_trend.length > 0 ? html`
              <div class="trend-bar">
                ${s.quality_trend.map(q => {
                  const h = Math.max(2, q * 20);
                  const color = q >= 0.7 ? 'var(--v-success)' : q >= 0.4 ? 'var(--v-warn)' : 'var(--v-accent)';
                  return html`<div class="trend-col" style="height:${h}px;background:${color}" title="${(q * 100).toFixed(0)}%"></div>`;
                })}
              </div>
            ` : nothing}
          `}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-learning-card': FcLearningCard; }
}
