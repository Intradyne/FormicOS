/**
 * Wave 72 Track 3: Knowledge health summary card.
 * Compact widget showing knowledge quality metrics for a workspace.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface KnowledgeEntry {
  entry_id: string;
  title: string;
  category: string;
  domains: string[];
  confidence: number;
  conf_alpha: number;
  conf_beta: number;
  status: string;
}

interface ActionsResponse {
  actions: { source_category: string }[];
  total: number;
  counts_by_kind: Record<string, number>;
}

@customElement('fc-knowledge-health-card')
export class FcKnowledgeHealthCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .health-row {
      display: flex; gap: 12px; flex-wrap: wrap; padding: 10px 14px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
      border-radius: 8px; font-family: var(--f-mono); font-size: 10px;
      color: var(--v-fg-muted); align-items: center;
    }
    .stat { display: flex; flex-direction: column; gap: 1px; }
    .stat-label {
      font-size: 8px; text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--v-fg-dim);
    }
    .stat-value {
      font-size: 13px; font-weight: 600; font-feature-settings: 'tnum';
      color: var(--v-fg);
    }
    .stat-value.warn { color: var(--v-warn, #F5B731); }
    .stat-value.danger { color: var(--v-danger, #F06464); }
    .divider {
      width: 1px; height: 24px; background: var(--v-border); flex-shrink: 0;
    }
    .domain-tags { display: flex; gap: 3px; flex-wrap: wrap; }
    .domain-tag {
      font-size: 7.5px; padding: 1px 4px; border-radius: 3px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim);
      border: 1px solid var(--v-border);
    }
  `];

  @property() workspaceId = '';

  @state() private _entries: KnowledgeEntry[] = [];
  @state() private _reviewCount = 0;
  @state() private _staleCount = 0;
  @state() private _contradictionCount = 0;
  @state() private _loading = true;

  connectedCallback(): void {
    super.connectedCallback();
    this._fetchData();
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has('workspaceId') && this.workspaceId) {
      this._fetchData();
    }
  }

  private async _fetchData(): Promise<void> {
    if (!this.workspaceId) { this._loading = false; return; }
    this._loading = true;
    try {
      const [kRes, aRes] = await Promise.all([
        fetch(`/api/v1/knowledge?workspace=${this.workspaceId}&limit=200`),
        fetch(`/api/v1/workspaces/${this.workspaceId}/operations/actions?kind=knowledge_review`),
      ]);
      if (kRes.ok) {
        const data = await kRes.json() as { entries?: KnowledgeEntry[] };
        this._entries = data.entries ?? [];
      }
      if (aRes.ok) {
        const data = await aRes.json() as ActionsResponse;
        this._reviewCount = data.total;
        this._staleCount = data.actions.filter(a => a.source_category === 'stale_authority').length;
        this._contradictionCount = data.actions.filter(a => a.source_category === 'contradiction').length;
      }
    } catch { /* endpoint unavailable */ }
    this._loading = false;
  }

  render() {
    if (this._loading || this._entries.length === 0) return nothing;

    const total = this._entries.length;
    const avgConf = total > 0
      ? this._entries.reduce((sum, e) => sum + (e.confidence ?? 0.5), 0) / total
      : 0;

    // Top domains by entry count
    const domainCounts = new Map<string, number>();
    for (const e of this._entries) {
      for (const d of (e.domains ?? [])) {
        domainCounts.set(d, (domainCounts.get(d) ?? 0) + 1);
      }
    }
    const topDomains = [...domainCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);

    return html`
      <div class="health-row">
        <div class="stat">
          <span class="stat-label">Entries</span>
          <span class="stat-value">${total}</span>
        </div>
        <div class="divider"></div>
        <div class="stat">
          <span class="stat-label">Pending Review</span>
          <span class="stat-value ${this._reviewCount > 0 ? 'warn' : ''}">${this._reviewCount}</span>
        </div>
        <div class="divider"></div>
        <div class="stat">
          <span class="stat-label">Avg Confidence</span>
          <span class="stat-value">${(avgConf * 100).toFixed(0)}%</span>
        </div>
        ${this._staleCount > 0 ? html`
          <div class="divider"></div>
          <div class="stat">
            <span class="stat-label">Stale</span>
            <span class="stat-value warn">${this._staleCount}</span>
          </div>
        ` : nothing}
        ${this._contradictionCount > 0 ? html`
          <div class="divider"></div>
          <div class="stat">
            <span class="stat-label">Contradictions</span>
            <span class="stat-value danger">${this._contradictionCount}</span>
          </div>
        ` : nothing}
        ${topDomains.length > 0 ? html`
          <div class="divider"></div>
          <div class="stat">
            <span class="stat-label">Top Domains</span>
            <div class="domain-tags">
              ${topDomains.map(([d, c]) => html`
                <span class="domain-tag">${d} (${c})</span>
              `)}
            </div>
          </div>
        ` : nothing}
      </div>
    `;
  }
}
