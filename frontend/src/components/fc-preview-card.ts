/**
 * Wave 49 Track A / Wave 50 Track A: Inline preview card for Queen chat.
 *
 * Renders structured preview metadata from a Queen thread message as a
 * compact card with Confirm / Cancel actions. Falls back gracefully when
 * metadata is absent (the chat message text is still shown by queen-chat).
 *
 * Wave 50: When Team 1's template metadata is present on the preview,
 * shows "Based on previous success: [name]" with success/failure stats.
 * Template annotation is a suggestion indicator, not an override.
 *
 * Does NOT parse LLM prose — requires structured `PreviewCardMeta` payload.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { PreviewCardMeta } from '../types.js';
import './atoms.js';

/** Wave 50: Template provenance metadata attached to preview by Team 1's Queen. */
interface TemplateAnnotation {
  templateName: string;
  templateId?: string;
  learned?: boolean;
  successCount?: number;
  failureCount?: number;
  useCount?: number;
  taskCategory?: string;
}

const TIER_COST_HINT: Record<string, string> = {
  flash: '~$0.01', light: '~$0.02', standard: '~$0.10', heavy: '~$0.30',
};

@customElement('fc-preview-card')
export class FcPreviewCard extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; }
    .card {
      border: 1px solid rgba(232,88,26,0.18);
      border-radius: 10px;
      background: rgba(232,88,26,0.03);
      padding: 12px 14px;
      font-family: var(--f-mono);
      font-size: 11.5px;
      color: var(--v-fg);
    }
    .card-header {
      display: flex; align-items: center; gap: 6px;
      margin-bottom: 8px;
    }
    .card-icon { font-size: 10px; color: var(--v-accent); }
    .card-title {
      font-family: var(--f-display); font-size: 12px; font-weight: 700;
      color: var(--v-accent); letter-spacing: -0.02em;
    }
    .fast-path-badge {
      font-size: 8px; padding: 1px 6px; border-radius: 4px;
      background: rgba(45,212,168,0.1); color: var(--v-success);
      font-weight: 600; letter-spacing: 0.05em;
    }
    .task-text {
      font-size: 12px; font-family: var(--f-body); color: var(--v-fg);
      line-height: 1.45; margin-bottom: 8px;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
    }
    .meta-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;
      margin-bottom: 8px;
    }
    .meta-item {
      display: flex; align-items: center; gap: 4px;
      font-size: 10px; color: var(--v-fg-muted);
    }
    .meta-label { color: var(--v-fg-dim); }
    .meta-value { color: var(--v-fg); font-weight: 600; }
    .team-row {
      display: flex; gap: 6px; flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .team-slot {
      display: inline-flex; align-items: center; gap: 3px;
      font-size: 9.5px; padding: 2px 7px; border-radius: 5px;
      border: 1px solid var(--v-border);
      background: rgba(255,255,255,0.02);
    }
    .team-caste { font-weight: 600; color: var(--v-fg); text-transform: capitalize; }
    .team-tier { color: var(--v-fg-dim); }
    .files-list {
      font-size: 10px; color: var(--v-fg-muted);
      margin-bottom: 8px; line-height: 1.5;
    }
    .files-label { color: var(--v-fg-dim); font-weight: 600; }
    .actions {
      display: flex; gap: 8px; margin-top: 10px;
    }
    /* Wave 50: template annotation */
    .template-hint {
      display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
      font-size: 10px; color: var(--v-fg-muted); margin-bottom: 8px;
      padding: 6px 8px; border-radius: 6px;
      background: rgba(167,139,250,0.04); border: 1px solid rgba(167,139,250,0.12);
    }
    .template-name { font-weight: 600; color: var(--v-fg); }
    .template-badge {
      font-size: 7.5px; padding: 1px 5px; border-radius: 3px;
      font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
    }
    .template-badge.learned {
      background: rgba(167,139,250,0.12); color: #A78BFA;
    }
    .template-badge.operator {
      background: rgba(245,183,49,0.12); color: var(--v-warn);
    }
    .template-stats {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .template-stats .win { color: var(--v-success); }
    .template-stats .lose { color: var(--v-danger); }
  `];

  @property({ type: Object }) preview: PreviewCardMeta | null = null;
  @property({ type: Boolean }) confirmed = false;
  @property({ type: Boolean }) cancelled = false;

  /** Extract template annotation from preview meta if Team 1 has populated it. */
  private get _template(): TemplateAnnotation | null {
    const p = this.preview;
    if (!p) return null;
    const meta = (p as Record<string, unknown>).template as Record<string, unknown> | undefined;
    if (!meta || !meta.templateName) return null;
    return {
      templateName: meta.templateName as string,
      templateId: (meta.templateId as string) ?? undefined,
      learned: (meta.learned as boolean) ?? false,
      successCount: (meta.successCount as number) ?? undefined,
      failureCount: (meta.failureCount as number) ?? undefined,
      useCount: (meta.useCount as number) ?? undefined,
      taskCategory: (meta.taskCategory as string) ?? undefined,
    };
  }

  render() {
    const p = this.preview;
    if (!p) return nothing;

    const tpl = this._template;

    return html`
      <div class="card">
        <div class="card-header">
          <span class="card-icon">\u25B6</span>
          <span class="card-title">Colony Preview</span>
          ${p.fastPath ? html`<span class="fast-path-badge">FAST PATH</span>` : nothing}
        </div>

        ${tpl ? html`
          <div class="template-hint">
            <span>Based on previous success:</span>
            <span class="template-name">${tpl.templateName}</span>
            <span class="template-badge ${tpl.learned ? 'learned' : 'operator'}">
              ${tpl.learned ? 'learned' : 'operator'}
            </span>
            ${tpl.successCount != null || tpl.failureCount != null ? html`
              <span class="template-stats">
                <span class="win">${tpl.successCount ?? 0}W</span>
                /
                <span class="lose">${tpl.failureCount ?? 0}L</span>
                ${tpl.useCount != null ? html` (${tpl.useCount} uses)` : nothing}
              </span>
            ` : nothing}
            ${tpl.taskCategory ? html`
              <fc-pill color="var(--v-fg-dim)" sm>${tpl.taskCategory}</fc-pill>
            ` : nothing}
          </div>
        ` : nothing}

        <div class="task-text">${p.task}</div>

        <div class="team-row">
          ${p.team.map(s => html`
            <span class="team-slot">
              <span class="team-caste">${s.caste}</span>
              <span class="team-tier">\u00D7${s.count} ${s.tier}</span>
              <span style="color:var(--v-fg-dim);font-size:8px">${TIER_COST_HINT[s.tier] ?? ''}</span>
            </span>
          `)}
        </div>

        <div class="meta-grid">
          <div class="meta-item">
            <span class="meta-label">Strategy</span>
            <span class="meta-value">${p.strategy}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Max rounds</span>
            <span class="meta-value">${p.maxRounds}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Budget</span>
            <span class="meta-value">$${p.budgetLimit.toFixed(2)}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Est. cost</span>
            <span class="meta-value" style="color:var(--v-accent)">$${p.estimatedCost.toFixed(2)}</span>
          </div>
        </div>

        ${p.targetFiles && p.targetFiles.length > 0 ? html`
          <div class="files-list">
            <span class="files-label">Target files:</span>
            ${p.targetFiles.slice(0, 5).join(', ')}
            ${p.targetFiles.length > 5 ? html` +${p.targetFiles.length - 5} more` : nothing}
          </div>
        ` : nothing}

        ${p.groups && p.groups.length > 1 ? html`
          <div class="files-list" style="margin-top:4px">
            <span class="files-label">${p.totalPlannedTasks ?? p.groups.flat().length} tasks in ${p.groups.length} groups:</span>
            ${p.groups.map((g, i) => html`
              <span style="font-size:10px;color:var(--v-fg-dim)">G${i + 1}(${g.tasks.length})</span>
            `)}
          </div>
        ` : nothing}

        ${this.confirmed ? html`
          <div style="font-size:10px;color:var(--v-success);font-weight:600;margin-top:6px">\u2713 Confirmed — colony dispatched</div>
        ` : this.cancelled ? html`
          <div style="font-size:10px;color:var(--v-fg-dim);margin-top:6px">\u2717 Cancelled</div>
        ` : html`
          <div class="actions">
            <fc-btn variant="primary" sm @click=${this._confirm}>Confirm</fc-btn>
            <fc-btn variant="ghost" sm @click=${this._cancel}>Cancel</fc-btn>
            <fc-btn variant="ghost" sm @click=${this._openEditor}>Open Full Editor</fc-btn>
          </div>
        `}
      </div>
    `;
  }

  private _confirm() {
    this.dispatchEvent(new CustomEvent('preview-confirm', {
      detail: this.preview,
      bubbles: true, composed: true,
    }));
  }

  private _cancel() {
    this.dispatchEvent(new CustomEvent('preview-cancel', {
      bubbles: true, composed: true,
    }));
  }

  private _openEditor() {
    this.dispatchEvent(new CustomEvent('preview-open-editor', {
      detail: this.preview,
      bubbles: true, composed: true,
    }));
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-preview-card': FcPreviewCard; }
}
