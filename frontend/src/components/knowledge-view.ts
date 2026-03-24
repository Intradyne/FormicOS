import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

// Plain interfaces (types.ts is frozen for Wave 13)
interface KGNode {
  id: string;
  name: string;
  entity_type: string;
  summary: string | null;
  source_colony: string | null;
  workspace_id: string;
  created_at: string;
}

interface KGEdge {
  id: string;
  from_node: string;
  to_node: string;
  predicate: string;
  confidence: number;
  source_colony: string | null;
  source_round: number | null;
  created_at: string;
}

interface KGData {
  nodes: KGNode[];
  edges: KGEdge[];
  stats: { nodes: number; edges: number };
}

interface LibraryFile { name: string; bytes: number; }

type TabId = 'graph' | 'library';

const TYPE_COLOR: Record<string, string> = {
  MODULE: 'var(--v-purple)',
  CONCEPT: 'var(--v-secondary)',
  SKILL: 'var(--v-success)',
  TOOL: 'var(--v-warn)',
  PERSON: 'var(--v-accent)',
  ORGANIZATION: 'var(--v-blue)',
};

@customElement('fc-knowledge-view')
export class FcKnowledgeView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; }
    .header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .header h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .tab-row { margin-left: auto; display: flex; gap: 4px; }
    .tab-pill {
      font-size: 9.5px; font-family: var(--f-mono); padding: 2px 10px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none; text-transform: capitalize;
    }
    .tab-pill.active { background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.2); color: var(--v-accent); }
    .badge-line {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-bottom: 10px;
    }

    /* Graph tab */
    .graph-layout { display: flex; gap: 14px; }
    .graph-svg-wrap { flex: 1; min-height: 380px; padding: 0; overflow: hidden; }
    .graph-svg-wrap svg { width: 100%; height: 380px; }
    .filter-row { display: flex; gap: 5px; margin-bottom: 10px; }
    .filter-pill {
      font-size: 8.5px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .filter-pill.active { border-color: currentColor; }
    .detail-panel { width: 220px; flex-shrink: 0; }
    .detail-name { font-family: var(--f-display); font-size: 14px; font-weight: 600; color: var(--v-fg); margin-bottom: 2px; }
    .detail-summary { font-size: 9px; color: var(--v-fg-muted); margin-top: 6px; line-height: 1.4; }
    .detail-source { font-size: 9px; color: var(--v-fg-dim); margin-top: 6px; }
    .conn-row { display: flex; align-items: center; gap: 3px; padding: 2px 0; font-size: 9px; }
    .conn-pred { color: var(--v-fg-dim); font-family: var(--f-mono); }
    .conn-arrow { color: var(--v-fg); }
    .conn-name { cursor: pointer; }
    .conn-name:hover { text-decoration: underline; }
    .empty-hint { padding: 16px; text-align: center; font-size: 10px; color: var(--v-fg-dim); }
    .graph-empty {
      display: flex; align-items: center; justify-content: center; min-height: 300px;
      color: var(--v-fg-muted); font-size: 12px; text-align: center;
    }

    /* Library tab */
    .lib-file-row {
      display: flex; align-items: center; gap: 8px; padding: 6px 12px;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid var(--v-border);
    }
    .lib-file-row:last-child { border-bottom: none; }
    .lib-file-name { color: var(--v-fg); flex: 1; }
    .lib-file-size { color: var(--v-fg-dim); font-size: 9.5px; }
    .lib-actions { display: flex; gap: 6px; margin-bottom: 12px; }
    .lib-status { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 8px; }
  `];

  @property() workspaceId = '';
  /** When true, render only the graph — hide the tab row and skills/library sections. */
  @property({ type: Boolean }) graphOnly = false;
  /** Which tab to show initially (ignored when graphOnly is true). */
  @property() initialTab: TabId = 'graph';

  @state() private tab: TabId = 'graph';
  @state() private kgData: KGData = { nodes: [], edges: [], stats: { nodes: 0, edges: 0 } };
  @state() private loading = false;
  @state() private selectedNode: string | null = null;
  @state() private filterType: string | null = null;
  // skillCount removed (Wave 28) — knowledge-view is now graph-only
  @state() private libFiles: LibraryFile[] = [];
  @state() private libIngesting = false;
  @state() private libStatus = '';

  connectedCallback() {
    super.connectedCallback();
    this.tab = this.graphOnly ? 'graph' : this.initialTab;
    void this._fetchKG();
  }

  private async _fetchKG() {
    this.loading = true;
    try {
      const resp = await fetch('/api/v1/knowledge-graph');
      if (resp.ok) {
        this.kgData = await resp.json();
      }
    } catch { /* graceful degradation */ }
    this.loading = false;
  }

  // ── Graph layout ─────────────────────────────────────────

  private get filteredNodes(): KGNode[] {
    if (!this.filterType) return this.kgData.nodes;
    return this.kgData.nodes.filter(n => n.entity_type === this.filterType);
  }

  private get filteredEdges(): KGEdge[] {
    const ids = new Set(this.filteredNodes.map(n => n.id));
    return this.kgData.edges.filter(e => ids.has(e.from_node) && ids.has(e.to_node));
  }

  private get entityTypes(): string[] {
    return [...new Set(this.kgData.nodes.map(n => n.entity_type))];
  }

  private nodePositions(): Map<string, { x: number; y: number }> {
    const nodes = this.filteredNodes;
    const pos = new Map<string, { x: number; y: number }>();
    const cx = 280, cy = 190;
    nodes.forEach((n, i) => {
      const angle = (i / Math.max(nodes.length, 1)) * 2 * Math.PI;
      const r = 120 + ((i * 17) % 40);
      pos.set(n.id, { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r });
    });
    return pos;
  }

  private _nodeById(id: string): KGNode | undefined {
    return this.kgData.nodes.find(n => n.id === id);
  }

  // ── Render ───────────────────────────────────────────────

  render() {
    // Graph-only mode: skip header/tabs, render only the graph visualization
    if (this.graphOnly) {
      return this._renderGraph();
    }

    const { stats } = this.kgData;

    return html`
      <div class="header">
        <h2><fc-gradient-text>Knowledge</fc-gradient-text></h2>
        <fc-pill color="var(--v-fg-dim)">${stats.nodes} entities</fc-pill>
        <div class="tab-row">
          ${(['graph', 'library'] as const).map(t => html`
            <span class="tab-pill ${this.tab === t ? 'active' : ''}"
              @click=${() => { this.tab = t; if (t === 'library') void this._fetchLibFiles(); }}>${t}</span>
          `)}
        </div>
      </div>

      ${this.tab === 'library' ? this._renderLibrary()
        : this.kgData.nodes.length === 0 && !this.loading
        ? html`
          <div class="empty-state">
            <div class="empty-icon">\u25C8</div>
            <div class="empty-title">Knowledge grows with experience</div>
            <div class="empty-desc">Graph entities appear here after your first completed colony.</div>
          </div>`
        : this._renderGraph()
      }
    `;
  }

  private _renderGraph() {
    const nodes = this.filteredNodes;
    const edges = this.filteredEdges;

    if (this.kgData.nodes.length === 0 && !this.loading) {
      return html`<div class="glass graph-empty">
        No knowledge graph data yet.<br>
        Entities will appear as colonies complete work.
      </div>`;
    }

    const pos = this.nodePositions();
    const sel = this.selectedNode;

    return html`
      <div class="filter-row">
        <span class="filter-pill ${!this.filterType ? 'active' : ''}"
          style="color:var(--v-accent)" @click=${() => { this.filterType = null; }}>All</span>
        ${this.entityTypes.map(t => html`
          <span class="filter-pill ${this.filterType === t ? 'active' : ''}"
            style="color:${TYPE_COLOR[t] ?? 'var(--v-fg-dim)'}"
            @click=${() => { this.filterType = this.filterType === t ? null : t; }}>${t}</span>
        `)}
      </div>

      <div class="graph-layout">
        <div class="glass graph-svg-wrap">
          <svg viewBox="0 0 560 380">
            <defs>
              <marker id="kgArrow" viewBox="0 0 10 6" refX="10" refY="3"
                markerWidth="5" markerHeight="3.5" orient="auto">
                <path d="M0,0 L10,3 L0,6" fill="var(--v-fg-dim)"/>
              </marker>
            </defs>

            ${edges.map(e => {
              const a = pos.get(e.from_node);
              const b = pos.get(e.to_node);
              if (!a || !b) return nothing;
              const hl = sel === e.from_node || sel === e.to_node;
              return html`
                <line x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y}
                  stroke=${hl ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.06)'}
                  stroke-width=${hl ? 1.5 : 0.8} marker-end="url(#kgArrow)"/>
                <text x=${(a.x + b.x) / 2} y=${(a.y + b.y) / 2 - 4}
                  text-anchor="middle" fill=${hl ? 'var(--v-fg-muted)' : 'var(--v-fg-dim)'}
                  style="font-family:var(--f-mono);font-size:6px">${e.predicate}</text>
              `;
            })}

            ${nodes.map(n => {
              const p = pos.get(n.id);
              if (!p) return nothing;
              const isSel = sel === n.id;
              const c = TYPE_COLOR[n.entity_type] ?? 'var(--v-fg-muted)';
              const label = n.name.length > 14 ? n.name.slice(0, 14) + '\u2026' : n.name;
              return html`
                <g @click=${() => { this.selectedNode = isSel ? null : n.id; }}
                   style="cursor:pointer">
                  ${isSel ? html`<circle cx=${p.x} cy=${p.y} r="26" fill="none"
                    stroke=${c} stroke-width="0.5" opacity="0.4"/>` : nothing}
                  <circle cx=${p.x} cy=${p.y} r=${isSel ? 16 : 12}
                    fill=${isSel ? `${c}20` : 'var(--v-surface)'}
                    stroke=${c} stroke-opacity=${isSel ? 0.38 : 0.19} stroke-width="1"/>
                  <text x=${p.x} y=${p.y + 3} text-anchor="middle"
                    fill=${isSel ? c : 'var(--v-fg-muted)'}
                    style="font-family:var(--f-mono);font-size:6px;font-weight:600">${label}</text>
                </g>
              `;
            })}
          </svg>
        </div>

        <div class="detail-panel">
          ${sel ? this._renderDetail(sel) : html`<div class="empty-hint">Click a node</div>`}
        </div>
      </div>
    `;
  }

  private _renderDetail(nodeId: string) {
    const node = this._nodeById(nodeId);
    if (!node) return nothing;

    const edges = this.kgData.edges.filter(e => e.from_node === nodeId || e.to_node === nodeId);
    const c = TYPE_COLOR[node.entity_type] ?? 'var(--v-fg-dim)';

    return html`
      <div class="glass" style="padding:12px">
        <div class="detail-name">${node.name}</div>
        <fc-pill color=${c} sm>${node.entity_type}</fc-pill>
        ${node.summary ? html`<div class="detail-summary">${node.summary}</div>` : nothing}
        ${node.source_colony ? html`<div class="detail-source">Source: ${node.source_colony}</div>` : nothing}
        ${edges.length > 0 ? html`
          <div style="margin-top:8px">
            <div class="s-label">Connections</div>
            ${edges.map(e => {
              const otherId = e.from_node === nodeId ? e.to_node : e.from_node;
              const other = this._nodeById(otherId);
              const dir = e.from_node === nodeId ? '\u2192' : '\u2190';
              const oc = TYPE_COLOR[other?.entity_type ?? ''] ?? 'var(--v-fg)';
              return html`
                <div class="conn-row">
                  <span class="conn-pred">${e.predicate}</span>
                  <span class="conn-arrow">${dir}</span>
                  <span class="conn-name" style="color:${oc}"
                    @click=${() => { this.selectedNode = otherId; }}>${other?.name ?? otherId}</span>
                </div>`;
            })}
          </div>
        ` : nothing}
      </div>
    `;
  }
  // ── Library tab (Wave 22 Track B) ────────────────────────

  private async _fetchLibFiles() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(`/api/v1/workspaces/${this.workspaceId}/files`);
      if (resp.ok) {
        const data = await resp.json() as { files?: LibraryFile[] };
        this.libFiles = data.files ?? [];
      }
    } catch { /* best-effort */ }
  }

  private _renderLibrary() {
    return html`
      <div class="badge-line">
        Workspace library — uploaded documents become searchable knowledge after ingestion
      </div>
      <div class="lib-actions">
        <fc-btn variant="primary" sm @click=${() => this._ingestUpload()}>
          Upload &amp; Ingest
        </fc-btn>
        <fc-btn variant="ghost" sm @click=${() => void this._fetchLibFiles()}>Refresh</fc-btn>
      </div>
      ${this.libStatus ? html`<div class="lib-status">${this.libStatus}</div>` : nothing}
      <div class="glass" style="padding:0;overflow:hidden">
        ${this.libFiles.length > 0
          ? this.libFiles.map(f => html`
            <div class="lib-file-row">
              <span class="lib-file-name">${f.name}</span>
              <span class="lib-file-size">${this._fmtBytes(f.bytes)}</span>
            </div>`)
          : html`<div class="empty-hint">Upload documents here to make them searchable by the Queen and colonies</div>`
        }
      </div>
    `;
  }

  private _ingestUpload() {
    if (!this.workspaceId) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.txt,.md,.py,.json,.yaml,.yml,.csv';
    input.onchange = async () => {
      if (!input.files?.length) return;
      const form = new FormData();
      for (const file of Array.from(input.files)) {
        form.append(file.name, file);
      }
      this.libIngesting = true;
      this.libStatus = 'Ingesting...';
      try {
        const resp = await fetch(
          `/api/v1/workspaces/${this.workspaceId}/ingest`,
          { method: 'POST', body: form },
        );
        if (resp.ok) {
          const data = await resp.json() as { ingested?: Array<{ name: string; chunks: number }> };
          const items = data.ingested ?? [];
          const names = items.map(i => `${i.name} (${i.chunks} chunks)`).join(', ');
          this.libStatus = items.length > 0 ? `Ingested: ${names}` : 'No files ingested.';
        } else {
          this.libStatus = 'Ingestion failed.';
        }
        await this._fetchLibFiles();
      } catch {
        this.libStatus = 'Ingestion failed.';
      }
      this.libIngesting = false;
    };
    input.click();
  }

  private _fmtBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-knowledge-view': FcKnowledgeView; }
}
