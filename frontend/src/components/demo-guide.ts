import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { store } from '../state/store.js';
import { allColonies } from '../helpers.js';
import type { TreeNode } from '../types.js';

/**
 * Compact, persistent annotation bar that guides the operator through the
 * demo flow. Appears below the proactive briefing during a demo workspace.
 *
 * Advances automatically from real AG-UI / app state changes:
 *  Step 0: Welcome — workspace just created, proactive briefing should show contradiction
 *  Step 1: Observe — look at the proactive briefing's contradiction insight
 *  Step 2: Task — suggest a task to the Queen
 *  Step 3: Planning — Queen generates a DelegationPlan (ParallelPlanCreated)
 *  Step 4: Execution — colonies are running, watch the DAG animate
 *  Step 5: Knowledge — colonies completed, knowledge extracted
 *  Step 6: Maintenance — maintenance colony spawned to resolve contradiction
 *  Step 7: Complete — demo flow finished
 */

interface DemoStep {
  label: string;
  hint: string;
}

const DEMO_STEPS: DemoStep[] = [
  { label: 'Welcome', hint: 'Your demo workspace is ready. The proactive briefing above should show a contradiction between two authentication entries.' },
  { label: 'Observe', hint: 'Read the proactive insight. The system detected conflicting knowledge before you did anything.' },
  { label: 'Give a Task', hint: 'Ask the Queen to "Build me an email validator with unit tests" (or any task). Watch how she plans.' },
  { label: 'Queen Planning', hint: 'The Queen is decomposing your task into a parallel execution plan. Watch the DAG appear.' },
  { label: 'Colonies Running', hint: 'Colonies are executing in parallel. Watch status dots pulse blue, cost accumulate, and groups complete.' },
  { label: 'Knowledge Extracted', hint: 'Colonies completed and extracted knowledge entries. Confidence posteriors are being established.' },
  { label: 'Self-Maintenance', hint: 'A maintenance colony was spawned to investigate the contradiction. The system is maintaining itself.' },
  { label: 'Demo Complete', hint: 'FormicOS planned, executed, extracted knowledge, and resolved a contradiction — all autonomously. Dismiss this guide to continue exploring.' },
];

@customElement('fc-demo-guide')
export class FcDemoGuide extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .guide-bar {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 12px; border-radius: 6px; margin-bottom: 12px;
      background: rgba(163,130,250,0.06);
      border: 1px solid rgba(163,130,250,0.2);
    }
    .guide-step {
      font-size: 9px; font-family: var(--f-mono); font-weight: 700;
      color: var(--v-purple); text-transform: uppercase; letter-spacing: 0.05em;
      white-space: nowrap; flex-shrink: 0;
    }
    .guide-hint {
      font-size: 10.5px; font-family: var(--f-body); color: var(--v-fg-muted);
      line-height: 1.4; flex: 1; min-width: 0;
    }
    .guide-progress {
      display: flex; gap: 3px; flex-shrink: 0;
    }
    .guide-pip {
      width: 6px; height: 6px; border-radius: 50%;
      background: rgba(163,130,250,0.15); transition: background 0.3s;
    }
    .guide-pip.done { background: var(--v-purple); }
    .guide-pip.current { background: var(--v-purple); animation: pip-pulse 1.5s infinite; }
    @keyframes pip-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .guide-dismiss {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
      cursor: pointer; padding: 2px 6px; border-radius: 4px;
      border: 1px solid var(--v-border); background: none;
      transition: border-color 0.15s;
      flex-shrink: 0;
    }
    .guide-dismiss:hover { border-color: var(--v-border-hover); color: var(--v-fg-muted); }
    .trigger-btn {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-purple);
      cursor: pointer; padding: 2px 8px; border-radius: 4px;
      border: 1px solid rgba(163,130,250,0.3); background: rgba(163,130,250,0.06);
      transition: background 0.15s;
      flex-shrink: 0;
    }
    .trigger-btn:hover { background: rgba(163,130,250,0.12); }
  `];

  @property({ type: String }) workspaceId = '';
  @property({ type: Array }) tree: TreeNode[] = [];
  @state() private _step = 0;
  @state() private _dismissed = false;
  @state() private _active = false;
  @state() private _maintenanceTriggered = false;

  private _unsub?: () => void;
  private _prevState = { hasPlans: false, hasRunning: false, hasCompleted: false, hasMaintenance: false };

  connectedCallback() {
    super.connectedCallback();
    this._unsub = store.subscribe(() => this._evaluateStep());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._unsub?.();
  }

  /** Start the demo guide for a given workspace. */
  start(workspaceId: string) {
    this._active = true;
    this._dismissed = false;
    this._step = 0;
    this._maintenanceTriggered = false;
    this.workspaceId = workspaceId;
    this._evaluateStep();
  }

  /** Evaluate current app state to determine which demo step we're on. */
  private _evaluateStep() {
    if (!this._active || this._dismissed) return;

    const threads = store.state.queenThreads.filter(qt => qt.workspaceId === this.workspaceId);
    const cols = allColonies(this.tree).filter(c => {
      // Filter to colonies in this workspace's threads
      const wsNode = this.tree.find(n => n.id === this.workspaceId);
      if (!wsNode) return false;
      const threadIds = new Set((wsNode.children ?? []).map(t => t.id));
      return threadIds.has(c.parentId ?? '');
    });

    const hasPlans = threads.some(qt => qt.parallel_groups && qt.parallel_groups.length > 0);
    const hasRunning = cols.some(c => c.status === 'running');
    const hasCompleted = cols.some(c => c.status === 'completed');
    const hasMaintenance = cols.some(c =>
      (c.task ?? '').toLowerCase().includes('maintenance') ||
      (c.task ?? '').toLowerCase().includes('contradiction'),
    );

    // Advance step based on observed state
    let newStep = this._step;
    if (newStep < 1 && threads.length === 0) {
      newStep = 1; // Observation step — briefing visible
    }
    if (newStep < 3 && hasPlans) {
      newStep = 3; // Queen planned
    }
    if (newStep < 4 && hasRunning) {
      newStep = 4; // Colonies running
    }
    if (newStep < 5 && hasCompleted && !hasRunning) {
      newStep = 5; // Knowledge extracted
    }
    if (newStep < 6 && hasMaintenance) {
      newStep = 6; // Maintenance running
    }
    if (newStep === 6 && hasMaintenance && !hasRunning) {
      newStep = 7; // Demo complete
    }

    if (newStep !== this._step) {
      this._step = newStep;
    }

    this._prevState = { hasPlans, hasRunning, hasCompleted, hasMaintenance };
  }

  private async _triggerMaintenance() {
    if (this._maintenanceTriggered || !this.workspaceId) return;
    this._maintenanceTriggered = true;
    try {
      await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/briefing`);
    } catch { /* briefing fetch is best-effort to nudge the maintenance loop */ }
  }

  render() {
    if (!this._active || this._dismissed) return nothing;

    const step = DEMO_STEPS[this._step] ?? DEMO_STEPS[0];
    const showMaintenanceTrigger = this._step === 5 && !this._maintenanceTriggered;

    return html`
      <div class="guide-bar">
        <span class="guide-step">Step ${this._step + 1}: ${step.label}</span>
        <span class="guide-hint">${step.hint}</span>
        <div class="guide-progress">
          ${DEMO_STEPS.map((_, i) => html`
            <span class="guide-pip ${i < this._step ? 'done' : i === this._step ? 'current' : ''}"></span>
          `)}
        </div>
        ${showMaintenanceTrigger ? html`
          <button class="trigger-btn" @click=${() => this._triggerMaintenance()}>Trigger Maintenance</button>
        ` : nothing}
        <button class="guide-dismiss" @click=${() => { this._dismissed = true; }}>Dismiss</button>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-demo-guide': FcDemoGuide;
  }
}
