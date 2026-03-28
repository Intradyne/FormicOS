/**
 * Wave 71.5 Team A: Operations view shell.
 * Integrator component that mounts Team B/C leaf components.
 * Layout: top summary row, two-column body (inbox left, journal/procedures right).
 */
import { LitElement, html, css } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './operations-inbox.js';
import './queen-journal-panel.js';
import './operating-procedures-editor.js';
import './operations-summary-card.js';

interface JournalSummary {
  exists: boolean;
  totalEntries: number;
  entries: { timestamp: string; source: string; message: string }[];
}

interface ProceduresSummary {
  exists: boolean;
  content: string;
}

@customElement('fc-operations-view')
export class FcOperationsView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow-y: auto; height: 100%; padding: 20px 24px; }
    .header {
      display: flex; align-items: center; gap: 12px; margin-bottom: 20px;
    }
    .header h1 {
      font-family: var(--f-display); font-size: 22px; font-weight: 700;
      color: var(--v-fg); margin: 0;
    }
    .header .badge {
      font-size: 10px; font-family: var(--f-mono); padding: 2px 8px;
      border-radius: 8px; background: rgba(232,88,26,0.12); color: var(--v-accent);
    }

    .summary-row {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--v-surface); border: 1px solid var(--v-border);
      border-radius: 8px; padding: 14px 16px;
    }
    .stat-label {
      font-size: 10px; font-family: var(--f-mono); text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--v-fg-dim); margin-bottom: 4px;
    }
    .stat-value {
      font-size: 20px; font-weight: 700; font-family: var(--f-display);
      color: var(--v-fg);
    }

    .columns {
      display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
    }
    @media (max-width: 900px) {
      .columns { grid-template-columns: 1fr; }
      .summary-row { grid-template-columns: 1fr; }
    }

    .panel {
      background: var(--v-surface); border: 1px solid var(--v-border);
      border-radius: 8px; padding: 16px; min-height: 120px;
    }
    .panel-title {
      font-size: 12px; font-family: var(--f-mono); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--v-fg-dim); margin: 0 0 12px;
    }

    .empty-state {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 24px 16px; text-align: center;
      color: var(--v-fg-dim); font-size: 12px; font-family: var(--f-mono);
      gap: 6px;
    }
    .empty-state .icon { font-size: 24px; opacity: 0.5; }
    .empty-state .hint { font-size: 11px; opacity: 0.6; }

    .right-stack { display: flex; flex-direction: column; gap: 16px; }

    .journal-entry {
      margin-bottom: 8px; padding: 6px 0;
      border-bottom: 1px solid var(--v-border-dim, rgba(255,255,255,0.04));
      font-size: 12px; font-family: var(--f-mono); color: var(--v-fg);
    }
    .journal-source {
      color: var(--v-fg-dim); font-size: 10px;
    }
    .journal-more {
      color: var(--v-fg-dim); font-size: 10px;
    }
    .proc-preview {
      font-size: 12px; font-family: var(--f-mono); color: var(--v-fg);
      white-space: pre-wrap; line-height: 1.5;
    }
  `];

  @property({ type: String }) workspaceId = '';

  @state() private _journal: JournalSummary | null = null;
  @state() private _procedures: ProceduresSummary | null = null;
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
      const [jRes, pRes] = await Promise.all([
        fetch(`/api/v1/workspaces/${this.workspaceId}/queen-journal`),
        fetch(`/api/v1/workspaces/${this.workspaceId}/operating-procedures`),
      ]);
      this._journal = jRes.ok ? await jRes.json() as JournalSummary : null;
      this._procedures = pRes.ok ? await pRes.json() as ProceduresSummary : null;
    } catch {
      // Network failure — leave nulls, show empty states
    }
    this._loading = false;
  }

  render() {
    if (!this.workspaceId) {
      return html`<div class="empty-state" style="height:100%">
        <span class="icon">&#x2318;</span>
        <span>Select a workspace to view operations</span>
      </div>`;
    }
    return html`
      <div class="header">
        <h1>Operations</h1>
        ${this._journalCount > 0
          ? html`<span class="badge">${this._journalCount} journal entries</span>`
          : ''}
      </div>

      ${this._renderSummaryRow()}

      <fc-operations-summary-card .workspaceId=${this.workspaceId}
        style="margin-bottom:16px"></fc-operations-summary-card>

      <div class="columns">
        <div>
          <div class="panel-title">Action Inbox</div>
          <fc-operations-inbox .workspaceId=${this.workspaceId}></fc-operations-inbox>
        </div>
        <div class="right-stack">
          <fc-queen-journal-panel .workspaceId=${this.workspaceId}></fc-queen-journal-panel>
          <fc-operating-procedures-editor .workspaceId=${this.workspaceId}></fc-operating-procedures-editor>
        </div>
      </div>
    `;
  }

  private get _journalCount(): number {
    return this._journal?.totalEntries ?? 0;
  }

  private _renderSummaryRow() {
    const journalCount = this._journal?.totalEntries ?? 0;
    const procExists = this._procedures?.exists ?? false;
    return html`
      <div class="summary-row">
        <div class="stat-card">
          <div class="stat-label">Journal Entries</div>
          <div class="stat-value">${this._loading ? '-' : journalCount}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Procedures</div>
          <div class="stat-value">${this._loading ? '-' : (procExists ? 'Active' : 'None')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending Actions</div>
          <div class="stat-value">${this._loading ? '-' : '0'}</div>
        </div>
      </div>
    `;
  }

  private _renderJournalSlot() {
    if (this._loading) {
      return html`<div class="empty-state"><span>Loading...</span></div>`;
    }
    if (!this._journal?.exists) {
      return html`<div class="empty-state">
        <span class="icon">&#x1F4D3;</span>
        <span>No journal entries yet</span>
        <span class="hint">The Queen records decisions and context here during sessions</span>
      </div>`;
    }
    const entries = this._journal.entries.slice(-5);
    return html`
      ${entries.map(e => html`
        <div class="journal-entry">
          <span class="journal-source">[${e.source}]</span>
          ${e.message}
        </div>
      `)}
      ${this._journal.totalEntries > 5
        ? html`<div class="journal-more">
            +${this._journal.totalEntries - 5} earlier entries
          </div>`
        : ''}
    `;
  }

  private _renderProceduresSlot() {
    if (this._loading) {
      return html`<div class="empty-state"><span>Loading...</span></div>`;
    }
    if (!this._procedures?.exists) {
      return html`<div class="empty-state">
        <span class="icon">&#x1F4CB;</span>
        <span>No procedures written yet</span>
        <span class="hint">Operating procedures guide Queen behavior for this workspace</span>
      </div>`;
    }
    const preview = this._procedures.content.length > 300
      ? this._procedures.content.slice(0, 300) + '...'
      : this._procedures.content;
    return html`<div class="proc-preview">${preview}</div>`;
  }
}
