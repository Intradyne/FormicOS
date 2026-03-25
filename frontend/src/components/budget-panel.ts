import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { formatCost } from '../helpers.js';

interface ModelUsageEntry {
  cost: number;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_read_tokens: number;
}

interface ColonyBudgetEntry {
  colony_id: string;
  name: string;
  status: string;
  cost: number;
  rounds: number;
}

interface BudgetData {
  workspace_id: string;
  total_cost: number;
  budget_limit: number;
  utilization_pct: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_reasoning_tokens: number;
  total_cache_read_tokens: number;
  model_usage: Record<string, ModelUsageEntry>;
  colonies: ColonyBudgetEntry[];
}

@customElement('fc-budget-panel')
export class FcBudgetPanel extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .budget-section { margin-bottom: 16px; }
    .section-header {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase;
      margin: 0 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--v-border);
    }
    .budget-top { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 12px; }
    .stat-card { padding: 12px; }
    .stat-label {
      font-size: 10px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); margin-bottom: 6px;
    }
    .stat-value {
      font-family: var(--f-mono); font-size: 16px; font-weight: 600;
      font-feature-settings: 'tnum'; color: var(--v-fg);
    }
    .stat-detail {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 4px;
    }
    /* Utilization bar */
    .util-bar-track {
      height: 8px; border-radius: 4px;
      background: rgba(255,255,255,0.03); margin-top: 8px; overflow: hidden;
    }
    .util-bar-fill {
      height: 100%; border-radius: 4px; transition: width 0.4s ease;
    }
    .util-label {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
      margin-top: 4px; font-feature-settings: 'tnum';
    }
    /* Model table */
    .model-table { width: 100%; border-collapse: collapse; }
    .model-table th, .model-table td {
      font-size: 9.5px; font-family: var(--f-mono); padding: 4px 6px;
      text-align: right; font-feature-settings: 'tnum';
    }
    .model-table th {
      color: var(--v-fg-dim); font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.08em; border-bottom: 1px solid var(--v-border);
      text-align: right;
    }
    .model-table th:first-child, .model-table td:first-child { text-align: left; }
    .model-table td { color: var(--v-fg-muted); border-bottom: 1px solid rgba(255,255,255,0.02); }
    .model-table tr:hover td { color: var(--v-fg); }
    .model-name { color: var(--v-fg); font-weight: 500; }
    .cost-cell { color: var(--v-accent); }
    /* Colony list */
    .colony-list { display: flex; flex-direction: column; gap: 4px; }
    .colony-row {
      display: flex; align-items: center; gap: 8px; padding: 6px 8px;
      border-radius: 6px; background: rgba(255,255,255,0.015);
      border: 1px solid rgba(255,255,255,0.03);
      font-size: 9.5px; font-family: var(--f-mono); font-feature-settings: 'tnum';
    }
    .colony-name { color: var(--v-fg); font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .colony-status { font-size: 8px; padding: 1px 5px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
    .colony-status-running { background: rgba(91,156,245,0.12); color: var(--v-blue); }
    .colony-status-completed { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .colony-status-failed { background: rgba(240,100,100,0.12); color: var(--v-danger); }
    .colony-status-pending { background: rgba(107,107,118,0.12); color: var(--v-fg-dim); }
    .colony-cost { color: var(--v-accent); }
    .colony-rounds { color: var(--v-fg-dim); }
    .efficiency-badges { display: flex; gap: 8px; margin-top: 4px; }
    .eff-badge {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 6px;
      border-radius: 4px; background: rgba(255,255,255,0.03); color: var(--v-fg-muted);
    }
    .eff-highlight { color: var(--v-purple); background: rgba(163,130,250,0.1); }
    .loading-msg { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); padding: 12px; }
    .error-msg { font-size: 10px; font-family: var(--f-mono); color: var(--v-danger); padding: 12px; }
    /* Wave 64 Track 5: provider breakdown */
    .provider-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .provider-chip {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 7px;
      border-radius: 4px; background: rgba(255,255,255,0.04);
      color: var(--v-fg); display: flex; align-items: center; gap: 4px;
      font-feature-settings: 'tnum';
    }
    .provider-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
  `];

  @property() workspaceId = '';
  @state() private _data: BudgetData | null = null;
  @state() private _loading = false;
  @state() private _error = false;
  private _fetchedWsId = '';

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId && this.workspaceId !== this._fetchedWsId) {
      this._fetchedWsId = this.workspaceId;
      void this._fetchBudget();
    }
  }

  private async _fetchBudget() {
    if (!this.workspaceId) return;
    this._loading = true;
    this._error = false;
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/budget`);
      if (res.ok) {
        this._data = await res.json() as BudgetData;
      } else {
        this._error = true;
      }
    } catch {
      this._error = true;
    }
    this._loading = false;
  }

  render() {
    if (this._loading && !this._data) return html`<div class="loading-msg">Loading budget...</div>`;
    if (this._error && !this._data) return html`<div class="error-msg">Budget data unavailable</div>`;
    if (!this._data) return nothing;

    const d = this._data;
    const utilColor = d.utilization_pct < 60 ? 'var(--v-success)' : d.utilization_pct < 90 ? 'var(--v-warn)' : 'var(--v-danger)';
    const localTokens = this._localTokens(d);
    const reasoningPct = d.total_output_tokens > 0 ? (d.total_reasoning_tokens / d.total_output_tokens * 100) : 0;
    const cacheHitPct = d.total_input_tokens > 0 ? (d.total_cache_read_tokens / d.total_input_tokens * 100) : 0;

    return html`
      <div class="budget-section">
        <div class="section-header">Budget</div>

        <!-- Top stats row -->
        <div class="budget-top">
          <div class="glass stat-card">
            <div class="stat-label">API Spend</div>
            <div class="stat-value" style="color:var(--v-accent)">${formatCost(d.total_cost)}</div>
            <div class="stat-detail">of ${formatCost(d.budget_limit)} budget</div>
            <div class="util-bar-track">
              <div class="util-bar-fill" style="width:${Math.min(d.utilization_pct, 100)}%;background:${utilColor}"></div>
            </div>
            <div class="util-label" style="color:${utilColor}">${d.utilization_pct.toFixed(1)}% utilized</div>
          </div>
          <div class="glass stat-card">
            <div class="stat-label">Total Tokens</div>
            <div class="stat-value">${this._fmtTokens(d.total_input_tokens + d.total_output_tokens)}</div>
            <div class="stat-detail">${this._fmtTokens(d.total_input_tokens)} in / ${this._fmtTokens(d.total_output_tokens)} out</div>
            ${localTokens > 0 ? html`
              <div class="stat-detail" style="color:var(--v-purple)">${this._fmtTokens(localTokens)} local (free)</div>
            ` : nothing}
          </div>
          <div class="glass stat-card">
            <div class="stat-label">Efficiency</div>
            <div class="efficiency-badges">
              ${d.total_reasoning_tokens > 0 ? html`
                <span class="eff-badge eff-highlight" title="Reasoning tokens as % of output tokens">
                  Reasoning ${reasoningPct.toFixed(0)}%
                </span>
              ` : nothing}
              ${d.total_cache_read_tokens > 0 ? html`
                <span class="eff-badge eff-highlight" title="Cache hits as % of input tokens">
                  Cache ${cacheHitPct.toFixed(0)}%
                </span>
              ` : nothing}
            </div>
            <div class="stat-detail" style="margin-top:6px">${d.colonies.length} colonies</div>
          </div>
        </div>

        <!-- Model breakdown -->
        ${Object.keys(d.model_usage).length > 0 ? html`
          <div class="glass" style="padding:10px;margin-bottom:12px">
            <table class="model-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Cost</th>
                  <th>Input</th>
                  <th>Output</th>
                  <th>Reasoning</th>
                  <th>Cache</th>
                </tr>
              </thead>
              <tbody>
                ${Object.entries(d.model_usage).map(([model, usage]) => html`
                  <tr>
                    <td class="model-name">${model}</td>
                    <td class="cost-cell">${formatCost((usage as ModelUsageEntry).cost ?? 0)}</td>
                    <td>${this._fmtTokens((usage as ModelUsageEntry).input_tokens ?? 0)}</td>
                    <td>${this._fmtTokens((usage as ModelUsageEntry).output_tokens ?? 0)}</td>
                    <td>${(usage as ModelUsageEntry).reasoning_tokens ? this._fmtTokens((usage as ModelUsageEntry).reasoning_tokens) : '\u2014'}</td>
                    <td>${(usage as ModelUsageEntry).cache_read_tokens ? this._fmtTokens((usage as ModelUsageEntry).cache_read_tokens) : '\u2014'}</td>
                  </tr>
                `)}
              </tbody>
            </table>
          </div>
        ` : nothing}

        <!-- Wave 64 Track 5: provider cost breakdown -->
        ${Object.keys(d.model_usage).length > 1 ? html`
          <div class="provider-summary glass" style="padding:10px;margin-bottom:12px">
            <div class="stat-label" style="margin-bottom:6px">Cost by Provider</div>
            <div class="provider-row">
              ${this._providerBreakdown(d).map(p => html`
                <span class="provider-chip" title="${p.provider}: ${formatCost(p.cost)}">
                  <span class="provider-dot" style="background:${p.color}"></span>
                  ${p.provider}: ${formatCost(p.cost)}
                </span>
              `)}
            </div>
          </div>
        ` : nothing}

        <!-- Colony list -->
        ${d.colonies.length > 0 ? html`
          <div class="colony-list">
            ${d.colonies.map(c => html`
              <div class="colony-row">
                <span class="colony-status colony-status-${c.status}">${c.status}</span>
                <span class="colony-name" title="${c.colony_id}">${c.name}</span>
                <span class="colony-rounds">R${c.rounds}</span>
                <span class="colony-cost">${formatCost(c.cost)}</span>
              </div>
            `)}
          </div>
        ` : nothing}
      </div>
    `;
  }

  /** Calculate local tokens (cost == 0 models). */
  private _localTokens(d: BudgetData): number {
    let total = 0;
    for (const usage of Object.values(d.model_usage)) {
      const u = usage as ModelUsageEntry;
      if ((u.cost ?? 0) === 0) {
        total += (u.input_tokens ?? 0) + (u.output_tokens ?? 0);
      }
    }
    return total;
  }

  private _fmtTokens(n: number): string {
    if (n === 0) return '0';
    if (n < 1000) return String(n);
    if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
    return `${(n / 1_000_000).toFixed(2)}M`;
  }

  /** Wave 64 Track 5: aggregate cost by provider prefix. */
  private _providerBreakdown(d: BudgetData): Array<{provider: string; cost: number; color: string}> {
    const _COLORS: Record<string, string> = {
      'anthropic': '#cc785c',
      'gemini': '#4285F4',
      'openai': '#10a37f',
      'deepseek': '#6366f1',
      'llama-cpp': '#8b5cf6',
      'ollama': '#64748b',
    };
    const byProvider: Record<string, number> = {};
    for (const [model, usage] of Object.entries(d.model_usage)) {
      const provider = model.split('/')[0];
      byProvider[provider] = (byProvider[provider] ?? 0) + ((usage as ModelUsageEntry).cost ?? 0);
    }
    return Object.entries(byProvider)
      .sort(([, a], [, b]) => b - a)
      .map(([provider, cost]) => ({
        provider,
        cost,
        color: _COLORS[provider] ?? '#888',
      }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-budget-panel': FcBudgetPanel;
  }
}
