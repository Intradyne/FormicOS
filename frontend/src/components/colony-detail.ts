import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { colonyName, providerColor } from '../helpers.js';
import type { Colony, QueenThread, RedirectHistoryEntry, RoutingOverride, ColonyTranscript, ArtifactPreview, ArtifactDetail, KnowledgeAccessTrace } from '../types.js';
import './atoms.js';
import './colony-audit.js';
import './colony-chat.js';
import './round-history.js';
import './topology-graph.js';
import './directive-panel.js';
import type { ColonyChatEntry } from './colony-chat.js';

interface FileEntry { name: string; bytes: number; }

@customElement('fc-colony-detail')
export class FcColonyDetail extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; gap: 16px; height: 100%; overflow: hidden; }
    .main { flex: 1; overflow: auto; padding-right: 4px; }
    .header { margin-bottom: 5px; }
    .name-row { display: flex; align-items: center; gap: 7px; margin-bottom: 3px; flex-wrap: wrap; }
    .name { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); letter-spacing: -0.03em; }
    .uuid { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .task { font-size: 12px; color: var(--v-fg-muted); margin: 0 0 12px; line-height: 1.45; }
    .grid { display: grid; grid-template-columns: 3fr 2fr; gap: 10px; margin-bottom: 16px; }
    .topo-header {
      padding: 6px 12px; border-bottom: 1px solid var(--v-border);
      display: flex; align-items: center; justify-content: space-between;
    }
    .topo-label { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase; font-weight: 600; }
    .topo-round { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); font-feature-settings: 'tnum'; }
    .topo-area { height: 190px; }
    .metrics { display: flex; flex-direction: column; gap: 10px; }
    .agents-table { width: 100%; border-collapse: collapse; font-family: var(--f-mono); font-size: 11.5px; }
    .agents-table th {
      padding: 6px 8px; text-align: left; color: var(--v-fg-dim); font-weight: 600; font-size: 9.5px;
      letter-spacing: 0.12em; text-transform: uppercase; border-bottom: 1px solid var(--v-border);
    }
    .agents-table td { padding: 6px 8px; }
    .ph-bar { width: 40px; height: 3px; background: rgba(255,255,255,0.03); border-radius: 2px; overflow: hidden; }
    .ph-fill { height: 100%; border-radius: 2px; background: var(--v-accent); }
    .actions { display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
    .quality-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-family: var(--f-mono); font-size: 11px; color: var(--v-fg-muted); }
    .quality-value { font-weight: 700; font-size: 13px; font-feature-settings: 'tnum'; }
    .skills-count { font-weight: 600; color: var(--v-purple); }
    .memory-count { font-weight: 600; color: var(--v-blue); cursor: pointer; }
    .memory-count:hover { text-decoration: underline; }
    .provider-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; margin-right: 4px; flex-shrink: 0; }
    .model-cell { color: var(--v-fg-muted); font-size: 10.5px; display: flex; align-items: center; }
    .routing-summary { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-bottom: 6px; display: flex; gap: 10px; flex-wrap: wrap; }
    .sparkline-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
    .sparkline-label { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    fc-colony-chat { width: 280px; flex-shrink: 0; border: 1px solid var(--v-border); border-radius: 10px; background: var(--v-surface); }
    :host([service]) fc-colony-chat { border-color: rgba(34,211,238,0.15); }
    .service-banner {
      display: flex; align-items: center; gap: 6px; padding: 8px 12px; margin-bottom: 12px;
      background: var(--v-service-muted); border: 1px solid rgba(34,211,238,0.1);
      border-radius: 8px; font-size: 11px; font-family: var(--f-mono); color: var(--v-service);
    }
    .service-type { font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; }
    .export-panel {
      margin-bottom: 16px; padding: 12px; border: 1px solid var(--v-border);
      border-radius: 8px; background: var(--v-surface);
    }
    .export-panel .s-label { margin-bottom: 8px; }
    .export-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 10px; }
    .export-col-header {
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
      margin-bottom: 6px;
    }
    .file-check { display: flex; align-items: center; gap: 6px; padding: 2px 0; font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted); }
    .file-check input { margin: 0; accent-color: var(--v-accent); }
    .file-check .file-size { color: var(--v-fg-dim); font-size: 9.5px; margin-left: auto; }
    .cat-check { display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 11.5px; color: var(--v-fg); }
    .cat-check input { margin: 0; accent-color: var(--v-accent); }
    .export-actions { display: flex; gap: 6px; align-items: center; }
    .ws-files { margin-bottom: 16px; }
    .ws-files-list { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; }
    .ws-file-row {
      display: flex; align-items: center; gap: 8px; padding: 4px 0;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid var(--v-border);
    }
    .ws-file-row:last-child { border-bottom: none; }
    .ws-file-name { color: var(--v-fg); flex: 1; }
    .ws-file-size { color: var(--v-fg-dim); font-size: 9.5px; }
    .ws-file-actions { display: flex; align-items: center; gap: 6px; }
    .preview-panel {
      margin-top: 10px; border-top: 1px solid var(--v-border);
      padding: 10px 12px 12px;
    }
    .preview-header {
      display: flex; align-items: center; justify-content: space-between; gap: 8px;
      margin-bottom: 8px;
    }
    .preview-name { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg); }
    .preview-body {
      max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word;
      font-family: var(--f-mono); font-size: 11px; line-height: 1.45; color: var(--v-fg-muted);
      background: var(--v-recessed); border: 1px solid var(--v-border); border-radius: 8px; padding: 10px;
    }
    .preview-note { margin-top: 6px; font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .empty-hint { font-size: 11px; color: var(--v-fg-dim); padding: 12px; text-align: center; }
    .tab-bar {
      display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--v-border);
    }
    .tab-btn {
      padding: 8px 16px; font-size: 11px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); background: none; border: none; cursor: pointer;
      border-bottom: 2px solid transparent; letter-spacing: 0.05em; text-transform: uppercase;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn:hover { color: var(--v-fg-muted); }
    .tab-btn.active { color: var(--v-accent); border-bottom-color: var(--v-accent); }
    .tab-btn .tab-count {
      font-size: 9px; padding: 1px 5px; border-radius: 8px;
      background: rgba(255,255,255,0.06); margin-left: 4px; font-weight: 400;
      font-feature-settings: 'tnum';
    }
    .artifacts-list { display: flex; flex-direction: column; gap: 0; }
    .artifact-tab-card {
      padding: 12px; border-bottom: 1px solid var(--v-border);
    }
    .artifact-tab-card:last-child { border-bottom: none; }
    .artifact-tab-header {
      display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    }
    .artifact-tab-name { font-family: var(--f-display); font-weight: 600; font-size: 12px; color: var(--v-fg); }
    .artifact-tab-meta {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      display: flex; gap: 8px; margin-bottom: 6px;
    }
    .artifact-tab-content {
      font-family: var(--f-mono); font-size: 10.5px; line-height: 1.5;
      color: var(--v-fg-muted); background: var(--v-recessed);
      border: 1px solid var(--v-border); border-radius: 6px;
      padding: 10px; white-space: pre-wrap; word-break: break-word;
      max-height: 300px; overflow: auto;
    }
    .activity-block {
      margin-bottom: 14px; padding: 10px 12px; border-radius: 8px;
      background: rgba(45,212,168,0.03); border: 1px solid rgba(45,212,168,0.1);
    }
    .activity-row {
      display: flex; align-items: center; gap: 6px; padding: 3px 0;
      font-size: 10.5px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .activity-dot {
      width: 4px; height: 4px; border-radius: 50%; flex-shrink: 0;
    }
    .activity-time { font-size: 9px; color: var(--v-fg-dim); margin-left: auto; font-feature-settings: 'tnum'; }
    .progress-block { margin-bottom: 14px; }
    .progress-label { font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted); margin-bottom: 4px; font-feature-settings: 'tnum'; }
    .progress-bar { height: 4px; background: rgba(255,255,255,0.04); border-radius: 2px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--v-accent); border-radius: 2px; transition: width 0.3s; }
    .outcome-section { margin-bottom: 14px; }
    .outcome-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px; padding: 12px;
    }
    .outcome-stat { text-align: center; }
    .outcome-val { font-family: var(--f-mono); font-size: 16px; font-weight: 700; color: var(--v-fg); font-feature-settings: 'tnum'; }
    .outcome-lbl { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
    .outcome-maintenance {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      padding: 4px 12px; border-top: 1px solid var(--v-border);
    }
    .final-output-section { margin-bottom: 14px; }
    .final-output-text {
      font-size: 11.5px; line-height: 1.55; color: var(--v-fg-muted);
      padding: 10px 12px; background: var(--v-recessed); border-radius: 6px;
      white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow: auto;
    }
    .final-output-agent { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-bottom: 3px; }
    .artifacts-section { margin-bottom: 14px; }
    .artifact-card {
      padding: 8px 10px; margin-bottom: 6px; border-bottom: 1px solid var(--v-border);
    }
    .artifact-card:last-child { border-bottom: none; margin-bottom: 0; }
    .artifact-header {
      display: flex; align-items: center; gap: 6px; margin-bottom: 4px; font-size: 11px;
    }
    .artifact-name { font-family: var(--f-display); font-weight: 600; color: var(--v-fg); }
    .artifact-meta { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); display: flex; gap: 8px; margin-bottom: 4px; }
    .artifact-preview {
      font-size: 10.5px; line-height: 1.45; color: var(--v-fg-muted);
      padding: 6px 8px; background: var(--v-recessed); border-radius: 4px;
      white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: auto;
    }
    .artifact-actions { margin-top: 6px; }
    .artifact-detail {
      margin-top: 8px; padding: 8px; background: var(--v-recessed); border-radius: 6px;
      border: 1px solid var(--v-border); font-size: 10.5px; line-height: 1.5;
      color: var(--v-fg-muted); white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto;
    }
    .knowledge-trace-section { margin-bottom: 14px; }
    .kt-round-header {
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;
      padding: 6px 10px; border-bottom: 1px solid var(--v-border);
    }
    .kt-item {
      display: flex; align-items: center; gap: 8px; padding: 5px 10px;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid rgba(255,255,255,0.02);
    }
    .kt-item:last-child { border-bottom: none; }
    .kt-source { font-size: 9px; padding: 1px 5px; border-radius: 4px; font-weight: 600; }
    .kt-source.inst { background: rgba(45,212,168,0.08); color: #2DD4A8; }
    .kt-source.legacy { background: rgba(232,162,47,0.08); color: #E8A22F; }
    .kt-title { color: var(--v-fg); font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .kt-conf { font-size: 9.5px; color: var(--v-fg-dim); font-feature-settings: 'tnum'; }
    .escalation-badge {
      display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 999px; font-size: 10px; font-family: var(--f-mono);
      font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    }
    .escalation-badge.heavy { background: rgba(91,156,245,0.1); color: #5B9CF5; border: 1px solid rgba(91,156,245,0.15); }
    .escalation-badge.max { background: rgba(167,139,250,0.1); color: #A78BFA; border: 1px solid rgba(167,139,250,0.15); }
    .escalation-badge.standard { background: rgba(45,212,168,0.1); color: #2DD4A8; border: 1px solid rgba(45,212,168,0.15); }
    .redirect-panel { margin-bottom: 16px; }
    .redirect-entry {
      padding: 8px 12px; border-left: 2px solid var(--v-accent);
      margin-bottom: 6px; font-size: 11px; font-family: var(--f-mono);
      color: var(--v-fg-muted); line-height: 1.45;
    }
    .redirect-entry .redirect-round { color: var(--v-fg-dim); font-size: 9.5px; }
    .redirect-entry .redirect-goal { color: var(--v-fg); font-weight: 500; margin-top: 2px; }
    .redirect-entry .redirect-reason { color: var(--v-fg-dim); font-style: italic; margin-top: 2px; }
    .original-goal { font-size: 11px; color: var(--v-fg-dim); margin-bottom: 6px; }
    .original-goal .label { font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600; }
    .files-changed-section { margin-bottom: 14px; }
    .files-changed-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .files-changed-count {
      font-size: 9px; font-family: var(--f-mono); padding: 1px 6px; border-radius: 8px;
      background: rgba(45,212,168,0.1); color: var(--v-success); font-feature-settings: 'tnum';
    }
    .files-changed-list { display: flex; flex-direction: column; gap: 0; padding: 8px 12px; }
    .file-change-row {
      display: flex; align-items: center; gap: 8px; padding: 5px 0;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid var(--v-border);
    }
    .file-change-row:last-child { border-bottom: none; }
    .file-change-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-change-badge {
      font-size: 8px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
      text-transform: uppercase; letter-spacing: 0.3px; flex-shrink: 0;
    }
    .file-change-badge.created { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .file-change-badge.modified { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .file-change-badge.deleted { background: rgba(240,100,100,0.12); color: var(--v-danger); }
  `];

  @property({ type: Object }) colony: Colony | null = null;
  @property({ type: Array }) queenThreads: QueenThread[] = [];
  @property() activeQT = '';
  @property({ type: Array }) colonyChatMessages: ColonyChatEntry[] = [];

  @state() private _exportOpen = false;
  @state() private _exportChat = true;
  @state() private _exportOutputs = true;
  @state() private _exportUploads = true;
  @state() private _exportWsFiles = false;
  @state() private _colonyFiles: FileEntry[] = [];
  @state() private _wsFiles: FileEntry[] = [];
  @state() private _selectedUploads = new Set<string>();
  @state() private _selectedWsFiles = new Set<string>();
  @state() private _previewName = '';
  @state() private _previewContent = '';
  @state() private _previewTruncated = false;
  @state() private _previewLoading = false;
  @state() private _transcript: ColonyTranscript | null = null;
  @state() private _memoryCount = 0;
  @state() private _artifactExpandedId = '';
  @state() private _artifactDetailLoadingId = '';
  @state() private _artifactDetails: Record<string, ArtifactDetail> = {};
  @state() private _outcome: { quality_score: number; total_cost: number; entries_extracted: number; entries_accessed: number; duration_ms: number; total_rounds: number; maintenance_source: string | null; total_reasoning_tokens: number; total_cache_read_tokens: number; total_output_tokens: number; total_input_tokens: number } | null = null;
  @state() private _activeTab: 'overview' | 'artifacts' = 'overview';
  @state() private _colonyArtifacts: ArtifactPreview[] = [];
  @state() private _artifactsLoaded = false;

  override updated(changed: Map<string, unknown>) {
    if (changed.has('colony') && this.colony) {
      this._previewName = '';
      this._previewContent = '';
      this._previewTruncated = false;
      this._previewLoading = false;
      this._artifactExpandedId = '';
      this._artifactDetailLoadingId = '';
      this._artifactDetails = {};
      this._activeTab = 'overview';
      this._colonyArtifacts = [];
      this._artifactsLoaded = false;
      this._loadWsFiles(this.colony);
      this._loadColonyFiles(this.colony);
      this._loadKnowledgeCount(this.colony);
      if (this.colony.status === 'completed' || this.colony.status === 'failed' || this.colony.status === 'killed') {
        this._loadTranscript(this.colony);
        void this._loadOutcome(this.colony);
      } else {
        this._transcript = null;
        this._outcome = null;
      }
    }
  }

  private async _loadWsFiles(c: Colony) {
    try {
      const wsId = (c as any).workspaceId ?? 'default';
      const res = await fetch(`/api/v1/workspaces/${wsId}/files`);
      if (res.ok) {
        const data = await res.json() as { files?: FileEntry[] };
        this._wsFiles = data.files ?? [];
      }
    } catch { /* best-effort */ }
  }

  private async _loadColonyFiles(c: Colony) {
    try {
      const res = await fetch(`/api/v1/colonies/${c.id}/files`);
      if (res.ok) {
        const data = await res.json() as { files?: FileEntry[] };
        this._colonyFiles = data.files ?? [];
      }
    } catch { /* best-effort */ }
  }

  private async _loadTranscript(c: Colony) {
    try {
      const res = await fetch(`/api/v1/colonies/${c.id}/transcript`);
      if (res.ok) {
        this._transcript = await res.json() as ColonyTranscript;
      }
    } catch { /* best-effort */ }
  }

  private async _loadKnowledgeCount(c: Colony) {
    try {
      const wsId = (c as any).workspaceId ?? 'default';
      const params = new URLSearchParams({
        limit: '200',
        workspace: wsId,
        source_colony_id: c.id,
      });
      const res = await fetch(`/api/v1/knowledge?${params}`);
      if (res.ok) {
        const data = await res.json() as { total: number };
        this._memoryCount = data.total;
      }
    } catch { this._memoryCount = 0; }
  }

  private async _loadOutcome(c: Colony) {
    this._outcome = null;
    try {
      const wsId = (c as any).workspaceId ?? 'default';
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(wsId)}/outcomes?period=30d`);
      if (res.ok) {
        const data = await res.json();
        const match = (data.outcomes ?? []).find((o: Record<string, unknown>) => o.colony_id === c.id);
        if (match) {
          this._outcome = {
            quality_score: (match.quality_score as number) ?? 0,
            total_cost: (match.total_cost as number) ?? 0,
            entries_extracted: (match.entries_extracted as number) ?? 0,
            entries_accessed: (match.entries_accessed as number) ?? 0,
            duration_ms: (match.duration_ms as number) ?? 0,
            total_rounds: (match.total_rounds as number) ?? 0,
            maintenance_source: (match.maintenance_source as string) ?? null,
            total_reasoning_tokens: (match.total_reasoning_tokens as number) ?? 0,
            total_cache_read_tokens: (match.total_cache_read_tokens as number) ?? 0,
            total_output_tokens: (match.total_output_tokens as number) ?? 0,
            total_input_tokens: (match.total_input_tokens as number) ?? 0,
          };
        }
      }
    } catch { /* best-effort */ }
  }

  private async _loadArtifacts(c: Colony) {
    if (this._artifactsLoaded) return;
    this._artifactsLoaded = true;
    try {
      const res = await fetch(`/api/v1/colonies/${c.id}/artifacts`);
      if (res.ok) {
        const data = await res.json() as { artifacts?: ArtifactPreview[] };
        this._colonyArtifacts = data.artifacts ?? [];
      }
    } catch { /* best-effort */ }
  }

  private _switchTab(tab: 'overview' | 'artifacts') {
    this._activeTab = tab;
    if (tab === 'artifacts' && this.colony) {
      void this._loadArtifacts(this.colony);
    }
  }

  render() {
    const c = this.colony;
    if (!c) return nothing;
    const name = colonyName(c);
    const totalTok = (c.agents ?? []).reduce((a, ag) => a + ag.tokens, 0);
    const isService = (c as Colony & { serviceType?: string }).serviceType != null;
    const serviceType = (c as Colony & { serviceType?: string }).serviceType;
    const statusColor = isService ? 'var(--v-service)'
      : c.status === 'running' ? 'var(--v-success)' : c.status === 'completed' ? 'var(--v-secondary)' : c.status === 'failed' || c.status === 'killed' ? 'var(--v-danger)' : 'var(--v-warn)';
    const convHistory = (c as Colony & { convergenceHistory?: number[] }).convergenceHistory;

    // Derive chat messages: explicit prop > colony snapshot data
    const chatMsgs = this.colonyChatMessages.length > 0
      ? this.colonyChatMessages
      : ((c as any).chatMessages ?? []) as ColonyChatEntry[];
    const templateId = (c as Colony & { templateId?: string }).templateId;

    return html`
      <div class="main">
        <div class="header">
          <div class="name-row">
            <span class="name">\u2B21 ${name}</span>
            <fc-btn variant="ghost" sm @click=${() => this._renameColony(c)} title="Rename colony">\u270E</fc-btn>
            ${c.displayName ? html`<span class="uuid" title="${c.id}">${c.id}</span>` : nothing}
            <fc-pill .color=${statusColor} glow>
              <fc-dot .status=${c.status} .size=${4}></fc-dot> ${c.status}
            </fc-pill>
            <fc-pill color="var(--v-fg-dim)" sm>${c.strategy ?? 'stigmergic'}</fc-pill>
            ${templateId ? html`<fc-pill color="var(--v-secondary)" sm>from template</fc-pill>` : nothing}
            ${c.routingOverride ? html`
              <span class="escalation-badge ${c.routingOverride.tier}" title="${c.routingOverride.reason}">
                \u2191 ${c.routingOverride.tier}
              </span>` : nothing}
            ${c.status === 'completed' && c.qualityScore > 0 ? html`
              <fc-pill .color=${c.qualityScore >= 0.8 ? 'var(--v-success)' : c.qualityScore >= 0.5 ? 'var(--v-warn)' : 'var(--v-danger)'} sm>
                quality ${(c.qualityScore * 100).toFixed(0)}%
              </fc-pill>` : nothing}
            ${this._renderCompletionPill(c)}
          </div>
          ${c.task ? html`<p class="task">${c.activeGoal && c.activeGoal !== c.task ? c.activeGoal : c.task}</p>` : nothing}
        </div>

        ${this._renderRedirectPanel(c)}

        ${c.status === 'running' ? html`
          <div class="progress-block">
            <div class="progress-label">Round ${c.round ?? 0} / ${c.maxRounds ?? 0}</div>
            <div class="progress-bar">
              <div class="progress-fill" style="width:${c.maxRounds ? ((c.round ?? 0) / c.maxRounds) * 100 : 0}%"></div>
            </div>
          </div>
          ${this._renderLatestActivity(c, chatMsgs)}` : nothing}

        <div class="tab-bar">
          <button class="tab-btn ${this._activeTab === 'overview' ? 'active' : ''}"
            @click=${() => this._switchTab('overview')}>Overview</button>
          <button class="tab-btn ${this._activeTab === 'artifacts' ? 'active' : ''}"
            @click=${() => this._switchTab('artifacts')}>Artifacts${(() => {
              const count = this._artifactsLoaded
                ? this._colonyArtifacts.length
                : (this._transcript?.artifacts?.length ?? 0);
              return count > 0 ? html`<span class="tab-count">${count}</span>` : nothing;
            })()}</button>
        </div>

        ${this._activeTab === 'artifacts' ? this._renderArtifactsTab() : nothing}

        ${this._activeTab === 'overview' ? html`
        ${this._outcome ? this._renderOutcome() : nothing}
        ${this._transcript ? this._renderFinalOutput(c) : nothing}
        ${this._transcript?.knowledge_trace ? this._renderKnowledgeTrace(this._transcript.knowledge_trace) : nothing}

        ${this._renderFilesChanged()}

        <!-- Wave 39 1A: Colony audit view -->
        <div class="audit-section glass" style="padding:12px;margin-bottom:14px">
          <div class="s-label" style="margin-bottom:8px">Audit Trail</div>
          <fc-colony-audit .colonyId=${c.id}></fc-colony-audit>
        </div>

        ${isService ? html`
          <div class="service-banner">
            <span>\u25C6</span>
            <span class="service-type">${serviceType}</span>
            <span>service colony \u2014 accepting queries</span>
          </div>` : nothing}

        <div class="grid">
          <div class="glass" style="padding:0;overflow:hidden">
            <div class="topo-header">
              <span class="topo-label">Topology \u00B7 Pheromone Trails</span>
              <span class="topo-round">R${c.round}/${c.maxRounds}</span>
            </div>
            <div class="topo-area">
              <fc-topology-graph .topology=${c.topology}></fc-topology-graph>
            </div>
          </div>
          <div class="metrics">
            <div class="glass" style="padding:12px">
              <fc-meter label="Convergence" .value=${c.convergence} .max=${1}
                .color=${c.convergence > 0.8 ? '#2DD4A8' : '#E8581A'}></fc-meter>
              ${convHistory && convHistory.length > 1 ? html`
                <div class="sparkline-row">
                  <span class="sparkline-label">trend</span>
                  <fc-sparkline .data=${convHistory} .width=${80} .height=${20}
                    .color=${c.convergence > 0.8 ? '#2DD4A8' : '#E8581A'}></fc-sparkline>
                </div>` : nothing}
              <fc-meter label="Cost" .value=${c.cost} .max=${c.budgetLimit ?? 0} unit="$"
                .color=${this._budgetColor(c.cost, c.budgetLimit ?? 0)}></fc-meter>
              <fc-meter label="Tokens" .value=${totalTok / 1000} .max=${80} unit="k" color="#5B9CF5"></fc-meter>
              ${this._renderQualityRow(c)}
            </div>
            ${c.defense ? html`
              <div class="glass" style="padding:12px">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                  <div class="s-label" style="margin-bottom:0">Defense</div>
                  <fc-defense-gauge .score=${c.defense.composite}></fc-defense-gauge>
                </div>
                ${c.defense.signals.map(s => html`
                  <fc-pheromone-bar .label=${s.name} .value=${s.value} .max=${s.threshold} trend="stable"></fc-pheromone-bar>
                `)}
              </div>` : nothing}
          </div>
        </div>

        ${(c.pheromones?.length ?? 0) > 0 ? html`
          <div style="margin-bottom:16px">
            <div class="s-label">Pheromone Trails</div>
            <div class="glass" style="padding:12px">
              ${c.pheromones.map(p => html`
                <fc-pheromone-bar .label=${`${p.from}\u2192${p.to}`} .value=${p.weight} .max=${2} .trend=${p.trend}></fc-pheromone-bar>
              `)}
            </div>
          </div>` : nothing}

        <div class="s-label">Agents</div>
        ${this._renderRoutingSummary(c)}
        <div class="glass" style="padding:0;margin-bottom:16px;overflow:hidden">
          <table class="agents-table">
            <thead><tr>
              <th></th><th>Agent</th><th>Caste</th><th>Model</th><th>Tokens</th><th>Pheromone</th><th>Status</th>
            </tr></thead>
            <tbody>${(c.agents ?? []).map(a => html`
              <tr style="border-bottom:1px solid var(--v-border)">
                <td><fc-dot .status=${a.status} .size=${5}></fc-dot></td>
                <td style="color:var(--v-fg);font-weight:500">${a.name}</td>
                <td style="color:var(--v-fg-muted);font-size:9.5px">${a.caste}</td>
                <td>
                  <span class="model-cell" title="${a.model}">
                    <span class="provider-dot" style="background:${providerColor(a.model)}"></span>
                    ${a.model.includes('/') ? a.model.split('/').pop() : a.model}
                  </span>
                </td>
                <td class="tnum" style="color:var(--v-fg-muted)">${a.tokens > 0 ? `${(a.tokens / 1000).toFixed(1)}k` : '\u2014'}</td>
                <td><div class="ph-bar"><div class="ph-fill" style="width:${(a.pheromone ?? 0) * 100}%;box-shadow:${a.pheromone > 0.6 ? '0 0 4px var(--v-accent-glow)' : 'none'}"></div></div></td>
                <td><fc-pill .color=${a.status === 'active' ? 'var(--v-success)' : a.status === 'done' ? 'var(--v-secondary)' : 'var(--v-warn)'} sm>${a.status}</fc-pill></td>
              </tr>
            `)}</tbody>
          </table>
        </div>

        <div class="actions">
          <fc-btn variant="secondary" sm @click=${() => this._toggleExport(c)}>
            ${this._exportOpen ? 'Close Export' : 'Export'}
          </fc-btn>
          ${c.status === 'completed' ? html`<fc-btn variant="secondary" sm @click=${() => this._saveAsTemplate(c)}>Save as Template</fc-btn>` : nothing}
          ${c.status === 'completed' && !isService ? html`<fc-btn variant="secondary" sm @click=${() => this._activateService(c)}>Activate as Service</fc-btn>` : nothing}
          <fc-btn variant="danger" sm @click=${() => this._fire('kill-colony', c.id)}>Kill Colony</fc-btn>
        </div>

        ${this._exportOpen ? this._renderExportPanel(c) : nothing}

        ${(c.rounds?.length ?? 0) > 0 ? html`
          <fc-round-history .rounds=${c.rounds}></fc-round-history>
        ` : nothing}

        ${c.status === 'running' ? html`
          <fc-directive-panel
            .colonyId=${c.id}
            @directive-send=${this._onDirectiveSend}
          ></fc-directive-panel>
        ` : nothing}

        ${this._renderWorkspaceFiles(c)}
        ` : nothing}
      </div>
      <fc-colony-chat
        .colonyId=${c.id}
        .colonyName=${name}
        .status=${isService ? 'service' as const : c.status}
        .messages=${chatMsgs}
      ></fc-colony-chat>`;
  }

  private _renderQualityRow(c: Colony) {
    const qs = c.qualityScore ?? 0;
    const sk = c.skillsExtracted ?? 0;
    const qColor = c.status === 'failed' || c.status === 'killed' ? 'var(--v-fg-dim)'
      : qs >= 0.7 ? '#2DD4A8' : qs >= 0.4 ? '#F5B731' : qs > 0 ? '#E8581A' : 'var(--v-fg-dim)';
    const mc = this._memoryCount;
    return html`
      <div class="quality-row">
        <span>Quality</span>
        <span class="quality-value" style="color:${qColor}">${(qs * 100).toFixed(0)}%</span>
        ${mc > 0 ? html`
          <span>\u00B7</span>
          <span class="memory-count" @click=${() => this._navToKnowledge(c)}
            title="View knowledge entries extracted from this colony">
            ${mc} knowledge entr${mc !== 1 ? 'ies' : 'y'}
          </span>` : nothing}
        ${sk > 0 ? html`
          <span>\u00B7</span>
          <span style="color:var(--v-fg-dim);font-size:10px"
            title="Frozen compatibility path for archived or imported skill records">${sk} archived skill record${sk !== 1 ? 's' : ''}</span>` : nothing}
      </div>`;
  }

  /** Wave 39 1B: tri-state completion pill */
  private _renderCompletionPill(c: Colony) {
    if (c.status === 'completed') {
      if (c.validatorVerdict === 'pass') {
        return html`<fc-pill color="var(--v-success)" sm>\u2713 validated</fc-pill>`;
      }
      return html`<fc-pill color="var(--v-warn)" sm>\u25CB unvalidated</fc-pill>`;
    }
    if (c.status === 'failed' || c.status === 'killed') {
      return html`<fc-pill color="var(--v-danger)" sm>\u25A0 stalled</fc-pill>`;
    }
    return nothing;
  }

  private _renderOutcome() {
    const o = this._outcome!;
    const durSec = o.duration_ms / 1000;
    const durLabel = durSec > 60 ? `${(durSec / 60).toFixed(1)}m` : `${durSec.toFixed(0)}s`;
    const costPerRound = o.total_rounds > 0 ? o.total_cost / o.total_rounds : 0;
    const qColor = o.quality_score >= 0.7 ? '#2DD4A8' : o.quality_score >= 0.4 ? '#F5B731' : o.quality_score > 0 ? '#E8581A' : 'var(--v-fg-dim)';
    return html`
      <div class="outcome-section">
        <div class="s-label">Outcome</div>
        <div class="glass outcome-grid">
          <div class="outcome-stat">
            <div class="outcome-val" style="color:${qColor}">${o.quality_score > 0 ? `${(o.quality_score * 100).toFixed(0)}%` : '\u2014'}</div>
            <div class="outcome-lbl">Quality</div>
          </div>
          <div class="outcome-stat">
            <div class="outcome-val" style="color:var(--v-accent)">$${o.total_cost.toFixed(2)}</div>
            <div class="outcome-lbl">Cost</div>
          </div>
          <div class="outcome-stat">
            <div class="outcome-val">${o.entries_extracted}</div>
            <div class="outcome-lbl">Extracted</div>
          </div>
          <div class="outcome-stat">
            <div class="outcome-val">${o.entries_accessed}</div>
            <div class="outcome-lbl">Accessed</div>
          </div>
          <div class="outcome-stat">
            <div class="outcome-val">${durLabel}</div>
            <div class="outcome-lbl">Duration</div>
          </div>
          <div class="outcome-stat">
            <div class="outcome-val">$${costPerRound.toFixed(3)}/r</div>
            <div class="outcome-lbl">Cost/Round</div>
          </div>
          ${o.total_reasoning_tokens > 0 ? html`
            <div class="outcome-stat">
              <div class="outcome-val">${(o.total_reasoning_tokens / 1000).toFixed(0)}k</div>
              <div class="outcome-lbl">Reasoning${o.total_output_tokens > 0 ? ` (${Math.round(o.total_reasoning_tokens / o.total_output_tokens * 100)}%)` : ''}</div>
            </div>` : nothing}
          ${o.total_cache_read_tokens > 0 ? html`
            <div class="outcome-stat">
              <div class="outcome-val">${(o.total_cache_read_tokens / 1000).toFixed(0)}k</div>
              <div class="outcome-lbl">Cached${o.total_input_tokens > 0 ? ` (${Math.round(o.total_cache_read_tokens / o.total_input_tokens * 100)}% of input)` : ''}</div>
            </div>` : nothing}
        </div>
        ${o.maintenance_source ? html`
          <div class="glass outcome-maintenance">Maintenance: ${o.maintenance_source}</div>
        ` : nothing}
      </div>`;
  }

  private _renderFinalOutput(_c: Colony) {
    const t = this._transcript;
    if (!t || !t.final_output) return nothing;

    return html`
      <div class="final-output-section">
        <div class="s-label">Final Output</div>
        <div class="glass" style="padding:12px">
          <div class="final-output-text">${t.final_output}</div>
        </div>
      </div>
      ${this._renderArtifacts(t.artifacts)}`;
  }

  private _renderArtifacts(artifacts: ArtifactPreview[]) {
    if (!artifacts || artifacts.length === 0) return nothing;

    return html`
      <div class="artifacts-section">
        <div class="s-label">Generated Artifacts</div>
        <div class="glass" style="padding:0;overflow:hidden">
          ${artifacts.map(a => html`
            <div class="artifact-card">
              <div class="artifact-header">
                <fc-pill color="var(--v-secondary)" sm>${a.artifact_type}</fc-pill>
                <span class="artifact-name">${a.name || a.id}</span>
              </div>
              <div class="artifact-meta">
                <span>${a.mime_type}</span>
                ${a.source_agent_id ? html`<span>agent: ${a.source_agent_id}</span>` : nothing}
                ${a.source_round > 0 ? html`<span>round ${a.source_round}</span>` : nothing}
              </div>
              ${a.content_preview ? html`
                <div class="artifact-preview">${a.content_preview}</div>
              ` : nothing}
              <div class="artifact-actions">
                <fc-btn variant="ghost" sm @click=${() => void this._toggleArtifactDetail(a.id)}>
                  ${this._artifactExpandedId === a.id ? 'Hide detail' : 'Inspect'}
                </fc-btn>
              </div>
              ${this._artifactExpandedId === a.id ? html`
                <div class="artifact-detail">
                  ${this._artifactDetailLoadingId === a.id
                    ? 'Loading full artifact…'
                    : (this._artifactDetails[a.id]?.content || 'Full artifact detail unavailable.')}
                </div>
              ` : nothing}
            </div>
          `)}
        </div>
      </div>`;
  }

  private _renderArtifactsTab() {
    const arts = this._colonyArtifacts;
    if (!this._artifactsLoaded) {
      return html`<div class="empty-hint">Loading artifacts...</div>`;
    }
    if (arts.length === 0) {
      return html`
        <div class="glass" style="padding:0;overflow:hidden">
          <div class="empty-hint">No artifacts produced</div>
        </div>`;
    }
    return html`
      <div class="glass" style="padding:0;overflow:hidden">
        <div class="artifacts-list">
          ${arts.map(a => html`
            <div class="artifact-tab-card">
              <div class="artifact-tab-header">
                <fc-pill color="var(--v-secondary)" sm>${a.artifact_type}</fc-pill>
                <span class="artifact-tab-name">${a.name || a.id}</span>
              </div>
              <div class="artifact-tab-meta">
                <span>${a.mime_type}</span>
                ${a.source_agent_id ? html`<span>agent: ${a.source_agent_id}</span>` : nothing}
                ${a.source_round > 0 ? html`<span>round ${a.source_round}</span>` : nothing}
              </div>
              <pre class="artifact-tab-content"><code>${a.content_preview || 'No content available.'}</code></pre>
              <div style="margin-top:6px">
                <fc-btn variant="ghost" sm @click=${() => void this._toggleArtifactDetail(a.id)}>
                  ${this._artifactExpandedId === a.id ? 'Hide full content' : 'View full content'}
                </fc-btn>
              </div>
              ${this._artifactExpandedId === a.id ? html`
                <div class="artifact-detail">
                  ${this._artifactDetailLoadingId === a.id
                    ? 'Loading full artifact...'
                    : (this._artifactDetails[a.id]?.content || 'Full artifact detail unavailable.')}
                </div>
              ` : nothing}
            </div>
          `)}
        </div>
      </div>`;
  }

  private _renderKnowledgeTrace(traces: KnowledgeAccessTrace[]) {
    if (!traces || traces.length === 0) return nothing;

    return html`
      <div class="knowledge-trace-section">
        <div class="s-label">Knowledge Used</div>
        <div class="glass" style="padding:0;overflow:hidden">
          ${traces.map(t => html`
            <div class="kt-round-header">Round ${t.round} · ${t.access_mode}</div>
            ${t.items.map(item => html`
              <div class="kt-item">
                <span class="kt-source ${item.source_system === 'institutional_memory' ? 'inst' : 'legacy'}">
                  ${item.source_system === 'institutional_memory' ? 'INST' : 'LEGACY'}
                </span>
                <span class="kt-title" title="${item.title}">${item.title || item.id}</span>
                <fc-pill color="var(--v-fg-dim)" sm>${item.canonical_type}</fc-pill>
                ${item.conf_alpha != null && item.conf_beta != null ? html`
                  <span class="kt-conf" title="Beta(${item.conf_alpha.toFixed(1)}, ${item.conf_beta.toFixed(1)})">${(item.conf_alpha / (item.conf_alpha + item.conf_beta) * 100).toFixed(0)}%</span>
                ` : html`
                  <span class="kt-conf">${(item.confidence * 100).toFixed(0)}%</span>
                `}
              </div>
            `)}
          `)}
        </div>
      </div>`;
  }

  private async _toggleArtifactDetail(artifactId: string) {
    const colony = this.colony;
    if (!colony) return;
    if (this._artifactExpandedId === artifactId) {
      this._artifactExpandedId = '';
      return;
    }
    this._artifactExpandedId = artifactId;
    if (this._artifactDetails[artifactId] || this._artifactDetailLoadingId === artifactId) {
      return;
    }
    this._artifactDetailLoadingId = artifactId;
    try {
      const res = await fetch(`/api/v1/colonies/${colony.id}/artifacts/${encodeURIComponent(artifactId)}`);
      if (res.ok) {
        const detail = await res.json() as ArtifactDetail;
        this._artifactDetails = { ...this._artifactDetails, [artifactId]: detail };
      }
    } catch {
      // Keep preview usable even if detail fetch fails.
    } finally {
      if (this._artifactDetailLoadingId === artifactId) {
        this._artifactDetailLoadingId = '';
      }
    }
  }

  private _renderRoutingSummary(c: Colony) {
    const agents = c.agents ?? [];
    if (agents.length === 0) return nothing;
    const counts = new Map<string, number>();
    for (const a of agents) {
      const name = a.model.includes('/') ? a.model.split('/').pop()! : a.model;
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    const parts = [...counts.entries()].map(([name, count]) => `${count} ${name}`);
    return html`<div class="routing-summary">${parts.join(', ')}</div>`;
  }

  private _renderLatestActivity(c: Colony, chatMsgs: ColonyChatEntry[]) {
    // Build a bounded list of recent activity from chat messages and agent state
    const recentMsgs = chatMsgs
      .filter(m => m.eventKind || m.sender === 'system')
      .slice(-5)
      .reverse();

    const activeAgents = (c.agents ?? []).filter(a => a.status === 'active');
    if (recentMsgs.length === 0 && activeAgents.length === 0) return nothing;

    const kindColors: Record<string, string> = {
      governance: 'var(--v-warn)',
      service: 'var(--v-service)',
      spawn: 'var(--v-accent)',
      phase: 'var(--v-blue)',
      complete: 'var(--v-success)',
    };

    return html`
      <div class="activity-block">
        <div class="s-label" style="margin-bottom:6px">Latest Activity</div>
        ${activeAgents.length > 0 ? html`
          <div class="activity-row">
            <span class="activity-dot" style="background:var(--v-success);animation:pulse 1.5s infinite"></span>
            <span>${activeAgents.length} agent${activeAgents.length > 1 ? 's' : ''} active: ${activeAgents.map(a => a.caste).join(', ')}</span>
          </div>
        ` : nothing}
        ${recentMsgs.map(m => html`
          <div class="activity-row">
            <span class="activity-dot" style="background:${kindColors[m.eventKind ?? ''] ?? 'var(--v-fg-dim)'}"></span>
            <span>${m.text.slice(0, 100)}${m.text.length > 100 ? '\u2026' : ''}</span>
            ${m.ts ? html`<span class="activity-time">${this._formatTime(m.ts)}</span>` : nothing}
          </div>
        `)}
      </div>
    `;
  }

  private _formatTime(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ''; }
  }

  private _renderRedirectPanel(c: Colony) {
    const history = c.redirectHistory ?? [];
    const hasRedirects = history.length > 0;
    const override = c.routingOverride;
    if (!hasRedirects && !override) return nothing;

    return html`
      <div class="redirect-panel">
        ${hasRedirects ? html`
          <div class="s-label">Redirect History</div>
          <div class="glass" style="padding:10px">
            <div class="original-goal">
              <span class="label">Original goal</span>
              <div style="margin-top:2px;color:var(--v-fg-muted)">${c.task}</div>
            </div>
            ${history.map(r => html`
              <div class="redirect-entry">
                <div class="redirect-round">Round ${r.round} \u00B7 ${r.trigger} \u00B7 #${r.redirectIndex + 1}</div>
                <div class="redirect-goal">${r.newGoal}</div>
                <div class="redirect-reason">${r.reason}</div>
              </div>
            `)}
          </div>
        ` : nothing}
        ${override ? html`
          <div class="s-label" style="margin-top:10px">Routing Override</div>
          <div class="glass" style="padding:10px;font-size:11px;font-family:var(--f-mono);color:var(--v-fg-muted)">
            <div>Tier: <strong style="color:var(--v-fg)">${override.tier}</strong> (since round ${override.setAtRound})</div>
            <div style="margin-top:4px;color:var(--v-fg-dim);font-style:italic">${override.reason}</div>
          </div>
        ` : nothing}
      </div>`;
  }

  private _renameColony(c: Colony) {
    const newName = prompt('Rename colony:', colonyName(c));
    if (newName && newName !== colonyName(c)) {
      this._fire('rename-colony', { colonyId: c.id, name: newName });
    }
  }

  private _activateService(c: Colony) {
    const serviceType = prompt('Service type (e.g. research, review, docs):', 'research');
    if (!serviceType) return;
    this._fire('activate-service', { colonyId: c.id, serviceType });
  }

  private async _saveAsTemplate(c: Colony) {
    const name = prompt('Template name:', colonyName(c));
    if (!name) return;
    const description = prompt('Description:', c.task || '');
    try {
      await fetch('/api/v1/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description: description || '',
          castes: (c.agents ?? []).map(a => a.caste).filter((v, i, arr) => arr.indexOf(v) === i).map(name => ({ caste: name, tier: 'standard', count: 1 })),
          strategy: c.strategy,
          budget_limit: c.budgetLimit ?? 1.0,
          max_rounds: c.maxRounds,
          source_colony_id: c.id,
        }),
      });
    } catch { /* best-effort */ }
  }

  private async _toggleExport(c: Colony) {
    this._exportOpen = !this._exportOpen;
    if (this._exportOpen) {
      await this._refreshFileLists(c);
    }
  }

  private async _refreshFileLists(c: Colony) {
    try {
      const [colRes, wsRes] = await Promise.all([
        fetch(`/api/v1/colonies/${c.id}/files`),
        fetch(`/api/v1/workspaces/${(c as any).workspaceId ?? 'default'}/files`),
      ]);
      if (colRes.ok) {
        const data = await colRes.json() as { files?: FileEntry[] };
        this._colonyFiles = data.files ?? [];
        this._selectedUploads = new Set(this._colonyFiles.map(f => f.name));
      }
      if (wsRes.ok) {
        const data = await wsRes.json() as { files?: FileEntry[] };
        this._wsFiles = data.files ?? [];
        this._selectedWsFiles = new Set(this._wsFiles.map(f => f.name));
      }
    } catch { /* best-effort */ }
  }

  private _renderExportPanel(c: Colony) {
    const hasUploads = this._colonyFiles.length > 0;
    const hasWsFiles = this._wsFiles.length > 0;
    const hasOutputs = (c.rounds?.length ?? 0) > 0;

    return html`
      <div class="export-panel">
        <div class="s-label">Export Colony Artifacts</div>
        <div style="display:flex;gap:16px;margin-bottom:10px;flex-wrap:wrap">
          <label class="cat-check">
            <input type="checkbox" .checked=${this._exportChat}
              @change=${(e: Event) => { this._exportChat = (e.target as HTMLInputElement).checked; }}>
            Chat transcript
          </label>
          <label class="cat-check">
            <input type="checkbox" .checked=${this._exportOutputs} ?disabled=${!hasOutputs}
              @change=${(e: Event) => { this._exportOutputs = (e.target as HTMLInputElement).checked; }}>
            Agent outputs${hasOutputs ? ` (${c.rounds?.length ?? 0} rounds)` : ''}
          </label>
          <label class="cat-check">
            <input type="checkbox" .checked=${this._exportUploads} ?disabled=${!hasUploads}
              @change=${(e: Event) => { this._exportUploads = (e.target as HTMLInputElement).checked; }}>
            Colony uploads${hasUploads ? ` (${this._colonyFiles.length})` : ''}
          </label>
          <label class="cat-check">
            <input type="checkbox" .checked=${this._exportWsFiles} ?disabled=${!hasWsFiles}
              @change=${(e: Event) => { this._exportWsFiles = (e.target as HTMLInputElement).checked; }}>
            Workspace files${hasWsFiles ? ` (${this._wsFiles.length})` : ''}
          </label>
        </div>

        ${(hasUploads || hasWsFiles) ? html`
          <div class="export-cols">
            ${hasUploads && this._exportUploads ? html`
              <div>
                <div class="export-col-header">Colony Uploads</div>
                ${this._colonyFiles.map(f => html`
                  <label class="file-check">
                    <input type="checkbox" .checked=${this._selectedUploads.has(f.name)}
                      @change=${(e: Event) => this._toggleFileSelection('uploads', f.name, (e.target as HTMLInputElement).checked)}>
                    <span>${f.name}</span>
                    <span class="file-size">${this._formatBytes(f.bytes)}</span>
                  </label>
                `)}
              </div>` : nothing}
            ${hasWsFiles && this._exportWsFiles ? html`
              <div>
                <div class="export-col-header">Workspace Files</div>
                ${this._wsFiles.map(f => html`
                  <label class="file-check">
                    <input type="checkbox" .checked=${this._selectedWsFiles.has(f.name)}
                      @change=${(e: Event) => this._toggleFileSelection('workspace', f.name, (e.target as HTMLInputElement).checked)}>
                    <span>${f.name}</span>
                    <span class="file-size">${this._formatBytes(f.bytes)}</span>
                  </label>
                `)}
              </div>` : nothing}
          </div>` : nothing}

        <div class="export-actions">
          <fc-btn variant="primary" sm @click=${() => this._doExport(c)}
            ?disabled=${!this._exportChat && !this._exportOutputs && !this._exportUploads && !this._exportWsFiles}>
            Download ZIP
          </fc-btn>
        </div>
      </div>`;
  }

  private _toggleFileSelection(group: 'uploads' | 'workspace', name: string, checked: boolean) {
    const set = group === 'uploads' ? new Set(this._selectedUploads) : new Set(this._selectedWsFiles);
    if (checked) { set.add(name); } else { set.delete(name); }
    if (group === 'uploads') { this._selectedUploads = set; } else { this._selectedWsFiles = set; }
  }

  private _doExport(c: Colony) {
    const items: string[] = [];
    if (this._exportChat) items.push('chat');
    if (this._exportOutputs) items.push('outputs');
    if (this._exportUploads) items.push('uploads');
    if (this._exportWsFiles) items.push('workspace_files');
    if (items.length === 0) return;

    const params = new URLSearchParams({ items: items.join(',') });
    if (this._exportUploads && this._selectedUploads.size > 0 && this._selectedUploads.size < this._colonyFiles.length) {
      params.set('uploads', [...this._selectedUploads].join(','));
    }
    if (this._exportWsFiles && this._selectedWsFiles.size > 0 && this._selectedWsFiles.size < this._wsFiles.length) {
      params.set('workspace_files', [...this._selectedWsFiles].join(','));
    }

    const a = document.createElement('a');
    a.href = `/api/v1/colonies/${c.id}/export?${params.toString()}`;
    a.download = `${c.id}-export.zip`;
    a.click();
  }

  private _renderFilesChanged() {
    // Derive file changes from artifacts: code artifacts = files created/modified
    const arts = this._colonyArtifacts.length > 0
      ? this._colonyArtifacts
      : (this._transcript?.artifacts ?? []);
    const codeArtifacts = arts.filter(a => a.artifact_type === 'code');
    if (codeArtifacts.length === 0) return nothing;

    return html`
      <div class="files-changed-section">
        <div class="files-changed-header">
          <span class="s-label" style="margin-bottom:0">Files Changed</span>
          <span class="files-changed-count">${codeArtifacts.length}</span>
        </div>
        <div class="glass" style="padding:0;overflow:hidden">
          <div class="files-changed-list">
            ${codeArtifacts.map(a => html`
              <div class="file-change-row">
                <span class="file-change-name" title=${a.name}>${a.name || a.id}</span>
                <span class="file-change-badge created">created</span>
                ${a.source_round > 0 ? html`<span style="font-size:9px;color:var(--v-fg-dim)">R${a.source_round}</span>` : nothing}
              </div>`)}
          </div>
        </div>
      </div>`;
  }

  private _renderWorkspaceFiles(c: Colony) {
    return html`
      ${this._colonyFiles.length > 0 ? html`
        <div class="ws-files">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <div class="s-label" style="margin-bottom:0">Colony Uploads</div>
          </div>
          <div class="glass" style="padding:0;overflow:hidden">
            <div class="ws-files-list">
              ${this._colonyFiles.map(f => html`
                <div class="ws-file-row">
                  <span class="ws-file-name">${f.name}</span>
                  <span class="ws-file-size">${this._formatBytes(f.bytes)}</span>
                </div>`)}
            </div>
          </div>
        </div>` : nothing}

      <div class="ws-files">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <div class="s-label" style="margin-bottom:0">Workspace Library</div>
          <fc-btn variant="ghost" sm @click=${() => this._uploadWorkspaceFile(c)}>+ Add</fc-btn>
        </div>
        <div class="glass" style="padding:0;overflow:hidden">
          ${this._wsFiles.length > 0
            ? html`<div class="ws-files-list">
                ${this._wsFiles.map(f => html`
                  <div class="ws-file-row">
                    <span class="ws-file-name">${f.name}</span>
                    <div class="ws-file-actions">
                      <span class="ws-file-size">${this._formatBytes(f.bytes)}</span>
                      <fc-btn variant="ghost" sm @click=${() => this._previewWorkspaceFile(c, f.name)}>Preview</fc-btn>
                    </div>
                  </div>`)}
                ${this._previewName ? html`
                  <div class="preview-panel">
                    <div class="preview-header">
                      <span class="preview-name">${this._previewName}</span>
                      <fc-btn variant="ghost" sm @click=${() => this._clearPreview()}>Close</fc-btn>
                    </div>
                    <div class="preview-body">${this._previewLoading ? 'Loading…' : this._previewContent}</div>
                    ${this._previewTruncated ? html`
                      <div class="preview-note">Preview truncated. Export the file for the full contents.</div>
                    ` : nothing}
                  </div>
                ` : nothing}
              </div>`
            : html`<div class="empty-hint">No workspace files yet. Click + Add to upload documents shared across colonies.</div>`}
        </div>
      </div>`;
  }

  private _uploadWorkspaceFile(c: Colony) {
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
      try {
        const wsId = (c as any).workspaceId ?? 'default';
        await fetch(`/api/v1/workspaces/${wsId}/files`, { method: 'POST', body: form });
        await this._refreshFileLists(c);
      } catch { /* best-effort */ }
    };
    input.click();
  }

  private async _previewWorkspaceFile(c: Colony, name: string) {
    this._previewName = name;
    this._previewContent = '';
    this._previewTruncated = false;
    this._previewLoading = true;
    try {
      const wsId = (c as any).workspaceId ?? 'default';
      const res = await fetch(`/api/v1/workspaces/${wsId}/files/${encodeURIComponent(name)}`);
      if (res.ok) {
        const data = await res.json() as { content?: string; truncated?: boolean };
        this._previewContent = data.content ?? '';
        this._previewTruncated = Boolean(data.truncated);
      } else {
        this._previewContent = 'Unable to preview this file.';
      }
    } catch {
      this._previewContent = 'Unable to preview this file.';
    }
    this._previewLoading = false;
  }

  private _clearPreview() {
    this._previewName = '';
    this._previewContent = '';
    this._previewTruncated = false;
    this._previewLoading = false;
  }

  private _formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private _budgetColor(cost: number, limit: number): string {
    if (limit <= 0) return '#6B6B76';
    const remaining = (limit - cost) / limit;
    if (remaining >= 0.70) return '#2DD4A8';
    if (remaining >= 0.30) return '#F5B731';
    if (remaining >= 0.10) return '#E8581A';
    return '#F06464';
  }

  private _navToKnowledge(c: Colony) {
    // Navigate to the knowledge browser filtered by this colony
    this.dispatchEvent(new CustomEvent('navigate-knowledge', {
      detail: { sourceColonyId: c.id },
      bubbles: true, composed: true,
    }));
  }

  private _onDirectiveSend(e: CustomEvent) {
    const d = e.detail as { colony_id: string; message: string; directive_type: string; directive_priority: string };
    this.dispatchEvent(new CustomEvent('send-colony-message', {
      detail: {
        colonyId: d.colony_id,
        message: d.message,
        directive_type: d.directive_type,
        directive_priority: d.directive_priority,
      },
      bubbles: true, composed: true,
    }));
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-colony-detail': FcColonyDetail; }
}
