/**
 * Wave 48: Thread-scoped timeline component.
 *
 * Chronological audit surface grounded in store truth. Reconstructs the thread
 * story from colonies, queen messages, workflow steps, and knowledge events
 * already available in the store tree and QueenThread data.
 *
 * Cross-surface links: rows navigate to colony detail and knowledge browser.
 */

import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { colonyName, timeAgo, formatCost } from '../helpers.js';
import type { TreeNode, Colony, QueenThread } from '../types.js';
import './atoms.js';

// ---------------------------------------------------------------------------
// Timeline entry model — derived from store truth, not a separate event stream
// ---------------------------------------------------------------------------

type TimelineKind =
  | 'colony_spawn'
  | 'colony_complete'
  | 'colony_failed'
  | 'colony_killed'
  | 'queen_message'
  | 'operator_message'
  | 'workflow_step'
  | 'plan_created'
  | 'knowledge';

interface TimelineEntry {
  id: string;
  kind: TimelineKind;
  ts: string;
  label: string;
  detail?: string;
  /** Colony id for navigation links. */
  colonyId?: string;
  /** Knowledge entry id for navigation links. */
  knowledgeId?: string;
  /** Extra metadata for display. */
  meta?: Record<string, unknown>;
}

// Kind metadata for display
const KIND_META: Record<TimelineKind, { icon: string; color: string; label: string }> = {
  colony_spawn:    { icon: '\u2B22', color: 'var(--v-accent)',    label: 'Spawn' },
  colony_complete: { icon: '\u2713', color: 'var(--v-success)',   label: 'Complete' },
  colony_failed:   { icon: '\u2717', color: 'var(--v-danger)',    label: 'Failed' },
  colony_killed:   { icon: '\u25A0', color: 'var(--v-fg-dim)',    label: 'Killed' },
  queen_message:   { icon: '\u265B', color: 'var(--v-warn)',      label: 'Queen' },
  operator_message:{ icon: '\u2709', color: 'var(--v-fg-muted)',  label: 'Operator' },
  workflow_step:   { icon: '\u25B6', color: 'var(--v-blue)',      label: 'Step' },
  plan_created:    { icon: '\u29C9', color: 'var(--v-secondary)', label: 'Plan' },
  knowledge:       { icon: '\u25C8', color: 'var(--v-success)',   label: 'Knowledge' },
};

const FILTER_GROUPS: { id: string; label: string; kinds: TimelineKind[] }[] = [
  { id: 'all',       label: 'All',        kinds: [] },
  { id: 'colonies',  label: 'Colonies',   kinds: ['colony_spawn', 'colony_complete', 'colony_failed', 'colony_killed'] },
  { id: 'queen',     label: 'Queen',      kinds: ['queen_message', 'operator_message'] },
  { id: 'workflow',  label: 'Workflow',   kinds: ['workflow_step', 'plan_created'] },
  { id: 'knowledge', label: 'Knowledge', kinds: ['knowledge'] },
];

@customElement('fc-thread-timeline')
export class FcThreadTimeline extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .tl-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .tl-title {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.12em; text-transform: uppercase; font-weight: 600;
    }
    .tl-count { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); }
    .filter-pills { display: flex; gap: 3px; margin-left: auto; }
    .filter-pill {
      padding: 1px 7px; border-radius: 999px; font-size: 8.5px;
      font-family: var(--f-mono); cursor: pointer; border: 1px solid var(--v-border);
      background: transparent; color: var(--v-fg-dim); transition: all 0.15s;
    }
    .filter-pill.active { color: var(--v-accent); border-color: var(--v-accent); background: rgba(232,88,26,0.05); }

    .tl-list { display: flex; flex-direction: column; gap: 0; position: relative; }
    .tl-line {
      position: absolute; left: 11px; top: 0; bottom: 0; width: 1px;
      background: var(--v-border);
    }

    .tl-row {
      display: flex; align-items: flex-start; gap: 10px; padding: 6px 0 6px 0;
      position: relative; z-index: 1;
    }
    .tl-dot {
      width: 22px; height: 22px; border-radius: 50%; display: flex;
      align-items: center; justify-content: center; font-size: 10px;
      flex-shrink: 0; border: 1px solid var(--v-border);
      background: var(--v-void);
    }
    .tl-body { flex: 1; min-width: 0; }
    .tl-label {
      font-size: 11.5px; font-family: var(--f-mono); color: var(--v-fg);
      line-height: 1.4;
    }
    .tl-detail {
      font-size: 10px; color: var(--v-fg-muted); line-height: 1.4;
      margin-top: 2px; max-height: 0; overflow: hidden; transition: max-height 0.2s;
    }
    .tl-row.expanded .tl-detail { max-height: 200px; }
    .tl-meta {
      display: flex; gap: 6px; align-items: center; margin-top: 2px;
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .tl-time { font-feature-settings: 'tnum'; }
    .tl-kind-badge {
      padding: 0 5px; border-radius: 4px; font-size: 8px;
      text-transform: uppercase; letter-spacing: 0.05em;
    }
    .tl-link {
      color: var(--v-accent); cursor: pointer; text-decoration: none;
      font-size: 9px;
    }
    .tl-link:hover { text-decoration: underline; }
    .tl-expand {
      cursor: pointer; font-size: 9px; color: var(--v-fg-dim);
      margin-left: auto; user-select: none;
    }
    .tl-expand:hover { color: var(--v-fg); }
    .empty-msg { font-size: 11px; color: var(--v-fg-dim); font-style: italic; padding: 12px 0; }
  `];

  @property({ type: Object }) thread: TreeNode | null = null;
  @property({ type: Object }) threadData: QueenThread | null = null;
  @state() private _filter = 'all';
  @state() private _expandedIds = new Set<string>();

  render() {
    if (!this.thread) return nothing;
    const entries = this._buildEntries();
    const filtered = this._filter === 'all'
      ? entries
      : entries.filter(e => {
          const group = FILTER_GROUPS.find(g => g.id === this._filter);
          return group ? group.kinds.includes(e.kind) : true;
        });

    return html`
      <div class="tl-header">
        <span class="tl-title">Timeline</span>
        <span class="tl-count">${filtered.length} events</span>
        <div class="filter-pills">
          ${FILTER_GROUPS.map(g => html`
            <span class="filter-pill ${this._filter === g.id ? 'active' : ''}"
              @click=${() => { this._filter = g.id; }}>${g.label}</span>
          `)}
        </div>
      </div>
      ${filtered.length === 0
        ? html`<div class="empty-msg">No timeline events yet</div>`
        : html`
          <div class="tl-list">
            <div class="tl-line"></div>
            ${filtered.map(e => this._renderEntry(e))}
          </div>
        `}
    `;
  }

  private _renderEntry(entry: TimelineEntry) {
    const km = KIND_META[entry.kind];
    const expanded = this._expandedIds.has(entry.id);

    return html`
      <div class="tl-row ${expanded ? 'expanded' : ''}">
        <div class="tl-dot" style="color:${km.color};border-color:${km.color}40">
          ${km.icon}
        </div>
        <div class="tl-body">
          <div class="tl-label">${entry.label}</div>
          ${entry.detail ? html`<div class="tl-detail">${entry.detail}</div>` : nothing}
          <div class="tl-meta">
            <span class="tl-kind-badge" style="background:${km.color}12;color:${km.color}">${km.label}</span>
            ${entry.ts ? html`<span class="tl-time">${timeAgo(entry.ts)}</span>` : nothing}
            ${entry.colonyId ? html`
              <span class="tl-link" @click=${(ev: Event) => {
                ev.stopPropagation();
                this._navigateTo(entry.colonyId!);
              }}>${(entry.meta?.['displayName'] as string) || entry.colonyId.slice(0, 8)} \u2192</span>
            ` : nothing}
            ${entry.knowledgeId ? html`
              <span class="tl-link" @click=${(ev: Event) => {
                ev.stopPropagation();
                this._navigateKnowledge(entry.knowledgeId!);
              }}>view entry \u2192</span>
            ` : nothing}
            ${entry.detail ? html`
              <span class="tl-expand" @click=${() => this._toggleExpand(entry.id)}>
                ${expanded ? '\u25B2 less' : '\u25BC more'}
              </span>
            ` : nothing}
          </div>
        </div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Build timeline entries from thread store data
  // ---------------------------------------------------------------------------

  private _buildEntries(): TimelineEntry[] {
    const entries: TimelineEntry[] = [];
    const colonies = (this.thread?.children ?? []) as Colony[];
    const td = this.threadData;

    // Colony lifecycle entries
    for (const c of colonies) {
      const displayLabel = colonyName(c);
      // Spawn
      entries.push({
        id: `spawn-${c.id}`,
        kind: 'colony_spawn',
        ts: (c as any).spawnedAt ?? '',
        label: `Colony spawned: ${displayLabel}`,
        detail: c.task ? `Task: ${c.task.slice(0, 200)}` : undefined,
        colonyId: c.id,
        meta: { displayName: c.displayName },
      });
      // Terminal state
      if (c.status === 'completed') {
        entries.push({
          id: `complete-${c.id}`,
          kind: 'colony_complete',
          ts: (c as any).completedAt ?? '',
          label: `Colony completed: ${displayLabel}`,
          detail: c.qualityScore > 0 ? `Quality: ${(c.qualityScore * 100).toFixed(0)}% \u00B7 Cost: ${formatCost(c.cost)}` : undefined,
          colonyId: c.id,
          meta: { displayName: c.displayName },
        });
      } else if (c.status === 'failed') {
        entries.push({
          id: `failed-${c.id}`,
          kind: 'colony_failed',
          ts: (c as any).completedAt ?? '',
          label: `Colony failed: ${displayLabel}`,
          colonyId: c.id,
          meta: { displayName: c.displayName },
        });
      } else if (c.status === 'killed') {
        entries.push({
          id: `killed-${c.id}`,
          kind: 'colony_killed',
          ts: (c as any).completedAt ?? '',
          label: `Colony killed: ${displayLabel}`,
          colonyId: c.id,
          meta: { displayName: c.displayName },
        });
      }
    }

    // Queen / operator messages
    if (td?.messages) {
      for (let i = 0; i < td.messages.length; i++) {
        const m = td.messages[i];
        if (m.role === 'queen') {
          entries.push({
            id: `qm-${i}`,
            kind: 'queen_message',
            ts: m.ts,
            label: m.text.slice(0, 120) + (m.text.length > 120 ? '\u2026' : ''),
            detail: m.text.length > 120 ? m.text : undefined,
          });
        } else if (m.role === 'operator') {
          entries.push({
            id: `om-${i}`,
            kind: 'operator_message',
            ts: m.ts,
            label: m.text.slice(0, 120) + (m.text.length > 120 ? '\u2026' : ''),
            detail: m.text.length > 120 ? m.text : undefined,
          });
        }
      }
    }

    // Workflow steps
    if (td?.workflow_steps) {
      for (const step of td.workflow_steps) {
        entries.push({
          id: `step-${step.step_index}`,
          kind: 'workflow_step',
          ts: '',
          label: `Step ${step.step_index + 1}: ${step.description}`,
          detail: `Status: ${step.status}${step.colony_id ? ` \u00B7 Colony: ${step.colony_id.slice(0, 8)}` : ''}`,
          colonyId: step.colony_id || undefined,
        });
      }
    }

    // Parallel plan
    if (td?.active_plan && td?.parallel_groups) {
      entries.push({
        id: 'plan-created',
        kind: 'plan_created',
        ts: '',
        label: `Delegation plan: ${td.active_plan.tasks.length} tasks in ${td.parallel_groups.length} groups`,
        detail: td.plan_reasoning ? `Reasoning: ${td.plan_reasoning.slice(0, 200)}` : undefined,
        meta: { estimatedCost: td.plan_estimated_cost },
      });
    }

    // Sort by timestamp (entries without ts go to end)
    entries.sort((a, b) => {
      if (!a.ts && !b.ts) return 0;
      if (!a.ts) return 1;
      if (!b.ts) return -1;
      return new Date(a.ts).getTime() - new Date(b.ts).getTime();
    });

    return entries;
  }

  private _toggleExpand(id: string) {
    const next = new Set(this._expandedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    this._expandedIds = next;
  }

  private _navigateTo(id: string) {
    this.dispatchEvent(new CustomEvent('navigate', { detail: id, bubbles: true, composed: true }));
  }

  private _navigateKnowledge(entryId: string) {
    this.dispatchEvent(new CustomEvent('navigate-knowledge', {
      detail: { entryId },
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-thread-timeline': FcThreadTimeline; }
}
