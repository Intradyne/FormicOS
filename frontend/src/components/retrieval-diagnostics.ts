import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

/** Per-stage latency snapshot for the retrieval pipeline. */
export interface RetrievalTiming {
  embedMs: number;
  denseMs: number;
  bm25Ms: number;
  graphMs: number;
  fusionMs: number;
  totalMs: number;
}

/** Counts for skill bank and knowledge graph. */
export interface RetrievalCounts {
  skillBankSize: number;
  kgEntities: number;
  kgEdges: number;
}

@customElement('fc-retrieval-diagnostics')
export class FcRetrievalDiagnostics extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .grid {
      display: grid; grid-template-columns: 1fr 1fr 1fr;
      gap: 8px; margin-bottom: 10px;
    }
    .info {
      font-size: 8.5px; font-family: var(--f-mono);
      color: var(--v-fg-dim); letter-spacing: 0.04em;
    }
    .counts {
      display: flex; gap: 14px; margin-top: 8px;
      padding-top: 8px; border-top: 1px solid var(--v-border);
    }
    .count-item {
      display: flex; flex-direction: column; gap: 1px;
    }
    .count-val {
      font-family: var(--f-mono); font-size: 12px;
      font-weight: 600; color: var(--v-fg);
      font-feature-settings: 'tnum';
    }
    .count-label {
      font-family: var(--f-mono); font-size: 7px;
      color: var(--v-fg-dim); letter-spacing: 0.1em;
      text-transform: uppercase;
    }
  `];

  @property({ type: Object }) timing: RetrievalTiming | null = null;
  @property({ type: Object }) counts: RetrievalCounts | null = null;
  @property() embeddingModel = '';
  @property({ type: Number }) embeddingDim = 0;
  @property() searchMode = '';

  render() {
    const t = this.timing;
    const c = this.counts;

    return html`
      <div class="s-label">Retrieval Pipeline</div>
      <div class="glass" style="padding:14px">
        <div class="grid">
          <fc-meter label="Embed" .value=${t?.embedMs ?? 0} .max=${100}
            unit="ms" color="var(--v-blue)"></fc-meter>
          <fc-meter label="Dense" .value=${t?.denseMs ?? 0} .max=${50}
            unit="ms" color="var(--v-purple)"></fc-meter>
          <fc-meter label="BM25" .value=${t?.bm25Ms ?? 0} .max=${50}
            unit="ms" color="var(--v-secondary)"></fc-meter>
          <fc-meter label="Graph" .value=${t?.graphMs ?? 0} .max=${50}
            unit="ms" color="var(--v-warn)"></fc-meter>
          <fc-meter label="RRF Fusion" .value=${t?.fusionMs ?? 0} .max=${10}
            unit="ms" color="var(--v-accent)"></fc-meter>
          <fc-meter label="Total" .value=${t?.totalMs ?? 0} .max=${200}
            unit="ms" color="var(--v-success)"></fc-meter>
        </div>

        ${this.embeddingModel ? html`
          <div class="info">
            ${this.embeddingModel}${this.embeddingDim ? html` · ${this.embeddingDim}-dim` : nothing}${this.searchMode ? html` · ${this.searchMode}` : nothing}
          </div>` : nothing}

        ${c ? html`
          <div class="counts">
            <div class="count-item">
              <span class="count-val">${c.skillBankSize}</span>
              <span class="count-label">Skills</span>
            </div>
            <div class="count-item">
              <span class="count-val">${c.kgEntities}</span>
              <span class="count-label">KG Entities</span>
            </div>
            <div class="count-item">
              <span class="count-val">${c.kgEdges}</span>
              <span class="count-label">KG Edges</span>
            </div>
          </div>` : nothing}
      </div>`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-retrieval-diagnostics': FcRetrievalDiagnostics; }
}
