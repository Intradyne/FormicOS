import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { store, findNode, allColonies, breadcrumb } from '../state/store.js';
import { colonyName, formatCost } from '../helpers.js';
import type { TreeNode, MergeEdge, QueenThread } from '../types.js';
import './atoms.js';
import './tree-nav.js';
import './queen-chat.js';
import './thread-view.js';
import './breadcrumb-nav.js';
import './queen-overview.js';
import './colony-detail.js';
import './approval-queue.js';
import './round-history.js';
import './workspace-config.js';
import './playbook-view.js';
import './model-registry.js';
import './settings-view.js';
import './knowledge-view.js';
import './knowledge-browser.js';
import './colony-creator.js';
import './colony-chat.js';
import './workspace-browser.js';
import './addons-view.js';
import './operations-view.js';

type ViewId = 'queen' | 'tree' | 'knowledge' | 'workspace' | 'operations' | 'addons' | 'playbook' | 'models' | 'settings';

const NAV_PRIMARY = [
  { id: 'queen' as const, label: 'Queen', icon: '\u265B' },
  { id: 'knowledge' as const, label: 'Knowledge', icon: '\u25C8' },
  { id: 'workspace' as const, label: 'Workspace', icon: '\u2302' },
  { id: 'operations' as const, label: 'Operations', icon: '\u2318' },
];

const NAV_SECONDARY = [
  { id: 'addons' as const, label: 'Addons', icon: '\u2B9E' },
  { id: 'playbook' as const, label: 'Playbook', icon: '\u29C9' },
  { id: 'models' as const, label: 'Models', icon: '\u2B22' },
  { id: 'settings' as const, label: 'Settings', icon: '\u2699' },
];

@customElement('formicos-app')
export class FormicOSApp extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: flex; flex-direction: column; height: 100vh; background: var(--v-void); color: var(--v-fg); font-family: var(--f-body); }
    .atmo { position: fixed; inset: 0; pointer-events: none; z-index: 0; }
    .atmo .orb1 { position: absolute; top: -30%; left: 25%; width: 800px; height: 800px; border-radius: 50%; filter: blur(200px); opacity: 0.02; background: radial-gradient(circle, var(--v-accent), transparent 70%); }
    .atmo .orb2 { position: absolute; bottom: -35%; right: 15%; width: 600px; height: 600px; border-radius: 50%; filter: blur(170px); opacity: 0.012; background: radial-gradient(circle, var(--v-secondary), transparent 70%); }
    .grid-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 1; opacity: 0.012; background-image: linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px); background-size: 64px 64px; }
    .topbar {
      min-height: 52px; border-bottom: 1px solid var(--v-border); display: grid;
      grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
      align-items: center; padding: 0 14px; gap: 16px; flex-shrink: 0; z-index: 10;
      background: rgba(6,6,12,0.85); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    }
    .topbar-left { display: flex; align-items: center; gap: 14px; min-width: 0; }
    .topbar-center { display: flex; justify-content: flex-start; }
    .topbar-right-wrap { display: flex; align-items: center; justify-content: flex-end; gap: 10px; min-width: 0; }
    .logo { display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .logo-text { font-family: var(--f-display); font-weight: 800; font-size: 15px; color: var(--v-fg); letter-spacing: -0.04em; }
    .logo-text .accent { color: var(--v-accent); }
    .logo-ver { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.05em; }
    .topbar-right { display: flex; align-items: center; gap: 14px; font-size: 12px; font-family: var(--f-mono); font-feature-settings: 'tnum'; }
    .top-nav {
      display: flex; align-items: center; gap: 6px;
    }
    .nav-group {
      display: inline-grid; gap: 4px; padding: 4px;
      border: 1px solid var(--v-border); border-radius: 11px;
      background: rgba(13,14,22,0.78); box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
    }
    .nav-group.primary { grid-template-columns: repeat(4, minmax(66px, auto)); }
    .nav-group.secondary { grid-template-columns: repeat(4, minmax(52px, auto)); }
    .top-nav-tab {
      min-height: 34px; min-width: 0; display: flex; align-items: center; justify-content: center;
      gap: 6px; border-radius: 8px; cursor: pointer; font-size: 12px; color: var(--v-fg-dim);
      transition: all 0.15s; padding: 4px 10px; text-align: center;
    }
    .top-nav-tab.active { background: rgba(232,88,26,0.08); color: var(--v-accent); }
    .top-nav-tab.active .tab-icon { filter: drop-shadow(0 0 3px rgba(232,88,26,0.25)); }
    .top-nav-label { font-size: 11.5px; font-weight: 500; line-height: 1.05; }
    .approval-badge { padding: 2px 8px; border-radius: 999px; cursor: pointer; background: var(--v-accent-muted); font-size: 11px; font-family: var(--f-mono); color: var(--v-accent); display: flex; align-items: center; gap: 4px; border: 1px solid rgba(232,88,26,0.09); box-shadow: 0 0 14px var(--v-accent-glow); }
    .approval-dot { width: 4px; height: 4px; border-radius: 50%; background: var(--v-accent); animation: pulse 1.5s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
    .body { flex: 1; display: flex; overflow: hidden; z-index: 3; }
    .sidebar { border-right: 1px solid var(--v-border); display: flex; flex-direction: column; flex-shrink: 0; background: rgba(13,14,22,0.53); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); transition: width 0.22s cubic-bezier(0.22,1,0.36,1); overflow: hidden; }
    .sidebar.open { width: 260px; }
    .sidebar.closed { width: 46px; }
    .nav-header { padding: 5px 10px; border-bottom: 1px solid var(--v-border); font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.14em; text-transform: uppercase; font-weight: 600; }
    .tree-panel { flex: 1; overflow: auto; }
    .sidebar-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; transition: opacity 0.18s; }
    .sidebar.closed .sidebar-content { opacity: 0; pointer-events: none; }
    .mini-colonies { flex: 1; display: flex; flex-direction: column; align-items: center; padding-top: 10px; gap: 5px; }
    .mini-colony { width: 26px; height: 26px; border-radius: 6px; display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1px solid var(--v-border); font-size: 10px; color: var(--v-fg-muted); }
    .mini-colony.active { background: rgba(232,88,26,0.05); border-color: rgba(232,88,26,0.15); }
    .create-ws-btn { display: block; width: 100%; padding: 6px 12px; margin-top: 4px; background: transparent; border: 1px dashed var(--v-border); border-radius: 6px; color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); cursor: pointer; text-align: left; }
    .create-ws-btn:hover { border-color: var(--v-accent); color: var(--v-accent); }
    .content { flex: 1; padding: 16px; overflow: hidden; display: flex; flex-direction: column; }
    .content-inner { flex: 1; min-height: 0; overflow: hidden; }
    .startup-shell {
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .startup-card {
      width: min(760px, 100%);
      display: grid;
      gap: 18px;
      padding: 24px;
      border-radius: 18px;
      border: 1px solid var(--v-border);
      background: linear-gradient(180deg, rgba(18,19,29,0.92), rgba(10,11,18,0.92));
      box-shadow: 0 24px 60px rgba(0,0,0,0.35);
    }
    .startup-kicker {
      font-family: var(--f-mono);
      font-size: 10px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--v-fg-dim);
    }
    .startup-title {
      margin: 0;
      font-family: var(--f-display);
      font-size: clamp(28px, 4vw, 42px);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }
    .startup-copy {
      margin: 0;
      max-width: 60ch;
      color: var(--v-fg-dim);
      line-height: 1.6;
      font-size: 14px;
    }
    .startup-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .startup-panel {
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--v-border);
      background: rgba(255,255,255,0.02);
      display: grid;
      gap: 10px;
    }
    .startup-panel h3 {
      margin: 0;
      font-size: 12px;
      color: var(--v-fg);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .startup-steps,
    .startup-checks {
      display: grid;
      gap: 8px;
    }
    .startup-step {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      font-size: 13px;
      color: var(--v-fg-dim);
      line-height: 1.45;
    }
    .startup-step code {
      font-family: var(--f-mono);
      font-size: 12px;
      color: var(--v-fg);
      background: rgba(255,255,255,0.03);
      padding: 1px 5px;
      border-radius: 5px;
    }
    .startup-dot {
      width: 8px;
      height: 8px;
      margin-top: 5px;
      border-radius: 50%;
      flex-shrink: 0;
      background: var(--v-fg-dim);
      box-shadow: 0 0 0 1px rgba(255,255,255,0.04);
    }
    .startup-dot.ready { background: var(--v-success); }
    .startup-dot.pending { background: var(--v-warn); }
    .startup-dot.waiting { background: var(--v-danger); }
    .startup-footnote {
      font-size: 12px;
      color: var(--v-fg-muted);
      line-height: 1.5;
    }
    .view-shell { display: flex; gap: 16px; height: 100%; min-width: 0; min-height: 0; }
    .view-main { flex: 1; min-width: 0; height: 100%; overflow: hidden; }
    .queen-rail {
      flex-shrink: 0;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      display: flex;
      transition: width 0.22s cubic-bezier(0.22,1,0.36,1);
    }
    .queen-rail.open { width: 320px; }
    .queen-rail.closed { width: 46px; }
    .queen-rail > fc-queen-chat {
      flex: 1;
      min-height: 0;
    }
    .chat-fab {
      width: 46px; height: 100%; display: flex; flex-direction: column;
      align-items: center; padding-top: 12px; gap: 8px; cursor: pointer;
    }
    .chat-fab-icon {
      width: 32px; height: 32px; border-radius: 8px; display: flex;
      align-items: center; justify-content: center; font-size: 16px;
      background: rgba(232,88,26,0.08); border: 1px solid rgba(232,88,26,0.15);
      color: var(--v-accent); transition: background 0.15s;
    }
    .chat-fab-icon:hover { background: rgba(232,88,26,0.15); }
    .chat-fab-label {
      writing-mode: vertical-rl; text-orientation: mixed;
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.1em; text-transform: uppercase;
    }
    .creator-overlay { position: fixed; inset: 0; z-index: 100; display: flex; align-items: center; justify-content: center; background: rgba(4,4,8,0.7); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); }
    .creator-panel { width: 480px; max-height: 80vh; overflow: auto; padding: 20px; border-radius: 12px; background: var(--v-surface); border: 1px solid var(--v-border); box-shadow: 0 20px 60px rgba(0,0,0,0.5); }
    .cost-btn {
      cursor: pointer; padding: 4px 8px; border-radius: 6px;
      transition: background 0.15s; color: var(--v-accent);
    }
    .cost-btn:hover { background: rgba(232,88,26,0.1); }
    .budget-backdrop { position: fixed; inset: 0; z-index: 99; }
    .budget-popover {
      position: absolute; top: 100%; right: 0; margin-top: 6px;
      background: var(--v-recessed); border: 1px solid var(--v-border);
      border-radius: 10px; padding: 16px; min-width: 260px; z-index: 100;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }
    .budget-row {
      display: flex; justify-content: space-between; align-items: center;
      padding: 4px 0; font-family: var(--f-mono);
    }
    .budget-label { font-size: 10px; color: var(--v-fg-dim); }
    .budget-value { font-size: 12px; color: var(--v-accent); }
    .budget-value.neutral { color: var(--v-fg); }
    .popover-link {
      display: block; margin-top: 10px; padding-top: 8px;
      border-top: 1px solid var(--v-border); font-size: 10px;
      font-family: var(--f-mono); color: var(--v-fg-dim); cursor: pointer;
      transition: color 0.15s;
    }
    .popover-link:hover { color: var(--v-accent); }
    .sidebar-toggle { padding: 4px 8px; cursor: pointer; text-align: center; font-size: 10px; color: var(--v-fg-dim); border-bottom: 1px solid var(--v-border); user-select: none; transition: color 0.15s; }
    .sidebar-toggle:hover { color: var(--v-fg-muted); }
    @media (max-width: 1380px) {
      .topbar {
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: auto auto auto;
        justify-items: stretch;
        padding-top: 8px;
        padding-bottom: 8px;
      }
      .topbar-center { order: 2; }
      .topbar-right-wrap { order: 3; }
      .top-nav { width: 100%; flex-wrap: wrap; }
      .nav-group { flex: 1; }
      .nav-group.primary, .nav-group.secondary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      .view-shell { flex-direction: column; }
      .queen-rail.open { width: 100%; height: 280px; }
      .queen-rail.closed { width: 100%; height: 46px; }
      .startup-grid { grid-template-columns: 1fr; }
    }
  `];

  @state() private view: ViewId = 'queen';
  @state() private treeSel: string | null = null;
  @state() private sideOpen = true;
  @state() private chatOpen = false;
  @state() private activeQT = '';
  @state() private tree: TreeNode[] = [];
  @state() private merges: MergeEdge[] = [];
  @state() private queenThreads: QueenThread[] = [];
  @state() private showCreator = false;
  @state() private creatorTemplateId = '';
  @state() private knowledgeSourceColony = '';
  @state() private _showBudgetPopover = false;
  @state() private _autonomyData: { grade: string; level: string; budget_spent: number; budget_total: number; daily_maintenance_budget?: number } | null = null;
  @state() private _showCreateWorkspace = false;
  @state() private _newWorkspaceName = '';
  @state() private _creatingWorkspace = false;

  private unsub?: () => void;
  private _subscribed = false;
  private _knownColonyIds = new Set<string>();

  connectedCallback() {
    super.connectedCallback();
    this.unsub = store.subscribe(() => this.syncFromStore());
    store.connect();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.unsub?.();
    store.disconnect();
  }

  private syncFromStore() {
    const s = store.state;
    this.tree = s.tree;
    this.merges = s.merges;
    this.queenThreads = s.queenThreads;
    if (!this.activeQT && s.queenThreads.length > 0) this.activeQT = s.queenThreads[0].id;

    // FIX BUG 2: Reset subscription flag on disconnect so we re-subscribe on reconnect
    if (s.connection !== 'connected') {
      this._subscribed = false;
    }

    // Auto-subscribe to all workspaces once connected and tree is available
    if (s.connection === 'connected' && this.tree.length > 0 && !this._subscribed) {
      this._subscribed = true;
      for (const ws of this.tree) {
        store.subscribeWorkspace(ws.id);
      }
    }

    // Auto-navigate to newly spawned colonies
    const currentIds = new Set(allColonies(this.tree).map(c => c.id));
    if (this._knownColonyIds.size > 0) {
      for (const id of currentIds) {
        if (!this._knownColonyIds.has(id)) {
          this.navTree(id);
          break;
        }
      }
    }
    this._knownColonyIds = currentIds;
  }

  private get activeWorkspaceId(): string {
    if (this.selNode) {
      const crumbs = breadcrumb(this.tree, this.selNode.id);
      const ws = crumbs?.find(n => n.type === 'workspace');
      if (ws) return ws.id;
    }
    return this.tree[0]?.id ?? '';
  }

  private get selNode(): TreeNode | null { return this.treeSel ? findNode(this.tree, this.treeSel) : null; }
  private get crumbs(): TreeNode[] | null { return this.treeSel ? breadcrumb(this.tree, this.treeSel) : null; }
  private get showFull(): boolean { return this.view === 'tree' || this.view === 'queen' || this.sideOpen; }

  private navTree(id: string) { this.treeSel = id; this.view = 'tree'; }
  private navTab(v: ViewId) {
    this.view = v;
    if (v !== 'tree') this.treeSel = null;
    if (v === 'knowledge') this.knowledgeSourceColony = '';
  }

  private get parentWs(): TreeNode | null {
    const sel = this.selNode;
    if (sel?.type !== 'thread') return null;
    return this.tree.find(ws => (ws.children ?? []).some(th => th.id === sel.id)) ?? null;
  }

  render() {
    const s = store.state;
    const colonies = allColonies(this.tree);
    const running = colonies.filter(c => c.status === 'running');
    const totalCost = colonies.reduce((a, c) => a + ((c as any).cost ?? 0), 0);

    return html`
      <div class="atmo"><div class="orb1"></div><div class="orb2"></div></div>
      <div class="grid-overlay"></div>

      <div class="topbar">
        <div class="topbar-left">
          <div class="logo" @click=${() => this.navTab('queen')}>
            <span class="logo-text">formic<span class="accent">OS</span></span>
            <span class="logo-ver">v3</span>
          </div>
          ${this.view === 'tree' && this.crumbs ? html`
            <fc-breadcrumb-nav .crumbs=${this.crumbs} @navigate=${(e: CustomEvent) => this.navTree(e.detail)}></fc-breadcrumb-nav>
          ` : nothing}
        </div>
        <div class="topbar-center">
          <div class="top-nav">
            <div class="nav-group primary">
              ${NAV_PRIMARY.map(n => {
                const active = this.view === n.id || (this.view === 'tree' && n.id === 'queen');
                return html`<div class="top-nav-tab ${active ? 'active' : ''}" @click=${() => this.navTab(n.id as ViewId)} title=${n.label}>
                  <span class="tab-icon" style="font-size:12px">${n.icon}</span>
                  <span class="top-nav-label">${n.label}</span>
                </div>`;
              })}
            </div>
            <div class="nav-group secondary">
              ${NAV_SECONDARY.map(n => {
                const active = this.view === n.id;
                return html`<div class="top-nav-tab ${active ? 'active' : ''}" @click=${() => this.navTab(n.id as ViewId)} title=${n.label}>
                  <span class="tab-icon" style="font-size:12px">${n.icon}</span>
                  <span class="top-nav-label">${n.label}</span>
                </div>`;
              })}
            </div>
          </div>
        </div>
        <div class="topbar-right-wrap" style="position:relative">
          <div class="topbar-right">
            <span class="cost-btn" @click=${(e: Event) => {
              e.stopPropagation();
              this._showBudgetPopover = !this._showBudgetPopover;
              if (this._showBudgetPopover) void this._fetchBudgetData();
            }}>${formatCost(totalCost)} spent</span>
          </div>
          ${this._showBudgetPopover ? html`
            <div class="budget-backdrop" @click=${() => { this._showBudgetPopover = false; }}></div>
            <div class="budget-popover">
              ${this._renderBudgetPopover(totalCost)}
            </div>
          ` : nothing}
          ${s.approvals.length > 0 ? html`
            <div class="approval-badge" @click=${() => this.navTab('queen')}>
              <span class="approval-dot"></span>${s.approvals.length}
            </div>` : nothing}
        </div>
      </div>

      <div class="body">
        <div class="sidebar ${this.showFull ? 'open' : 'closed'}">
          <div class="sidebar-toggle" @click=${() => { this.sideOpen = !this.sideOpen; }}>
            ${this.sideOpen ? '\u25C2' : '\u25B8'}
          </div>
          ${this.showFull ? html`
            <div class="sidebar-content">
              <div class="nav-header">Navigator</div>
              <div class="tree-panel">
                <fc-tree-nav .tree=${this.tree} .selected=${this.treeSel}
                  @node-select=${(e: CustomEvent) => this.navTree(e.detail)}></fc-tree-nav>
              </div>
              <div style="padding:0 8px 8px">
                ${this._showCreateWorkspace ? html`
                  <div class="glass" style="padding:10px;margin-top:4px;border-radius:6px">
                    <input class="config-input" type="text" placeholder="Workspace name"
                      .value=${this._newWorkspaceName}
                      @input=${(e: Event) => { this._newWorkspaceName = (e.target as HTMLInputElement).value; }}
                      @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter') this._createWorkspace(); }}
                      style="width:100%;box-sizing:border-box;margin-bottom:6px">
                    <div style="display:flex;gap:6px">
                      <fc-btn variant="ghost" sm @click=${() => { this._showCreateWorkspace = false; this._newWorkspaceName = ''; }}>Cancel</fc-btn>
                      <fc-btn variant="primary" sm
                        ?disabled=${!this._newWorkspaceName.trim() || this._creatingWorkspace}
                        @click=${() => this._createWorkspace()}>
                        ${this._creatingWorkspace ? 'Creating...' : 'Create'}
                      </fc-btn>
                    </div>
                  </div>
                ` : html`
                  <button class="create-ws-btn" @click=${() => { this._showCreateWorkspace = true; }}>+ New Workspace</button>
                `}
              </div>
            </div>
          ` : html`
            <div class="mini-colonies">
              ${running.map(c => html`
                <div class="mini-colony ${this.treeSel === c.id ? 'active' : ''}"
                  @click=${() => this.navTree(c.id)} title=${colonyName(c)}>\u2B21</div>
              `)}
            </div>
          `}
        </div>

        <div class="content"><div class="content-inner">
          ${this._renderContentArea()}
        </div></div>
      </div>

      ${this.showCreator ? html`
        <div class="creator-overlay" @click=${(e: Event) => { if (e.target === e.currentTarget) this._closeCreator(); }}>
          <div class="creator-panel">
            <fc-colony-creator
              .castes=${store.state.castes}
              .initialTemplateId=${this.creatorTemplateId}
              .governance=${store.state.runtimeConfig?.governance ?? null}
              @spawn-colony=${(e: CustomEvent) => {
                store.send('spawn_colony', this.activeWorkspaceId, e.detail);
                this._closeCreator();
              }}
              @cancel=${() => this._closeCreator()}
            ></fc-colony-creator>
          </div>
        </div>` : nothing}`;
  }

  private _renderContentArea() {
    if (this.tree.length === 0) return this._renderStartupShell();
    if (this.view === 'queen') return this.renderView();
    return html`
      <div class="view-shell">
        <div class="view-main">${this.renderView()}</div>
        <div class="queen-rail ${this.chatOpen ? 'open' : 'closed'}">
          ${this.chatOpen
            ? html`<div style="display:flex;flex-direction:column;width:100%">
                <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-bottom:1px solid var(--v-border)">
                  <span style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim);letter-spacing:0.1em;text-transform:uppercase">Queen Chat</span>
                  <fc-btn variant="ghost" sm @click=${() => { this.chatOpen = false; }}>\u2715</fc-btn>
                </div>
                ${this._renderQueenChatRail()}
              </div>`
            : html`<div class="chat-fab" @click=${() => { this.chatOpen = true; }}>
                <div class="chat-fab-icon">\u265B</div>
                <span class="chat-fab-label">Queen</span>
              </div>`}
        </div>
      </div>
    `;
  }

  private _renderStartupShell() {
    const s = store.state;
    const connState = s.connection;
    const connReady = connState === 'connected';
    const snapshotReady = !!s.protocolStatus;
    const treeReady = this.tree.length > 0;
    const statusTone = connReady ? (snapshotReady ? 'ready' : 'pending') : (connState === 'connecting' ? 'pending' : 'waiting');
    const title = connState === 'connecting'
      ? 'Connecting to the colony substrate'
      : connState === 'connected'
        ? 'Bootstrapping your default workspace'
        : 'Waiting for FormicOS services';
    const copy = connState === 'connected'
      ? 'The backend is live. FormicOS is replaying state, loading the workspace tree, and preparing the first-run Queen thread.'
      : 'The UI is still waiting for the backend WebSocket. This is normal while Docker brings up the app, model server, embedder, and Qdrant.';
    return html`
      <div class="startup-shell">
        <div class="startup-card">
          <div>
            <div class="startup-kicker">Startup Sequence</div>
            <h1 class="startup-title">${title}</h1>
          </div>
          <p class="startup-copy">${copy}</p>
          <div class="startup-grid">
            <div class="startup-panel">
              <h3>Readiness</h3>
              <div class="startup-checks">
                <div class="startup-step">
                  <span class="startup-dot ${connReady ? 'ready' : connState === 'connecting' ? 'pending' : 'waiting'}"></span>
                  <span>Surface connection: <code>${connState}</code></span>
                </div>
                <div class="startup-step">
                  <span class="startup-dot ${snapshotReady ? 'ready' : statusTone}"></span>
                  <span>Operator snapshot: ${snapshotReady ? 'loaded' : 'waiting for first state frame'}</span>
                </div>
                <div class="startup-step">
                  <span class="startup-dot ${treeReady ? 'ready' : statusTone}"></span>
                  <span>Workspace bootstrap: ${treeReady ? 'tree ready' : 'default workspace and thread not visible yet'}</span>
                </div>
              </div>
            </div>
            <div class="startup-panel">
              <h3>If This Stalls</h3>
              <div class="startup-steps">
                <div class="startup-step">
                  <span class="startup-dot pending"></span>
                  <span>Run <code>docker compose ps</code> and make sure <code>formicos</code>, <code>llm</code>, <code>formicos-embed</code>, and <code>qdrant</code> are up.</span>
                </div>
                <div class="startup-step">
                  <span class="startup-dot pending"></span>
                  <span>Check <code>http://localhost:8080/health</code> for replay and bootstrap counts.</span>
                </div>
                <div class="startup-step">
                  <span class="startup-dot pending"></span>
                  <span>Tail <code>docker compose logs formicos --tail 120</code> if the tree never appears.</span>
                </div>
              </div>
            </div>
          </div>
          <div class="startup-footnote">
            When startup completes, the Queen tab will show a welcome note. From there you can click <code>+</code> to spawn your first colony or ask the Queen to plan a task.
          </div>
        </div>
      </div>
    `;
  }

  // Wave 62 Track 6: component registry map (replaces switch statement)
  private _viewRegistry: Record<string, () => typeof nothing | ReturnType<typeof html>> = {
    'queen': () => this._renderQueen(),
    'tree': () => this._renderTree(),
    'knowledge': () => this._renderKnowledge(),
    'workspace': () => this._renderWorkspace(),
    'operations': () => html`<fc-operations-view .workspaceId=${this.activeWorkspaceId}></fc-operations-view>`,
    'addons': () => html`<fc-addons-view></fc-addons-view>`,
    'playbook': () => this._renderPlaybook(),
    'models': () => this._renderModels(),
    'settings': () => this._renderSettings(),
  };

  private renderView() {
    const renderer = this._viewRegistry[this.view];
    return renderer ? renderer() : nothing;
  }

  private _renderQueen() {
    const s = store.state;
    return html`<fc-queen-overview
      .tree=${this.tree} .approvals=${s.approvals} .localModels=${s.localModels}
      .cloudEndpoints=${s.cloudEndpoints}
      .queenThreads=${this.queenThreads} .activeQT=${this.activeQT} .castes=${s.castes}
      .runtimeConfig=${s.runtimeConfig}
      .skillBankStats=${s.skillBankStats}
      @navigate=${(e: CustomEvent) => this.navTree(e.detail)}
      @approve=${(e: CustomEvent) => store.send('approve', this.activeWorkspaceId, { requestId: e.detail })}
      @deny=${(e: CustomEvent) => store.send('deny', this.activeWorkspaceId, { requestId: e.detail })}
      @switch-thread=${(e: CustomEvent) => { this.activeQT = e.detail; }}
      @new-thread=${() => {
        const name = `thread-${Date.now().toString(36)}`;
        store.send('create_thread', this.activeWorkspaceId, { name });
      }}
      @send-message=${(e: CustomEvent) => {
        const wsId = (e.detail as any).workspaceId || this.activeWorkspaceId;
        store.send('send_queen_message', wsId, e.detail);
      }}
      @spawn-colony-request=${() => this._openCreator()}
      @save-queen-note=${(e: CustomEvent) => {
        store.send('save_queen_note', this.activeWorkspaceId, e.detail);
      }}
      @send-colony-message=${(e: CustomEvent) => store.send('chat_colony', this.activeWorkspaceId, e.detail)}
      @confirm-preview=${(e: CustomEvent) => this._handleConfirmPreview(e)}
      @open-colony-editor=${() => this._openCreator()}
      @update-config=${(e: CustomEvent) => store.send('update_config', this.activeWorkspaceId, e.detail)}
    ></fc-queen-overview>`;
  }

  private _renderTree() {
    const sel = this.selNode;
    const s = store.state;
    if (sel?.type === 'colony') return html`<fc-colony-detail .colony=${sel as any}
      .queenThreads=${this.queenThreads} .activeQT=${this.activeQT}
      @switch-thread=${(e: CustomEvent) => { this.activeQT = e.detail; }}
      @new-thread=${() => {
        const name = `thread-${Date.now().toString(36)}`;
        store.send('create_thread', this.activeWorkspaceId, { name });
      }}
      @rename-colony=${(e: CustomEvent) => store.send('rename_colony', this.activeWorkspaceId, e.detail)}
      @send-message=${(e: CustomEvent) => store.send('send_queen_message', this.activeWorkspaceId, e.detail)}
      @kill-colony=${(e: CustomEvent) => store.send('kill_colony', this.activeWorkspaceId, { colonyId: e.detail })}
      @activate-service=${(e: CustomEvent) => store.send('activate_service', this.activeWorkspaceId, e.detail)}
      @send-colony-message=${(e: CustomEvent) => store.send('chat_colony', this.activeWorkspaceId, e.detail)}
      @navigate-knowledge=${(e: CustomEvent) => {
        this.knowledgeSourceColony = (e.detail as any)?.sourceColonyId ?? '';
        this.view = 'knowledge' as ViewId;
      }}
    ></fc-colony-detail>`;
    if (sel?.type === 'thread') return html`<fc-thread-view .thread=${sel} .parentWsName=${this.parentWs?.name ?? ''}
      .merges=${this.merges}
      @navigate=${(e: CustomEvent) => this.navTree(e.detail)}
      @create-merge=${(e: CustomEvent) => store.send('create_merge', this.activeWorkspaceId, e.detail)}
      @prune-merge=${(e: CustomEvent) => store.send('prune_merge', this.activeWorkspaceId, { edgeId: e.detail })}
      @broadcast=${(e: CustomEvent) => {
        const d = e.detail;
        const payload = typeof d === 'object' && d !== null ? d : { threadId: d };
        store.send('broadcast', this.activeWorkspaceId, payload);
      }}
      @spawn-colony=${(e: CustomEvent) => store.send('spawn_colony', this.activeWorkspaceId, e.detail)}
      @rename-thread=${(e: CustomEvent) => store.send('rename_thread', this.activeWorkspaceId, e.detail)}
      @navigate-knowledge=${(e: CustomEvent) => {
        this.knowledgeSourceColony = '';
        this.view = 'knowledge' as ViewId;
      }}
    ></fc-thread-view>`;
    if (sel?.type === 'workspace') return html`<fc-workspace-config .workspace=${sel as any}
      .castes=${s.castes} .runtimeConfig=${s.runtimeConfig}
      @navigate=${(e: CustomEvent) => this.navTree(e.detail)}
      @update-config=${(e: CustomEvent) => store.send('update_config', sel.id, e.detail)}
      @spawn-colony-request=${() => this._openCreator()}
      @navigate-tab=${(e: CustomEvent) => this.navTab(e.detail)}
    ></fc-workspace-config>`;
    return nothing;
  }

  private get _addonPanels() {
    return store.state.addons.flatMap(a =>
      (a.panels ?? []).map(p => ({
        target: p.target,
        display_type: p.displayType,
        path: p.path,
        addon_name: p.addonName,
      }))
    );
  }

  private _renderKnowledge() {
    return html`<fc-knowledge-browser .workspaceId=${this.activeWorkspaceId}
      .sourceColonyId=${this.knowledgeSourceColony}
      .addonPanels=${this._addonPanels}></fc-knowledge-browser>`;
  }

  private _renderWorkspace() {
    return html`<fc-workspace-browser .workspaceId=${this.activeWorkspaceId}
      .addonPanels=${this._addonPanels}></fc-workspace-browser>`;
  }

  private _renderPlaybook() {
    const s = store.state;
    return html`<fc-playbook-view
      .castes=${s.castes} .tree=${this.tree} .runtimeConfig=${s.runtimeConfig}
      @navigate=${(e: CustomEvent) => this.navTree(e.detail)}
      @select-template=${(e: CustomEvent) => this._openCreator(e.detail?.id ?? '')}
    ></fc-playbook-view>`;
  }

  private _renderModels() {
    const s = store.state;
    return html`<fc-model-registry .localModels=${s.localModels}
      .cloudEndpoints=${s.cloudEndpoints}
      .castes=${s.castes}
      .runtimeConfig=${s.runtimeConfig}></fc-model-registry>`;
  }

  private _renderSettings() {
    const s = store.state;
    return html`<fc-settings-view .protocolStatus=${s.protocolStatus} .runtimeConfig=${s.runtimeConfig} .skillBankStats=${s.skillBankStats} .tree=${this.tree} .addons=${s.addons}></fc-settings-view>`;
  }

  private _renderQueenChatRail() {
    const rc = allColonies(this.tree)
      .filter(c => c.status === 'running')
      .map(c => ({ id: c.id, name: colonyName(c) }));
    return html`<fc-queen-chat
      .threads=${this.queenThreads}
      .activeThreadId=${this.activeQT}
      .runningColonies=${rc}
      @switch-thread=${(e: CustomEvent) => { this.activeQT = e.detail; }}
      @new-thread=${() => {
        const name = `thread-${Date.now().toString(36)}`;
        store.send('create_thread', this.activeWorkspaceId, { name });
      }}
      @send-message=${(e: CustomEvent) => {
        const wsId = (e.detail as any).workspaceId || this.activeWorkspaceId;
        store.send('send_queen_message', wsId, e.detail);
      }}
      @save-queen-note=${(e: CustomEvent) => {
        store.send('save_queen_note', this.activeWorkspaceId, e.detail);
      }}
      @send-colony-message=${(e: CustomEvent) => store.send('chat_colony', this.activeWorkspaceId, e.detail)}
      @confirm-preview=${(e: CustomEvent) => this._handleConfirmPreview(e)}
      @navigate=${(e: CustomEvent) => this.navTree(e.detail)}
      @open-colony-editor=${() => this._openCreator()}
    ></fc-queen-chat>`;
  }

  /** Wave 49: dispatch colony directly from stored preview parameters. */
  private _handleConfirmPreview(e: CustomEvent) {
    const preview = e.detail;
    if (!preview) return;
    const wsId = preview.workspaceId || this.activeWorkspaceId;
    const threadId = preview.threadId || this.activeQT;
    // Build spawn payload from preview metadata
    const payload: Record<string, unknown> = {
      task: preview.task,
      strategy: preview.strategy,
      maxRounds: preview.maxRounds,
      budgetLimit: preview.budgetLimit,
      threadId,
      team: preview.team,
    };
    if (preview.targetFiles?.length) {
      payload.targetFiles = preview.targetFiles;
    }
    store.send('spawn_colony', wsId, payload);
    // Send a visible confirmation message to the thread
    store.send('send_queen_message', wsId, {
      threadId,
      content: `\u2713 Confirmed: dispatching colony for "${preview.task}"`,
    });
  }

  private _openCreator(templateId = '') {
    this.creatorTemplateId = templateId;
    this.showCreator = true;
  }

  private _closeCreator() {
    this.showCreator = false;
    this.creatorTemplateId = '';
  }

  private async _createWorkspace() {
    if (!this._newWorkspaceName.trim()) return;
    this._creatingWorkspace = true;
    try {
      const resp = await fetch('/api/v1/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: this._newWorkspaceName.trim() }),
      });
      if (resp.ok) {
        this._showCreateWorkspace = false;
        this._newWorkspaceName = '';
      } else {
        const data = await resp.json().catch(() => ({}));
        console.error('Failed to create workspace:', (data as Record<string, unknown>).error ?? resp.statusText);
      }
    } catch (e) {
      console.error('Failed to create workspace:', e);
    }
    this._creatingWorkspace = false;
  }

  private async _fetchBudgetData() {
    const wsId = store.state.tree?.[0]?.id;
    if (!wsId) return;
    try {
      const resp = await fetch(`/api/v1/workspaces/${wsId}/autonomy-status`);
      if (resp.ok) this._autonomyData = await resp.json() as typeof this._autonomyData;
    } catch { /* popover shows what it has */ }
  }

  private _renderBudgetPopover(totalCost: number) {
    const perColonyCap = (store.state as any).runtimeConfig?.governance?.defaultBudgetPerColony ?? 1.0;
    const a = this._autonomyData;
    return html`
      <div class="budget-row">
        <span class="budget-label">Total spent</span>
        <span class="budget-value">${formatCost(totalCost)}</span>
      </div>
      <div class="budget-row">
        <span class="budget-label">Per-colony cap</span>
        <span class="budget-value">${formatCost(perColonyCap as number)}</span>
      </div>
      ${a ? html`
        <div class="budget-row">
          <span class="budget-label">Daily maintenance</span>
          <span class="budget-value">${formatCost(a.budget_spent)} / ${formatCost(a.budget_total || a.daily_maintenance_budget || 0)}</span>
        </div>
        <div class="budget-row">
          <span class="budget-label">Autonomy</span>
          <span class="budget-value neutral">Grade ${a.grade} · ${a.level}</span>
        </div>
      ` : html`
        <div class="budget-row">
          <span class="budget-label">Daily maintenance</span>
          <span class="budget-value neutral">—</span>
        </div>
      `}
      <span class="popover-link" @click=${() => { this._showBudgetPopover = false; this.navTab('settings'); }}>All budget settings \u2192</span>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'formicos-app': FormicOSApp; }
}
