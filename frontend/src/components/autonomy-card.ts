/**
 * Wave 70.5 Track 3: Autonomy trust card for settings page.
 * Fetches from GET /api/v1/workspaces/{id}/autonomy-status and renders
 * trust score, daily budget, and recent autonomous actions.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { AutonomyStatusData } from '../types.js';
import './atoms.js';

@customElement('fc-autonomy-card')
export class FcAutonomyCard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }

    .grade {
      display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; border-radius: 6px;
      font-family: var(--f-display); font-weight: 700; font-size: 14px;
      margin-right: 10px;
    }
    .grade-a { background: rgba(45,212,168,0.12); color: var(--v-success); }
    .grade-b { background: rgba(91,156,245,0.12); color: var(--v-blue); }
    .grade-c { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .grade-d { background: rgba(245,113,49,0.12); color: var(--v-danger); }
    .grade-f { background: rgba(232,72,72,0.12); color: var(--v-danger); }

    .header-row {
      display: flex; align-items: center; margin-bottom: 10px;
    }
    .score-text {
      font-family: var(--f-mono); font-size: 11px; color: var(--v-fg-muted);
    }
    .level-pill {
      font-family: var(--f-mono); font-size: 9px; font-weight: 600;
      padding: 2px 7px; border-radius: 5px; margin-left: 8px;
      background: rgba(255,255,255,0.05); color: var(--v-fg-dim);
      border: 1px solid var(--v-border);
    }

    .budget-bar {
      display: flex; align-items: center; gap: 10px;
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
      margin-bottom: 10px;
    }
    .bar-track {
      flex: 1; height: 4px; border-radius: 2px;
      background: rgba(255,255,255,0.06);
    }
    .bar-fill {
      height: 100%; border-radius: 2px;
      transition: width 0.3s;
    }
    .bar-fill-ok { background: var(--v-success); }
    .bar-fill-warn { background: var(--v-warn); }
    .bar-fill-danger { background: var(--v-danger); }

    .components {
      display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px;
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
      margin-bottom: 10px;
    }
    .comp-label { color: var(--v-fg-dim); }

    .rec-text {
      font-family: var(--f-mono); font-size: 10px; color: var(--v-fg-muted);
      padding: 6px 8px; border-radius: 6px;
      background: rgba(167,139,250,0.04);
      border: 1px solid rgba(167,139,250,0.12);
      margin-bottom: 10px;
    }

    .actions-table {
      width: 100%; border-collapse: collapse;
      font-family: var(--f-mono); font-size: 10px;
    }
    .actions-table th {
      text-align: left; font-weight: 600; color: var(--v-fg-dim);
      border-bottom: 1px solid var(--v-border); padding: 4px 6px;
      font-size: 9px; letter-spacing: 0.04em;
    }
    .actions-table td {
      color: var(--v-fg-muted); padding: 3px 6px;
      border-bottom: 1px solid rgba(255,255,255,0.02);
    }
    .outcome-ok { color: var(--v-success); }
    .outcome-fail { color: var(--v-danger); }

    .empty-text {
      font-family: var(--f-mono); font-size: 10.5px; color: var(--v-fg-dim);
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; }
    }
  `];

  @property({ type: String }) workspaceId = '';
  @state() private _data: AutonomyStatusData | null = null;
  @state() private _error = '';

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/autonomy-status`,
      );
      if (!resp.ok) {
        this._error = `HTTP ${resp.status}`;
        return;
      }
      this._data = await resp.json() as AutonomyStatusData;
      this._error = '';
    } catch {
      this._error = 'Failed to fetch autonomy status';
    }
  }

  private _gradeClass(grade: string): string {
    const g = grade.toLowerCase();
    if (g === 'a') return 'grade-a';
    if (g === 'b') return 'grade-b';
    if (g === 'c') return 'grade-c';
    if (g === 'd') return 'grade-d';
    return 'grade-f';
  }

  render() {
    if (this._error) {
      return html`<div class="empty-text">${this._error}</div>`;
    }
    const d = this._data;
    if (!d) return html`<div class="empty-text">Loading autonomy status\u2026</div>`;

    const budgetPct = d.daily_budget > 0
      ? Math.min(100, (d.daily_spend / d.daily_budget) * 100)
      : 0;
    const barClass = budgetPct >= 90
      ? 'bar-fill-danger'
      : budgetPct >= 70 ? 'bar-fill-warn' : 'bar-fill-ok';

    const recent = (d.recent_actions ?? []).slice(0, 5);

    return html`
      <div class="header-row">
        <span class="grade ${this._gradeClass(d.grade)}">${d.grade}</span>
        <span class="score-text">
          ${d.score}/100
        </span>
        <span class="level-pill">${d.level}</span>
      </div>

      <div class="budget-bar">
        <span>$${d.daily_spend.toFixed(2)} / $${d.daily_budget.toFixed(2)}</span>
        <div class="bar-track">
          <div class="bar-fill ${barClass}"
            style="width:${budgetPct.toFixed(1)}%"></div>
        </div>
        <span>$${d.remaining.toFixed(2)} left</span>
      </div>

      <div class="components">
        ${Object.entries(d.components).map(([k, v]) => html`
          <span class="comp-label">${k.replace(/_/g, ' ')}</span>
          <span>${(v as number).toFixed(2)}</span>
        `)}
      </div>

      ${d.recommendation ? html`
        <div class="rec-text">${d.recommendation}</div>
      ` : nothing}

      ${recent.length > 0 ? html`
        <table class="actions-table">
          <tr>
            <th>Colony</th><th>Strategy</th><th>Cost</th><th>Outcome</th>
          </tr>
          ${recent.map(a => html`
            <tr>
              <td>${a.colony_id.slice(0, 8)}</td>
              <td>${a.strategy}</td>
              <td>$${a.cost.toFixed(3)}</td>
              <td class="${a.outcome === 'completed' ? 'outcome-ok' : 'outcome-fail'}">
                ${a.outcome}
              </td>
            </tr>
          `)}
        </table>
      ` : html`
        <div class="empty-text">No recent autonomous actions.</div>
      `}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-autonomy-card': FcAutonomyCard; }
}
