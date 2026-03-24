import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import { colonyName } from '../helpers.js';
import type { TreeNode } from '../types.js';

@customElement('fc-breadcrumb-nav')
export class FcBreadcrumbNav extends LitElement {
  static styles = [voidTokens, css`
    :host { display: flex; align-items: center; gap: 2px; font-size: 10.5px; font-family: var(--f-mono); }
    .sep { color: var(--v-fg-dim); font-size: 7px; }
    .crumb { cursor: pointer; color: var(--v-fg-muted); transition: color 0.12s; }
    .crumb:hover { color: var(--v-fg); }
    .crumb.current { color: var(--v-fg); }
  `];

  @property({ type: Array }) crumbs: TreeNode[] = [];

  render() {
    return html`${this.crumbs.map((n, i) => html`
      ${i > 0 ? html`<span class="sep">\u27E9</span>` : ''}
      <span class="crumb ${i === this.crumbs.length - 1 ? 'current' : ''}"
        @click=${() => this.dispatchEvent(new CustomEvent('navigate', { detail: n.id, bubbles: true, composed: true }))}>${colonyName(n)}</span>
    `)}`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-breadcrumb-nav': FcBreadcrumbNav; }
}
