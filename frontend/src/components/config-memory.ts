import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

/** Matches ConfigRecommendation from proactive_intelligence.py */
interface ConfigRecommendation {
  dimension: string;
  recommended_value: string;
  evidence_summary: string;
  sample_size: number;
  avg_quality: number;
  confidence: 'high' | 'moderate' | 'low';
}

/** Matches ConfigOverrideRecord from projections.py */
interface ConfigOverride {
  suggestion_category: string;
  original_config: Record<string, unknown>;
  overridden_config: Record<string, unknown>;
  reason: string;
  actor: string;
  timestamp: string;
}

/**
 * Wave 50: Learned template info from Team 1's TemplateProjection.
 * Fetched from /api/v1/workspaces/{id}/templates endpoint.
 * Operator-authored templates come from the same endpoint with learned=false.
 */
interface TemplateSummary {
  id: string;
  name: string;
  description: string;
  strategy: string;
  learned: boolean;
  task_category: string;
  success_count: number;
  failure_count: number;
  use_count: number;
  max_rounds: number;
  budget_limit: number;
  fast_path: boolean;
  castes: { caste: string; tier: string; count: number }[];
}

/** Time-ago helper */
function timeAgo(iso: string): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

@customElement('fc-config-memory')
export class FcConfigMemory extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; max-width: 960px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .title-row h3 {
      font-family: var(--f-display); font-size: 14px; font-weight: 700;
      color: var(--v-fg); margin: 0;
    }
    .title-icon { font-size: 14px; color: var(--v-accent); }
    .refresh-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; margin-left: auto;
    }
    .refresh-btn:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }

    .rec-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; margin-bottom: 14px; }
    .rec-card { padding: 12px; }
    .rec-dimension {
      font-size: 8px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.1em; text-transform: uppercase;
      margin-bottom: 4px;
    }
    .rec-value {
      font-family: var(--f-mono); font-size: 14px; font-weight: 600;
      color: var(--v-fg); margin-bottom: 4px;
    }
    .rec-evidence {
      font-size: 10px; color: var(--v-fg-muted); line-height: 1.4; margin-bottom: 6px;
    }
    .rec-meta { display: flex; gap: 6px; align-items: center; }
    .confidence-badge {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600; padding: 2px 6px;
      border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px;
    }
    .confidence-high { background: rgba(45,212,168,0.15); color: var(--v-success); }
    .confidence-moderate { background: rgba(245,183,49,0.15); color: var(--v-warn); }
    .confidence-low { background: rgba(91,156,245,0.15); color: var(--v-blue); }
    .quality-bar {
      height: 3px; border-radius: 2px; background: rgba(255,255,255,0.05);
      flex: 1; overflow: hidden;
    }
    .quality-fill { height: 100%; border-radius: 2px; background: var(--v-success); transition: width 0.3s; }
    .sample-count {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      font-feature-settings: 'tnum';
    }

    /* Override history section */
    .history-section { margin-top: 14px; }
    .section-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase;
      margin-bottom: 6px; padding-bottom: 3px; border-bottom: 1px solid var(--v-border);
    }
    .override-list { display: flex; flex-direction: column; gap: 4px; }
    .override-card { padding: 8px 10px; font-size: 10px; }
    .override-header { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
    .override-category {
      font-family: var(--f-mono); font-weight: 600; font-size: 10px; color: var(--v-fg);
    }
    .override-time { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-left: auto; }
    .override-detail { color: var(--v-fg-muted); font-size: 10px; line-height: 1.4; }
    .override-arrow { color: var(--v-accent); font-family: var(--f-mono); }

    .empty-state { padding: 16px; text-align: center; color: var(--v-fg-muted); font-size: 11px; }

    /* Wave 50: Template section */
    .tpl-section { margin-bottom: 14px; }
    .tpl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
    .tpl-card { padding: 10px 12px; }
    .tpl-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
    .tpl-name {
      font-family: var(--f-display); font-size: 12px; font-weight: 600;
      color: var(--v-fg); flex: 1;
    }
    .tpl-badge {
      font-size: 7.5px; padding: 1px 5px; border-radius: 3px;
      font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    }
    .tpl-badge.learned { background: rgba(167,139,250,0.12); color: #A78BFA; }
    .tpl-badge.operator { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .tpl-desc {
      font-size: 10px; color: var(--v-fg-muted); line-height: 1.4; margin-bottom: 6px;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .tpl-meta { display: flex; gap: 8px; flex-wrap: wrap; font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .tpl-stat { display: flex; gap: 3px; align-items: center; }
    .tpl-stat .win { color: var(--v-success); font-weight: 600; }
    .tpl-stat .lose { color: var(--v-danger); font-weight: 600; }
    .tpl-stat .val { color: var(--v-fg); font-weight: 600; }
    .tpl-category {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 3px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border);
    }
    .tpl-castes {
      display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px;
    }
    .tpl-caste-slot {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 3px;
      border: 1px solid var(--v-border); background: rgba(255,255,255,0.02);
    }
    .tpl-caste-name { font-weight: 600; text-transform: capitalize; }
  `];

  @property() workspaceId = '';
  @state() private _recommendations: ConfigRecommendation[] = [];
  @state() private _overrides: ConfigOverride[] = [];
  @state() private _templates: TemplateSummary[] = [];
  @state() private _loading = true;
  @state() private _recsFailed = false;
  @state() private _overridesFailed = false;
  @state() private _templatesFailed = false;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchData();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) void this._fetchData();
  }

  private async _fetchData() {
    this._loading = true;
    this._recsFailed = false;
    this._overridesFailed = false;
    this._templatesFailed = false;
    await Promise.all([this._fetchRecommendations(), this._fetchOverrides(), this._fetchTemplates()]);
    this._loading = false;
  }

  private async _fetchRecommendations() {
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/config-recommendations`,
      );
      if (res.ok) {
        const data = await res.json();
        this._recommendations = (data.recommendations ?? []) as ConfigRecommendation[];
      } else {
        this._recsFailed = true;
      }
    } catch { this._recsFailed = true; }
  }

  private async _fetchOverrides() {
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/config-overrides`,
      );
      if (res.ok) {
        const data = await res.json();
        this._overrides = (data.overrides ?? []) as ConfigOverride[];
      } else {
        this._overridesFailed = true;
      }
    } catch { this._overridesFailed = true; }
  }

  /** Wave 50: Fetch templates (both operator-authored and learned) from Team 1's endpoint. */
  private async _fetchTemplates() {
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/templates`,
      );
      if (res.ok) {
        const data = await res.json();
        this._templates = (data.templates ?? []) as TemplateSummary[];
      } else {
        this._templatesFailed = true;
      }
    } catch { this._templatesFailed = true; }
  }

  render() {
    if (this._loading) {
      return html`<div class="glass empty-state" style="height:auto;padding:16px">Loading configuration memory\u2026</div>`;
    }

    const hasContent = this._recommendations.length > 0 || this._overrides.length > 0 || this._templates.length > 0;
    const hasFailed = this._recsFailed || this._overridesFailed || this._templatesFailed;
    if (!hasContent && !hasFailed) {
      return html`
        <div class="glass empty-state">
          No configuration data yet. Colony outcomes will surface recommendations here.
        </div>
      `;
    }

    return html`
      <div class="title-row">
        <span class="title-icon">\u2699</span>
        <h3>Configuration Intelligence</h3>
        <button class="refresh-btn" @click=${() => void this._fetchData()}>Refresh</button>
      </div>

      ${this._templates.length > 0 ? this._renderTemplates() : this._templatesFailed ? this._renderUnavailable('Templates') : nothing}
      ${this._recommendations.length > 0 ? this._renderRecommendations() : this._recsFailed ? this._renderUnavailable('Recommendations') : nothing}
      ${this._overrides.length > 0 ? this._renderOverrides() : this._overridesFailed ? this._renderUnavailable('Override History') : nothing}
    `;
  }

  /** Wave 50: Render learned and operator templates side by side. */
  private _renderTemplates() {
    // Sort: learned first, then operator. Within each group, most-used first.
    const sorted = [...this._templates].sort((a, b) => {
      if (a.learned !== b.learned) return a.learned ? -1 : 1;
      return (b.use_count ?? 0) - (a.use_count ?? 0);
    });
    const learnedCount = sorted.filter(t => t.learned).length;
    const operatorCount = sorted.length - learnedCount;
    return html`
      <div class="tpl-section">
        <div class="section-label">
          Templates
          ${learnedCount > 0 ? html` \u00B7 ${learnedCount} learned` : nothing}
          ${operatorCount > 0 ? html` \u00B7 ${operatorCount} operator` : nothing}
        </div>
        <div class="tpl-grid">
          ${sorted.map(t => html`
            <div class="glass tpl-card">
              <div class="tpl-header">
                <span class="tpl-name">${t.name}</span>
                <span class="tpl-badge ${t.learned ? 'learned' : 'operator'}">
                  ${t.learned ? 'learned' : 'operator'}
                </span>
              </div>
              ${t.description ? html`<div class="tpl-desc">${t.description}</div>` : nothing}
              <div class="tpl-meta">
                ${t.task_category ? html`<span class="tpl-category">${t.task_category}</span>` : nothing}
                <span class="tpl-stat">${t.strategy}</span>
                <span class="tpl-stat">
                  <span class="win">${t.success_count ?? 0}W</span>
                  /
                  <span class="lose">${t.failure_count ?? 0}L</span>
                </span>
                <span class="tpl-stat">
                  <span class="val">${t.use_count ?? 0}</span> uses
                </span>
                <span class="tpl-stat">
                  max <span class="val">${t.max_rounds ?? '?'}</span> rds
                </span>
                <span class="tpl-stat">
                  $<span class="val">${(t.budget_limit ?? 0).toFixed(2)}</span> budget
                </span>
                ${t.fast_path ? html`<span class="tpl-stat" style="color:var(--v-success)">fast-path</span>` : nothing}
              </div>
              ${t.castes && t.castes.length > 0 ? html`
                <div class="tpl-castes">
                  ${t.castes.map(s => html`
                    <span class="tpl-caste-slot">
                      <span class="tpl-caste-name">${s.caste}</span>
                      \u00D7${s.count} ${s.tier}
                    </span>
                  `)}
                </div>
              ` : nothing}
            </div>
          `)}
        </div>
      </div>
    `;
  }

  private _renderRecommendations() {
    return html`
      <div class="rec-grid">
        ${this._recommendations.map(r => html`
          <div class="glass rec-card">
            <div class="rec-dimension">${this._dimensionLabel(r.dimension)}</div>
            <div class="rec-value">${r.recommended_value}</div>
            <div class="rec-evidence">${r.evidence_summary}</div>
            <div class="rec-meta">
              <span class="confidence-badge confidence-${r.confidence}">${r.confidence}</span>
              <div class="quality-bar">
                <div class="quality-fill" style="width:${(r.avg_quality * 100).toFixed(0)}%"></div>
              </div>
              <span class="sample-count">n=${r.sample_size}</span>
            </div>
          </div>
        `)}
      </div>
    `;
  }

  private _renderOverrides() {
    const sorted = [...this._overrides].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
    return html`
      <div class="history-section">
        <div class="section-label">Override History</div>
        <div class="override-list">
          ${sorted.slice(0, 10).map(o => html`
            <div class="glass override-card">
              <div class="override-header">
                <span class="override-category">${o.suggestion_category}</span>
                <span class="override-time">${timeAgo(o.timestamp)}</span>
              </div>
              <div class="override-detail">
                ${JSON.stringify(o.original_config)}
                <span class="override-arrow"> \u2192 </span>
                ${JSON.stringify(o.overridden_config)}
                ${o.reason ? html` \u2014 <em>${o.reason}</em>` : nothing}
              </div>
            </div>
          `)}
        </div>
      </div>
    `;
  }

  private _renderUnavailable(section: string) {
    return html`
      <div class="glass" style="padding:10px 12px;margin-bottom:8px;opacity:0.6">
        <span style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">${section} \u2014 unavailable</span>
      </div>
    `;
  }

  private _dimensionLabel(dim: string): string {
    const labels: Record<string, string> = {
      strategy: 'Recommended Strategy',
      caste: 'Best Caste Composition',
      max_rounds: 'Optimal Round Range',
      model_tier: 'Best Model Tier',
    };
    return labels[dim] ?? dim;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-config-memory': FcConfigMemory; }
}
