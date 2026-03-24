import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

/** Matches KnowledgeInsight from proactive_intelligence.py */
interface Insight {
  severity: 'info' | 'attention' | 'action_required';
  category: string;
  title: string;
  detail: string;
  affectedEntries: string[];
  suggestedAction: string;
}

/** Matches ProactiveBriefing from proactive_intelligence.py */
interface Briefing {
  workspaceId: string;
  generatedAt: string;
  insights: Insight[];
  totalEntries: number;
  entriesByStatus: Record<string, number>;
  avgConfidence: number;
  predictionErrorRate: number;
  activeClusters: number;
  federationSummary: Record<string, unknown>;
}

/** Matches ForageCycleSummary from projections.py */
interface ForageCycle {
  forage_request_seq: number;
  mode: string;
  reason: string;
  queries_issued: number;
  pages_fetched: number;
  pages_rejected: number;
  entries_admitted: number;
  entries_deduplicated: number;
  duration_ms: number;
  error: string;
  timestamp: string;
}

/** Matches DomainOverrideProjection from projections.py */
interface DomainOverride {
  domain: string;
  action: string;
  actor: string;
  reason: string;
  timestamp: string;
}

/** Forager activity data from the cycles + domains endpoints */
interface ForagerActivity {
  cycles: ForageCycle[];
  total: number;
  trustedDomains: string[];
  distrustedDomains: string[];
}

@customElement('fc-proactive-briefing')
export class FcProactiveBriefing extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; max-width: 960px; margin-bottom: 16px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .generated-at { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-left: auto; }
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; }
    .stat-card {
      padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,0.02);
      border: 1px solid var(--v-border); text-align: center;
    }
    .stat-value { font-family: var(--f-mono); font-size: 18px; font-weight: 700; color: var(--v-fg); font-feature-settings: 'tnum'; }
    .stat-label { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
    .insight-list { display: flex; flex-direction: column; gap: 6px; }
    .insight-card { padding: 12px; }
    .insight-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
    .insight-title { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .insight-detail { font-size: 11.5px; color: var(--v-fg-muted); line-height: 1.45; margin-bottom: 6px; }
    .insight-action {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-accent); padding: 4px 8px;
      border-radius: 6px; background: rgba(232,88,26,0.06); border: 1px solid rgba(232,88,26,0.15);
      display: inline-block;
    }
    .severity-badge {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600; padding: 2px 6px;
      border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px;
    }
    .severity-action_required { background: rgba(240,100,100,0.15); color: var(--v-danger); }
    .severity-attention { background: rgba(245,183,49,0.15); color: var(--v-warn); }
    .severity-info { background: rgba(91,156,245,0.15); color: var(--v-blue); }
    .category-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border);
    }
    .affected-ids { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 4px; }
    .empty-state { padding: 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px; }
    .dismiss-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 6px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); margin-top: 4px; transition: all 0.15s;
    }
    .dismiss-btn:hover { border-color: rgba(240,100,100,0.3); color: var(--v-danger); }
    .insight-action-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 3px 10px; border-radius: 6px;
      cursor: pointer; border: 1px solid rgba(232,88,26,0.2); background: rgba(232,88,26,0.06);
      color: var(--v-accent); transition: all 0.15s; margin-top: 6px; margin-right: 4px;
    }
    .insight-action-btn:hover { background: rgba(232,88,26,0.12); border-color: rgba(232,88,26,0.35); }
    .status-grid { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
    .status-chip {
      font-size: 9px; font-family: var(--f-mono); padding: 3px 8px; border-radius: 6px;
      border: 1px solid var(--v-border); color: var(--v-fg-muted);
    }
    .refresh-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s;
    }
    .refresh-btn:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }
    .forager-section { margin-bottom: 14px; }
    .forager-header {
      font-family: var(--f-display); font-size: 13px; font-weight: 600;
      color: var(--v-fg); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
    }
    .forager-cycle-row {
      display: grid; grid-template-columns: 1fr auto auto auto;
      gap: 8px; align-items: center; padding: 6px 10px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid var(--v-border);
    }
    .forager-cycle-row:last-child { border-bottom: none; }
    .forager-mode { font-size: 8px; padding: 1px 5px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px; }
    .forager-mode-reactive { background: rgba(245,183,49,0.15); color: var(--v-warn); }
    .forager-mode-proactive { background: rgba(91,156,245,0.15); color: var(--v-blue); }
    .forager-mode-operator { background: rgba(232,88,26,0.12); color: var(--v-accent); }
    .forager-stat { text-align: right; }
    .forager-domains { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
    .domain-chip {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 6px; border-radius: 4px;
      border: 1px solid var(--v-border); display: inline-flex; align-items: center; gap: 4px;
    }
    .domain-trusted { color: var(--v-green, #4caf50); border-color: rgba(76,175,80,0.3); }
    .domain-distrusted { color: var(--v-danger); border-color: rgba(240,100,100,0.3); }
    .domain-action {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 4px; border-radius: 3px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; line-height: 1;
    }
    .domain-action:hover { border-color: rgba(232,88,26,0.3); color: var(--v-accent); }
  `];

  @property() workspaceId = '';
  @state() private briefing: Briefing | null = null;
  @state() private foragerActivity: ForagerActivity | null = null;
  @state() private loading = true;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchAll();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId')) void this._fetchAll();
  }

  private async _fetchAll() {
    this.loading = true;
    await Promise.all([this._fetchBriefing(), this._fetchForagerActivity()]);
    this.loading = false;
  }

  private async _fetchBriefing() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/briefing`);
      if (res.ok) {
        const data = await res.json();
        this.briefing = {
          workspaceId: data.workspace_id ?? '',
          generatedAt: data.generated_at ?? '',
          insights: (data.insights ?? []).map((i: Record<string, unknown>) => ({
            severity: i.severity as string ?? 'info',
            category: i.category as string ?? '',
            title: i.title as string ?? '',
            detail: i.detail as string ?? '',
            affectedEntries: (i.affected_entries as string[]) ?? [],
            suggestedAction: i.suggested_action as string ?? '',
          })),
          totalEntries: data.total_entries as number ?? 0,
          entriesByStatus: (data.entries_by_status ?? {}) as Record<string, number>,
          avgConfidence: data.avg_confidence as number ?? 0,
          predictionErrorRate: data.prediction_error_rate as number ?? 0,
          activeClusters: data.active_clusters as number ?? 0,
          federationSummary: (data.federation_summary ?? {}) as Record<string, unknown>,
        };
      }
    } catch { /* endpoint may not exist yet */ }
  }

  private async _fetchForagerActivity() {
    try {
      const ws = encodeURIComponent(this.workspaceId);
      const [cyclesRes, domainsRes] = await Promise.all([
        fetch(`/api/v1/workspaces/${ws}/forager/cycles?limit=5`),
        fetch(`/api/v1/workspaces/${ws}/forager/domains`),
      ]);
      const cycles: ForageCycle[] = [];
      let total = 0;
      if (cyclesRes.ok) {
        const data = await cyclesRes.json();
        cycles.push(...(data.cycles ?? []));
        total = data.total ?? 0;
      }
      const trusted: string[] = [];
      const distrusted: string[] = [];
      if (domainsRes.ok) {
        const data = await domainsRes.json();
        const overrides = (data.overrides ?? {}) as Record<string, DomainOverride>;
        for (const [domain, ovr] of Object.entries(overrides)) {
          if (ovr.action === 'trust') trusted.push(domain);
          else if (ovr.action === 'distrust') distrusted.push(domain);
        }
      }
      this.foragerActivity = { cycles, total, trustedDomains: trusted, distrustedDomains: distrusted };
    } catch {
      this.foragerActivity = null;
    }
  }

  render() {
    return html`
      <div class="title-row">
        <h2>Intelligence Briefing</h2>
        <button class="refresh-btn" @click=${() => void this._fetchAll()}>Refresh</button>
        ${this.briefing ? html`
          <span class="generated-at">Generated: ${this.briefing.generatedAt}</span>
        ` : nothing}
      </div>

      ${this.loading ? html`<div class="empty-state">Loading briefing\u2026</div>` : html`
        ${this.briefing ? html`
          ${this._renderStats()}
          ${this._renderForagerActivity()}
          ${this._renderInsights()}
        ` : html`<div class="glass empty-state">No briefing data available.</div>`}
      `}
    `;
  }

  private _renderStats() {
    const b = this.briefing!;
    return html`
      <div class="stat-grid">
        <div class="glass stat-card">
          <div class="stat-value">${b.totalEntries}</div>
          <div class="stat-label">Entries</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${(b.avgConfidence * 100).toFixed(0)}%</div>
          <div class="stat-label">Avg Confidence</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${b.insights.length}</div>
          <div class="stat-label">Insights</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${(b.predictionErrorRate * 100).toFixed(0)}%</div>
          <div class="stat-label">Pred. Error Rate</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${b.activeClusters}</div>
          <div class="stat-label">Active Clusters</div>
        </div>
      </div>

      <div class="status-grid">
        ${Object.entries(b.entriesByStatus).map(([status, count]) => html`
          <span class="status-chip">${status}: ${count}</span>
        `)}
      </div>
    `;
  }

  private _timeAgo(iso: string): string {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  private _renderForagerActivity() {
    const fa = this.foragerActivity;
    if (!fa) return nothing;
    const hasCycles = fa.cycles.length > 0;
    const hasDomains = fa.trustedDomains.length > 0 || fa.distrustedDomains.length > 0;
    if (!hasCycles && !hasDomains) {
      return html`
        <div class="forager-section">
          <div class="forager-header">
            <fc-pill class="severity-info" sm>web</fc-pill> Forager Activity
          </div>
          <div class="glass" style="padding:10px;font-size:11px;color:var(--v-fg-muted)">
            No forage cycles recorded yet.
          </div>
        </div>
      `;
    }
    return html`
      <div class="forager-section">
        <div class="forager-header">
          <fc-pill class="severity-info" sm>web</fc-pill>
          Forager Activity
          ${fa.total > 0 ? html`<span style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim)">${fa.total} total cycles</span>` : nothing}
        </div>
        ${hasCycles ? html`
          <div class="glass" style="padding:4px 0">
            ${fa.cycles.map(c => html`
              <div class="forager-cycle-row">
                <div>
                  <span class="forager-mode forager-mode-${c.mode}">${c.mode}</span>
                  <span style="margin-left:6px">${c.reason || '—'}</span>
                </div>
                <div class="forager-stat">${c.pages_fetched} fetched</div>
                <div class="forager-stat">${c.entries_admitted} admitted</div>
                <div class="forager-stat" style="color:var(--v-fg-dim)">${this._timeAgo(c.timestamp)}</div>
              </div>
            `)}
          </div>
        ` : nothing}
        ${hasDomains ? html`
          <div class="forager-domains">
            ${fa.trustedDomains.map(d => html`
              <span class="domain-chip domain-trusted">
                ${d}
                <button class="domain-action" title="Distrust ${d}" @click=${(e: Event) => { e.stopPropagation(); void this._domainOverride(d, 'distrust'); }}>\u2715</button>
                <button class="domain-action" title="Reset ${d}" @click=${(e: Event) => { e.stopPropagation(); void this._domainOverride(d, 'reset'); }}>\u21BA</button>
              </span>
            `)}
            ${fa.distrustedDomains.map(d => html`
              <span class="domain-chip domain-distrusted">
                ${d}
                <button class="domain-action" title="Trust ${d}" @click=${(e: Event) => { e.stopPropagation(); void this._domainOverride(d, 'trust'); }}>\u2713</button>
                <button class="domain-action" title="Reset ${d}" @click=${(e: Event) => { e.stopPropagation(); void this._domainOverride(d, 'reset'); }}>\u21BA</button>
              </span>
            `)}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private async _domainOverride(domain: string, action: 'trust' | 'distrust' | 'reset') {
    try {
      const ws = encodeURIComponent(this.workspaceId);
      await fetch(`/api/v1/workspaces/${ws}/forager/domain-override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, action, reason: `Operator ${action} via briefing` }),
      });
      void this._fetchForagerActivity();
    } catch { /* best-effort */ }
  }

  private async _dismissAutonomy(insight: Insight) {
    // Extract category from title (e.g. "Earned autonomy: promote 'coverage'" -> "coverage")
    const match = insight.title.match(/'([^']+)'/);
    const category = match?.[1] ?? insight.category;
    try {
      const wsId = this.workspaceId;
      await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/dismiss-autonomy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category }),
      });
      void this._fetchBriefing();
    } catch { /* ignore */ }
  }

  /** Wave 55: action buttons mapped to insight categories. */
  private _renderInsightActions(insight: Insight) {
    const cat = insight.category;
    const actions: { label: string; action: string }[] = [];
    if (cat === 'coverage_gap' || cat === 'coverage') {
      actions.push({ label: '\u2192 Research gap', action: 'research-gap' });
    }
    if (cat === 'stagnation' || cat === 'branching_stagnation') {
      actions.push({ label: '\u2192 Inspect colony', action: 'inspect-stagnation' });
    }
    if (cat === 'outcome_digest' || cat === 'diminishing_rounds' || cat === 'cost_outlier') {
      actions.push({ label: '\u2192 View outcomes', action: 'view-outcomes' });
    }
    if (cat === 'knowledge_roi') {
      actions.push({ label: '\u2192 Browse knowledge', action: 'browse-knowledge' });
    }
    if (cat === 'contradiction') {
      actions.push({ label: '\u2192 Resolve contradiction', action: 'resolve-contradiction' });
    }
    if (cat === 'confidence_decline' || cat === 'stale_cluster') {
      actions.push({ label: '\u2192 Review entries', action: 'review-entries' });
    }
    if (actions.length === 0) return nothing;
    return actions.map(a => html`
      <button class="insight-action-btn"
        @click=${(e: Event) => { e.stopPropagation(); this._dispatchAction(a.action, insight); }}
      >${a.label}</button>
    `);
  }

  private _dispatchAction(action: string, insight: Insight) {
    this.dispatchEvent(new CustomEvent('briefing-action', {
      detail: { action, category: insight.category, title: insight.title, affectedEntries: insight.affectedEntries },
      bubbles: true,
      composed: true,
    }));
  }

  private _renderInsights() {
    const b = this.briefing!;
    if (b.insights.length === 0) {
      return html`<div class="glass empty-state" style="padding:14px;text-align:left">
        Knowledge system healthy — no issues detected
      </div>`;
    }

    // Sort: action_required first, then attention, then info
    const sorted = [...b.insights].sort((a, b) => {
      const order: Record<string, number> = { action_required: 0, attention: 1, info: 2 };
      return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
    });

    return html`
      <div class="insight-list">
        ${sorted.map(insight => html`
          <div class="glass insight-card">
            <div class="insight-header">
              <span class="severity-badge severity-${insight.severity}">${insight.severity.replace('_', ' ')}</span>
              <span class="category-badge">${insight.category}</span>
              <span class="insight-title">${insight.title}</span>
            </div>
            <div class="insight-detail">${insight.detail}</div>
            ${insight.suggestedAction ? html`
              <div class="insight-action">\u2192 ${insight.suggestedAction}</div>
            ` : nothing}
            <div>
              ${this._renderInsightActions(insight)}
              ${insight.category === 'earned_autonomy' ? html`
                <button class="dismiss-btn" @click=${(e: Event) => { e.stopPropagation(); void this._dismissAutonomy(insight); }}>Dismiss</button>
              ` : nothing}
            </div>
            ${insight.affectedEntries.length > 0 ? html`
              <div class="affected-ids">Affected: ${insight.affectedEntries.slice(0, 5).join(', ')}${insight.affectedEntries.length > 5 ? ` +${insight.affectedEntries.length - 5} more` : ''}</div>
            ` : nothing}
          </div>
        `)}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-proactive-briefing': FcProactiveBriefing; }
}
