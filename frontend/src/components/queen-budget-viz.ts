import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface BudgetSlot {
  name: string;
  fraction: number;
  fallback_tokens: number;
  allocated: number;
  consumed: number;
  utilization: number;
}

interface BudgetData {
  queen_model: string;
  queen_model_type: string;
  context_window: number;
  num_slots: number;
  effective_context: number;
  output_reserve: number;
  available: number;
  slots: BudgetSlot[];
  total_consumed: number;
  total_utilization: number;
}

const SLOT_COLORS: Record<string, string> = {
  system_prompt: '#8b5cf6',
  memory_retrieval: '#22c55e',
  project_context: '#3b82f6',
  project_plan: '#6366f1',
  operating_procedures: '#f59e0b',
  queen_journal: '#ef4444',
  thread_context: '#06b6d4',
  tool_memory: '#ec4899',
  conversation_history: '#E8581A',
  working_memory: '#14b8a6',
};

function displayName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function fmtNum(n: number): string {
  return n.toLocaleString();
}

@customElement('fc-queen-budget-viz')
export class FcQueenBudgetViz extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .headline {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      padding: 4px 0; line-height: 1.6;
    }
    .headline strong { color: var(--v-fg); }
    .slot-row {
      display: flex; align-items: center; gap: 6px; margin-bottom: 4px;
      font-size: 10px; font-family: var(--f-mono);
    }
    .slot-label { width: 140px; color: var(--v-fg-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .slot-bar-track {
      flex: 1; height: 10px; border-radius: 5px; background: rgba(255,255,255,0.06);
      overflow: hidden; position: relative;
    }
    .slot-bar-alloc {
      position: absolute; top: 0; left: 0; height: 100%; border-radius: 5px;
      opacity: 0.25;
    }
    .slot-bar-fill {
      position: absolute; top: 0; left: 0; height: 100%; border-radius: 5px;
      transition: width 0.3s;
    }
    .slot-nums {
      width: 110px; text-align: right; color: var(--v-fg-dim); font-size: 9px;
      white-space: nowrap;
    }
    .slot-pct { width: 38px; text-align: right; color: var(--v-fg); font-size: 9px; }
    .warn { color: #ef4444; }
    .summary {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); cursor: pointer;
      padding: 6px 8px; user-select: none;
    }
    .summary:hover { color: var(--v-fg-muted); }
  `];

  @property() workspaceId = '';
  @state() private _data: BudgetData | null = null;
  @state() private _expanded = false;
  @state() private _loaded = false;
  private _timer: ReturnType<typeof setInterval> | null = null;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  }

  private async _fetch() {
    try {
      const qs = this.workspaceId ? `?workspace_id=${encodeURIComponent(this.workspaceId)}` : '';
      const resp = await fetch(`/api/v1/queen-budget${qs}`);
      if (resp.ok) {
        this._data = await resp.json() as BudgetData;
        this._loaded = true;
      }
    } catch { /* silent */ }
  }

  private _toggleExpand() {
    this._expanded = !this._expanded;
    if (this._expanded && !this._timer) {
      this._timer = setInterval(() => { void this._fetch(); }, 30000);
    } else if (!this._expanded && this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  render() {
    if (!this._loaded || !this._data) return nothing;
    const d = this._data;

    const modelShort = d.queen_model.split('/').pop() ?? d.queen_model;
    const isLocal = d.queen_model_type === 'local';
    const pctUsed = d.available > 0 ? (d.total_consumed / d.available * 100) : 0;

    const headlineCtx = isLocal && d.num_slots > 1
      ? html`Per-slot: <strong>${fmtNum(d.effective_context)}</strong>`
      : html`Context: <strong>${fmtNum(d.context_window)}</strong>`;

    const modelTag = isLocal
      ? `${modelShort} (local${d.num_slots > 1 ? `, ${d.num_slots} slots` : ''})`
      : `${modelShort} (cloud)`;

    return html`
      <div class="s-label">Context Budget</div>
      <div class="glass summary" @click=${this._toggleExpand}>
        ${this._expanded ? '\u25BE' : '\u25B8'}
        Queen: <strong>${modelTag}</strong> | ${headlineCtx} | Available: <strong>${fmtNum(d.available)}</strong>
        ${d.total_consumed > 0
          ? html`<br>Used: <strong>${fmtNum(d.total_consumed)}</strong> / ${fmtNum(d.available)} (${pctUsed.toFixed(1)}%)`
          : nothing}
      </div>
      ${this._expanded ? html`
        <div class="glass" style="padding:10px;margin-top:4px">
          ${d.slots.map(slot => {
            const pct = slot.allocated > 0 ? Math.min(100, slot.consumed / slot.allocated * 100) : 0;
            const allocPct = d.available > 0 ? Math.min(100, slot.allocated / d.available * 100) : 0;
            const color = SLOT_COLORS[slot.name] ?? 'var(--v-fg-dim)';
            const isWarn = slot.utilization > 0.9;
            return html`
              <div class="slot-row">
                <span class="slot-label" title=${displayName(slot.name)}>${displayName(slot.name)}</span>
                <div class="slot-bar-track">
                  <div class="slot-bar-alloc" style="width:${allocPct}%;background:${color}"></div>
                  <div class="slot-bar-fill" style="width:${allocPct * pct / 100}%;background:${isWarn ? '#ef4444' : color}"></div>
                </div>
                <span class="slot-nums">${fmtNum(slot.consumed)} / ${fmtNum(slot.allocated)}</span>
                <span class="slot-pct ${isWarn ? 'warn' : ''}">${pct.toFixed(0)}%</span>
              </div>
            `;
          })}
        </div>
      ` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-budget-viz': FcQueenBudgetViz; }
}
