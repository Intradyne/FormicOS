/**
 * Wave 70.5 Track 2: Project Plan overview card.
 *
 * Renders the workspace-level project plan from GET /api/v1/project-plan.
 * No frontend markdown parsing — uses structured JSON only.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface ProjectMilestone {
  index: number;
  status: string;
  description: string;
  thread_id?: string;
  completed_at?: string;
  note?: string;
}

interface ProjectPlanData {
  exists: boolean;
  goal?: string;
  updated?: string;
  milestones?: ProjectMilestone[];
}

@customElement('fc-project-plan-card')
export class FcProjectPlanCard extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .plan-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 10px;
    }
    .plan-title {
      font-family: var(--f-display); font-size: 11px; font-weight: 600;
      color: var(--v-fg); text-transform: uppercase; letter-spacing: 0.06em;
    }
    .plan-updated {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .plan-goal {
      font-size: 12px; font-family: var(--f-body); color: var(--v-fg);
      margin-bottom: 10px; line-height: 1.4;
    }
    .milestone-list { display: flex; flex-direction: column; gap: 6px; }
    .milestone {
      display: flex; align-items: flex-start; gap: 8px;
      padding: 6px 8px; border-radius: 6px;
      background: rgba(255,255,255,0.015);
      border: 1px solid transparent;
      transition: border-color 0.15s;
    }
    .milestone:hover { border-color: var(--v-border); }
    .milestone-check {
      flex-shrink: 0; width: 16px; height: 16px; margin-top: 1px;
      display: flex; align-items: center; justify-content: center;
      font-size: 11px;
    }
    .milestone-check.completed { color: var(--v-success, #2DD4A8); }
    .milestone-check.pending { color: var(--v-fg-dim); }
    .milestone-check.active { color: var(--v-accent); }
    .milestone-body { flex: 1; min-width: 0; }
    .milestone-desc {
      font-size: 11px; font-family: var(--f-body); color: var(--v-fg);
      word-break: break-word; line-height: 1.35;
    }
    .milestone-meta {
      display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 3px;
    }
    .status-chip {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600;
      padding: 1px 5px; border-radius: 4px; text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .chip-completed {
      background: rgba(45,212,168,0.1); color: var(--v-success);
      border: 1px solid rgba(45,212,168,0.2);
    }
    .chip-pending {
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim);
      border: 1px solid var(--v-border);
    }
    .chip-active {
      background: rgba(167,139,250,0.1); color: #A78BFA;
      border: 1px solid rgba(167,139,250,0.2);
    }
    .thread-link {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-accent);
      cursor: pointer; text-decoration: none;
    }
    .thread-link:hover { text-decoration: underline; }
    .completed-at {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .milestone-note {
      font-size: 10px; font-family: var(--f-body); color: var(--v-fg-muted);
      margin-top: 2px; font-style: italic;
    }
    .progress-bar {
      height: 3px; background: rgba(255,255,255,0.04); border-radius: 2px;
      overflow: hidden; margin-bottom: 10px;
    }
    .progress-fill {
      height: 100%; border-radius: 2px; background: var(--v-accent);
      transition: width 0.3s ease;
    }
    .progress-label {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      text-align: right; margin-bottom: 4px;
    }
  `];

  @property() workspaceId = '';

  @state() private _plan: ProjectPlanData | null = null;
  @state() private _error = false;

  override connectedCallback() {
    super.connectedCallback();
    this._fetchPlan();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('workspaceId') && this.workspaceId) {
      this._fetchPlan();
    }
  }

  private async _fetchPlan() {
    try {
      const resp = await fetch('/api/v1/project-plan');
      if (!resp.ok) { this._error = true; return; }
      this._plan = await resp.json() as ProjectPlanData;
      this._error = false;
    } catch {
      this._error = true;
    }
  }

  private _statusIcon(status: string): string {
    if (status === 'completed') return '\u2713';
    if (status === 'active') return '\u25B6';
    return '\u25CB';
  }

  private _chipClass(status: string): string {
    if (status === 'completed') return 'chip-completed';
    if (status === 'active') return 'chip-active';
    return 'chip-pending';
  }

  private _formatDate(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    } catch {
      return iso;
    }
  }

  private _onThreadClick(threadId: string) {
    this.dispatchEvent(new CustomEvent('navigate', {
      detail: threadId,
      bubbles: true, composed: true,
    }));
  }

  private _cleanDescription(desc: string): string {
    // Strip inline metadata: (thread ...) and [completed_at ...]
    return desc
      .replace(/\(thread\s+\S+\)/g, '')
      .replace(/\[completed_at\s+[^\]]+\]/g, '')
      .trim();
  }

  render() {
    // Hide entirely when no plan exists or on error
    if (this._error || !this._plan?.exists) return nothing;

    const milestones = this._plan.milestones ?? [];
    const completed = milestones.filter(m => m.status === 'completed').length;
    const total = milestones.length;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

    return html`
      <div class="glass">
        <div class="plan-header">
          <span class="plan-title">\u25E8 Project Plan</span>
          ${this._plan.updated ? html`
            <span class="plan-updated">${this._formatDate(this._plan.updated)}</span>
          ` : nothing}
        </div>

        ${this._plan.goal ? html`
          <div class="plan-goal">${this._plan.goal}</div>
        ` : nothing}

        ${total > 0 ? html`
          <div class="progress-label">${completed}/${total} milestones (${pct}%)</div>
          <div class="progress-bar">
            <span class="progress-fill" style="width:${pct}%"></span>
          </div>
        ` : nothing}

        ${milestones.length > 0 ? html`
          <div class="milestone-list">
            ${milestones.map(ms => html`
              <div class="milestone">
                <div class="milestone-check ${ms.status}">
                  ${this._statusIcon(ms.status)}
                </div>
                <div class="milestone-body">
                  <div class="milestone-desc">${this._cleanDescription(ms.description)}</div>
                  <div class="milestone-meta">
                    <span class="status-chip ${this._chipClass(ms.status)}">${ms.status}</span>
                    ${ms.thread_id ? html`
                      <span class="thread-link"
                        @click=${() => this._onThreadClick(ms.thread_id!)}
                      >\u2192 ${ms.thread_id.slice(0, 12)}</span>
                    ` : nothing}
                    ${ms.completed_at ? html`
                      <span class="completed-at">${this._formatDate(ms.completed_at)}</span>
                    ` : nothing}
                  </div>
                  ${ms.note ? html`
                    <div class="milestone-note">${ms.note}</div>
                  ` : nothing}
                </div>
              </div>
            `)}
          </div>
        ` : nothing}
      </div>
    `;
  }
}
