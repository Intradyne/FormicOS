import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface StatusItem { label: string; value: string; }
interface TableData { columns: string[]; rows: unknown[][]; }
interface LogEntry { ts: string; message: string; }

@customElement('fc-addon-panel')
export class FcAddonPanel extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; margin-bottom: 12px; }
    .panel { padding: 10px 14px; border-radius: 10px; background: var(--v-recessed); border: 1px solid var(--v-border); }
    .panel-title { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
    .status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; }
    .status-item { display: flex; flex-direction: column; gap: 2px; }
    .status-label { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .status-value { font-size: 12px; font-family: var(--f-mono); color: var(--v-fg); font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; font-family: var(--f-mono); }
    th { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--v-border); color: var(--v-fg-dim); font-weight: 500; }
    td { padding: 4px 8px; color: var(--v-fg); }
    .log-entry { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted); padding: 2px 0; }
    .log-ts { color: var(--v-fg-dim); margin-right: 8px; }
    .error { color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); }
  `];

  @property() src = '';
  @property({ attribute: 'display-type' }) displayType = 'status_card';
  @property() label = '';
  @state() private _data: unknown = null;
  @state() private _error = '';
  private _timer?: ReturnType<typeof setInterval>;

  connectedCallback() {
    super.connectedCallback();
    this._fetch();
    this._timer = setInterval(() => this._fetch(), 60000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._timer) clearInterval(this._timer);
  }

  private async _fetch() {
    if (!this.src) return;
    try {
      const res = await fetch(this.src);
      if (res.ok) {
        this._data = await res.json();
        this._error = '';
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
        ${this.label ? html`<div class="panel-title">${this.label}</div>` : nothing}
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
      default: return html`<div class="error">Unknown display type: ${type}</div>`;
    }
  }

  private _renderStatusCard(data: Record<string, unknown>) {
    const items = (data.items ?? []) as StatusItem[];
    return html`
      <div class="status-grid">
        ${items.map(i => html`
          <div class="status-item">
            <span class="status-label">${i.label}</span>
            <span class="status-value">${i.value}</span>
          </div>
        `)}
      </div>
    `;
  }

  private _renderTable(data: Record<string, unknown>) {
    const td = data as unknown as TableData;
    return html`
      <table>
        <thead><tr>${(td.columns ?? []).map(c => html`<th>${c}</th>`)}</tr></thead>
        <tbody>
          ${(td.rows ?? []).map(row => html`
            <tr>${(row as unknown[]).map(cell => html`<td>${String(cell)}</td>`)}</tr>
          `)}
        </tbody>
      </table>
    `;
  }

  private _renderLog(data: Record<string, unknown>) {
    const entries = (data.entries ?? []) as LogEntry[];
    return html`
      ${entries.map(e => html`
        <div class="log-entry">
          <span class="log-ts">${e.ts}</span>${e.message}
        </div>
      `)}
    `;
  }
}
