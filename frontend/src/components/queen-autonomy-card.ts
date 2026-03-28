import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface AutonomyComponents {
  success_rate: number;
  volume: number;
  cost_efficiency: number;
  operator_trust: number;
}

interface AutonomyData {
  score: number;
  grade: string;
  level: string;
  components: AutonomyComponents;
  recommendation: string;
  daily_budget: number;
  daily_spend: number;
  auto_actions: string[];
}

const GRADE_COLORS: Record<string, string> = {
  a: 'var(--v-green, #22c55e)',
  b: 'var(--v-green, #22c55e)',
  c: 'var(--v-warning, #f59e0b)',
  d: 'var(--v-danger, #ef4444)',
  f: 'var(--v-danger, #ef4444)',
};

const COMPONENT_LABELS: [keyof AutonomyComponents, string, string][] = [
  ['success_rate', 'Success Rate', '40%'],
  ['volume', 'Volume', '20%'],
  ['cost_efficiency', 'Cost Eff.', '20%'],
  ['operator_trust', 'Trust', '20%'],
];

@customElement('fc-queen-autonomy-card')
export class FcQueenAutonomyCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .grade-badge {
      display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; border-radius: 6px; font-family: var(--f-display);
      font-size: 16px; font-weight: 700; color: var(--v-void);
    }
    .bar-track {
      flex: 1; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.06);
      overflow: hidden;
    }
    .bar-fill {
      height: 100%; border-radius: 3px; transition: width 0.3s;
    }
    .comp-row {
      display: flex; align-items: center; gap: 6px; margin-bottom: 5px;
      font-size: 10px; font-family: var(--f-mono);
    }
    .comp-label { width: 80px; color: var(--v-fg-dim); }
    .comp-value { width: 32px; text-align: right; color: var(--v-fg); }
    .comp-weight { width: 24px; text-align: right; color: var(--v-fg-dim); font-size: 8px; }
    .recommendation {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      line-height: 1.4; margin-top: 8px; padding: 6px 8px;
      border-left: 2px solid var(--v-border); background: rgba(255,255,255,0.02);
    }
    .budget-bar {
      height: 4px; border-radius: 2px; background: rgba(255,255,255,0.06);
      margin-top: 6px; overflow: hidden;
    }
    .budget-fill { height: 100%; border-radius: 2px; background: var(--v-accent); }
  `];

  @property() workspaceId = '';
  @state() private _data: AutonomyData | null = null;
  @state() private _expanded = false;
  private _timer: ReturnType<typeof setInterval> | null = null;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
    this._timer = setInterval(() => void this._fetch(), 60_000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._timer) clearInterval(this._timer);
  }

  updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      void this._fetch();
    }
  }

  private async _fetch() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(`/api/v1/workspaces/${this.workspaceId}/autonomy-status`);
      if (resp.ok) {
        this._data = await resp.json() as AutonomyData;
      }
    } catch { /* silent */ }
  }

  render() {
    if (!this._data) return html`<div class="s-label">Queen Health</div><div style="font-size:10px;color:var(--v-fg-dim);font-family:var(--f-mono)">Loading...</div>`;

    const d = this._data;
    const gradeColor = GRADE_COLORS[d.grade.toLowerCase()] ?? 'var(--v-fg-dim)';
    const budgetPct = d.daily_budget > 0 ? Math.min(100, (d.daily_spend / d.daily_budget) * 100) : 0;

    return html`
      <div class="s-label">Queen Health</div>
      <div class="glass" style="padding:12px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:${this._expanded ? '10' : '0'}px">
          <span class="grade-badge" style="background:${gradeColor}">${d.grade}</span>
          <span style="font-family:var(--f-mono);font-size:12px;color:var(--v-fg)">${d.score}/100</span>
          <fc-pill color="var(--v-fg-dim)" sm>${d.level}</fc-pill>
          <span style="margin-left:auto;font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">$${d.daily_spend.toFixed(2)} / $${d.daily_budget.toFixed(2)}</span>
        </div>
        ${this._expanded ? this._renderBreakdown() : nothing}
        <div style="text-align:center;margin-top:6px">
          <fc-btn variant="ghost" sm @click=${() => { this._expanded = !this._expanded; }}>
            ${this._expanded ? 'Less' : 'Details'}
          </fc-btn>
        </div>
      </div>
    `;
  }

  private _renderBreakdown() {
    const d = this._data!;
    const budgetPct = d.daily_budget > 0 ? Math.min(100, (d.daily_spend / d.daily_budget) * 100) : 0;

    return html`
      <div style="margin-bottom:8px">
        ${COMPONENT_LABELS.map(([key, label, weight]) => {
          const val = d.components[key];
          return html`
            <div class="comp-row">
              <span class="comp-label">${label}</span>
              <div class="bar-track">
                <div class="bar-fill" style="width:${Math.round(val * 100)}%;background:${GRADE_COLORS[d.grade.toLowerCase()] ?? 'var(--v-accent)'}"></div>
              </div>
              <span class="comp-value">${val.toFixed(2)}</span>
              <span class="comp-weight">(${weight})</span>
            </div>`;
        })}
      </div>
      <div class="budget-bar">
        <div class="budget-fill" style="width:${budgetPct}%"></div>
      </div>
      <div style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim);margin-top:2px;text-align:right">
        daily budget: $${d.daily_spend.toFixed(2)} / $${d.daily_budget.toFixed(2)}
      </div>
      ${d.recommendation ? html`
        <div class="recommendation">${d.recommendation}</div>
      ` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-autonomy-card': FcQueenAutonomyCard; }
}
