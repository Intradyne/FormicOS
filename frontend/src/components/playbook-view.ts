import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { CasteDefinition, TreeNode, RuntimeConfig, TemplateInfo } from '../types.js';
import type { EditorMode } from './template-editor.js';
import type { CasteRecipePayload } from './caste-editor.js';
import './castes-view.js';
import './template-browser.js';
import './template-editor.js';
import './caste-editor.js';

type PlaybookTab = 'templates' | 'castes' | 'playbooks';
type OverlayKind = 'template' | 'caste' | null;

interface PlaybookData {
  task_class?: string;
  castes?: string[];
  workflow?: string;
  steps?: string[];
  productive_tools?: string[];
  observation_tools?: string[];
  observation_limit?: number;
  example?: { name?: string; arguments?: Record<string, unknown> };
  _file?: string;
  // Wave 78 Track 4: auto-generated playbook fields
  source?: string;        // 'agent' for auto-generated
  status?: string;        // 'candidate' | 'approved'
  proposed_by?: string;   // colony ID
  proposed_at?: string;   // ISO timestamp
}

@customElement('fc-playbook-view')
export class FcPlaybookView extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; height: 100%; overflow: hidden; }
    .tab-row { display: flex; gap: 4px; margin-bottom: 12px; }
    .tab-pill {
      font-size: 9.5px; font-family: var(--f-mono); padding: 3px 12px;
      border-radius: 8px; cursor: pointer; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim);
      transition: all 0.15s; user-select: none;
    }
    .tab-pill.active {
      background: rgba(232,88,26,0.08);
      border-color: rgba(232,88,26,0.2);
      color: var(--v-accent);
    }
    .panel { height: calc(100% - 36px); overflow: hidden; }
    .playbook-scroll { height: 100%; overflow-y: auto; padding-right: 4px; }
    .editor-overlay {
      position: fixed; inset: 0; z-index: 100;
      display: flex; align-items: center; justify-content: center;
      background: rgba(4,4,8,0.7);
      backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
    }
    .editor-panel {
      width: 520px; max-height: 85vh; overflow: auto; padding: 20px;
      border-radius: 12px; background: var(--v-surface);
      border: 1px solid var(--v-border);
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    .pb-card {
      border: 1px solid var(--v-border); border-radius: 8px;
      padding: 14px 16px; margin-bottom: 10px;
      background: var(--v-surface);
    }
    .pb-header {
      display: flex; align-items: baseline; gap: 8px;
      margin-bottom: 8px;
    }
    .pb-title {
      font-family: var(--f-mono); font-size: 11px;
      font-weight: 600; color: var(--v-accent);
    }
    .pb-castes {
      font-family: var(--f-mono); font-size: 9px;
      color: var(--v-fg-dim);
    }
    .pb-workflow {
      font-size: 10px; color: var(--v-fg);
      margin-bottom: 8px; line-height: 1.4;
    }
    .pb-section-label {
      font-family: var(--f-mono); font-size: 8.5px;
      color: var(--v-fg-dim); text-transform: uppercase;
      letter-spacing: 0.5px; margin: 8px 0 4px;
    }
    .pb-steps {
      list-style: decimal; padding-left: 18px; margin: 0;
    }
    .pb-steps li {
      font-size: 10px; color: var(--v-fg);
      line-height: 1.5; margin-bottom: 2px;
    }
    .pb-tools {
      font-family: var(--f-mono); font-size: 9px;
      color: var(--v-fg-dim); line-height: 1.5;
    }
    .pb-tools .productive { color: var(--v-accent); }
    .pb-example {
      font-family: var(--f-mono); font-size: 9px;
      color: var(--v-fg-dim); background: rgba(255,255,255,0.03);
      border-radius: 4px; padding: 8px; margin-top: 4px;
      white-space: pre-wrap; overflow-x: auto;
    }
    .pb-empty {
      font-size: 10px; color: var(--v-fg-dim);
      text-align: center; padding: 32px 0;
    }
    .pb-card.candidate {
      border-color: rgba(245,183,49,0.3);
      background: rgba(245,183,49,0.03);
    }
    .pb-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px;
      border-radius: 4px; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .pb-badge.proposed {
      background: rgba(245,183,49,0.12); color: var(--v-warn);
      border: 1px solid rgba(245,183,49,0.25);
    }
    .pb-badge.approved {
      background: rgba(45,212,168,0.1); color: var(--v-success);
      border: 1px solid rgba(45,212,168,0.2);
    }
    .pb-proposed-by {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      margin-bottom: 6px;
    }
    .pb-actions {
      display: flex; gap: 6px; margin-top: 8px;
    }
    .pb-action-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 10px;
      border-radius: 8px; cursor: pointer; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); transition: all 0.15s;
    }
    .pb-action-btn.approve {
      border-color: rgba(45,212,168,0.3); color: var(--v-success);
    }
    .pb-action-btn.approve:hover {
      background: rgba(45,212,168,0.08);
    }
    .pb-action-btn.dismiss {
      border-color: rgba(240,100,100,0.3); color: var(--v-danger);
    }
    .pb-action-btn.dismiss:hover {
      background: rgba(240,100,100,0.08);
    }
  `];

  @property({ type: Array }) castes: CasteDefinition[] = [];
  @property({ type: Array }) tree: TreeNode[] = [];
  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;

  @state() private activeTab: PlaybookTab = 'castes';

  // Template editor state
  @state() private overlayKind: OverlayKind = null;
  @state() private editorMode: EditorMode = 'create';
  @state() private editorTemplate: TemplateInfo | null = null;

  // Caste editor state
  @state() private casteEditorId = '';
  @state() private casteEditorRecipe: CasteRecipePayload | null = null;
  @state() private casteEditorIsNew = false;

  // Playbook data
  @state() private _playbooks: PlaybookData[] = [];
  @state() private _playbooksLoaded = false;

  render() {
    return html`
      <div class="tab-row">
        <span class="tab-pill ${this.activeTab === 'templates' ? 'active' : ''}"
          @click=${() => { this.activeTab = 'templates'; }}>Templates</span>
        <span class="tab-pill ${this.activeTab === 'castes' ? 'active' : ''}"
          @click=${() => { this.activeTab = 'castes'; }}>Castes</span>
        <span class="tab-pill ${this.activeTab === 'playbooks' ? 'active' : ''}"
          @click=${() => { this.activeTab = 'playbooks'; this._ensurePlaybooksLoaded(); }}>Playbooks</span>
      </div>
      <div class="panel">
        ${this.activeTab === 'templates'
          ? html`<fc-template-browser
              @select-template=${(e: CustomEvent) => this._fire('select-template', e.detail)}
              @navigate=${(e: CustomEvent) => this._fire('navigate', e.detail)}
              @new-template=${() => this._openTemplateEditor('create', null)}
              @edit-template=${(e: CustomEvent) => this._openTemplateEditor('edit', e.detail)}
              @duplicate-template=${(e: CustomEvent) => this._openTemplateEditor('duplicate', e.detail)}
            ></fc-template-browser>`
          : this.activeTab === 'castes'
          ? html`<fc-castes-view .castes=${this.castes} .tree=${this.tree}
              .runtimeConfig=${this.runtimeConfig}
              @edit-caste=${(e: CustomEvent) => this._openCasteEditor(e.detail.id, e.detail.recipe)}
              @new-caste=${() => this._openNewCasteEditor()}
            ></fc-castes-view>`
          : this._renderPlaybooks()
        }
      </div>

      ${this.overlayKind ? html`
        <div class="editor-overlay"
          @click=${(e: Event) => {
            if (e.target === e.currentTarget) this._closeOverlay();
          }}>
          <div class="editor-panel">
            ${this.overlayKind === 'template' ? html`
              <fc-template-editor
                .mode=${this.editorMode}
                .template=${this.editorTemplate}
                .governance=${this.runtimeConfig?.governance ?? null}
                @saved=${() => this._onTemplateSaved()}
                @cancel=${() => this._closeOverlay()}
              ></fc-template-editor>
            ` : html`
              <fc-caste-editor
                .casteId=${this.casteEditorId}
                .recipe=${this.casteEditorRecipe}
                .isNew=${this.casteEditorIsNew}
                .runtimeConfig=${this.runtimeConfig}
                @saved=${() => this._onCasteSaved()}
                @cancel=${() => this._closeOverlay()}
              ></fc-caste-editor>
            `}
          </div>
        </div>` : nothing}
    `;
  }

  private _renderPlaybooks() {
    if (!this._playbooksLoaded) {
      return html`<div class="pb-empty">Loading playbooks...</div>`;
    }
    if (this._playbooks.length === 0) {
      return html`<div class="pb-empty">No operational playbooks found.</div>`;
    }
    return html`
      <div class="playbook-scroll">
        ${this._playbooks.map(pb => this._renderPlaybookCard(pb))}
      </div>
    `;
  }

  private _renderPlaybookCard(pb: PlaybookData) {
    const taskClass = pb.task_class || pb._file || 'unknown';
    const castes = (pb.castes || []).join(', ');
    const steps = pb.steps || [];
    const productive = (pb.productive_tools || []).join(', ');
    const observation = (pb.observation_tools || []).join(', ');
    const obsLimit = pb.observation_limit ?? 2;
    const example = pb.example;
    const isCandidate = pb.source === 'agent' && pb.status === 'candidate';
    const isApproved = pb.status === 'approved';

    return html`
      <div class="pb-card ${isCandidate ? 'candidate' : ''}">
        <div class="pb-header">
          <span class="pb-title">${taskClass}</span>
          <span class="pb-castes">${castes}</span>
          ${isCandidate ? html`<span class="pb-badge proposed">Proposed</span>` : nothing}
          ${isApproved && pb.source === 'agent' ? html`<span class="pb-badge approved">Approved</span>` : nothing}
        </div>
        ${pb.proposed_by ? html`
          <div class="pb-proposed-by">Proposed by colony ${pb.proposed_by.slice(0, 12)}</div>
        ` : nothing}
        ${pb.workflow ? html`<div class="pb-workflow">${pb.workflow}</div>` : nothing}
        ${steps.length > 0 ? html`
          <div class="pb-section-label">Steps</div>
          <ol class="pb-steps">
            ${steps.map(s => html`<li>${s}</li>`)}
          </ol>
        ` : nothing}
        <div class="pb-section-label">Tools</div>
        <div class="pb-tools">
          <span class="productive">${productive}</span>
          ${observation ? html` \u00B7 observe: ${observation} (limit ${obsLimit})` : nothing}
        </div>
        ${example?.name ? html`
          <div class="pb-section-label">Example</div>
          <div class="pb-example">${JSON.stringify({ name: example.name, arguments: example.arguments || {} }, null, 2)}</div>
        ` : nothing}
        ${isCandidate && pb._file ? html`
          <div class="pb-actions">
            <button class="pb-action-btn approve"
              @click=${() => void this._approvePlaybook(pb._file!)}>Approve</button>
            <button class="pb-action-btn dismiss"
              @click=${() => void this._dismissPlaybook(pb._file!)}>Dismiss</button>
          </div>
        ` : nothing}
      </div>
    `;
  }

  private async _ensurePlaybooksLoaded() {
    if (this._playbooksLoaded) return;
    try {
      const resp = await fetch('/api/v1/playbooks');
      if (resp.ok) {
        const data = await resp.json();
        this._playbooks = data.playbooks || [];
      }
    } catch {
      // Silently fail — empty list is fine
    }
    this._playbooksLoaded = true;
  }

  /** Wave 78 Track 4: Approve a candidate playbook. */
  private async _approvePlaybook(filename: string) {
    try {
      const resp = await fetch(`/api/v1/playbooks/${encodeURIComponent(filename)}/approve`, {
        method: 'PUT',
      });
      if (resp.ok) {
        this._playbooksLoaded = false;
        this._ensurePlaybooksLoaded();
      }
    } catch { /* best-effort */ }
  }

  /** Wave 78 Track 4: Dismiss (delete) a candidate playbook. */
  private async _dismissPlaybook(filename: string) {
    try {
      const resp = await fetch(`/api/v1/playbooks/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
      if (resp.ok) {
        this._playbooksLoaded = false;
        this._ensurePlaybooksLoaded();
      }
    } catch { /* best-effort */ }
  }

  private _openTemplateEditor(mode: EditorMode, template: TemplateInfo | null) {
    this.editorMode = mode;
    this.editorTemplate = template;
    this.overlayKind = 'template';
  }

  private _openCasteEditor(id: string, recipe: CasteRecipePayload | null) {
    this.casteEditorId = id;
    this.casteEditorRecipe = recipe;
    this.casteEditorIsNew = false;
    this.overlayKind = 'caste';
  }

  private _openNewCasteEditor() {
    this.casteEditorId = '';
    this.casteEditorRecipe = null;
    this.casteEditorIsNew = true;
    this.overlayKind = 'caste';
  }

  private _closeOverlay() {
    this.overlayKind = null;
    this.editorTemplate = null;
    this.casteEditorRecipe = null;
  }

  private _onTemplateSaved() {
    this._closeOverlay();
    const browser = this.shadowRoot?.querySelector('fc-template-browser');
    if (browser) (browser as any).refresh();
  }

  private _onCasteSaved() {
    this._closeOverlay();
    const castesView = this.shadowRoot?.querySelector('fc-castes-view');
    if (castesView) (castesView as any).refresh();
  }

  private _fire(name: string, detail: unknown) {
    this.dispatchEvent(
      new CustomEvent(name, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-playbook-view': FcPlaybookView; }
}
