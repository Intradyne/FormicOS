/**
 * Wave 69 Track 7: Source-grouped search results from unified search endpoint.
 *
 * Renders results grouped by source with distinct card styling per source type.
 */
import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import type { UnifiedSearchResult } from '../types.js';
import './atoms.js';

@customElement('fc-knowledge-search-results')
export class FcKnowledgeSearchResults extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; }
    .source-group { margin-bottom: 16px; }
    .source-header {
      font-family: var(--f-display); font-size: 11px; font-weight: 600;
      color: var(--v-fg-muted); text-transform: uppercase; letter-spacing: 0.08em;
      margin-bottom: 8px; padding-left: 2px;
    }
    .result-list { display: flex; flex-direction: column; gap: 6px; }
    .result-card { padding: 10px 12px; cursor: pointer; transition: border-color 0.15s; }
    .result-card:hover { border-color: rgba(232,88,26,0.25); }
    .result-title {
      font-family: var(--f-display); font-size: 12px; font-weight: 600;
      color: var(--v-fg); margin-bottom: 4px; word-break: break-word;
    }
    .result-snippet {
      font-size: 11px; color: var(--v-fg-muted); line-height: 1.45;
      max-height: 48px; overflow: hidden; word-break: break-word;
    }
    .result-snippet.code-snippet {
      font-family: var(--f-mono); font-size: 10.5px; white-space: pre-wrap;
      background: rgba(255,255,255,0.02); padding: 4px 6px; border-radius: 4px;
      border: 1px solid var(--v-border);
    }
    .result-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 6px; }
    .conf-indicator { display: flex; align-items: center; gap: 4px; }
    .conf-label {
      font-size: 9px; font-family: var(--f-mono); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    .conf-high { color: var(--v-success, #2DD4A8); }
    .conf-medium { color: var(--v-warn, #F5B731); }
    .conf-low { color: var(--v-danger, #F06464); }
    .domain-tag {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border);
    }
    .status-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .status-verified { background: rgba(45,212,168,0.1); color: var(--v-success); border: 1px solid rgba(45,212,168,0.2); }
    .status-candidate { background: rgba(245,183,49,0.1); color: var(--v-warn); border: 1px solid rgba(245,183,49,0.2); }
    .status-active { background: rgba(167,139,250,0.1); color: #A78BFA; border: 1px solid rgba(167,139,250,0.2); }
    .file-path {
      font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim);
    }
    .line-range {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-accent);
    }
    .score-bar {
      width: 40px; height: 3px; background: rgba(255,255,255,0.04);
      border-radius: 2px; overflow: hidden; display: inline-block; vertical-align: middle;
    }
    .score-fill { height: 100%; border-radius: 2px; background: var(--v-accent); }
    .empty-state {
      padding: 24px; text-align: center; color: var(--v-fg-muted);
      font-size: 12px; font-family: var(--f-body);
    }
  `];

  @property({ type: Array }) results: UnifiedSearchResult[] = [];
  @property() activeWorkspaceId = '';

  private _groupResults(): Map<string, UnifiedSearchResult[]> {
    const groups = new Map<string, UnifiedSearchResult[]>();
    for (const r of this.results) {
      const existing = groups.get(r.source) ?? [];
      existing.push(r);
      groups.set(r.source, existing);
    }
    return groups;
  }

  private _confLevel(conf: number): 'high' | 'medium' | 'low' {
    if (conf >= 0.7) return 'high';
    if (conf >= 0.4) return 'medium';
    return 'low';
  }

  private _confLabel(conf: number): string {
    if (conf >= 0.7) return 'High';
    if (conf >= 0.4) return 'Medium';
    return 'Low';
  }

  private _isCodeSource(source: string): boolean {
    return source === 'codebase-index' || source.includes('code');
  }

  private _onEntryClick(result: UnifiedSearchResult) {
    if (result.source === 'memory') {
      this.dispatchEvent(new CustomEvent('entry-selected', {
        detail: { id: result.id },
        bubbles: true, composed: true,
      }));
    } else {
      const filePath = (result.metadata?.file_path as string) || result.title;
      this.dispatchEvent(new CustomEvent('file-selected', {
        detail: { filePath, source: result.source },
        bubbles: true, composed: true,
      }));
    }
  }

  private _renderMemoryResult(r: UnifiedSearchResult) {
    const conf = (r.metadata?.confidence as number) ?? 0.5;
    const level = this._confLevel(conf);
    const domains = (r.metadata?.domains as string[]) ?? [];
    const status = (r.metadata?.status as string) ?? '';
    return html`
      <div class="glass result-card" @click=${() => this._onEntryClick(r)}>
        <div class="result-title">${r.title || r.id.slice(0, 24)}</div>
        ${r.snippet ? html`<div class="result-snippet">${r.snippet}</div>` : nothing}
        <div class="result-meta">
          <div class="conf-indicator">
            <fc-dot status=${level === 'high' ? 'loaded' : level === 'medium' ? 'pending' : 'error'}></fc-dot>
            <span class="conf-label conf-${level}">${this._confLabel(conf)}</span>
          </div>
          ${status ? html`<span class="status-badge status-${status}">${status}</span>` : nothing}
          ${domains.slice(0, 3).map(d => html`<span class="domain-tag">${d}</span>`)}
        </div>
      </div>
    `;
  }

  private _renderAddonResult(r: UnifiedSearchResult) {
    const filePath = (r.metadata?.file_path as string) || r.title;
    const lineRange = (r.metadata?.line_range as string) || '';
    const isCode = this._isCodeSource(r.source);
    return html`
      <div class="glass result-card" @click=${() => this._onEntryClick(r)}>
        <div class="result-title">
          <span class="file-path">${filePath}</span>
          ${lineRange ? html`<span class="line-range">:${lineRange}</span>` : nothing}
        </div>
        ${r.snippet ? html`
          <div class="result-snippet ${isCode ? 'code-snippet' : ''}">${r.snippet}</div>
        ` : nothing}
        <div class="result-meta">
          ${r.score > 0 ? html`
            <span class="score-bar"><span class="score-fill" style="width:${Math.min(r.score * 100, 100)}%"></span></span>
            <span style="font-size:9px;font-family:var(--f-mono);color:var(--v-fg-dim)">${r.score.toFixed(3)}</span>
          ` : nothing}
        </div>
      </div>
    `;
  }

  render() {
    if (this.results.length === 0) {
      return html`<div class="empty-state">No results found. Try a different query.</div>`;
    }
    const groups = this._groupResults();
    return html`
      ${Array.from(groups.entries()).map(([source, items]) => {
        const label = items[0]?.source_label || source;
        return html`
          <div class="source-group">
            <div class="source-header">From ${label}</div>
            <div class="result-list">
              ${items.map(r => source === 'memory'
                ? this._renderMemoryResult(r)
                : this._renderAddonResult(r)
              )}
            </div>
          </div>
        `;
      })}
    `;
  }
}
