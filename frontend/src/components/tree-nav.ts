import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import { colonyName } from '../helpers.js';
import type { TreeNode } from '../types.js';
import './atoms.js';

const icons: Record<string, string> = { workspace: '\u25A3', thread: '\u25B7', colony: '\u2B21' };
const colors: Record<string, string> = { workspace: '#E8581A', thread: '#5B9CF5', colony: '#6B6B76' };

@customElement('fc-tree-nav')
export class FcTreeNav extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; padding-top: 1px; }
    .node {
      padding: 4px 8px; cursor: pointer; display: flex; align-items: center; gap: 4px;
      border-left: 2px solid transparent; transition: all 0.12s; font-size: 11px; font-family: var(--f-mono);
    }
    .node.selected { background: rgba(232,88,26,0.05); border-left-color: var(--v-accent); border-radius: 0 3px 3px 0; }
    .toggle {
      color: var(--v-fg-dim); font-size: 7px; width: 20px; height: 20px;
      display: inline-flex; align-items: center; justify-content: center;
      cursor: pointer; border-radius: 4px; flex-shrink: 0;
      transition: background 0.12s, color 0.12s;
      user-select: none; -webkit-user-select: none;
    }
    .toggle:hover { background: rgba(255,255,255,0.06); color: var(--v-fg-muted); }
    .icon { font-size: 9px; }
    .name { overflow: hidden; text-overflow: ellipsis; flex: 1; font-size: 10.5px; }
    .spacer { width: 20px; flex-shrink: 0; }
  `];

  @property({ type: Array }) tree: TreeNode[] = [];
  @property() selected: string | null = null;
  @state() private expanded: Record<string, boolean> = {};

  private renderNode(node: TreeNode, depth = 0): unknown {
    const sel = this.selected === node.id;
    const exp = this.expanded[node.id] !== false;
    const has = (node.children?.length ?? 0) > 0;
    const qs = (node as any).qualityScore as number | undefined;
    return html`
      <div>
        <div class="node ${sel ? 'selected' : ''}" style="padding-left:${6 + depth * 12}px"
          @click=${(e: Event) => { if (this._clickedToggle(e)) return; this.select(node.id); }}>
          ${has
            ? html`<span class="toggle" @click=${(e: Event) => { e.stopPropagation(); e.preventDefault(); this.toggle(node.id); }}>${exp ? '\u25BC' : '\u25B6'}</span>`
            : html`<span class="spacer"></span>`}
          <span class="icon" style="color:${colors[node.type] ?? '#6B6B76'}">${icons[node.type] ?? ''}</span>
          <span class="name" style="color:${sel ? 'var(--v-fg)' : 'var(--v-fg-muted)'}">${colonyName(node)}</span>
          ${node.status ? html`<fc-dot .status=${node.status} .size=${4}></fc-dot>` : nothing}
          ${qs != null && qs > 0 ? html`<fc-quality-dot .quality=${qs} .size=${4}></fc-quality-dot>` : nothing}
        </div>
        ${has && exp ? node.children!.map(c => this.renderNode(c, depth + 1)) : nothing}
      </div>`;
  }

  render() {
    return html`${this.tree.map(n => this.renderNode(n))}`;
  }

  private select(id: string) {
    this.dispatchEvent(new CustomEvent('node-select', { detail: id, bubbles: true, composed: true }));
  }

  private toggle(id: string) {
    const wasExpanded = this.expanded[id] !== false;
    this.expanded = { ...this.expanded, [id]: !wasExpanded };
  }

  private _clickedToggle(e: Event): boolean {
    return e.composedPath().some(target =>
      target instanceof HTMLElement && target.classList.contains('toggle'),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-tree-nav': FcTreeNav; }
}
