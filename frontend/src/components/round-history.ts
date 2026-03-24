import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { providerColor } from '../helpers.js';
import type { RoundRecord } from '../types.js';
import './atoms.js';

const phaseColor: Record<string, string> = {
  goal: '#E8581A', Goal: '#E8581A',
  intent: '#A78BFA', Intent: '#A78BFA',
  route: '#F5B731', Route: '#F5B731',
  execute: '#5B9CF5', Execute: '#5B9CF5',
  compress: '#3DD6F5', Compress: '#3DD6F5',
};

/** Extended round agent — handles optional output/tools defensively. */
interface RoundAgentExt {
  agentId?: string;
  name: string;
  model: string;
  tokens: number;
  status: string;
  output?: string | null;
  tools?: string[];
}

/** Extended round record — handles optional convergence/cost/duration defensively. */
interface RoundRecordExt extends RoundRecord {
  convergence?: number;
  cost?: number;
  duration?: number | null;
}

@customElement('fc-round-history')
export class FcRoundHistory extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .rounds-toggle {
      display: flex; align-items: center; gap: 5px; cursor: pointer; user-select: none;
      padding: 4px 0; font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.06em; transition: color 0.12s;
    }
    .rounds-toggle:hover { color: var(--v-fg-muted); }
    .round { padding-left: 10px; }
    .round-header {
      display: flex; align-items: center; gap: 5px; margin-bottom: 3px;
      cursor: pointer; user-select: none;
    }
    .round-header:hover { opacity: 0.85; }
    .round-num { font-family: var(--f-display); font-size: 11px; font-weight: 700; }
    .phase-label { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.08em; }
    .meta { font-size: 8px; font-family: var(--f-mono); font-feature-settings: 'tnum'; }
    .chevron { font-size: 8px; color: var(--v-fg-dim); margin-left: auto; }

    .agent-row-compact {
      display: flex; align-items: center; gap: 5px; padding: 1px 0 1px 4px; font-size: 9.5px;
    }
    .agent-name { color: var(--v-fg-muted); width: 55px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .agent-model { color: var(--v-fg-dim); font-size: 9px; display: inline-flex; align-items: center; gap: 2px; }
    .agent-tokens { color: var(--v-fg-dim); font-size: 9px; margin-left: auto; font-feature-settings: 'tnum'; }
    .provider-dot { display: inline-block; width: 4px; height: 4px; border-radius: 50%; flex-shrink: 0; }

    .agent-expanded {
      padding: 4px 0 4px 6px; margin-bottom: 2px;
      border-bottom: 1px solid var(--v-border);
    }
    .agent-expanded:last-child { border-bottom: none; }
    .agent-exp-row { display: flex; align-items: center; gap: 5px; font-size: 9.5px; }
    .agent-exp-name {
      color: var(--v-fg); width: 70px; font-weight: 500;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .output-text {
      font-size: 9.5px; color: var(--v-fg-muted); line-height: 1.4;
      margin-top: 3px; padding-left: 16px;
    }
    .tool-pills { display: flex; gap: 3px; margin-top: 3px; padding-left: 16px; flex-wrap: wrap; }
  `];

  @property({ type: Array }) rounds: RoundRecord[] = [];
  @state() private _expanded: number | null = null;
  @state() private _showRounds = false;

  render() {
    if (this.rounds.length === 0) return html`<div class="empty-hint" style="padding:16px;text-align:center;font-size:11px;color:var(--v-fg-dim)">Waiting for first round to complete\u2026</div>`;

    return html`
      <div class="rounds-toggle" @click=${() => { this._showRounds = !this._showRounds; }}>
        <span>${this._showRounds ? '\u25BC' : '\u25B6'}</span>
        <span>Round History (${this.rounds.length} round${this.rounds.length !== 1 ? 's' : ''})</span>
      </div>
      ${this._showRounds ? html`
        <div class="glass" style="padding:12px">
          ${(this.rounds as RoundRecordExt[]).map((r, ri) => {
            const pc = phaseColor[r.phase] ?? '#E8581A';
            const isExp = this._expanded === ri;
            return html`
              <div class="round" style="border-left:2px solid ${pc};${ri < this.rounds.length - 1 ? 'margin-bottom:10px' : ''}">
                <div class="round-header" @click=${() => { this._expanded = isExp ? null : ri; }}>
                  <span class="round-num" style="color:${pc}">R${r.roundNumber}</span>
                  <span class="phase-label">${r.phase}</span>
                  ${r.convergence != null ? html`<span class="meta" style="color:var(--v-fg-muted)">conv ${(r.convergence * 100).toFixed(0)}%</span>` : nothing}
                  ${r.cost != null ? html`<span class="meta" style="color:var(--v-accent)">$${r.cost.toFixed(2)}</span>` : nothing}
                  ${r.duration ? html`<span class="meta" style="color:var(--v-fg-dim)">${(r.duration / 1000).toFixed(1)}s</span>` : nothing}
                  <span class="chevron">${isExp ? '\u25B2' : '\u25BC'}</span>
                </div>
                ${isExp ? this._renderExpanded(r) : this._renderCollapsed(r)}
              </div>`;
          })}
        </div>` : nothing}`;
  }

  private _renderCollapsed(r: RoundRecordExt) {
    return html`${(r.agents as RoundAgentExt[]).map(a => html`
      <div class="agent-row-compact">
        <fc-dot .status=${a.status} .size=${4}></fc-dot>
        <span class="agent-name">${a.name}</span>
        <span class="agent-model">
          <span class="provider-dot" style="background:${providerColor(a.model)}"></span>
          ${a.model}
        </span>
        ${a.tokens > 0 ? html`<span class="agent-tokens">${(a.tokens / 1000).toFixed(1)}k</span>` : nothing}
      </div>
    `)}`;
  }

  private _renderExpanded(r: RoundRecordExt) {
    return html`${(r.agents as RoundAgentExt[]).map(a => html`
      <div class="agent-expanded">
        <div class="agent-exp-row">
          <fc-dot .status=${a.status} .size=${4}></fc-dot>
          <span class="agent-exp-name">${a.name}</span>
          <span class="agent-model">
            <span class="provider-dot" style="background:${providerColor(a.model)}"></span>
            ${a.model}
          </span>
          ${a.tokens > 0 ? html`<span class="agent-tokens">${(a.tokens / 1000).toFixed(1)}k</span>` : nothing}
        </div>
        ${a.output ? html`<div class="output-text">${a.output}</div>` : nothing}
        ${(a.tools?.length ?? 0) > 0 ? html`
          <div class="tool-pills">
            ${a.tools!.map(t => html`<fc-pill color="var(--v-purple)" sm>${t}</fc-pill>`)}
          </div>` : nothing}
      </div>
    `)}`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-round-history': FcRoundHistory; }
}
