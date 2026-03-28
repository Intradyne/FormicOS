/**
 * Wave 69 Track 2: Consulted-sources chip strip.
 *
 * Renders a horizontal strip of clickable chips below Queen messages
 * showing which knowledge entries were available during reasoning.
 * Labeled "Consulted Knowledge" — not "Citations."
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { ConsultedEntry } from '../types.js';
import './atoms.js';

@customElement('fc-consulted-sources')
export class ConsultedSources extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .strip {
      display: flex; flex-wrap: wrap; align-items: center;
      gap: 5px; padding: 4px 0 2px;
    }
    .label {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      color: var(--v-fg-dim); letter-spacing: 0.08em;
      text-transform: uppercase; margin-right: 2px;
    }
    .chip {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 8px; border-radius: 4px;
      border: 1px solid var(--v-border);
      background: rgba(255,255,255,0.02);
      font-size: 10px; font-family: var(--f-body);
      color: var(--v-fg-muted); cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
      max-width: 220px;
    }
    @media (prefers-reduced-motion: reduce) {
      .chip { transition: none; }
    }
    .chip:hover {
      border-color: var(--v-border-hover);
      background: rgba(255,255,255,0.04);
      color: var(--v-fg);
    }
    .chip-title {
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .conf-dot {
      width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
    }
  `];

  @property({ type: Array }) entries: ConsultedEntry[] = [];

  render() {
    if (!this.entries?.length) return nothing;

    return html`
      <div class="strip">
        <span class="label">Consulted Knowledge</span>
        ${this.entries.map(e => this._renderChip(e))}
      </div>
    `;
  }

  private _renderChip(entry: ConsultedEntry) {
    const conf = entry.confidence ?? 0.5;
    const color = conf >= 0.7 ? 'var(--v-success)'
      : conf >= 0.4 ? 'var(--v-warn)'
      : 'var(--v-danger)';
    const title = (entry.title ?? '').slice(0, 40) || 'Untitled';

    return html`
      <span class="chip" title="${entry.title ?? ''} (confidence: ${(conf * 100).toFixed(0)}%)"
        @click=${() => this._navigate(entry.id)}>
        <span class="conf-dot" style="background:${color}"></span>
        <span class="chip-title">${title}</span>
      </span>
    `;
  }

  private _navigate(entryId: string) {
    if (!entryId) return;
    this.dispatchEvent(new CustomEvent('navigate-knowledge', {
      detail: { entryId },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-consulted-sources': ConsultedSources; }
}
