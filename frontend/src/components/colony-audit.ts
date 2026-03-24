/**
 * Wave 39 1A: Colony reasoning audit view.
 *
 * Compact structured audit surface grounded in replay-safe projection state.
 * Shows knowledge used, directives received, governance actions, escalations,
 * validator state, and completion classification — without requiring raw
 * transcript reading.
 *
 * All data is fetched from GET /api/v1/colonies/{id}/audit which returns
 * only replay-safe truth. Runtime-only internals are not presented as
 * exact historical fact.
 */

import { LitElement, html, css, nothing } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import './atoms.js';

interface AuditKnowledgeItem {
  id: string;
  title: string;
  source_system: string;
  canonical_type: string;
  confidence: number | null;
  round: number | null;
  access_mode: string;
  source_url?: string;
  source_domain?: string;
  source_credibility?: number;
}

interface AuditDirective {
  sender: string;
  content: string;
  timestamp: string;
  event_kind: string;
}

interface AuditGovernanceAction {
  content: string;
  timestamp: string;
}

interface AuditEscalation {
  tier: string;
  reason: string;
  set_at_round: number;
}

interface AuditValidator {
  task_type: string;
  verdict: string;
  reason: string;
}

interface AuditData {
  colony_id: string;
  task: string;
  status: string;
  completion_state: string;
  knowledge_used: AuditKnowledgeItem[];
  directives: AuditDirective[];
  governance_actions: AuditGovernanceAction[];
  escalation: AuditEscalation | null;
  redirects: Record<string, unknown>[];
  validator: AuditValidator | null;
  round_count: number;
  max_rounds: number;
  quality_score: number;
  cost: number;
  entries_extracted: number;
  replay_safe_note: string;
}

@customElement('fc-colony-audit')
export class FcColonyAudit extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .audit-section { margin-bottom: 14px; }
    .s-label {
      font-size: 9.5px; font-family: var(--f-mono); color: var(--v-fg-dim);
      letter-spacing: 0.12em; text-transform: uppercase; font-weight: 600;
      margin-bottom: 6px;
    }
    .completion-badge {
      display: inline-flex; align-items: center; gap: 5px;
      font-family: var(--f-mono); font-size: 11px; font-weight: 600;
      padding: 3px 8px; border-radius: 4px;
    }
    .completion-badge.validated { color: var(--v-success); background: rgba(52,211,153,0.08); }
    .completion-badge.unvalidated { color: var(--v-warn); background: rgba(251,191,36,0.08); }
    .completion-badge.stalled { color: var(--v-danger); background: rgba(248,113,113,0.08); }
    .completion-badge.running { color: var(--v-accent); background: rgba(96,165,250,0.08); }
    .knowledge-list, .directive-list, .gov-list { list-style: none; padding: 0; margin: 0; }
    .knowledge-list li, .directive-list li, .gov-list li {
      font-size: 11.5px; font-family: var(--f-mono); padding: 4px 0;
      border-bottom: 1px solid rgba(255,255,255,0.03);
      color: var(--v-fg-muted); line-height: 1.4;
    }
    .knowledge-list li:last-child, .directive-list li:last-child, .gov-list li:last-child {
      border-bottom: none;
    }
    .ki-title { color: var(--v-fg); font-weight: 600; cursor: pointer; }
    .ki-title:hover { color: var(--v-accent); text-decoration: underline; }
    .ki-meta { font-size: 10px; color: var(--v-fg-dim); }
    .ki-source-link {
      font-size: 9px; color: var(--v-secondary); cursor: pointer;
      text-decoration: none; word-break: break-all;
    }
    .ki-source-link:hover { text-decoration: underline; }
    .ki-forager-badge {
      display: inline-flex; align-items: center; gap: 2px;
      font-size: 8px; padding: 0 5px; border-radius: 4px;
      background: rgba(61,214,245,0.08); color: var(--v-secondary);
      font-family: var(--f-mono); letter-spacing: 0.05em;
    }
    .escalation-card {
      font-size: 11.5px; font-family: var(--f-mono); padding: 8px 10px;
      border: 1px solid var(--v-border); border-radius: 6px;
      background: rgba(255,255,255,0.015);
    }
    .esc-tier { font-weight: 700; color: var(--v-accent); }
    .esc-reason { color: var(--v-fg-muted); }
    .validator-card {
      font-size: 11.5px; font-family: var(--f-mono); padding: 8px 10px;
      border: 1px solid var(--v-border); border-radius: 6px;
      background: rgba(255,255,255,0.015);
      display: flex; gap: 10px; align-items: center;
    }
    .verdict-pass { color: var(--v-success); font-weight: 700; }
    .verdict-fail { color: var(--v-danger); font-weight: 700; }
    .verdict-inconclusive { color: var(--v-warn); font-weight: 700; }
    .empty-msg { font-size: 11px; color: var(--v-fg-dim); font-style: italic; }
    .replay-note {
      font-size: 10px; color: var(--v-fg-dim); font-style: italic;
      margin-top: 12px; padding: 6px 8px; border-left: 2px solid var(--v-border);
    }
  `];

  @property({ type: String }) colonyId = '';
  @state() private _audit: AuditData | null = null;
  @state() private _loading = false;

  override connectedCallback() {
    super.connectedCallback();
    if (this.colonyId) this._fetchAudit();
  }

  override willUpdate(changed: Map<string, unknown>) {
    if (changed.has('colonyId') && this.colonyId) {
      this._fetchAudit();
    }
  }

  private async _fetchAudit() {
    if (!this.colonyId) return;
    this._loading = true;
    try {
      const res = await fetch(`/api/v1/colonies/${this.colonyId}/audit`);
      if (res.ok) {
        this._audit = await res.json();
      }
    } catch { /* swallow */ }
    this._loading = false;
  }

  private _completionBadge(state: string) {
    const labels: Record<string, string> = {
      validated: 'Done (validated)',
      unvalidated: 'Done (unvalidated)',
      stalled: 'Stalled',
      running: 'Running',
      pending: 'Pending',
    };
    return html`<span class="completion-badge ${state}">${labels[state] ?? state}</span>`;
  }

  private _verdictClass(verdict: string) {
    if (verdict === 'pass') return 'verdict-pass';
    if (verdict === 'fail') return 'verdict-fail';
    return 'verdict-inconclusive';
  }

  private _navigateKnowledge(entryId: string) {
    this.dispatchEvent(new CustomEvent('navigate-knowledge', {
      detail: { entryId },
      bubbles: true, composed: true,
    }));
  }

  override render() {
    if (this._loading) return html`<div class="empty-msg">Loading audit…</div>`;
    const a = this._audit;
    if (!a) return html`<div class="empty-msg">No audit data available</div>`;

    return html`
      <!-- Completion State -->
      <div class="audit-section">
        <div class="s-label">Completion</div>
        ${this._completionBadge(a.completion_state)}
      </div>

      <!-- Validator -->
      ${a.validator ? html`
        <div class="audit-section">
          <div class="s-label">Validator</div>
          <div class="validator-card">
            <span class="${this._verdictClass(a.validator.verdict)}">
              ${a.validator.verdict.toUpperCase()}
            </span>
            <span>${a.validator.task_type}</span>
            <span style="color:var(--v-fg-dim)">— ${a.validator.reason}</span>
          </div>
        </div>
      ` : nothing}

      <!-- Knowledge Used -->
      <div class="audit-section">
        <div class="s-label">Knowledge Used (${a.knowledge_used.length})</div>
        ${a.knowledge_used.length === 0
          ? html`<div class="empty-msg">No knowledge accessed</div>`
          : html`
            <ul class="knowledge-list">
              ${a.knowledge_used.slice(0, 10).map(k => html`
                <li>
                  <span class="ki-title" @click=${() => this._navigateKnowledge(k.id)}>${k.title || k.id}</span>
                  ${k.source_system === 'web' || k.source_url ? html`
                    <span class="ki-forager-badge">\u25C8 forager</span>
                  ` : nothing}
                  <div class="ki-meta">
                    ${k.canonical_type} \u00B7 ${k.source_system}
                    ${k.confidence != null ? html` \u00B7 conf ${(k.confidence * 100).toFixed(0)}%` : nothing}
                    ${k.round != null ? html` \u00B7 round ${k.round}` : nothing}
                    ${k.source_domain ? html` \u00B7 ${k.source_domain}` : nothing}
                    ${k.source_credibility != null ? html` \u00B7 cred ${(k.source_credibility * 100).toFixed(0)}%` : nothing}
                  </div>
                  ${k.source_url ? html`
                    <a class="ki-source-link" href="${k.source_url}" target="_blank" rel="noopener">${k.source_url}</a>
                  ` : nothing}
                </li>
              `)}
              ${a.knowledge_used.length > 10
                ? html`<li class="empty-msg">…and ${a.knowledge_used.length - 10} more</li>`
                : nothing}
            </ul>
          `}
      </div>

      <!-- Directives -->
      ${a.directives.length > 0 ? html`
        <div class="audit-section">
          <div class="s-label">Directives (${a.directives.length})</div>
          <ul class="directive-list">
            ${a.directives.map(d => html`
              <li>${d.sender}: ${d.content}</li>
            `)}
          </ul>
        </div>
      ` : nothing}

      <!-- Governance Actions -->
      ${a.governance_actions.length > 0 ? html`
        <div class="audit-section">
          <div class="s-label">Governance Actions (${a.governance_actions.length})</div>
          <ul class="gov-list">
            ${a.governance_actions.map(g => html`
              <li>${g.content}</li>
            `)}
          </ul>
        </div>
      ` : nothing}

      <!-- Escalation -->
      ${a.escalation ? html`
        <div class="audit-section">
          <div class="s-label">Escalation</div>
          <div class="escalation-card">
            Tier: <span class="esc-tier">${a.escalation.tier}</span>
            at round ${a.escalation.set_at_round}
            <span class="esc-reason">— ${a.escalation.reason}</span>
          </div>
        </div>
      ` : nothing}

      <!-- Redirects -->
      ${a.redirects.length > 0 ? html`
        <div class="audit-section">
          <div class="s-label">Redirects (${a.redirects.length})</div>
          <ul class="gov-list">
            ${a.redirects.map((r: any) => html`
              <li>Round ${r.round ?? '?'}: ${r.reason ?? r.new_goal ?? 'redirected'}</li>
            `)}
          </ul>
        </div>
      ` : nothing}

      <!-- Replay-safe note -->
      <div class="replay-note">${a.replay_safe_note}</div>
    `;
  }
}
