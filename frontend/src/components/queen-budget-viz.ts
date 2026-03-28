import { LitElement, html, css, nothing } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface BudgetSlot {
  name: string;
  fraction: number;
  fallback_tokens: number;
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
};

function displayName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

@customElement('fc-queen-budget-viz')
export class FcQueenBudgetViz extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .slot-row {
      display: flex; align-items: center; gap: 6px; margin-bottom: 4px;
      font-size: 10px; font-family: var(--f-mono);
    }
    .slot-label { width: 140px; color: var(--v-fg-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .slot-bar-track {
      flex: 1; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.06);
      overflow: hidden;
    }
    .slot-bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
    .slot-pct { width: 30px; text-align: right; color: var(--v-fg); }
    .slot-tokens { width: 55px; text-align: right; color: var(--v-fg-dim); font-size: 9px; }
    .summary {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); cursor: pointer;
      padding: 6px 8px; user-select: none;
    }
    .summary:hover { color: var(--v-fg-muted); }
  `];

  @state() private _slots: BudgetSlot[] = [];
  @state() private _expanded = false;
  @state() private _loaded = false;

  connectedCallback() {
    super.connectedCallback();
    void this._fetch();
  }

  private async _fetch() {
    try {
      const resp = await fetch('/api/v1/queen-budget');
      if (resp.ok) {
        const data = await resp.json() as { slots: BudgetSlot[] };
        this._slots = data.slots;
        this._loaded = true;
      }
    } catch { /* silent */ }
  }

  render() {
    if (!this._loaded) return nothing;

    const largest = this._slots.reduce((a, b) => b.fraction > a.fraction ? b : a, this._slots[0]);

    return html`
      <div class="s-label">Context Budget</div>
      <div class="glass summary" @click=${() => { this._expanded = !this._expanded; }}>
        ${this._expanded ? '\u25BE' : '\u25B8'} ${this._slots.length} slots, largest = ${displayName(largest?.name ?? '')} ${Math.round((largest?.fraction ?? 0) * 100)}%
      </div>
      ${this._expanded ? html`
        <div class="glass" style="padding:10px;margin-top:4px">
          ${this._slots.map(slot => html`
            <div class="slot-row">
              <span class="slot-label" title=${displayName(slot.name)}>${displayName(slot.name)}</span>
              <div class="slot-bar-track">
                <div class="slot-bar-fill" style="width:${slot.fraction * 100}%;background:${SLOT_COLORS[slot.name] ?? 'var(--v-fg-dim)'}"></div>
              </div>
              <span class="slot-pct">${Math.round(slot.fraction * 100)}%</span>
              <span class="slot-tokens">${slot.fallback_tokens} min</span>
            </div>
          `)}
        </div>
      ` : nothing}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-queen-budget-viz': FcQueenBudgetViz; }
}
