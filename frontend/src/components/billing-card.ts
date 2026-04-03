/**
 * Wave 77.5 B3: Billing dashboard card.
 * Shows current billing period token usage, fee, and by-model breakdown.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface BillingData {
  period_start: string;
  period_end: string;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cache_read_tokens: number;
  total_tokens: number;
  total_cost: number;
  computed_fee: number;
  by_model: Record<string, {
    input_tokens: number;
    output_tokens: number;
    reasoning_tokens: number;
    cache_read_tokens: number;
    cost: number;
  }>;
}

@customElement('fc-billing-card')
export class FcBillingCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .card { padding: 14px 16px; }
    .title {
      font-size: 12px; font-family: var(--f-mono); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--v-fg-dim); margin-bottom: 10px;
    }
    .period {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-muted);
      margin-left: 8px; text-transform: none; letter-spacing: 0;
    }
    .main-stat {
      font-size: 16px; font-weight: 700; font-family: var(--f-display);
      color: var(--v-fg); margin-bottom: 4px;
    }
    .sub-stat {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 2px;
    }
    .fee-row {
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg);
      margin-top: 6px; display: flex; align-items: center; gap: 6px;
    }
    .tier-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px;
      border-radius: 4px; background: rgba(45,212,168,0.1);
      color: var(--v-success); border: 1px solid rgba(45,212,168,0.2);
      font-weight: 600; text-transform: uppercase;
    }
    .model-breakdown { margin-top: 8px; }
    .model-row {
      display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .model-name { min-width: 180px; overflow: hidden; text-overflow: ellipsis; }
    .model-bar {
      flex: 1; height: 4px; background: rgba(255,255,255,0.04);
      border-radius: 2px; overflow: hidden; max-width: 120px;
    }
    .model-fill { height: 100%; border-radius: 2px; }
    .model-fill.local { background: var(--v-success); }
    .model-fill.cloud { background: var(--v-accent); }
    .cache-note {
      font-size: 8.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-top: 6px; opacity: 0.7;
    }
  `];

  @property() workspaceId = '';
  @state() private _data: BillingData | null = null;
  @state() private _loading = true;

  connectedCallback(): void {
    super.connectedCallback();
    void this._fetch();
  }

  private async _fetch() {
    this._loading = true;
    try {
      const resp = await fetch('/api/v1/billing/status');
      if (resp.ok) {
        this._data = await resp.json() as BillingData;
      }
    } catch { /* network error */ }
    this._loading = false;
  }

  private _fmt(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  }

  private _periodLabel(start: string): string {
    try {
      const d = new Date(start);
      return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    } catch { return ''; }
  }

  private _tierLabel(tokens: number): string {
    if (tokens < 10_000_000) return 'Tier 1 \u2014 Free';
    return 'Tier 2 \u2014 Metered';
  }

  render() {
    if (this._loading) {
      return html`<div class="glass card" style="padding:12px;font-size:10px;color:var(--v-fg-dim);font-family:var(--f-mono)">Loading billing\u2026</div>`;
    }
    const d = this._data;
    if (!d) return nothing;

    const models = Object.entries(d.by_model);
    const maxTokens = Math.max(1, ...models.map(([, s]) =>
      (s.input_tokens ?? 0) + (s.output_tokens ?? 0) + (s.reasoning_tokens ?? 0)
    ));

    return html`
      <div class="glass card">
        <div class="title">
          Billing<span class="period">${this._periodLabel(d.period_start)}</span>
        </div>
        <div class="main-stat">${this._fmt(d.total_tokens)} tokens</div>
        <div class="sub-stat">
          input: ${this._fmt(d.input_tokens)}
          \u00B7 output: ${this._fmt(d.output_tokens)}
          \u00B7 reasoning: ${this._fmt(d.reasoning_tokens)}
        </div>
        <div class="fee-row">
          Fee: $${d.computed_fee.toFixed(2)}
          <span class="tier-badge">${this._tierLabel(d.total_tokens)}</span>
        </div>
        ${d.cache_read_tokens > 0 ? html`
          <div class="cache-note">
            Cache-read: ${this._fmt(d.cache_read_tokens)} (informational, not billed)
          </div>
        ` : nothing}
        ${models.length > 0 ? html`
          <div class="model-breakdown">
            ${models.map(([model, stats]) => {
              const total = (stats.input_tokens ?? 0) + (stats.output_tokens ?? 0) + (stats.reasoning_tokens ?? 0);
              const pct = (total / maxTokens) * 100;
              const isLocal = model.startsWith('llama-cpp/');
              return html`
                <div class="model-row">
                  <span class="model-name">${model}</span>
                  <div class="model-bar">
                    <div class="model-fill ${isLocal ? 'local' : 'cloud'}"
                      style="width:${pct.toFixed(1)}%"></div>
                  </div>
                  <span>${this._fmt(total)}</span>
                  <span>$${(stats.cost ?? 0).toFixed(4)}</span>
                </div>
              `;
            })}
          </div>
        ` : nothing}
      </div>
    `;
  }
}
