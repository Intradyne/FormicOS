/**
 * Wave 70.5 Team A: MCP server management card.
 *
 * Self-contained Lit component that fetches bridge health and config
 * from existing 70.0 contracts. No store dependency — Team C mounts it
 * in settings-view without shared state changes.
 */

import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface McpServer {
  name: string;
  url: string;
  status?: string;
  toolCount?: number;
  callCount?: number;
  lastError?: string | null;
}

interface BridgeHealth {
  connectedServers: number;
  unhealthyServers: number;
  totalRemoteTools: number;
  servers: McpServer[];
}

@customElement('fc-mcp-servers-card')
export class McpServersCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }

    .card {
      background: var(--v-surface);
      border: 1px solid var(--v-border);
      border-radius: 10px;
      padding: 16px 20px;
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }

    .card-title {
      font-family: var(--f-display);
      font-size: 14px;
      font-weight: 600;
      color: var(--v-fg);
    }

    .summary {
      font-family: var(--f-mono);
      font-size: 10px;
      color: var(--v-fg-dim);
      letter-spacing: 0.06em;
    }

    .server-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-bottom: 14px;
    }

    .server-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      background: var(--v-recessed);
      border: 1px solid var(--v-border);
      border-radius: 8px;
      transition: border-color 0.15s;
    }
    .server-row:hover { border-color: var(--v-border-hover); }

    .health-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .health-dot.connected { background: var(--v-success); }
    .health-dot.disconnected { background: var(--v-fg-dim); }
    .health-dot.error { background: var(--v-danger); }

    .server-info {
      flex: 1;
      min-width: 0;
    }

    .server-name {
      font-family: var(--f-mono);
      font-size: 12px;
      font-weight: 600;
      color: var(--v-fg);
    }

    .server-url {
      font-family: var(--f-mono);
      font-size: 10px;
      color: var(--v-fg-dim);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .server-meta {
      font-family: var(--f-mono);
      font-size: 9.5px;
      color: var(--v-fg-dim);
      margin-top: 2px;
    }

    .server-error {
      font-family: var(--f-mono);
      font-size: 9px;
      color: var(--v-danger);
      margin-top: 2px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .server-actions {
      display: flex;
      gap: 6px;
      flex-shrink: 0;
    }

    .action-btn {
      font-family: var(--f-mono);
      font-size: 9px;
      padding: 3px 8px;
      border-radius: 5px;
      cursor: pointer;
      border: 1px solid var(--v-border);
      background: rgba(255,255,255,0.02);
      color: var(--v-fg-dim);
      transition: all 0.15s;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .action-btn:hover {
      border-color: var(--v-border-hover);
      color: var(--v-fg);
      background: rgba(255,255,255,0.04);
    }
    .action-btn.danger:hover {
      border-color: var(--v-danger);
      color: var(--v-danger);
    }

    .add-form {
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }

    .field {
      display: flex;
      flex-direction: column;
      gap: 3px;
      flex: 1;
    }

    .field label {
      font-family: var(--f-mono);
      font-size: 9.5px;
      font-weight: 600;
      color: var(--v-fg-dim);
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }

    .field input {
      font-family: var(--f-mono);
      font-size: 11px;
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid var(--v-border);
      background: var(--v-recessed);
      color: var(--v-fg);
      outline: none;
      transition: border-color 0.15s;
    }
    .field input:focus { border-color: var(--v-accent); }
    .field input::placeholder { color: var(--v-fg-dim); }

    .add-btn {
      font-family: var(--f-mono);
      font-size: 10px;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      border: 1px solid var(--v-accent);
      background: rgba(232,88,26,0.1);
      color: var(--v-accent);
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      transition: all 0.15s;
      white-space: nowrap;
    }
    .add-btn:hover {
      background: rgba(232,88,26,0.2);
    }
    .add-btn:disabled {
      opacity: 0.4;
      cursor: default;
    }

    .empty {
      text-align: center;
      padding: 20px;
      font-family: var(--f-body);
      font-size: 12px;
      color: var(--v-fg-dim);
    }

    .status-msg {
      font-family: var(--f-mono);
      font-size: 10px;
      margin-top: 8px;
      padding: 6px 10px;
      border-radius: 6px;
    }
    .status-msg.ok {
      color: var(--v-success);
      background: rgba(45,212,168,0.08);
    }
    .status-msg.err {
      color: var(--v-danger);
      background: rgba(240,100,100,0.08);
    }

    @media (prefers-reduced-motion: reduce) {
      .server-row, .action-btn, .add-btn, .field input { transition: none; }
    }
  `];

  @state() private _health: BridgeHealth | null = null;
  @state() private _bridgeInstalled = true;
  @state() private _loading = true;
  @state() private _newName = '';
  @state() private _newUrl = '';
  @state() private _saving = false;
  @state() private _statusMsg = '';
  @state() private _statusOk = true;

  connectedCallback(): void {
    super.connectedCallback();
    this._fetch();
  }

  private async _fetch(): Promise<void> {
    this._loading = true;
    try {
      const resp = await fetch('/api/v1/addons');
      if (!resp.ok) {
        this._bridgeInstalled = false;
        this._loading = false;
        return;
      }
      const addons: Array<Record<string, unknown>> = await resp.json();
      const bridge = addons.find(
        (a) => a.bridgeHealth !== undefined && a.bridgeHealth !== null,
      );
      if (!bridge) {
        // No addon exposes bridge health — check if mcp-bridge addon exists
        const mcpAddon = addons.find((a) => a.name === 'mcp-bridge');
        this._bridgeInstalled = !!mcpAddon;
        if (mcpAddon) {
          // Installed but no health yet (no servers configured)
          this._health = {
            connectedServers: 0,
            unhealthyServers: 0,
            totalRemoteTools: 0,
            servers: [],
          };
        }
        this._loading = false;
        return;
      }
      this._bridgeInstalled = true;
      this._health = bridge.bridgeHealth as BridgeHealth;
    } catch {
      this._bridgeInstalled = false;
    }
    this._loading = false;
  }

  private async _addServer(): Promise<void> {
    const name = this._newName.trim();
    const url = this._newUrl.trim();
    if (!name || !url) return;

    this._saving = true;
    this._statusMsg = '';

    // Build updated server list
    const existing = (this._health?.servers ?? []).map((s) => ({
      name: s.name,
      url: s.url,
    }));
    existing.push({ name, url });

    try {
      const resp = await fetch('/api/v1/addons/mcp-bridge/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: '_global',
          values: { mcp_servers: JSON.stringify(existing) },
        }),
      });
      if (resp.ok) {
        this._newName = '';
        this._newUrl = '';
        this._statusMsg = `Server "${name}" added`;
        this._statusOk = true;
        await this._fetch();
      } else {
        const data = await resp.json().catch(() => ({}));
        this._statusMsg = `Error: ${(data as Record<string, string>).message ?? resp.statusText}`;
        this._statusOk = false;
      }
    } catch (e) {
      this._statusMsg = `Error: ${e}`;
      this._statusOk = false;
    }
    this._saving = false;
  }

  private async _removeServer(name: string): Promise<void> {
    const remaining = (this._health?.servers ?? [])
      .filter((s) => s.name !== name)
      .map((s) => ({ name: s.name, url: s.url }));

    try {
      const resp = await fetch('/api/v1/addons/mcp-bridge/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: '_global',
          values: { mcp_servers: JSON.stringify(remaining) },
        }),
      });
      if (resp.ok) {
        this._statusMsg = `Server "${name}" removed`;
        this._statusOk = true;
        await this._fetch();
      }
    } catch (e) {
      this._statusMsg = `Error: ${e}`;
      this._statusOk = false;
    }
  }

  render() {
    if (this._loading) {
      return html`<div class="card"><div class="empty">Loading MCP bridge status\u2026</div></div>`;
    }

    if (!this._bridgeInstalled) {
      return html`
        <div class="card">
          <div class="card-header">
            <span class="card-title">MCP Servers</span>
          </div>
          <div class="empty">MCP bridge addon is not installed.</div>
        </div>
      `;
    }

    const servers = this._health?.servers ?? [];
    const connected = this._health?.connectedServers ?? 0;
    const tools = this._health?.totalRemoteTools ?? 0;

    return html`
      <div class="card">
        <div class="card-header">
          <span class="card-title">MCP Servers</span>
          <span class="summary">
            ${connected} connected \u00b7 ${tools} tools
          </span>
        </div>

        ${servers.length > 0 ? html`
          <div class="server-list">
            ${servers.map((s) => this._renderServer(s))}
          </div>
        ` : html`
          <div class="empty">No MCP servers configured. Add one below.</div>
        `}

        ${this._renderAddForm()}

        ${this._statusMsg ? html`
          <div class="status-msg ${this._statusOk ? 'ok' : 'err'}">
            ${this._statusMsg}
          </div>
        ` : nothing}
      </div>
    `;
  }

  private _renderServer(s: McpServer) {
    const status = s.status ?? 'disconnected';
    const dotClass = status === 'connected' ? 'connected'
      : status === 'error' ? 'error'
      : 'disconnected';

    return html`
      <div class="server-row">
        <div class="health-dot ${dotClass}"></div>
        <div class="server-info">
          <div class="server-name">${s.name}</div>
          <div class="server-url">${s.url}</div>
          ${(s.toolCount ?? 0) > 0 ? html`
            <div class="server-meta">
              ${s.toolCount} tools \u00b7 ${s.callCount ?? 0} calls
            </div>
          ` : nothing}
          ${s.lastError ? html`
            <div class="server-error" title="${s.lastError}">${s.lastError}</div>
          ` : nothing}
        </div>
        <div class="server-actions">
          <button class="action-btn danger"
            @click=${() => this._removeServer(s.name)}>
            Remove
          </button>
        </div>
      </div>
    `;
  }

  private _renderAddForm() {
    return html`
      <div class="add-form">
        <div class="field">
          <label>Name</label>
          <input type="text"
            placeholder="e.g. github-mcp"
            .value=${this._newName}
            @input=${(e: InputEvent) => { this._newName = (e.target as HTMLInputElement).value; }}>
        </div>
        <div class="field" style="flex:2">
          <label>URL</label>
          <input type="text"
            placeholder="e.g. http://localhost:8080/sse"
            .value=${this._newUrl}
            @input=${(e: InputEvent) => { this._newUrl = (e.target as HTMLInputElement).value; }}>
        </div>
        <button class="add-btn"
          ?disabled=${this._saving || !this._newName.trim() || !this._newUrl.trim()}
          @click=${() => this._addServer()}>
          Add
        </button>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-mcp-servers-card': McpServersCard; }
}
