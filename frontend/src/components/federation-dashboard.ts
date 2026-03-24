import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

/** Peer trust and sync status from projections. */
interface PeerStatus {
  instanceId: string;
  trustScore: number;
  trustMean: number;
  successCount: number;
  failureCount: number;
  lastSync: string;
  eventsPending: number;
  domainsExchanged: string[];
  entriesSent: number;
  entriesReceived: number;
}

/** Conflict resolution log entry. */
interface ConflictLogEntry {
  entryId: string;
  localTitle: string;
  remoteTitle: string;
  resolution: string;
  timestamp: string;
}

@customElement('fc-federation-dashboard')
export class FcFederationDashboard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 960px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .section-title { font-family: var(--f-display); font-size: 14px; font-weight: 600; color: var(--v-fg); margin: 16px 0 8px; }
    .peer-table {
      width: 100%; border-collapse: collapse; font-size: 11px; font-family: var(--f-mono);
    }
    .peer-table th {
      text-align: left; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
      color: var(--v-fg-dim); padding: 6px 8px; border-bottom: 1px solid var(--v-border);
    }
    .peer-table td { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--v-fg-muted); }
    .trust-bar { display: inline-block; width: 60px; height: 4px; background: rgba(255,255,255,0.04); border-radius: 2px; overflow: hidden; vertical-align: middle; margin-left: 4px; }
    .trust-fill { height: 100%; border-radius: 2px; }
    .trust-high { background: var(--v-tier-high); }
    .trust-medium { background: var(--v-tier-moderate); }
    .trust-low { background: var(--v-tier-exploratory); }
    .conflict-card { padding: 10px 12px; margin-bottom: 6px; border-left: 3px solid #F5B731; }
    .conflict-method { font-size: 9px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px; background: rgba(245,183,49,0.1); color: #F5B731; }
    .conflict-pair { display: flex; gap: 12px; font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted); }
    .conflict-vs { font-size: 10px; color: #F5B731; font-weight: 700; align-self: center; }
    .empty-state { padding: 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px; }
    .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-bottom: 14px; }
    .stat-card {
      padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,0.02);
      border: 1px solid var(--v-border); text-align: center;
    }
    .stat-value { font-family: var(--f-mono); font-size: 18px; font-weight: 700; color: var(--v-fg); font-feature-settings: 'tnum'; }
    .stat-label { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
    .domain-tag { font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px; background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border); }
  `];

  @property() workspaceId = '';
  @state() private peers: PeerStatus[] = [];
  @state() private conflicts: ConflictLogEntry[] = [];
  @state() private loading = true;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchData();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId')) void this._fetchData();
  }

  private async _fetchData() {
    this.loading = true;
    try {
      const res = await fetch(`/api/v1/federation/status?workspace=${encodeURIComponent(this.workspaceId)}`);
      if (res.ok) {
        const data = await res.json();
        this.peers = (data.peers ?? []).map((p: Record<string, unknown>) => ({
          instanceId: p.instance_id as string ?? '',
          trustScore: p.trust_score as number ?? 0,
          trustMean: p.trust_mean as number ?? 0,
          successCount: p.success_count as number ?? 0,
          failureCount: p.failure_count as number ?? 0,
          lastSync: p.last_sync as string ?? '',
          eventsPending: p.events_pending as number ?? 0,
          domainsExchanged: (p.domains_exchanged as string[]) ?? [],
          entriesSent: p.entries_sent as number ?? 0,
          entriesReceived: p.entries_received as number ?? 0,
        }));
        this.conflicts = (data.conflicts ?? []).map((c: Record<string, unknown>) => ({
          entryId: c.entry_id as string ?? '',
          localTitle: c.local_title as string ?? '',
          remoteTitle: c.remote_title as string ?? '',
          resolution: c.resolution as string ?? '',
          timestamp: c.timestamp as string ?? '',
        }));
      }
    } catch { /* endpoint may not exist yet */ }
    this.loading = false;
  }

  private _trustColor(score: number): string {
    if (score >= 0.7) return 'trust-high';
    if (score >= 0.4) return 'trust-medium';
    return 'trust-low';
  }

  render() {
    return html`
      <div class="title-row">
        <h2>Federation</h2>
      </div>

      ${this.loading ? html`<div class="empty-state">Loading federation status\u2026</div>` : html`
        ${this._renderStats()}
        ${this._renderPeerTable()}
        ${this._renderConflicts()}
      `}
    `;
  }

  private _renderStats() {
    const totalSent = this.peers.reduce((s, p) => s + p.entriesSent, 0);
    const totalReceived = this.peers.reduce((s, p) => s + p.entriesReceived, 0);
    const avgTrust = this.peers.length > 0
      ? this.peers.reduce((s, p) => s + p.trustScore, 0) / this.peers.length : 0;
    return html`
      <div class="stat-grid">
        <div class="glass stat-card">
          <div class="stat-value">${this.peers.length}</div>
          <div class="stat-label">Peers</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${totalSent}</div>
          <div class="stat-label">Entries Sent</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${totalReceived}</div>
          <div class="stat-label">Entries Received</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${(avgTrust * 100).toFixed(0)}%</div>
          <div class="stat-label">Avg Trust</div>
        </div>
        <div class="glass stat-card">
          <div class="stat-value">${this.conflicts.length}</div>
          <div class="stat-label">Conflicts</div>
        </div>
      </div>
    `;
  }

  private _renderPeerTable() {
    if (this.peers.length === 0) {
      return html`<div class="glass empty-state">No federation peers configured.</div>`;
    }
    return html`
      <div class="section-title">Peer Trust</div>
      <div class="glass" style="padding:8px;overflow-x:auto">
        <table class="peer-table">
          <thead><tr>
            <th>Instance</th><th>Trust</th><th>S/F</th><th>Last Sync</th><th>Pending</th><th>Domains</th><th>Flow</th>
          </tr></thead>
          <tbody>
            ${this.peers.map(p => html`
              <tr>
                <td style="font-weight:500;color:var(--v-fg)">${p.instanceId}</td>
                <td>
                  ${(p.trustScore * 100).toFixed(0)}%
                  <span class="trust-bar"><span class="trust-fill ${this._trustColor(p.trustScore)}" style="width:${Math.round(p.trustScore * 100)}%"></span></span>
                </td>
                <td>${p.successCount}/${p.failureCount}</td>
                <td>${p.lastSync || '\u2014'}</td>
                <td>${p.eventsPending}</td>
                <td>${p.domainsExchanged.length > 0
                  ? p.domainsExchanged.slice(0, 3).map(d => html`<span class="domain-tag">${d}</span> `)
                  : '\u2014'}</td>
                <td>\u2191${p.entriesSent} \u2193${p.entriesReceived}</td>
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    `;
  }

  private _renderConflicts() {
    if (this.conflicts.length === 0) return nothing;
    return html`
      <div class="section-title">Recent Conflicts</div>
      ${this.conflicts.map(c => html`
        <div class="glass conflict-card">
          <div class="conflict-pair">
            <span>${c.localTitle || c.entryId}</span>
            <span class="conflict-vs">vs</span>
            <span>${c.remoteTitle || '(remote)'}</span>
            <span class="conflict-method">${c.resolution}</span>
          </div>
        </div>
      `)}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-federation-dashboard': FcFederationDashboard; }
}
