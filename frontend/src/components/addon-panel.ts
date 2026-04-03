import { LitElement, html, css, nothing, svg } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface StatusItem { label: string; value: string; status?: string; }
interface TableData {
  columns: string[];
  rows: unknown[][];
  row_status?: string[];  // optional per-row status for coloring
}
interface LogEntry { ts: string; message: string; level?: string; }
interface KpiItem {
  label: string;
  value: string | number;
  unit?: string;
  trend?: number[];       // recent values for sparkline
  status?: string;        // ok | warn | error
}

const _DEFAULT_REFRESH_S = 60;

@customElement('fc-addon-panel')
export class FcAddonPanel extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; margin-bottom: 12px; }
    .panel {
      padding: 10px 14px; border-radius: 10px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
    }
    .panel-title {
      font-size: 9.5px; font-family: var(--f-mono);
      color: var(--v-fg-dim); margin-bottom: 8px;
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 6px;
    }
    .status-item { display: flex; flex-direction: column; gap: 2px; }
    .status-label {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .status-value {
      font-size: 12px; font-family: var(--f-mono);
      color: var(--v-fg); font-weight: 600;
    }
    .status-value.ok { color: var(--v-success); }
    .status-value.warn { color: var(--v-warn); }
    .status-value.error { color: var(--v-danger); }
    table {
      width: 100%; border-collapse: collapse;
      font-size: 11px; font-family: var(--f-mono);
    }
    th {
      text-align: left; padding: 4px 8px;
      border-bottom: 1px solid var(--v-border);
      color: var(--v-fg-dim); font-weight: 500;
    }
    td { padding: 4px 8px; color: var(--v-fg); }
    tr.row-warn td { color: var(--v-warn); }
    tr.row-error td { color: var(--v-danger); }
    .log-entry {
      font-size: 10px; font-family: var(--f-mono);
      color: var(--v-fg-muted); padding: 2px 0;
    }
    .log-ts { color: var(--v-fg-dim); margin-right: 8px; }
    .log-warn { color: var(--v-warn); }
    .log-error { color: var(--v-danger); }
    .error {
      color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono);
    }
    /* Wave 87: KPI card */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 10px;
    }
    .kpi-card {
      display: flex; flex-direction: column; gap: 2px;
      padding: 8px 10px; border-radius: 8px;
      background: rgba(255,255,255,0.02);
      border: 1px solid var(--v-border);
    }
    .kpi-label {
      font-size: 8.5px; font-family: var(--f-mono);
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .kpi-value-row { display: flex; align-items: baseline; gap: 4px; }
    .kpi-value {
      font-size: 18px; font-weight: 700;
      font-family: var(--f-display); color: var(--v-fg);
      font-feature-settings: 'tnum';
    }
    .kpi-value.ok { color: var(--v-success); }
    .kpi-value.warn { color: var(--v-warn); }
    .kpi-value.error { color: var(--v-danger); }
    .kpi-unit {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .kpi-sparkline { margin-top: 2px; }
  `];

  @property() src = '';
  @property({ attribute: 'display-type' }) displayType = 'status_card';
  @property() label = '';
  /** Wave 87: workspace context for panel fetch URLs. */
  @property({ attribute: 'workspace-id' }) workspaceId = '';
  /** Wave 87: per-panel refresh interval in seconds. */
  @property({ type: Number, attribute: 'refresh-interval' })
  refreshInterval = _DEFAULT_REFRESH_S;

  @state() private _data: unknown = null;
  @state() private _error = '';
  private _timer?: ReturnType<typeof setInterval>;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
    const interval = Math.max(5, this.refreshInterval) * 1000;
    this._timer = setInterval(() => void this._fetch(), interval);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._timer) clearInterval(this._timer);
  }

  /** Restart timer when refresh interval changes. */
  updated(changed: Map<string, unknown>) {
    if (changed.has('refreshInterval') && this._timer) {
      clearInterval(this._timer);
      const interval = Math.max(5, this.refreshInterval) * 1000;
      this._timer = setInterval(() => void this._fetch(), interval);
    }
  }

  private async _fetch() {
    if (!this.src) return;
    // Wave 87: append workspace_id query param
    let url = this.src;
    if (this.workspaceId) {
      const sep = url.includes('?') ? '&' : '?';
      url = `${url}${sep}workspace_id=${encodeURIComponent(this.workspaceId)}`;
    }
    try {
      const res = await fetch(url);
      if (res.ok) {
        const payload = await res.json() as Record<string, unknown>;
        this._data = payload;
        this._error = '';
        // Honor server-provided refresh interval
        if (
          typeof payload.refresh_interval_s === 'number'
          && payload.refresh_interval_s !== this.refreshInterval
        ) {
          this.refreshInterval = payload.refresh_interval_s as number;
        }
      } else if (res.status === 500) {
        this._error = '';
        this._data = null;
        return;
      } else {
        this._error = `HTTP ${res.status}`;
      }
    } catch (e) {
      this._error = String(e);
    }
  }

  render() {
    if (!this._data && !this._error) return nothing;

    return html`
      <div class="panel">
        ${this.label
          ? html`<div class="panel-title">${this.label}</div>`
          : nothing}
        ${this._error
          ? html`<div class="error">${this._error}</div>`
          : this._renderContent()}
      </div>
    `;
  }

  private _renderContent() {
    const data = this._data as Record<string, unknown>;
    const type = (data?.display_type as string) || this.displayType;

    switch (type) {
      case 'status_card': return this._renderStatusCard(data);
      case 'table': return this._renderTable(data);
      case 'log': return this._renderLog(data);
      case 'kpi_card': return this._renderKpiCard(data);
      default:
        return html`<div class="error">Unknown type: ${type}</div>`;
    }
  }

  private _renderStatusCard(data: Record<string, unknown>) {
    const items = (data.items ?? []) as StatusItem[];
    return html`
      <div class="status-grid">
        ${items.map(i => html`
          <div class="status-item">
            <span class="status-label">${i.label}</span>
            <span class="status-value ${i.status ?? ''}">${i.value}</span>
          </div>
        `)}
      </div>
    `;
  }

  private _renderTable(data: Record<string, unknown>) {
    const td = data as unknown as TableData;
    const statuses = td.row_status ?? [];
    return html`
      <table>
        <thead>
          <tr>${(td.columns ?? []).map(c => html`<th>${c}</th>`)}</tr>
        </thead>
        <tbody>
          ${(td.rows ?? []).map((row, idx) => {
            const rs = statuses[idx] ?? '';
            const cls = rs === 'warn' ? 'row-warn'
              : rs === 'error' ? 'row-error' : '';
            return html`
              <tr class=${cls}>
                ${(row as unknown[]).map(cell => html`<td>${String(cell)}</td>`)}
              </tr>
            `;
          })}
        </tbody>
      </table>
    `;
  }

  private _renderLog(data: Record<string, unknown>) {
    const entries = (data.entries ?? []) as LogEntry[];
    return html`
      ${entries.map(e => {
        const cls = e.level === 'warn' ? 'log-warn'
          : e.level === 'error' ? 'log-error' : '';
        return html`
          <div class="log-entry ${cls}">
            <span class="log-ts">${e.ts}</span>${e.message}
          </div>
        `;
      })}
    `;
  }

  /** Wave 87: KPI card with optional sparkline trend. */
  private _renderKpiCard(data: Record<string, unknown>) {
    const items = (data.items ?? []) as KpiItem[];
    return html`
      <div class="kpi-grid">
        ${items.map(i => html`
          <div class="kpi-card">
            <span class="kpi-label">${i.label}</span>
            <div class="kpi-value-row">
              <span class="kpi-value ${i.status ?? ''}">${i.value}</span>
              ${i.unit ? html`<span class="kpi-unit">${i.unit}</span>` : nothing}
            </div>
            ${i.trend?.length ? this._renderSparkline(i.trend, i.status) : nothing}
          </div>
        `)}
      </div>
    `;
  }

  /** Inline SVG sparkline from trend data. */
  private _renderSparkline(
    values: number[],
    status?: string,
  ) {
    if (values.length < 2) return nothing;
    const w = 80;
    const h = 20;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * w;
        const y = h - ((v - min) / range) * h;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
    const color = status === 'error' ? 'var(--v-danger)'
      : status === 'warn' ? 'var(--v-warn)'
      : 'var(--v-success)';
    return html`
      <svg class="kpi-sparkline" width=${w} height=${h}
        viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline
          points=${points}
          fill="none"
          stroke=${color}
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    `;
  }
}
