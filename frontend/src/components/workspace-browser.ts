import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface WsFile { name: string; bytes: number; }

interface TreeFolder {
  name: string;
  path: string;
  children: TreeFolder[];
  files: WsFile[];
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
    .layout { display: flex; gap: 12px; height: calc(100% - 50px); min-height: 400px; }
    .tree-panel {
      width: 260px; flex-shrink: 0; overflow: auto;
      background: var(--v-glass); border: 1px solid var(--v-border); border-radius: 10px;
      backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    }
    .tree-inner { padding: 8px; }
    .tree-folder {
      padding: 0; margin: 0;
    }
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
    .content-body {
      flex: 1; overflow: auto; padding: 12px 14px;
    }
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
    /* Wave 63: Project context editor */
    .context-section {
      margin-top: 16px; padding: 14px;
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
  `];

  @property() workspaceId = '';

  @state() private _files: WsFile[] = [];
  @state() private _loading = true;
  @state() private _selectedFile = '';
  @state() private _fileContent = '';
  @state() private _fileTruncated = false;
  @state() private _fileLoading = false;
  @state() private _expandedFolders = new Set<string>();
  /** Wave 63: Project context editor state */
  @state() private _projectContext = '';
  @state() private _projectContextOriginal = '';
  @state() private _projectContextSaved = false;

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._loadFiles();
      void this._loadProjectContext();
    }
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.workspaceId) {
      void this._loadFiles();
      void this._loadProjectContext();
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
        // Auto-expand all folders
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

  render() {
    if (this._loading) {
      return html`<div class="loading">Loading workspace files...</div>`;
    }

    return html`
      <div class="title-row">
        <h2>Workspace Files</h2>
        ${this._files.length > 0 ? html`<span class="file-count">${this._files.length} files</span>` : nothing}
        <div class="title-actions">
          <fc-btn variant="ghost" sm @click=${() => void this._loadFiles()}>Refresh</fc-btn>
        </div>
      </div>

      ${this._renderProjectContext()}

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
    `;
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
      </div>
    `;
  }

  // Wave 63: Project context editor
  private async _loadProjectContext() {
    try {
      const res = await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/files/${encodeURIComponent('.formicos/project_context.md')}`
      );
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

  private async _saveProjectContext() {
    try {
      await fetch(
        `/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/files/${encodeURIComponent('.formicos/project_context.md')}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: this._projectContext }),
        }
      );
      this._projectContextOriginal = this._projectContext;
      this._projectContextSaved = true;
      setTimeout(() => { this._projectContextSaved = false; }, 2000);
    } catch { /* best-effort */ }
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
