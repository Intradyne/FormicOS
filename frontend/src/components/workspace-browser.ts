import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';
import './addon-panel.js';

interface AddonPanel { target: string; display_type: string; path: string; addon_name: string; refresh_interval_s?: number; }

interface WsFile { name: string; bytes: number; }

interface TreeFolder {
  name: string;
  path: string;
  children: TreeFolder[];
  files: WsFile[];
}

interface AiFsEntry {
  name: string;
  type: 'file' | 'dir';
  size?: number;
  children?: AiFsEntry[];
}

const EXT_LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  py: 'python', rs: 'rust', go: 'go', java: 'java', rb: 'ruby',
  sh: 'bash', bash: 'bash', zsh: 'bash', yaml: 'yaml', yml: 'yaml',
  json: 'json', toml: 'toml', md: 'markdown', html: 'html', css: 'css',
  sql: 'sql', xml: 'xml', c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp',
};

function langClass(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  return EXT_LANG[ext] ?? '';
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildTree(files: WsFile[]): TreeFolder {
  const root: TreeFolder = { name: '', path: '', children: [], files: [] };
  for (const f of files) {
    const parts = f.name.replace(/\\/g, '/').split('/');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts[i];
      let child = node.children.find(c => c.name === seg);
      if (!child) {
        child = { name: seg, path: parts.slice(0, i + 1).join('/'), children: [], files: [] };
        node.children.push(child);
      }
      node = child;
    }
    node.files.push(f);
  }
  return root;
}

function countFsEntries(entries: AiFsEntry[]): { files: number; dirs: number } {
  let files = 0, dirs = 0;
  for (const e of entries) {
    if (e.type === 'file') files++;
    else { dirs++; if (e.children) { const sub = countFsEntries(e.children); files += sub.files; dirs += sub.dirs; } }
  }
  return { files, dirs };
}

@customElement('fc-workspace-browser')
export class FcWorkspaceBrowser extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 960px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .title-actions { margin-left: auto; display: flex; gap: 6px; }
    .file-count {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      background: rgba(232,88,26,0.08); color: var(--v-accent); font-feature-settings: 'tnum';
    }
    .section { margin-bottom: 16px; }
    .section-header {
      font-size: 11px; font-family: var(--f-mono); font-weight: 700; color: var(--v-fg);
      margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .layout { display: flex; gap: 12px; height: calc(100% - 50px); min-height: 400px; }
    .tree-panel {
      width: 260px; flex-shrink: 0; overflow: auto;
      background: var(--v-glass); border: 1px solid var(--v-border); border-radius: 10px;
      backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    }
    .tree-inner { padding: 8px; }
    .tree-folder { padding: 0; margin: 0; }
    .folder-row {
      display: flex; align-items: center; gap: 6px; padding: 4px 6px;
      cursor: pointer; border-radius: 6px; transition: background 0.12s;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      user-select: none;
    }
    .folder-row:hover { background: rgba(255,255,255,0.03); }
    .folder-icon { font-size: 10px; width: 14px; text-align: center; flex-shrink: 0; }
    .folder-name { font-weight: 600; }
    .folder-children { padding-left: 14px; }
    .file-row {
      display: flex; align-items: center; gap: 6px; padding: 4px 6px;
      cursor: pointer; border-radius: 6px; transition: background 0.12s;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .file-row:hover { background: rgba(255,255,255,0.04); color: var(--v-fg); }
    .file-row.selected { background: rgba(232,88,26,0.08); color: var(--v-accent); }
    .file-icon { font-size: 9px; width: 14px; text-align: center; flex-shrink: 0; color: var(--v-fg-dim); }
    .file-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-size { font-size: 9px; color: var(--v-fg-dim); flex-shrink: 0; font-feature-settings: 'tnum'; }
    .file-actions { display: none; gap: 2px; flex-shrink: 0; }
    .file-row:hover .file-actions { display: flex; }
    .file-action {
      font-size: 10px; cursor: pointer; padding: 1px 3px; border-radius: 3px;
      color: var(--v-fg-dim); opacity: 0.6;
    }
    .file-action:hover { opacity: 1; background: rgba(255,255,255,0.06); }
    .content-panel {
      flex: 1; min-width: 0; display: flex; flex-direction: column;
      background: var(--v-glass); border: 1px solid var(--v-border); border-radius: 10px;
      backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
      overflow: hidden;
    }
    .content-header {
      display: flex; align-items: center; gap: 8px; padding: 10px 14px;
      border-bottom: 1px solid var(--v-border); flex-shrink: 0;
    }
    .content-filename { font-size: 11px; font-family: var(--f-mono); font-weight: 600; color: var(--v-fg); flex: 1; }
    .content-meta { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .content-body { flex: 1; overflow: auto; padding: 12px 14px; }
    .content-body pre {
      margin: 0; white-space: pre-wrap; word-break: break-word;
      font-family: var(--f-mono); font-size: 11px; line-height: 1.55; color: var(--v-fg-muted);
    }
    .content-body code { font-family: inherit; }
    .truncated-note {
      padding: 6px 14px; font-size: 9px; font-family: var(--f-mono);
      color: var(--v-warn); border-top: 1px solid var(--v-border);
    }
    .empty-state {
      padding: 48px 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px;
      line-height: 1.6;
    }
    .empty-state .empty-icon { font-size: 28px; margin-bottom: 12px; opacity: 0.4; }
    .empty-content {
      display: flex; align-items: center; justify-content: center; height: 100%;
      color: var(--v-fg-dim); font-size: 11px; font-family: var(--f-mono);
    }
    .loading { padding: 16px; text-align: center; color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); }
    .context-section {
      margin-top: 8px; margin-bottom: 16px; padding: 14px;
      background: var(--v-glass); border: 1px solid var(--v-border); border-radius: 10px;
      backdrop-filter: blur(14px);
    }
    .context-header {
      display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
    }
    .context-header h3 {
      font-family: var(--f-display); font-size: 14px; font-weight: 700; color: var(--v-fg); margin: 0;
    }
    .context-desc {
      font-size: 10px; color: var(--v-fg-muted); margin-bottom: 8px; line-height: 1.5;
    }
    .context-textarea {
      width: 100%; min-height: 150px; padding: 10px 12px; border-radius: 8px;
      border: 1px solid var(--v-border); background: var(--v-recessed); color: var(--v-fg);
      font-size: 11px; font-family: var(--f-mono); line-height: 1.6; outline: none;
      resize: vertical; box-sizing: border-box;
    }
    .context-textarea:focus { border-color: rgba(232,88,26,0.3); }
    .context-actions { display: flex; gap: 6px; margin-top: 8px; align-items: center; }
    .context-saved { font-size: 10px; color: var(--v-success); font-family: var(--f-mono); }
    .op-file-row {
      display: flex; align-items: center; gap: 8px; padding: 6px 10px;
      font-size: 11px; font-family: var(--f-mono); color: var(--v-fg-muted);
      border-bottom: 1px solid rgba(255,255,255,0.03);
    }
    .op-file-row:last-child { border-bottom: none; }
    .op-file-label { flex: 1; }
    .op-file-hint { font-size: 9px; color: var(--v-fg-dim); }
    .journal-entry {
      padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.03);
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted); line-height: 1.5;
    }
    .journal-entry:last-child { border-bottom: none; }
    .journal-ts { color: var(--v-fg-dim); margin-right: 8px; }
    .aifs-row {
      display: flex; align-items: center; gap: 8px; padding: 4px 10px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .aifs-label { flex: 1; }
    .aifs-count { color: var(--v-fg-dim); }
    .aifs-action {
      font-size: 9px; padding: 1px 6px; border-radius: 3px; cursor: pointer;
      background: var(--v-surface-2); color: var(--v-fg-muted); border: 1px solid var(--v-border);
    }
    .aifs-action:hover { background: var(--v-accent); color: var(--v-fg); }
    .ingest-bar {
      display: flex; align-items: center; gap: 8px; padding: 6px 14px;
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .ingest-btn {
      font-size: 10px; padding: 3px 10px; border-radius: 4px; cursor: pointer;
      background: var(--v-surface-2); color: var(--v-fg-muted); border: 1px solid var(--v-border);
    }
    .ingest-btn:hover { background: var(--v-accent); color: var(--v-fg); }
  `];

  @property() workspaceId = '';
  @property({ type: Array }) addonPanels: AddonPanel[] = [];

  @state() private _files: WsFile[] = [];
  @state() private _loading = true;
  @state() private _selectedFile = '';
  @state() private _fileContent = '';
  @state() private _fileTruncated = false;
  @state() private _fileLoading = false;
  @state() private _expandedFolders = new Set<string>();
  // Operator file editors
  @state() private _projectContext = '';
  @state() private _projectContextOriginal = '';
  @state() private _projectContextSaved = false;
  @state() private _projectPlan = '';
  @state() private _projectPlanOriginal = '';
  @state() private _projectPlanSaved = false;
  // Read-only sections
  @state() private _journalEntries: Array<{ts: string; content: string}> = [];
  @state() private _proceduresContent = '';
  // AI Filesystem
  @state() private _aifsRuntime: AiFsEntry[] = [];
  @state() private _aifsArtifacts: AiFsEntry[] = [];
  // Upload & Ingest
  @state() private _ingestStatus = '';
  @state() private _ingestBusy = false;

  // Wave 81: project binding state
  @state() private _projectBound = false;
  @state() private _projectRoot = '';
  @state() private _projectFileTree: WsFile[] = [];

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._loadAll();
    }
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.workspaceId) void this._loadAll();
  }

  private async _loadAll() {
    await Promise.all([
      this._loadFiles(),
      this._loadProjectContext(),
      this._loadProjectPlan(),
      this._loadJournal(),
      this._loadProcedures(),
      this._loadAiFilesystem(),
      this._loadProjectBinding(),
    ]);
  }

  /** Wave 81: fetch project binding status and file listing. */
  private async _loadProjectBinding() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/project-binding`);
      if (res.ok) {
        const data = await res.json() as { bound?: boolean; project_root?: string };
        this._projectBound = !!data.bound;
        this._projectRoot = data.project_root ?? '';
      } else {
        this._projectBound = false;
        this._projectRoot = '';
      }
    } catch {
      this._projectBound = false;
      this._projectRoot = '';
    }
    if (this._projectBound) {
      try {
        const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/project-files`);
        if (res.ok) {
          const data = await res.json() as { files?: WsFile[] };
          this._projectFileTree = data.files ?? [];
        }
      } catch { /* degrade gracefully */ }
    }
  }

  private async _loadFiles() {
    this._loading = true;
    this._files = [];
    this._selectedFile = '';
    this._fileContent = '';
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/files`);
      if (res.ok) {
        const data = await res.json() as { files?: WsFile[] };
        this._files = data.files ?? [];
        const tree = buildTree(this._files);
        const expanded = new Set<string>();
        const walk = (folder: TreeFolder) => {
          if (folder.path) expanded.add(folder.path);
          folder.children.forEach(walk);
        };
        walk(tree);
        this._expandedFolders = expanded;
      }
    } catch { /* best-effort */ }
    this._loading = false;
  }

  private async _loadProjectContext() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/project-context`);
      if (res.ok) {
        const data = await res.json() as { content?: string };
        this._projectContext = data.content ?? '';
        this._projectContextOriginal = this._projectContext;
      } else {
        this._projectContext = '';
        this._projectContextOriginal = '';
      }
    } catch {
      this._projectContext = '';
      this._projectContextOriginal = '';
    }
  }

  private async _loadProjectPlan() {
    try {
      const res = await fetch(`/api/v1/project-plan?workspace_id=${encodeURIComponent(this.workspaceId)}`);
      if (res.ok) {
        const data = await res.json() as { raw_content?: string; exists?: boolean };
        this._projectPlan = data.raw_content ?? '';
        this._projectPlanOriginal = this._projectPlan;
      } else {
        this._projectPlan = '';
        this._projectPlanOriginal = '';
      }
    } catch {
      this._projectPlan = '';
      this._projectPlanOriginal = '';
    }
  }

  private async _loadJournal() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/queen-journal`);
      if (res.ok) {
        const data = await res.json() as { entries?: Array<{ts: string; content: string}> };
        this._journalEntries = (data.entries ?? []).slice(-10);
      }
    } catch { /* silent */ }
  }

  private async _loadProcedures() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/operating-procedures`);
      if (res.ok) {
        const data = await res.json() as { content?: string };
        this._proceduresContent = data.content ?? '';
      }
    } catch { /* silent */ }
  }

  private async _loadAiFilesystem() {
    try {
      const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/ai-filesystem`);
      if (res.ok) {
        const data = await res.json() as { runtime?: AiFsEntry[]; artifacts?: AiFsEntry[] };
        this._aifsRuntime = data.runtime ?? [];
        this._aifsArtifacts = data.artifacts ?? [];
      }
    } catch { /* silent */ }
  }

  private async _selectFile(name: string) {
    if (this._selectedFile === name) return;
    this._selectedFile = name;
    this._fileContent = '';
    this._fileTruncated = false;
    this._fileLoading = true;
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/files/${encodeURIComponent(name)}`
      );
      if (res.ok) {
        const data = await res.json() as { content?: string; truncated?: boolean };
        this._fileContent = data.content ?? '';
        this._fileTruncated = Boolean(data.truncated);
      } else {
        this._fileContent = 'Unable to load file content.';
      }
    } catch {
      this._fileContent = 'Unable to load file content.';
    }
    this._fileLoading = false;
  }

  private _toggleFolder(path: string) {
    const next = new Set(this._expandedFolders);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    this._expandedFolders = next;
  }

  private _ingestUpload() {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.txt,.md,.py,.json,.yaml,.yml,.csv';
    input.onchange = async () => {
      const files = input.files;
      if (!files || files.length === 0) return;
      this._ingestBusy = true;
      this._ingestStatus = '';
      const form = new FormData();
      for (const f of files) form.append(f.name, f);
      try {
        const res = await fetch(
          `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/ingest`,
          { method: 'POST', body: form },
        );
        if (res.ok) {
          const data = await res.json() as { ingested?: Array<{ name: string; chunks: number }> };
          const parts = (data.ingested ?? []).map(i => `${i.name} (${i.chunks})`);
          this._ingestStatus = `Ingested: ${parts.join(', ')}`;
          await this._loadFiles();
        } else {
          this._ingestStatus = 'Ingest failed.';
        }
      } catch {
        this._ingestStatus = 'Ingest failed.';
      }
      this._ingestBusy = false;
    };
    input.click();
  }

  private async _saveProjectContext() {
    try {
      await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/project-context`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: this._projectContext }),
      });
      this._projectContextOriginal = this._projectContext;
      this._projectContextSaved = true;
      setTimeout(() => { this._projectContextSaved = false; }, 2000);
    } catch { /* best-effort */ }
  }

  private async _saveProjectPlan() {
    try {
      await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/project-plan`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: this._projectPlan }),
      });
      this._projectPlanOriginal = this._projectPlan;
      this._projectPlanSaved = true;
      setTimeout(() => { this._projectPlanSaved = false; }, 2000);
    } catch { /* best-effort */ }
  }

  render() {
    if (this._loading) {
      return html`<div class="loading">Loading workspace...</div>`;
    }

    return html`
      <div class="title-row">
        <h2>Workspace</h2>
        <div class="title-actions">
          <fc-btn variant="ghost" sm @click=${() => void this._loadAll()}>Refresh</fc-btn>
        </div>
      </div>

      ${this.addonPanels.filter(p => p.target === 'workspace').map(p => html`
        <fc-addon-panel
          src="/addons/${p.addon_name}${p.path}"
          display-type="${p.display_type}"
          label="${p.addon_name}"
          workspace-id="${this.workspaceId}"
          .refreshInterval=${p.refresh_interval_s ?? 60}>
        </fc-addon-panel>
      `)}

      <!-- Section 0: Project Files (when a project is bound) -->
      ${this._renderProjectFiles()}

      <!-- Section 1: Operator Files -->
      <div class="section">
        <div class="section-header">Operator Files</div>
        ${this._renderProjectContext()}
        ${this._renderProjectPlan()}
        ${this._renderProceduresPreview()}
        ${this._renderJournalPreview()}
      </div>

      <!-- Section 2: Working Memory (AI Filesystem) -->
      <div class="section">
        <div class="section-header">Working Memory</div>
        ${this._renderAiFilesystem()}
      </div>

      <!-- Section 3: Workspace Library -->
      <div class="section">
        <div class="section-header">Workspace Library ${this._files.length > 0 ? html`<span class="file-count">${this._files.length} files</span>` : nothing}</div>
        <div class="ingest-bar">
          <button class="ingest-btn" ?disabled=${this._ingestBusy} @click=${() => this._ingestUpload()}>
            ${this._ingestBusy ? 'Ingesting...' : 'Upload & Ingest'}
          </button>
          ${this._ingestStatus ? html`<span>${this._ingestStatus}</span>` : nothing}
        </div>
        ${this._files.length === 0
          ? html`<div class="empty-state">
              <div class="empty-icon">\u2601</div>
              No workspace files yet. Colonies create files as they work.
            </div>`
          : html`<div class="layout">
              <div class="tree-panel">
                <div class="tree-inner">
                  ${this._renderTree(buildTree(this._files))}
                </div>
              </div>
              <div class="content-panel">
                ${this._selectedFile
                  ? this._renderFileContent()
                  : html`<div class="empty-content">Select a file to view its contents</div>`}
              </div>
            </div>`}
      </div>
    `;
  }

  private _renderProjectContext(): unknown {
    const dirty = this._projectContext !== this._projectContextOriginal;
    return html`
      <div class="context-section">
        <div class="context-header">
          <h3>Project Context</h3>
          <fc-pill color="var(--v-accent)" sm>.formicos/project_context.md</fc-pill>
        </div>
        <div class="context-desc">
          Operator-authored context injected into every colony's system prompt.
          Use this to share project knowledge, conventions, and architecture with agents.
        </div>
        <textarea class="context-textarea"
          placeholder="# Project Context\n\nDescribe your project here..."
          .value=${this._projectContext}
          @input=${(e: Event) => { this._projectContext = (e.target as HTMLTextAreaElement).value; this._projectContextSaved = false; }}
        ></textarea>
        <div class="context-actions">
          <fc-btn variant="primary" sm ?disabled=${!dirty} @click=${() => void this._saveProjectContext()}>Save</fc-btn>
          ${dirty ? html`<fc-btn variant="ghost" sm @click=${() => { this._projectContext = this._projectContextOriginal; }}>Revert</fc-btn>` : nothing}
          ${this._projectContextSaved ? html`<span class="context-saved">Saved</span>` : nothing}
        </div>
      </div>`;
  }

  private _renderProjectPlan(): unknown {
    const dirty = this._projectPlan !== this._projectPlanOriginal;
    return html`
      <div class="context-section">
        <div class="context-header">
          <h3>Project Plan</h3>
          <fc-pill color="var(--v-accent)" sm>.formicos/project_plan.md</fc-pill>
        </div>
        <div class="context-desc">
          Milestones and deliverables visible to the Queen during planning.
        </div>
        <textarea class="context-textarea"
          placeholder="# Project Plan\n\n## Milestone 1\n- [ ] Task..."
          .value=${this._projectPlan}
          @input=${(e: Event) => { this._projectPlan = (e.target as HTMLTextAreaElement).value; this._projectPlanSaved = false; }}
        ></textarea>
        <div class="context-actions">
          <fc-btn variant="primary" sm ?disabled=${!dirty} @click=${() => void this._saveProjectPlan()}>Save</fc-btn>
          ${dirty ? html`<fc-btn variant="ghost" sm @click=${() => { this._projectPlan = this._projectPlanOriginal; }}>Revert</fc-btn>` : nothing}
          ${this._projectPlanSaved ? html`<span class="context-saved">Saved</span>` : nothing}
        </div>
      </div>`;
  }

  private _renderProceduresPreview(): unknown {
    if (!this._proceduresContent) return nothing;
    return html`
      <div class="context-section">
        <div class="context-header">
          <h3>Operating Procedures</h3>
          <fc-pill color="var(--v-fg-dim)" sm>Read-only</fc-pill>
        </div>
        <div class="context-desc">Edit in the Operations tab.</div>
        <pre style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-muted);max-height:120px;overflow:auto;margin:0;white-space:pre-wrap">${this._proceduresContent.slice(0, 500)}${this._proceduresContent.length > 500 ? '...' : ''}</pre>
      </div>`;
  }

  /** Wave 81: show bound project files when a project root is active. */
  private _renderProjectFiles(): unknown {
    if (!this._projectBound) return nothing;
    return html`
      <div class="section">
        <div class="section-header">
          Project Files
          <fc-pill color="var(--v-success)" sm>${this._projectRoot || 'bound'}</fc-pill>
          <span class="file-count">${this._projectFileTree.length} files</span>
        </div>
        ${this._projectFileTree.length === 0
          ? html`<div class="empty-state">
              <div class="empty-icon">\u{1F4C2}</div>
              Project is bound but no files listed yet. The backend may not expose project-file routes yet (Track A).
            </div>`
          : html`<div class="layout">
              <div class="tree-panel">
                <div class="tree-inner">
                  ${this._renderTree(buildTree(this._projectFileTree))}
                </div>
              </div>
              <div class="content-panel">
                ${this._selectedFile
                  ? this._renderFileContent()
                  : html`<div class="empty-content">Select a file to view</div>`}
              </div>
            </div>`}
      </div>
    `;
  }

  private _renderJournalPreview(): unknown {
    if (this._journalEntries.length === 0) return nothing;
    return html`
      <div class="context-section">
        <div class="context-header">
          <h3>Queen Journal</h3>
          <fc-pill color="var(--v-fg-dim)" sm>Last ${this._journalEntries.length} entries</fc-pill>
        </div>
        ${this._journalEntries.map(e => html`
          <div class="journal-entry">
            <span class="journal-ts">${e.ts?.slice(0, 16) ?? ''}</span>
            ${e.content}
          </div>
        `)}
      </div>`;
  }

  private _renderAiFilesystem(): unknown {
    const rtCounts = countFsEntries(this._aifsRuntime);
    const artCounts = countFsEntries(this._aifsArtifacts);
    const hasContent = rtCounts.files > 0 || rtCounts.dirs > 0 || artCounts.files > 0 || artCounts.dirs > 0;
    if (!hasContent) {
      return html`<div class="context-section" style="padding:10px 14px">
        <div style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">No working memory files yet.</div>
      </div>`;
    }
    return html`
      <div class="context-section" style="padding:10px 14px">
        ${this._aifsRuntime.length > 0 ? html`
          ${this._aifsRuntime.map(e => this._renderAiFsEntry(e, 'runtime/'))}
        ` : nothing}
        ${this._aifsArtifacts.length > 0 ? html`
          ${this._aifsArtifacts.map(e => this._renderAiFsEntry(e, 'artifacts/'))}
        ` : nothing}
      </div>`;
  }

  private _renderAiFsEntry(entry: AiFsEntry, prefix: string): unknown {
    if (entry.type === 'dir') {
      const sub = countFsEntries(entry.children ?? []);
      return html`
        <div class="aifs-row">
          <span class="aifs-label">${prefix}${entry.name}/</span>
          <span class="aifs-count">${sub.files} file${sub.files !== 1 ? 's' : ''}${sub.dirs > 0 ? `, ${sub.dirs} dir${sub.dirs !== 1 ? 's' : ''}` : ''}</span>
        </div>
        ${(entry.children ?? []).map(c => this._renderAiFsEntry(c, `${prefix}${entry.name}/`))}
      `;
    }
    const isRuntime = prefix.startsWith('runtime/');
    const scope = isRuntime ? 'runtime' : 'artifacts';
    const relPath = prefix.replace(/^(runtime|artifacts)\//, '') + entry.name;
    return html`
      <div class="aifs-row" style="cursor:pointer" @click=${() => void this._previewAiFile(scope, relPath)}>
        <span class="aifs-label" style="text-decoration:underline dotted;text-underline-offset:2px">${prefix}${entry.name}</span>
        <span class="aifs-count">${entry.size != null ? formatBytes(entry.size) : ''}</span>
        ${isRuntime ? html`<span class="aifs-action" @click=${(e: Event) => { e.stopPropagation(); void this._promoteFile(relPath); }}>Promote</span>` : nothing}
      </div>
    `;
  }

  private async _previewAiFile(scope: string, relPath: string) {
    this._selectedFile = `[${scope}] ${relPath}`;
    this._fileContent = '';
    this._fileTruncated = false;
    this._fileLoading = true;
    try {
      const url = `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/ai-filesystem/file?scope=${encodeURIComponent(scope)}&path=${encodeURIComponent(relPath)}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json() as { content?: string; error?: string };
        this._fileContent = data.content || data.error || '';
      } else {
        this._fileContent = 'Unable to load file.';
      }
    } catch {
      this._fileContent = 'Unable to load file.';
    }
    this._fileLoading = false;
  }

  private async _promoteFile(relPath: string) {
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/ai-filesystem/promote`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: relPath }) },
      );
      const data = await res.json() as { ok?: boolean; path?: string; error?: string };
      if (data.ok) {
        await this._loadAiFilesystem();
      } else {
        this._fileContent = data.error || 'Promote failed';
      }
    } catch {
      this._fileContent = 'Promote failed';
    }
  }

  private _renderTree(folder: TreeFolder): unknown {
    return html`
      <div class="tree-folder">
        ${folder.children.map(child => this._renderFolder(child))}
        ${folder.files.map(f => this._renderFileRow(f))}
      </div>
    `;
  }

  private _renderFolder(folder: TreeFolder): unknown {
    const expanded = this._expandedFolders.has(folder.path);
    return html`
      <div class="folder-row" @click=${() => this._toggleFolder(folder.path)}>
        <span class="folder-icon">${expanded ? '\u25BE' : '\u25B8'}</span>
        <span class="folder-name">${folder.name}</span>
      </div>
      ${expanded ? html`
        <div class="folder-children">
          ${folder.children.map(child => this._renderFolder(child))}
          ${folder.files.map(f => this._renderFileRow(f))}
        </div>
      ` : nothing}
    `;
  }

  private _renderFileRow(f: WsFile): unknown {
    const fileName = f.name.replace(/\\/g, '/').split('/').pop() ?? f.name;
    const selected = this._selectedFile === f.name;
    return html`
      <div class="file-row ${selected ? 'selected' : ''}" @click=${() => void this._selectFile(f.name)}>
        <span class="file-icon">\u25CB</span>
        <span class="file-label" title=${f.name}>${fileName}</span>
        <span class="file-size">${formatBytes(f.bytes)}</span>
        <span class="file-actions" @click=${(e: Event) => e.stopPropagation()}>
          <span class="file-action" title="Use as target file"
            @click=${() => this._emitFileAction('use-as-target-file', f.name)}>\u25ce</span>
          <span class="file-action" title="Open in Colony Creator"
            @click=${() => this._emitFileAction('open-in-creator', f.name)}>\u25b6</span>
          <span class="file-action" title="Ask Queen"
            @click=${() => this._emitFileAction('ask-queen', f.name)}>\u2606</span>
        </span>
      </div>
    `;
  }

  private _emitFileAction(action: string, path: string) {
    this.dispatchEvent(new CustomEvent(action, {
      detail: { path },
      bubbles: true, composed: true,
    }));
  }

  private _renderFileContent(): unknown {
    const lang = langClass(this._selectedFile);
    return html`
      <div class="content-header">
        <span class="content-filename">${this._selectedFile}</span>
        <span class="content-meta">${formatBytes(this._files.find(f => f.name === this._selectedFile)?.bytes ?? 0)}</span>
      </div>
      <div class="content-body">
        ${this._fileLoading
          ? html`<div class="loading">Loading...</div>`
          : html`<pre><code class="${lang ? `language-${lang}` : ''}">${this._fileContent}</code></pre>`}
      </div>
      ${this._fileTruncated ? html`<div class="truncated-note">File content was truncated. Download the full file for complete contents.</div>` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-workspace-browser': FcWorkspaceBrowser; }
}
