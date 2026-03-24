import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { timeAgo } from '../helpers.js';
import type { MemoryEntryPreview } from '../types.js';
import './atoms.js';

type SortBy = 'newest' | 'confidence' | 'status';
type FilterType = '' | 'skill' | 'experience';
type FilterStatus = '' | 'candidate' | 'verified' | 'rejected' | 'stale';

@customElement('fc-memory-browser')
export class FcMemoryBrowser extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 960px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .controls { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; flex-wrap: wrap; }
    .search-input {
      flex: 1; min-width: 180px; max-width: 320px; padding: 6px 10px; border-radius: 8px;
      border: 1px solid var(--v-border); background: var(--v-recessed); color: var(--v-fg);
      font-size: 11px; font-family: var(--f-mono); outline: none;
    }
    .search-input::placeholder { color: var(--v-fg-dim); }
    .search-input:focus { border-color: rgba(232,88,26,0.3); }
    .filter-pill {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .filter-pill.active { background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.2); color: var(--v-accent); }
    .divider { width: 1px; height: 16px; background: var(--v-border); margin: 0 4px; }
    .entry-list { display: flex; flex-direction: column; gap: 6px; }
    .entry-card { padding: 12px; }
    .entry-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
    .entry-title { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .entry-content {
      font-size: 11.5px; color: var(--v-fg-muted); line-height: 1.45; margin-bottom: 6px;
      word-break: break-word; max-height: 80px; overflow: hidden;
    }
    .entry-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .entry-right { width: 80px; flex-shrink: 0; text-align: right; }
    .conf-big { font-family: var(--f-mono); font-size: 14px; font-weight: 600; font-feature-settings: 'tnum'; }
    .conf-bar { height: 3px; background: rgba(255,255,255,0.04); border-radius: 2px; overflow: hidden; margin-top: 3px; }
    .conf-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }
    .entry-row { display: flex; gap: 10px; align-items: flex-start; }
    .entry-left { flex: 1; min-width: 0; }
    .polarity-pos { color: #2DD4A8; }
    .polarity-neg { color: #F06464; }
    .polarity-neu { color: var(--v-fg-dim); }
    .type-skill { background: rgba(167,139,250,0.1); color: #A78BFA; border-color: rgba(167,139,250,0.2); }
    .type-experience { background: rgba(91,156,245,0.1); color: #5B9CF5; border-color: rgba(91,156,245,0.2); }
    .status-verified { background: rgba(45,212,168,0.1); color: #2DD4A8; border-color: rgba(45,212,168,0.2); }
    .status-candidate { background: rgba(245,183,49,0.1); color: #F5B731; border-color: rgba(245,183,49,0.2); }
    .status-rejected { background: rgba(240,100,100,0.1); color: #F06464; border-color: rgba(240,100,100,0.2); }
    .status-stale { background: rgba(107,107,118,0.1); color: #6B6B76; border-color: rgba(107,107,118,0.2); }
    .empty-state { padding: 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px; }
    .loading { padding: 16px; text-align: center; color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); }
    .domains-row { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
    .domain-tag {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border);
    }
  `];

  @property() workspaceId = '';
  /** Optional: pre-filter to a specific source colony */
  @property() sourceColonyId = '';

  @state() private entries: MemoryEntryPreview[] = [];
  @state() private loading = true;
  @state() private searchQuery = '';
  @state() private filterType: FilterType = '';
  @state() private filterStatus: FilterStatus = '';
  @state() private sortBy: SortBy = 'newest';
  @state() private total = 0;

  private _debounceTimer = 0;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchEntries();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('sourceColonyId') || changed.has('workspaceId')) {
      void this._fetchEntries();
    }
  }

  private async _fetchEntries() {
    this.loading = true;
    try {
      if (this.searchQuery.trim()) {
        await this._searchEntries();
      } else {
        await this._listEntries();
      }
    } catch {
      this.entries = [];
      this.total = 0;
    }
    this.loading = false;
  }

  private async _listEntries() {
    const params = new URLSearchParams({ limit: '100' });
    if (this.filterType) params.set('type', this.filterType);
    if (this.filterStatus) params.set('status', this.filterStatus);
    if (this.workspaceId) params.set('workspace', this.workspaceId);
    const resp = await fetch(`/api/v1/memory?${params}`);
    if (resp.ok) {
      const data = await resp.json() as { entries: MemoryEntryPreview[]; total: number };
      let entries = data.entries;
      if (this.sourceColonyId) {
        entries = entries.filter(e => e.source_colony_id === this.sourceColonyId);
      }
      this.entries = entries;
      this.total = data.total;
    } else {
      this.entries = [];
      this.total = 0;
    }
  }

  private async _searchEntries() {
    const params = new URLSearchParams({ q: this.searchQuery.trim(), limit: '50' });
    if (this.filterType) params.set('type', this.filterType);
    if (this.workspaceId) params.set('workspace', this.workspaceId);
    const resp = await fetch(`/api/v1/memory/search?${params}`);
    if (resp.ok) {
      const data = await resp.json() as { results: MemoryEntryPreview[]; total: number };
      this.entries = data.results;
      this.total = data.total;
    } else {
      this.entries = [];
      this.total = 0;
    }
  }

  private _onSearchInput(e: Event) {
    const val = (e.target as HTMLInputElement).value;
    this.searchQuery = val;
    clearTimeout(this._debounceTimer);
    this._debounceTimer = window.setTimeout(() => void this._fetchEntries(), 300);
  }

  private _setFilterType(t: FilterType) {
    this.filterType = this.filterType === t ? '' : t;
    void this._fetchEntries();
  }

  private _setFilterStatus(s: FilterStatus) {
    this.filterStatus = this.filterStatus === s ? '' : s;
    void this._fetchEntries();
  }

  private _setSortBy(s: SortBy) {
    this.sortBy = s;
    this.requestUpdate();
  }

  private get sorted(): MemoryEntryPreview[] {
    const list = [...this.entries];
    if (this.sortBy === 'confidence') {
      list.sort((a, b) => b.confidence - a.confidence);
    } else if (this.sortBy === 'status') {
      const order: Record<string, number> = { verified: 0, candidate: 1, stale: 2, rejected: 3 };
      list.sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
    } else {
      list.sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
    }
    return list;
  }

  render() {
    const sorted = this.sorted;
    return html`
      <div class="title-row">
        <h2><fc-gradient-text>Institutional Memory</fc-gradient-text></h2>
        ${!this.loading && this.entries.length > 0
          ? html`<fc-pill color="var(--v-secondary)" glow>${this.total} entries</fc-pill>`
          : nothing}
        ${this.sourceColonyId
          ? html`<fc-pill color="var(--v-fg-dim)" sm>colony: ${this.sourceColonyId.slice(0, 12)}</fc-pill>`
          : nothing}
      </div>

      <div class="controls">
        <input class="search-input" type="text" placeholder="Search memory..."
          .value=${this.searchQuery} @input=${this._onSearchInput}>
        <span class="divider"></span>
        <span class="filter-pill ${this.filterType === 'skill' ? 'active' : ''}"
          @click=${() => this._setFilterType('skill')}>skill</span>
        <span class="filter-pill ${this.filterType === 'experience' ? 'active' : ''}"
          @click=${() => this._setFilterType('experience')}>experience</span>
        <span class="divider"></span>
        ${(['verified', 'candidate', 'rejected', 'stale'] as const).map(s => html`
          <span class="filter-pill ${this.filterStatus === s ? 'active' : ''}"
            @click=${() => this._setFilterStatus(s)}>${s}</span>
        `)}
        <span class="divider"></span>
        ${(['newest', 'confidence', 'status'] as const).map(s => html`
          <span class="filter-pill ${this.sortBy === s ? 'active' : ''}"
            @click=${() => this._setSortBy(s)}>${s}</span>
        `)}
      </div>

      ${this.loading
        ? html`<div class="loading">Loading memory entries\u2026</div>`
        : sorted.length === 0
          ? html`<div class="glass empty-state">No memory entries match the current filter.</div>`
          : html`<div class="entry-list">${sorted.map(e => this._renderEntry(e))}</div>`}
    `;
  }

  private _renderEntry(e: MemoryEntryPreview) {
    const confColor = e.confidence >= 0.7 ? '#2DD4A8' : e.confidence >= 0.4 ? '#F5B731' : '#E8581A';
    const polarityClass = e.polarity === 'positive' ? 'polarity-pos'
      : e.polarity === 'negative' ? 'polarity-neg' : 'polarity-neu';
    const polarityIcon = e.polarity === 'positive' ? '\u2191' : e.polarity === 'negative' ? '\u2193' : '\u2194';
    const age = e.created_at ? timeAgo(e.created_at) : '';

    return html`
      <div class="glass entry-card">
        <div class="entry-row">
          <div class="entry-left">
            <div class="entry-header">
              <fc-pill class="type-${e.entry_type}" sm>${e.entry_type}</fc-pill>
              <fc-pill class="status-${e.status}" sm>${e.status}</fc-pill>
              <span class="${polarityClass}" style="font-size:11px;font-weight:600" title="${e.polarity}">${polarityIcon}</span>
              <span class="entry-title">${e.title}</span>
            </div>
            <div class="entry-content">${e.summary || e.content}</div>
            <div class="entry-meta">
              <fc-pill color="var(--v-fg-dim)" sm>${e.source_colony_id.slice(0, 12)}</fc-pill>
              ${age ? html`<span style="font-size:8px;font-family:var(--f-mono);color:var(--v-fg-dim)">${age}</span>` : nothing}
              ${e.scan_status && e.scan_status !== 'safe' ? html`
                <fc-pill color="${e.scan_status === 'critical' || e.scan_status === 'high' ? 'var(--v-danger)' : 'var(--v-warn)'}" sm>
                  scan: ${e.scan_status}
                </fc-pill>` : nothing}
            </div>
            ${(e.domains.length > 0 || e.tool_refs.length > 0) ? html`
              <div class="domains-row">
                ${e.domains.map(d => html`<span class="domain-tag">${d}</span>`)}
                ${e.tool_refs.map(t => html`<span class="domain-tag">${t}</span>`)}
              </div>` : nothing}
          </div>
          <div class="entry-right">
            <div class="conf-big" style="color:${confColor}">${(e.confidence * 100).toFixed(0)}%</div>
            <div class="conf-bar">
              <div class="conf-fill" style="width:${Math.round(e.confidence * 100)}%;background:${confColor}"></div>
            </div>
          </div>
        </div>
      </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-memory-browser': FcMemoryBrowser; }
}
