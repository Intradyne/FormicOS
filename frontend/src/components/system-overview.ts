/**
 * Wave 69 Track 11: System capability summary header.
 * Compact one-line overview rendered at top of settings page.
 */
import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { RuntimeConfig, AddonSummary } from '../types.js';

@customElement('fc-system-overview')
export class FcSystemOverview extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; margin-bottom: 14px; }
    .summary {
      font-family: var(--f-mono);
      font-size: 10.5px;
      color: var(--v-fg-muted);
      line-height: 1.6;
    }
    .sep { margin: 0 4px; }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: Object }) runtimeConfig: RuntimeConfig | null = null;
  @property({ type: Array }) addons: AddonSummary[] = [];
  @property({ type: Number }) knowledgeTotal = 0;
  @property({ type: Number }) domainCount = 0;

  private get _queenToolCount(): number {
    // Hardcoded from caste_recipes.yaml — 43 tools as of Wave 70
    return 43;
  }

  private get _addonCount(): number {
    return this.addons.length;
  }

  private get _providerCount(): number {
    const reg = this.runtimeConfig?.models?.registry ?? [];
    const providers = new Set(reg.map(m => m.provider));
    return providers.size;
  }

  render() {
    const parts: string[] = [];
    parts.push(`${this._queenToolCount} Queen tools`);
    parts.push(`${this._addonCount} addon${this._addonCount !== 1 ? 's' : ''}`);
    parts.push(`${this._providerCount} provider${this._providerCount !== 1 ? 's' : ''}`);
    if (this.knowledgeTotal > 0) {
      parts.push(`${this.knowledgeTotal} knowledge entries`);
    }
    if (this.domainCount > 0) {
      parts.push(`across ${this.domainCount} domains`);
    }

    return html`<div class="summary">${parts.join(' \u00B7 ')}</div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-system-overview': FcSystemOverview; }
}
