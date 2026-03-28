import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';
import { timeAgo } from '../helpers.js';
import type { KnowledgeItemDetail, KnowledgeItemPreview, ContradictionPair, TrustRationale, KnowledgeProvenance, ForagerProvenance, ProvenanceChainItem, UnifiedSearchResult, UnifiedSearchResponse } from '../types.js';
import './atoms.js';
import './addon-panel.js';
import './knowledge-view.js';
import './knowledge-search-results.js';
import './knowledge-health-card.js';

interface AddonPanel { target: string; display_type: string; path: string; addon_name: string; }

type SubView = 'catalog' | 'graph' | 'tree';

interface TreeBranch {
  path: string;
  label: string;
  entryCount: number;
  confidence: { alpha: number; beta: number; mean: number };
  children: TreeBranch[];
}
type FilterId = '' | 'skill' | 'experience';
type SortBy = 'newest' | 'confidence' | 'relevance';
type ThreadFilter = 'all' | 'thread' | 'workspace' | 'global';

@customElement('fc-knowledge-browser')
export class FcKnowledgeBrowser extends LitElement {
  static styles = [voidTokens, sharedStyles, css`
    :host { display: block; overflow: auto; height: 100%; max-width: 960px; }
    .title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .title-row h2 { font-family: var(--f-display); font-size: 20px; font-weight: 700; color: var(--v-fg); margin: 0; }
    .sub-tabs { margin-left: auto; display: flex; gap: 4px; }
    .sub-tab {
      font-size: 9.5px; font-family: var(--f-mono); padding: 2px 10px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none; text-transform: capitalize;
    }
    .sub-tab.active { background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.2); color: var(--v-accent); }
    .controls { display: flex; gap: 8px; margin-bottom: 14px; align-items: center; flex-wrap: wrap; }
    .search-input {
      flex: 1; min-width: 180px; max-width: 320px; padding: 6px 10px; border-radius: 8px;
      border: 1px solid var(--v-border); background: var(--v-recessed); color: var(--v-fg);
      font-size: 11px; font-family: var(--f-mono); outline: none;
    }
    .search-input::placeholder { color: var(--v-fg-dim); }
    .search-input:focus { border-color: rgba(232,88,26,0.3); }
    .filter-pill {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .filter-pill.active { background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.2); color: var(--v-accent); }
    .divider { width: 1px; height: 16px; background: var(--v-border); margin: 0 4px; }
    .entry-list { display: flex; flex-direction: column; gap: 6px; }
    .entry-card { padding: 12px; }
    .entry-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
    .entry-title { font-family: var(--f-display); font-size: 13px; font-weight: 600; color: var(--v-fg); }
    .entry-content {
      font-size: 11.5px; color: var(--v-fg-muted); line-height: 1.45; margin-bottom: 6px;
      word-break: break-word; max-height: 80px; overflow: hidden;
    }
    .entry-meta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .entry-row { display: flex; gap: 10px; align-items: flex-start; }
    .entry-left { flex: 1; min-width: 0; }
    .entry-right { width: 80px; flex-shrink: 0; text-align: right; }
    .entry-actions { margin-top: 8px; }
    .detail-toggle {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .detail-toggle:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }
    .conf-big { font-family: var(--f-mono); font-size: 14px; font-weight: 600; font-feature-settings: 'tnum'; }
    .conf-bar { height: 3px; background: rgba(255,255,255,0.04); border-radius: 2px; overflow: hidden; margin-top: 3px; }
    .conf-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }
    .conf-tier {
      font-size: 8px; font-family: var(--f-mono); font-weight: 600; padding: 1px 5px;
      border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px; display: inline-block; margin-top: 2px;
    }
    .tier-HIGH { background: rgba(45,212,168,0.15); color: var(--v-tier-high); }
    .tier-MODERATE { background: rgba(245,183,49,0.15); color: var(--v-tier-moderate); }
    .tier-LOW { background: rgba(245,183,49,0.15); color: var(--v-tier-low); }
    .tier-EXPLORATORY { background: rgba(240,100,100,0.15); color: var(--v-tier-exploratory); }
    .tier-STALE { background: rgba(107,107,118,0.15); color: var(--v-tier-stale); }
    .conf-summary { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 2px; line-height: 1.3; }
    .conf-hover-detail {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 4px;
      padding: 4px 6px; background: rgba(255,255,255,0.02); border-radius: 4px; border: 1px solid var(--v-border);
      display: none; line-height: 1.5;
    }
    .entry-right:hover .conf-hover-detail { display: block; }
    .power-panel {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 6px;
      padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 4px; border: 1px solid var(--v-border);
      line-height: 1.5;
    }
    .power-toggle {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 6px; border-radius: 4px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); margin-top: 4px;
    }
    .power-toggle:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }
    .polarity-pos { color: var(--v-success); }
    .polarity-neg { color: var(--v-danger); }
    .polarity-neu { color: var(--v-fg-dim); }
    .source-legacy { background: rgba(245,183,49,0.1); color: var(--v-warn); border-color: rgba(245,183,49,0.2); }
    .source-inst { background: rgba(45,212,168,0.1); color: var(--v-success); border-color: rgba(45,212,168,0.2); }
    .source-web { background: rgba(91,156,245,0.1); color: var(--v-blue); border-color: rgba(91,156,245,0.2); }
    .type-skill { background: rgba(167,139,250,0.1); color: var(--v-purple); border-color: rgba(167,139,250,0.2); }
    .type-experience { background: rgba(91,156,245,0.1); color: var(--v-blue); border-color: rgba(91,156,245,0.2); }
    .status-verified { background: rgba(45,212,168,0.1); color: var(--v-success); border-color: rgba(45,212,168,0.2); }
    .status-candidate { background: rgba(245,183,49,0.1); color: var(--v-warn); border-color: rgba(245,183,49,0.2); }
    .status-active { background: rgba(167,139,250,0.1); color: var(--v-purple); border-color: rgba(167,139,250,0.2); }
    .status-rejected { background: rgba(240,100,100,0.1); color: var(--v-danger); border-color: rgba(240,100,100,0.2); }
    .status-stale { background: rgba(107,107,118,0.1); color: var(--v-fg-muted); border-color: rgba(107,107,118,0.2); }
    .score-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-top: 4px; cursor: pointer; }
    .score-bar .seg { height: 100%; transition: width 0.3s; }
    .score-bar .seg-semantic { background: #5B9CF5; }
    .score-bar .seg-thompson { background: #A78BFA; }
    .score-bar .seg-freshness { background: #2DD4A8; }
    .score-bar .seg-status { background: #F5B731; }
    .score-bar .seg-thread { background: #67E8F9; }
    .score-bar .seg-cooccurrence { background: #E85D1A; }
    .score-bar .seg-graph_proximity { background: #34D399; }
    .score-detail { font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 2px; line-height: 1.5; }
    .domains-row { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
    .entry-detail {
      margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--v-border);
      font-size: 11.5px; color: var(--v-fg-muted); line-height: 1.5; white-space: pre-wrap;
      word-break: break-word;
    }
    .domain-tag {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      background: rgba(255,255,255,0.04); color: var(--v-fg-dim); border: 1px solid var(--v-border);
    }
    .thread-badge {
      font-size: 8px; font-family: var(--f-mono); padding: 1px 5px; border-radius: 4px;
      background: rgba(91,156,245,0.1); color: var(--v-blue); border: 1px solid rgba(91,156,245,0.2);
    }
    .usage-badge {
      font-size: 7.5px; font-family: var(--f-mono); font-weight: 600; padding: 1px 5px;
      border-radius: 3px; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .usage-hot { background: rgba(232,88,26,0.12); color: var(--v-accent); }
    .usage-warm { background: rgba(245,183,49,0.12); color: var(--v-warn); }
    .usage-cold { background: rgba(107,107,118,0.1); color: var(--v-fg-dim); }
    .promote-btn, .maintenance-btn {
      font-size: 9px; font-family: var(--f-mono); padding: 2px 8px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none;
    }
    .promote-btn:hover { border-color: rgba(45,212,168,0.3); color: var(--v-success); }
    .maintenance-btn:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }
    .empty-state { padding: 24px; text-align: center; color: var(--v-fg-muted); font-size: 12px; }
    .loading { padding: 16px; text-align: center; color: var(--v-fg-dim); font-size: 10px; font-family: var(--f-mono); }
    .graph-container { height: calc(100% - 60px); min-height: 400px; }
    .contradiction-section { margin-bottom: 14px; }
    .contradiction-card {
      padding: 10px 12px; margin-bottom: 6px; border-left: 3px solid var(--v-danger);
    }
    .contradiction-pair { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 6px; }
    .contradiction-entry { flex: 1; font-size: 11px; font-family: var(--f-mono); }
    .contradiction-title { color: var(--v-fg); font-weight: 500; margin-bottom: 2px; }
    .contradiction-meta { font-size: 9px; color: var(--v-fg-dim); }
    .contradiction-actions { display: flex; gap: 6px; }
    .contradiction-vs { font-size: 10px; color: var(--v-danger); font-weight: 700; align-self: center; }
    .health-widget {
      padding: 10px 14px; margin-bottom: 14px; border-radius: 8px;
      background: rgba(255,255,255,0.02); border: 1px solid var(--v-border);
      display: flex; gap: 16px; flex-wrap: wrap; font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-muted);
    }
    .health-stat { display: flex; flex-direction: column; gap: 2px; }
    .health-label { font-size: 8px; color: var(--v-fg-dim); text-transform: uppercase; letter-spacing: 0.5px; }
    .health-value { font-size: 12px; font-weight: 600; font-feature-settings: 'tnum'; }
    .trust-panel {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); margin-top: 6px;
      padding: 6px 8px; background: rgba(255,255,255,0.02); border-radius: 4px;
      border: 1px solid var(--v-border); line-height: 1.5;
    }
    .trust-panel-header {
      font-size: 8px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
      color: var(--v-fg-muted); margin-bottom: 3px;
    }
    .trust-score-bar {
      display: inline-block; width: 40px; height: 4px; border-radius: 2px;
      background: rgba(255,255,255,0.06); overflow: hidden; vertical-align: middle; margin-left: 4px;
    }
    .trust-score-fill { height: 100%; border-radius: 2px; }
    .trust-flag {
      font-size: 7.5px; padding: 1px 4px; border-radius: 3px;
      background: rgba(240,100,100,0.1); color: var(--v-danger); border: 1px solid rgba(240,100,100,0.2);
      display: inline-block; margin-right: 3px;
    }
    .trust-flag.ok {
      background: rgba(45,212,168,0.1); color: var(--v-success); border-color: rgba(45,212,168,0.2);
    }
    .provenance-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 3px; }
    .provenance-item { white-space: nowrap; }
    .provenance-label { color: var(--v-fg-dim); }
    .provenance-value { color: var(--v-fg-muted); }
    .fed-badge {
      font-size: 7.5px; padding: 1px 4px; border-radius: 3px;
      background: rgba(245,183,49,0.1); color: var(--v-warn); border: 1px solid rgba(245,183,49,0.2);
    }
    .local-badge {
      font-size: 7.5px; padding: 1px 4px; border-radius: 3px;
      background: rgba(45,212,168,0.1); color: var(--v-success); border: 1px solid rgba(45,212,168,0.2);
    }
    /* Wave 50: Knowledge scope badges */
    .scope-badge {
      font-size: 7.5px; padding: 1px 5px; border-radius: 3px;
      font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
    }
    .scope-thread {
      background: rgba(91,156,245,0.1); color: var(--v-blue); border: 1px solid rgba(91,156,245,0.2);
    }
    .scope-workspace {
      background: rgba(167,139,250,0.1); color: #A78BFA; border: 1px solid rgba(167,139,250,0.2);
    }
    .scope-global {
      background: rgba(45,212,168,0.1); color: var(--v-success); border: 1px solid rgba(45,212,168,0.2);
    }
    .promote-global-btn {
      font-size: 8.5px; font-family: var(--f-mono); padding: 2px 7px; border-radius: 6px;
      cursor: pointer; border: 1px solid rgba(45,212,168,0.2); background: transparent;
      color: var(--v-success); transition: all 0.15s; user-select: none;
    }
    .promote-global-btn:hover {
      border-color: rgba(45,212,168,0.4); background: rgba(45,212,168,0.06);
    }
    .confirm-overlay {
      font-size: 10px; font-family: var(--f-mono); padding: 8px 10px;
      background: rgba(0,0,0,0.6); border: 1px solid var(--v-border); border-radius: 6px;
      margin-top: 6px; color: var(--v-fg);
    }
    .confirm-overlay .confirm-actions { display: flex; gap: 6px; margin-top: 6px; }
    .promotion-candidate-hint {
      font-size: 7.5px; padding: 1px 5px; border-radius: 3px;
      background: rgba(45,212,168,0.06); color: var(--v-success); border: 1px solid rgba(45,212,168,0.15);
      font-weight: 600; letter-spacing: 0.04em; cursor: default;
    }
    /* Wave 60: feedback buttons */
    .feedback-row { display: flex; gap: 4px; margin-top: 4px; }
    .fb-btn {
      font-size: 12px; padding: 1px 6px; border-radius: 4px; cursor: pointer;
      border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none; line-height: 1;
    }
    .fb-btn:hover { border-color: rgba(232,88,26,0.3); }
    .fb-btn.fb-up:hover { color: var(--v-success); border-color: rgba(45,212,168,0.4); }
    .fb-btn.fb-down:hover { color: var(--v-danger); border-color: rgba(240,100,100,0.4); }
    .fb-btn.fb-sent { opacity: 0.5; pointer-events: none; }
    /* Wave 60: relationships section */
    .relationships-section {
      margin-top: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02);
      border-radius: 4px; border: 1px solid var(--v-border);
    }
    .rel-header {
      font-size: 8px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
      color: var(--v-fg-muted); margin-bottom: 4px;
    }
    .rel-item {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); line-height: 1.6;
    }
    .rel-predicate {
      font-weight: 600; color: var(--v-accent); margin-right: 4px;
    }
    .rel-link {
      color: var(--v-fg-muted); cursor: pointer; text-decoration: underline;
      text-decoration-color: rgba(255,255,255,0.1);
    }
    .rel-link:hover { color: var(--v-fg); text-decoration-color: rgba(232,88,26,0.3); }
    /* Wave 67.5: provenance timeline */
    .provenance-section {
      margin-top: 8px; padding: 6px 8px; background: rgba(255,255,255,0.02);
      border-radius: 4px; border: 1px solid var(--v-border);
    }
    .prov-header {
      font-size: 8px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
      color: var(--v-fg-muted); margin-bottom: 4px;
    }
    .prov-item {
      font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-dim); line-height: 1.8;
      display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap;
    }
    .prov-time { color: var(--v-fg-muted); min-width: 50px; }
    .prov-type { font-weight: 600; color: var(--v-accent); font-size: 8px; }
    .prov-detail { flex: 1; }
    .prov-delta { font-weight: 700; font-size: 8px; }
    .prov-delta-pos { color: var(--v-success, #2DD4A8); }
    .prov-delta-neg { color: var(--v-accent, #F06464); }
    /* Wave 63: inline edit + create forms */
    .edit-overlay, .create-overlay {
      padding: 12px; margin-bottom: 10px;
      background: var(--v-glass); border: 1px solid var(--v-border); border-radius: 10px;
      backdrop-filter: blur(14px);
    }
    .edit-overlay h4, .create-overlay h4 {
      font-family: var(--f-display); font-size: 13px; font-weight: 700; margin: 0 0 8px 0; color: var(--v-fg);
    }
    .form-input {
      width: 100%; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--v-border);
      background: var(--v-recessed); color: var(--v-fg); font-size: 11px; font-family: var(--f-mono);
      outline: none; box-sizing: border-box; margin-bottom: 6px;
    }
    .form-input:focus { border-color: rgba(232,88,26,0.3); }
    .form-textarea { min-height: 80px; resize: vertical; }
    .form-row { display: flex; gap: 6px; margin-bottom: 6px; }
    .form-actions { display: flex; gap: 6px; margin-top: 8px; }
    /* Wave 67: hierarchy tree view */
    .tree-branch {
      padding: 6px 8px; margin-bottom: 2px; border-radius: 6px; cursor: pointer;
      border: 1px solid transparent; transition: all 0.15s;
    }
    .tree-branch:hover { border-color: var(--v-border); background: rgba(255,255,255,0.02); }
    .tree-branch-header { display: flex; align-items: center; gap: 8px; }
    .tree-chevron {
      font-size: 9px; color: var(--v-fg-dim); width: 12px; text-align: center;
      transition: transform 0.15s; display: inline-block;
    }
    .tree-chevron.open { transform: rotate(90deg); }
    .tree-label { font-family: var(--f-mono); font-size: 12px; color: var(--v-fg); font-weight: 600; }
    .tree-count {
      font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-dim);
      background: rgba(255,255,255,0.04); padding: 1px 5px; border-radius: 4px;
    }
    .tree-conf-bar { width: 60px; height: 3px; background: rgba(255,255,255,0.04); border-radius: 2px; overflow: hidden; }
    .tree-conf-fill { height: 100%; border-radius: 2px; }
    .tree-conf-pct { font-family: var(--f-mono); font-size: 9px; color: var(--v-fg-dim); min-width: 32px; text-align: right; }
    .tree-children { padding-left: 20px; }
    .tree-empty { font-size: 11px; color: var(--v-fg-dim); padding: 20px; text-align: center; }
    /* Wave 69: Search-first layout */
    .search-hero {
      margin-bottom: 16px;
    }
    .search-hero-input {
      width: 100%; padding: 10px 14px; border-radius: 10px;
      border: 1px solid var(--v-border); background: var(--v-surface);
      color: var(--v-fg); font-size: 14px; font-family: var(--f-body);
      outline: none; box-sizing: border-box;
      transition: border-color 0.15s;
    }
    .search-hero-input::placeholder { color: var(--v-fg-dim); }
    .search-hero-input:focus { border-color: var(--v-accent); }
    .quick-stats {
      font-family: var(--f-mono); font-size: 10.5px; color: var(--v-fg-muted);
      margin-top: 8px; padding-left: 2px;
    }
    .quick-stats .sep { margin: 0 6px; color: var(--v-fg-dim); }
    /* Wave 69 Track 9: Filter pills */
    .filter-strip {
      display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .filter-group-label {
      font-size: 8px; font-family: var(--f-mono); color: var(--v-fg-dim);
      text-transform: uppercase; letter-spacing: 0.08em; margin-right: 2px;
    }
    .qf-pill {
      padding: 4px 10px; border-radius: 12px;
      font-family: var(--f-mono); font-size: 10px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      background: var(--v-surface); border: 1px solid var(--v-border);
      cursor: pointer; transition: all 0.15s; user-select: none; color: var(--v-fg-dim);
    }
    .qf-pill.active {
      background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.3);
      color: var(--v-accent);
    }
    .qf-pill:hover:not(.active) { border-color: rgba(232,88,26,0.15); }
    /* Wave 69 Track 8: Detail mode toggle */
    .detail-mode-toggle {
      font-size: 9px; font-family: var(--f-mono); padding: 3px 10px; border-radius: 8px;
      cursor: pointer; border: 1px solid var(--v-border); background: transparent;
      color: var(--v-fg-dim); transition: all 0.15s; user-select: none; margin-left: auto;
    }
    .detail-mode-toggle.active {
      background: rgba(232,88,26,0.08); border-color: rgba(232,88,26,0.2);
      color: var(--v-accent);
    }
    .detail-mode-toggle:hover { border-color: rgba(232,88,26,0.25); color: var(--v-accent); }
    /* Wave 69: Simple entry card (non-detail mode) */
    .simple-conf {
      display: flex; align-items: center; gap: 4px;
      font-size: 9px; font-family: var(--f-mono); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    .simple-conf-high { color: var(--v-success, #2DD4A8); }
    .simple-conf-medium { color: var(--v-warn, #F5B731); }
    .simple-conf-low { color: var(--v-danger, #F06464); }
  `];

  @property() workspaceId = '';
  /** Pre-filter to a specific source colony (from colony-detail navigation) */
  @property() sourceColonyId = '';
  /** Current thread ID for thread-scoped filtering (Wave 29). */
  @property() threadId = '';
  /** Addon panels targeting this tab (Wave 66 T3). */
  @property({ type: Array }) addonPanels: AddonPanel[] = [];

  @state() private subView: SubView = 'catalog';
  @state() private items: KnowledgeItemPreview[] = [];
  @state() private loading = true;
  @state() private searchQuery = '';
  @state() private filter: FilterId = '';
  @state() private sortBy: SortBy = 'newest';
  @state() private threadFilter: ThreadFilter = 'all';
  @state() private total = 0;
  @state() private expandedId = '';
  @state() private detailLoadingId = '';
  @state() private detailCache: Record<string, KnowledgeItemDetail> = {};
  @state() private contradictions: ContradictionPair[] = [];
  @state() private healthStats: { byStatus: Record<string, number>; medianConf: number; freshness: Record<string, number>; topDomains: [string, number][]; lastMaintenance: string } | null = null;
  /** Wave 50: Entry ID currently showing promote-to-global confirmation. */
  @state() private _confirmPromoteGlobalId = '';
  /** Wave 60: Cached relationships per entry. */
  @state() private _relCache: Record<string, Array<{entry_id: string; predicate: string; confidence: number; title: string}>> = {};
  /** Wave 60: Entry IDs where feedback was sent (prevent double-click). */
  @state() private _feedbackSent: Record<string, 'positive' | 'negative'> = {};
  /** Wave 63: Inline edit state. */
  @state() private _editingId = '';
  @state() private _editTitle = '';
  @state() private _editContent = '';
  /** Wave 63: Create entry modal state. */
  @state() private _showCreate = false;
  @state() private _createTitle = '';
  @state() private _createContent = '';
  @state() private _createCategory = 'experience';
  @state() private _createDomain = '';
  /** Wave 67: hierarchy tree data. */
  @state() private _treeBranches: TreeBranch[] = [];
  @state() private _treeLoading = false;
  @state() private _treeExpanded: Set<string> = new Set();
  /** Wave 67.5: provenance chain cache. */
  @state() private _provCache: Record<string, ProvenanceChainItem[]> = {};
  /** Wave 69 Track 8: Detail mode toggle (off = simple, on = power-user). */
  @state() private _detailMode = false;
  /** Wave 72 Track 4: Ingest/reindex status. */
  @state() private _ingestStatus = '';
  @state() private _reindexStatus = '';
  /** Wave 69 Track 7: Unified search results from /workspaces/{id}/search. */
  @state() private _unifiedResults: UnifiedSearchResult[] = [];
  @state() private _unifiedSearchActive = false;
  @state() private _unifiedLoading = false;
  /** Wave 69 Track 9: Quick filter state. */
  @state() private _sourceFilter: 'all' | 'memory' | 'docs' | 'code' = 'all';
  @state() private _domainFilter = '';
  @state() private _statusFilter: 'all' | 'verified' | 'candidate' = 'all';
  /** Wave 69: Quick stats for search-first view. */
  @state() private _quickStats: { entryCount: number; domainCount: number } | null = null;

  private _debounceTimer = 0;

  connectedCallback() {
    super.connectedCallback();
    void this._fetchItems();
    void this._fetchQuickStats();
  }

  override updated(changed: Map<string, unknown>) {
    if (changed.has('sourceColonyId') || changed.has('workspaceId')) {
      this.subView = 'catalog';
      this.expandedId = '';
      this.detailLoadingId = '';
      this.detailCache = {};
    }
    if (changed.has('sourceColonyId')) {
      this.searchQuery = '';
      this.filter = '';
      this.sortBy = 'newest';
    }
    if (changed.has('sourceColonyId') || changed.has('workspaceId')) {
      void this._fetchItems();
    }
    if (changed.has('workspaceId')) {
      void this._fetchContradictions();
    }
  }

  private async _fetchItems() {
    this.loading = true;
    try {
      if (this.searchQuery.trim()) {
        await this._searchItems();
      } else {
        await this._listItems();
      }
    } catch {
      this.items = [];
      this.total = 0;
    }
    this._computeHealthStats();
    this.loading = false;
  }

  private async _listItems() {
    const params = new URLSearchParams({ limit: '100' });
    const [source, ctype] = this._filterToParams();
    if (source) params.set('source', source);
    if (ctype) params.set('type', ctype);
    if (this.workspaceId) params.set('workspace', this.workspaceId);
    if (this.sourceColonyId) params.set('source_colony_id', this.sourceColonyId);
    this._applyThreadFilter(params);
    const resp = await fetch(`/api/v1/knowledge?${params}`);
    if (resp.ok) {
      const data = await resp.json() as { items: KnowledgeItemPreview[]; total: number };
      this.items = data.items;
      this.total = data.total;
    } else {
      this.items = [];
      this.total = 0;
    }
  }

  private async _searchItems() {
    const params = new URLSearchParams({ q: this.searchQuery.trim(), limit: '50' });
    const [source, ctype] = this._filterToParams();
    if (source) params.set('source', source);
    if (ctype) params.set('type', ctype);
    if (this.workspaceId) params.set('workspace', this.workspaceId);
    if (this.sourceColonyId) params.set('source_colony_id', this.sourceColonyId);
    this._applyThreadFilter(params);
    const resp = await fetch(`/api/v1/knowledge/search?${params}`);
    if (resp.ok) {
      const data = await resp.json() as { results: KnowledgeItemPreview[]; total: number };
      this.items = data.results;
      this.total = data.total;
    } else {
      this.items = [];
      this.total = 0;
    }
  }

  /** Map filter ID to (source_system, canonical_type) query params. */
  private _filterToParams(): [string, string] {
    switch (this.filter) {
      case 'skill': return ['', 'skill'];
      case 'experience': return ['', 'experience'];
      default: return ['', ''];
    }
  }

  private _onSearchInput(e: Event) {
    this.searchQuery = (e.target as HTMLInputElement).value;
    clearTimeout(this._debounceTimer);
    if (!this._detailMode) {
      // Wave 69: In simple mode, use unified search
      this._debounceTimer = window.setTimeout(() => void this._unifiedSearch(), 300);
    } else {
      this._debounceTimer = window.setTimeout(() => void this._fetchItems(), 300);
    }
  }

  /** Wave 69 Track 7: Search across memory + addon indices via unified endpoint. */
  private async _unifiedSearch() {
    const q = this.searchQuery.trim();
    if (!q) {
      this._unifiedResults = [];
      this._unifiedSearchActive = false;
      return;
    }
    if (!this.workspaceId) return;
    this._unifiedLoading = true;
    this._unifiedSearchActive = true;
    try {
      const params = new URLSearchParams({ q, limit: '10' });
      if (this._sourceFilter !== 'all') {
        params.set('sources', this._sourceFilter);
      }
      const resp = await fetch(
        `/api/v1/workspaces/${this.workspaceId}/search?${params}`,
      );
      if (resp.ok) {
        const data = await resp.json() as UnifiedSearchResponse;
        let results = data.results;
        // Client-side domain filter
        if (this._domainFilter) {
          results = results.filter(r => {
            const domains = (r.metadata?.domains as string[]) ?? [];
            return domains.includes(this._domainFilter);
          });
        }
        // Client-side status filter
        if (this._statusFilter !== 'all') {
          results = results.filter(r => {
            const status = (r.metadata?.status as string) ?? '';
            return status === this._statusFilter;
          });
        }
        this._unifiedResults = results;
      } else {
        this._unifiedResults = [];
      }
    } catch {
      this._unifiedResults = [];
    }
    this._unifiedLoading = false;
  }

  /** Wave 69: Fetch quick stats for the search-first landing. */
  private async _fetchQuickStats() {
    if (!this.workspaceId) return;
    try {
      const resp = await fetch(`/api/v1/knowledge?workspace=${this.workspaceId}&limit=1`);
      if (resp.ok) {
        const data = await resp.json() as { items: KnowledgeItemPreview[]; total: number };
        const domainSet = new Set<string>();
        // Use full items list to count domains (fetch a larger batch)
        const resp2 = await fetch(`/api/v1/knowledge?workspace=${this.workspaceId}&limit=200`);
        if (resp2.ok) {
          const data2 = await resp2.json() as { items: KnowledgeItemPreview[]; total: number };
          for (const it of data2.items) {
            for (const d of it.domains) domainSet.add(d);
          }
        }
        this._quickStats = { entryCount: data.total, domainCount: domainSet.size };
      }
    } catch { /* best-effort */ }
  }

  /** Wave 69 Track 9: Set source filter and re-search. */
  private _setSourceFilter(f: 'all' | 'memory' | 'docs' | 'code') {
    this._sourceFilter = f;
    if (this._unifiedSearchActive) void this._unifiedSearch();
  }

  /** Wave 69 Track 9: Set domain filter and re-search. */
  private _setDomainFilter(d: string) {
    this._domainFilter = this._domainFilter === d ? '' : d;
    if (this._unifiedSearchActive) void this._unifiedSearch();
  }

  /** Wave 69 Track 9: Set status filter and re-search. */
  private _setStatusFilter(s: 'all' | 'verified' | 'candidate') {
    this._statusFilter = s;
    if (this._unifiedSearchActive) void this._unifiedSearch();
  }

  private _setFilter(f: FilterId) {
    this.filter = this.filter === f ? '' : f;
    void this._fetchItems();
  }

  private _setSortBy(s: SortBy) {
    this.sortBy = s;
    this.requestUpdate();
  }

  private async _toggleDetail(id: string) {
    if (this.expandedId === id) {
      this.expandedId = '';
      return;
    }
    this.expandedId = id;
    // Wave 60: fetch relationships alongside detail
    void this._fetchRelationships(id);
    void this._fetchProvenance(id);
    if (this.detailCache[id] || this.detailLoadingId === id) {
      return;
    }
    this.detailLoadingId = id;
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(id)}`);
      if (resp.ok) {
        const detail = await resp.json() as KnowledgeItemDetail;
        this.detailCache = { ...this.detailCache, [id]: detail };
      }
    } catch {
      // Keep the preview-only card usable even if detail fetch fails.
    } finally {
      if (this.detailLoadingId === id) {
        this.detailLoadingId = '';
      }
    }
  }

  private _applyThreadFilter(params: URLSearchParams) {
    if (this.threadFilter === 'thread' && this.threadId) {
      params.set('thread', this.threadId);
    } else if (this.threadFilter === 'workspace') {
      params.set('thread', '');
    } else if (this.threadFilter === 'global') {
      // Wave 50: filter to global-scoped entries only (Team 1's endpoint contract)
      params.set('scope', 'global');
    }
  }

  private _setThreadFilter(f: ThreadFilter) {
    this.threadFilter = f;
    void this._fetchItems();
  }

  private async _promoteEntry(id: string) {
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(id)}/promote`, { method: 'POST' });
      if (resp.ok) {
        void this._fetchItems();
      }
    } catch { /* best-effort */ }
  }

  /**
   * Wave 50: Promote a workspace-scoped entry to global scope.
   * Calls Team 1's extended promotion route with target_scope=global.
   */
  private async _promoteToGlobal(id: string) {
    this._confirmPromoteGlobalId = '';
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(id)}/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_scope: 'global' }),
      });
      if (resp.ok) {
        void this._fetchItems();
      }
    } catch { /* best-effort */ }
  }

  /** Wave 50: Infer knowledge scope from entry fields. */
  private _inferScope(e: KnowledgeItemPreview): 'thread' | 'workspace' | 'global' {
    // Team 1 may add an explicit `scope` field; use it if present.
    const explicit = (e as Record<string, unknown>).scope as string | undefined;
    if (explicit === 'global') return 'global';
    if (explicit === 'workspace') return 'workspace';
    if (explicit === 'thread') return 'thread';
    // Fallback heuristic from existing fields
    if (e.thread_id) return 'thread';
    return 'workspace';
  }

  /**
   * Wave 50: Check if an entry is an auto-promotion candidate.
   * Team 1 may add a `promotion_candidate` boolean; use it if present.
   */
  private _isPromotionCandidate(e: KnowledgeItemPreview): boolean {
    return (e as Record<string, unknown>).promotion_candidate === true;
  }

  private async _runMaintenance(serviceType: string) {
    try {
      await fetch('/api/v1/services/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service_type: serviceType, query: 'run' }),
      });
    } catch { /* best-effort */ }
  }

  private _computeHealthStats() {
    if (this.items.length === 0) { this.healthStats = null; return; }
    const byStatus: Record<string, number> = {};
    const confs: number[] = [];
    const domainCounts: Record<string, number> = {};
    const now = Date.now();
    const freshness: Record<string, number> = { '7d': 0, '30d': 0, '90d': 0 };

    for (const e of this.items) {
      byStatus[e.status] = (byStatus[e.status] ?? 0) + 1;
      confs.push(this._betaConf(e));
      for (const d of e.domains) {
        domainCounts[d] = (domainCounts[d] ?? 0) + 1;
      }
      if (e.created_at) {
        const age = now - new Date(e.created_at).getTime();
        const days = age / 86_400_000;
        if (days <= 7) freshness['7d']++;
        if (days <= 30) freshness['30d']++;
        if (days <= 90) freshness['90d']++;
      }
    }

    confs.sort((a, b) => a - b);
    const medianConf = confs.length > 0 ? confs[Math.floor(confs.length / 2)] : 0;
    const topDomains = Object.entries(domainCounts).sort((a, b) => b[1] - a[1]).slice(0, 5) as [string, number][];

    this.healthStats = { byStatus, medianConf, freshness, topDomains, lastMaintenance: '' };
  }

  private async _fetchContradictions() {
    try {
      const params = new URLSearchParams();
      if (this.workspaceId) params.set('workspace', this.workspaceId);
      const resp = await fetch(`/api/v1/knowledge/contradictions?${params}`);
      if (resp.ok) {
        const data = await resp.json() as { pairs: ContradictionPair[] };
        this.contradictions = data.pairs ?? [];
      } else {
        this.contradictions = [];
      }
    } catch { this.contradictions = []; }
  }

  private async _dismissContradiction(entryA: string, entryB: string) {
    try {
      await fetch(`/api/v1/knowledge/${encodeURIComponent(entryA)}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'verified', reason: `dedup:dismissed pair=${entryB}` }),
      });
      this.contradictions = this.contradictions.filter(c => !(c.entry_a === entryA && c.entry_b === entryB));
    } catch { /* best-effort */ }
  }

  private async _rejectEntry(entryId: string, pairedWith: string) {
    try {
      await fetch(`/api/v1/knowledge/${encodeURIComponent(entryId)}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'rejected', reason: `contradiction with ${pairedWith}` }),
      });
      this.contradictions = this.contradictions.filter(c => !(c.entry_a === entryId || c.entry_b === entryId));
      void this._fetchItems();
    } catch { /* best-effort */ }
  }

  // --- Wave 60 B1: fetch relationships for an entry ---
  private async _fetchRelationships(entryId: string) {
    if (this._relCache[entryId]) return;
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(entryId)}/relationships`);
      if (resp.ok) {
        const data = await resp.json() as { relationships: Array<{entry_id: string; predicate: string; confidence: number; title: string}> };
        this._relCache = { ...this._relCache, [entryId]: data.relationships ?? [] };
      } else {
        console.warn(`fetchRelationships: ${resp.status} for ${entryId}`);
      }
    } catch (err) { console.warn('fetchRelationships failed:', err); }
  }

  // --- Wave 67.5: fetch provenance chain ---
  private async _fetchProvenance(entryId: string) {
    if (this._provCache[entryId]) return;
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(entryId)}/provenance`);
      if (resp.ok) {
        const data = await resp.json() as { chain: ProvenanceChainItem[] };
        this._provCache = { ...this._provCache, [entryId]: data.chain ?? [] };
      }
    } catch { /* non-critical */ }
  }

  private _renderProvenance(entryId: string) {
    const chain = this._provCache[entryId];
    if (!chain || chain.length === 0) return nothing;
    return html`
      <div class="provenance-section">
        <div class="prov-header">Provenance</div>
        ${chain.map(item => html`
          <div class="prov-item">
            <span class="prov-time">${timeAgo(item.timestamp)}</span>
            <span class="prov-type">${item.event_type.replace(/([A-Z])/g, ' $1').trim()}</span>
            <span class="prov-detail">${item.detail}</span>
            ${item.confidence_delta != null ? html`
              <span class="prov-delta ${item.confidence_delta >= 0 ? 'prov-delta-pos' : 'prov-delta-neg'}">
                ${item.confidence_delta >= 0 ? '+' : ''}${(item.confidence_delta * 100).toFixed(1)}%
              </span>
            ` : nothing}
          </div>
        `)}
      </div>
    `;
  }

  // --- Wave 60 B2: submit operator feedback ---
  private async _submitFeedback(entryId: string, positive: boolean) {
    if (this._feedbackSent[entryId]) return;
    try {
      const resp = await fetch(`/api/v1/knowledge/${encodeURIComponent(entryId)}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positive }),
      });
      if (resp.ok) {
        this._feedbackSent = { ...this._feedbackSent, [entryId]: positive ? 'positive' : 'negative' };
        // Refresh items to get updated confidence
        void this._fetchItems();
      } else {
        console.warn(`submitFeedback: ${resp.status} for ${entryId}`);
      }
    } catch (err) { console.warn('submitFeedback failed:', err); }
  }

  private get sorted(): KnowledgeItemPreview[] {
    const list = [...this.items];
    if (this.sortBy === 'confidence') {
      list.sort((a, b) => this._betaConf(b) - this._betaConf(a));
    } else if (this.sortBy === 'relevance' && this.searchQuery.trim()) {
      list.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    } else {
      list.sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
    }
    return list;
  }

  render() {
    return html`
      <div class="title-row">
        <h2><fc-gradient-text>Knowledge</fc-gradient-text></h2>
        ${!this.loading && this.items.length > 0
          ? html`<fc-pill color="var(--v-secondary)" glow>${this.total} entries</fc-pill>`
          : nothing}
        ${this.sourceColonyId
          ? html`<fc-pill color="var(--v-fg-dim)" sm>colony: ${this.sourceColonyId.slice(0, 12)}</fc-pill>`
          : nothing}
        <span class="detail-mode-toggle ${this._detailMode ? 'active' : ''}"
          @click=${() => { this._detailMode = !this._detailMode; }}
          title="${this._detailMode ? 'Switch to simple view' : 'Switch to detail view'}">
          ${this._detailMode ? '◆ Detail' : '◇ Simple'}
        </span>
        ${this._detailMode ? html`
          <div class="sub-tabs">
            <span class="sub-tab ${this.subView === 'catalog' ? 'active' : ''}"
              @click=${() => { this.subView = 'catalog'; }}>Catalog</span>
            <span class="sub-tab ${this.subView === 'graph' ? 'active' : ''}"
              @click=${() => { this.subView = 'graph'; }}>Graph</span>
            <span class="sub-tab ${this.subView === 'tree' ? 'active' : ''}"
              @click=${() => { this.subView = 'tree'; void this._fetchTree(); }}>Tree</span>
          </div>
        ` : nothing}
      </div>

      <fc-knowledge-health-card .workspaceId=${this.workspaceId}
        style="margin-bottom:10px"></fc-knowledge-health-card>

      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
        <button class="promote-btn" @click=${() => this._ingestUpload()}>Upload &amp; Ingest</button>
        <button class="promote-btn" @click=${() => void this._triggerReindex('docs-index')}>Reindex Docs</button>
        <button class="promote-btn" @click=${() => void this._triggerReindex('codebase-index')}>Reindex Code</button>
        <button class="promote-btn" @click=${() => void this._fetch()}>Refresh Library</button>
        ${this._ingestStatus ? html`
          <span style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">${this._ingestStatus}</span>
        ` : nothing}
        ${this._reindexStatus ? html`
          <span style="font-size:10px;font-family:var(--f-mono);color:var(--v-fg-dim)">${this._reindexStatus}</span>
        ` : nothing}
      </div>

      ${this.addonPanels.filter(p => p.target === 'knowledge').map(p => html`
        <fc-addon-panel
          src="/addons/${p.addon_name}${p.path}"
          display-type="${p.display_type}"
          label="${p.addon_name}">
        </fc-addon-panel>
      `)}

      ${!this._detailMode
        ? this._renderSearchFirst()
        : this.subView === 'graph'
        ? html`<div class="graph-container">
            <fc-knowledge-view .workspaceId=${this.workspaceId} .graphOnly=${true}></fc-knowledge-view>
          </div>`
        : this.subView === 'tree'
        ? this._renderTreeView()
        : this._renderCatalog()}
    `;
  }

  /** Wave 69 Track 7: Search-first default view. */
  private _renderSearchFirst() {
    const stats = this._quickStats;
    const topDomains = this.healthStats?.topDomains ?? [];
    return html`
      <div class="search-hero">
        <input class="search-hero-input" type="text"
          placeholder="Search knowledge, docs, code..."
          .value=${this.searchQuery}
          @input=${this._onSearchInput}>
        ${stats ? html`
          <div class="quick-stats">
            ${stats.entryCount} entries<span class="sep">·</span>${stats.domainCount} domains
          </div>
        ` : nothing}
      </div>

      ${this._renderFilterStrip(topDomains)}

      ${this._unifiedLoading
        ? html`<div class="loading">Searching\u2026</div>`
        : this._unifiedSearchActive
          ? html`<fc-knowledge-search-results
              .results=${this._unifiedResults}
              .activeWorkspaceId=${this.workspaceId}
              @entry-selected=${(e: CustomEvent) => {
                this.expandedId = e.detail.id;
                this._detailMode = true;
                this.subView = 'catalog';
                void this._toggleDetail(e.detail.id);
              }}
            ></fc-knowledge-search-results>`
          : this._renderSimpleCatalog()}
    `;
  }

  /** Wave 69 Track 9: Source / domain / status filter pills. */
  private _renderFilterStrip(topDomains: [string, number][]) {
    return html`
      <div class="filter-strip">
        <span class="filter-group-label">Source</span>
        ${(['all', 'memory', 'docs', 'code'] as const).map(s => html`
          <span class="qf-pill ${this._sourceFilter === s ? 'active' : ''}"
            @click=${() => this._setSourceFilter(s)}>${s}</span>
        `)}
        <span class="divider"></span>
        ${topDomains.length > 0 ? html`
          <span class="filter-group-label">Domain</span>
          ${topDomains.slice(0, 6).map(([d]) => html`
            <span class="qf-pill ${this._domainFilter === d ? 'active' : ''}"
              @click=${() => this._setDomainFilter(d)}>${d}</span>
          `)}
          <span class="divider"></span>
        ` : nothing}
        <span class="filter-group-label">Status</span>
        ${(['all', 'verified', 'candidate'] as const).map(s => html`
          <span class="qf-pill ${this._statusFilter === s ? 'active' : ''}"
            @click=${() => this._setStatusFilter(s)}>${s}</span>
        `)}
      </div>
    `;
  }

  /** Wave 69: Simplified catalog for non-detail mode (no score bars, no Beta, no provenance). */
  private _renderSimpleCatalog() {
    if (this.loading) return html`<div class="loading">Loading knowledge entries\u2026</div>`;
    const sorted = this.sorted;
    if (sorted.length === 0) {
      return this.total === 0 && !this.searchQuery.trim()
        ? html`<div class="glass empty-state">
            <div style="margin-bottom:8px;font-weight:600;color:var(--v-fg)">No knowledge entries yet.</div>
            <div>Knowledge is extracted automatically when colonies complete.</div>
          </div>`
        : html`<div class="glass empty-state">No entries match the current filter.</div>`;
    }
    return html`<div class="entry-list">${sorted.map(e => this._renderSimpleEntry(e))}</div>`;
  }

  /** Wave 69 Track 8: Simple entry card (detail mode off). */
  private _renderSimpleEntry(e: KnowledgeItemPreview) {
    const conf = this._betaConf(e);
    const level = conf >= 0.7 ? 'high' : conf >= 0.4 ? 'medium' : 'low';
    const label = level === 'high' ? 'High' : level === 'medium' ? 'Medium' : 'Low';
    const snippet = e.summary || e.content_preview || '';
    return html`
      <div class="glass entry-card" @click=${() => {
        this.expandedId = e.id;
        this._detailMode = true;
        this.subView = 'catalog';
        void this._toggleDetail(e.id);
      }} style="cursor:pointer">
        <div class="entry-header">
          <span class="entry-title">${e.title || e.id.slice(0, 24)}</span>
          <fc-pill class="type-${e.canonical_type}" sm>${e.canonical_type}</fc-pill>
          <fc-pill class="status-${e.status}" sm>${e.status}</fc-pill>
        </div>
        ${snippet ? html`
          <div class="entry-content" style="max-height:40px">${snippet.slice(0, 160)}</div>
        ` : nothing}
        <div class="entry-meta">
          <div class="simple-conf">
            <fc-dot status=${level === 'high' ? 'loaded' : level === 'medium' ? 'pending' : 'error'}></fc-dot>
            <span class="simple-conf-${level}">${label}</span>
          </div>
          ${e.domains.slice(0, 3).map(d => html`<span class="domain-tag">${d}</span>`)}
        </div>
      </div>
    `;
  }

  private _renderHealthWidget() {
    const h = this.healthStats;
    if (!h) return nothing;
    const statColor = (s: string) => s === 'verified' ? '#2DD4A8' : s === 'candidate' ? '#F5B731' : s === 'stale' ? '#6B6B76' : s === 'rejected' ? '#F06464' : 'var(--v-fg-muted)';
    return html`
      <div class="health-widget">
        ${['verified', 'candidate', 'stale', 'rejected'].map(s => html`
          <div class="health-stat">
            <span class="health-label">${s}</span>
            <span class="health-value" style="color:${statColor(s)}">${h.byStatus[s] ?? 0}</span>
          </div>
        `)}
        <div class="health-stat">
          <span class="health-label">median conf</span>
          <span class="health-value">${(h.medianConf * 100).toFixed(0)}%</span>
        </div>
        <div class="health-stat">
          <span class="health-label">7d / 30d / 90d</span>
          <span class="health-value">${h.freshness['7d']} / ${h.freshness['30d']} / ${h.freshness['90d']}</span>
        </div>
        ${h.topDomains.length > 0 ? html`
          <div class="health-stat">
            <span class="health-label">top domains</span>
            <span style="font-size:9px">${h.topDomains.map(([d, n]) => `${d}(${n})`).join(', ')}</span>
          </div>
        ` : nothing}
      </div>`;
  }

  private _renderContradictions() {
    if (this.contradictions.length === 0) return nothing;
    return html`
      <div class="contradiction-section">
        <div style="font-size:10px;font-family:var(--f-mono);color:#F06464;margin-bottom:6px;font-weight:600">
          ${this.contradictions.length} contradiction${this.contradictions.length !== 1 ? 's' : ''} flagged
        </div>
        ${this.contradictions.map(c => {
          const weaker = c.conf_a <= c.conf_b ? c.entry_a : c.entry_b;
          return html`
            <div class="glass contradiction-card">
              <div class="contradiction-pair">
                <div class="contradiction-entry">
                  <div class="contradiction-title">${c.title_a}</div>
                  <div class="contradiction-meta">
                    <span class="${c.polarity_a === 'positive' ? 'polarity-pos' : 'polarity-neg'}">${c.polarity_a}</span>
                    · ${(c.conf_a * 100).toFixed(0)}%
                    ${c.source_colony_a ? html` · ${c.source_colony_a.slice(0, 8)}` : nothing}
                  </div>
                </div>
                <span class="contradiction-vs">VS</span>
                <div class="contradiction-entry">
                  <div class="contradiction-title">${c.title_b}</div>
                  <div class="contradiction-meta">
                    <span class="${c.polarity_b === 'positive' ? 'polarity-pos' : 'polarity-neg'}">${c.polarity_b}</span>
                    · ${(c.conf_b * 100).toFixed(0)}%
                    ${c.source_colony_b ? html` · ${c.source_colony_b.slice(0, 8)}` : nothing}
                  </div>
                </div>
              </div>
              <div style="font-size:8px;color:var(--v-fg-dim);margin-bottom:6px">
                domains: ${c.shared_domains.join(', ')} · jaccard: ${c.jaccard.toFixed(2)}
              </div>
              <div class="contradiction-actions">
                <button class="promote-btn" @click=${() => void this._dismissContradiction(c.entry_a, c.entry_b)}>Dismiss</button>
                <button class="maintenance-btn" style="border-color:rgba(240,100,100,0.3);color:#F06464"
                  @click=${() => void this._rejectEntry(weaker, weaker === c.entry_a ? c.entry_b : c.entry_a)}>Reject Weaker</button>
              </div>
            </div>`;
        })}
      </div>`;
  }

  /* ---- Wave 67: hierarchy tree view ---- */

  private async _fetchTree() {
    if (!this.workspaceId || this._treeLoading) return;
    this._treeLoading = true;
    try {
      const res = await fetch(`/api/v1/workspaces/${this.workspaceId}/knowledge-tree`);
      if (res.ok) {
        const data = await res.json();
        this._treeBranches = data.branches ?? [];
      }
    } catch { /* ignore */ }
    this._treeLoading = false;
  }

  private _toggleBranch(path: string) {
    const next = new Set(this._treeExpanded);
    if (next.has(path)) next.delete(path); else next.add(path);
    this._treeExpanded = next;
  }

  private _filterByBranch(path: string) {
    this.searchQuery = `path:${path}`;
    this.subView = 'catalog';
    void this._fetchItems();
  }

  private _confColor(mean: number): string {
    if (mean >= 0.7) return 'var(--v-tier-high, #2DD4A8)';
    if (mean >= 0.4) return 'var(--v-tier-moderate, #F5B731)';
    return 'var(--v-tier-exploratory, #F06464)';
  }

  // Wave 72 Track 4: Upload & Ingest (ported from knowledge-view.ts)
  private _ingestUpload() {
    if (!this.workspaceId) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.txt,.md,.py,.json,.yaml,.yml,.csv';
    input.onchange = async () => {
      if (!input.files?.length) return;
      const form = new FormData();
      for (const file of Array.from(input.files)) {
        form.append(file.name, file);
      }
      this._ingestStatus = 'Ingesting...';
      try {
        const resp = await fetch(
          `/api/v1/workspaces/${this.workspaceId}/ingest`,
          { method: 'POST', body: form },
        );
        if (resp.ok) {
          const data = await resp.json() as { ingested?: Array<{ name: string; chunks: number }> };
          const items = (data.ingested ?? []) as Array<{ name: string; chunks: number }>;
          const names = items.map((i: { name: string; chunks: number }) => `${i.name} (${i.chunks})`).join(', ');
          this._ingestStatus = items.length > 0 ? `Ingested: ${names}` : 'No files ingested.';
        } else {
          this._ingestStatus = 'Ingest failed.';
        }
      } catch {
        this._ingestStatus = 'Ingest error.';
      }
    };
    input.click();
  }

  private async _triggerReindex(addonName: string) {
    this._reindexStatus = `Reindexing ${addonName}...`;
    try {
      const resp = await fetch(`/api/v1/addons/${addonName}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ handler: '' }),
      });
      if (resp.ok) {
        const data = await resp.json() as { result?: string };
        this._reindexStatus = `${addonName}: ${data.result ?? 'ok'}`;
      } else {
        this._reindexStatus = `${addonName}: failed`;
      }
    } catch {
      this._reindexStatus = `${addonName}: error`;
    }
  }

  private _renderTreeView() {
    if (this._treeLoading) return html`<div class="tree-empty">Loading hierarchy...</div>`;
    if (this._treeBranches.length === 0) return html`<div class="tree-empty">No hierarchy branches yet. Entries will be organized as knowledge is created.</div>`;
    return html`<div style="margin-top: 8px;">
      ${this._treeBranches.map(b => this._renderBranch(b, 0))}
    </div>`;
  }

  private _renderBranch(branch: TreeBranch, depth: number) {
    const expanded = this._treeExpanded.has(branch.path);
    const hasChildren = branch.children.length > 0;
    const pct = (branch.confidence.mean * 100).toFixed(0);
    return html`
      <div class="tree-branch" style="padding-left: ${depth * 20 + 8}px;">
        <div class="tree-branch-header">
          <span class="tree-chevron ${expanded ? 'open' : ''}"
            @click=${(e: Event) => { e.stopPropagation(); if (hasChildren) this._toggleBranch(branch.path); }}
            style="visibility: ${hasChildren ? 'visible' : 'hidden'}">▶</span>
          <span class="tree-label" @click=${() => this._filterByBranch(branch.path)}>${branch.label}</span>
          <span class="tree-count">${branch.entryCount}</span>
          <div class="tree-conf-bar">
            <div class="tree-conf-fill" style="width: ${pct}%; background: ${this._confColor(branch.confidence.mean)};"></div>
          </div>
          <span class="tree-conf-pct">${pct}%</span>
        </div>
      </div>
      ${expanded && hasChildren ? html`<div class="tree-children">
        ${branch.children.map(c => this._renderBranch(c, depth + 1))}
      </div>` : nothing}
    `;
  }

  private _renderCatalog() {
    const sorted = this.sorted;
    return html`
      <div class="controls">
        <input class="search-input" type="text" placeholder="Search knowledge..."
          .value=${this.searchQuery} @input=${this._onSearchInput}>
        <span class="divider"></span>
        <span class="filter-pill ${this.filter === '' ? 'active' : ''}"
          @click=${() => this._setFilter('')}>All</span>
        <span class="filter-pill ${this.filter === 'skill' ? 'active' : ''}"
          @click=${() => this._setFilter('skill')}>Skills</span>
        <span class="filter-pill ${this.filter === 'experience' ? 'active' : ''}"
          @click=${() => this._setFilter('experience')}>Experiences</span>
        ${this.threadId ? html`
          <span class="divider"></span>
          <span class="filter-pill ${this.threadFilter === 'all' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('all')}>All</span>
          <span class="filter-pill ${this.threadFilter === 'thread' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('thread')}>This Thread</span>
          <span class="filter-pill ${this.threadFilter === 'workspace' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('workspace')}>Workspace-wide</span>
          <span class="filter-pill ${this.threadFilter === 'global' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('global')}>Global</span>
        ` : html`
          <span class="divider"></span>
          <span class="filter-pill ${this.threadFilter === 'all' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('all')}>All Scopes</span>
          <span class="filter-pill ${this.threadFilter === 'global' ? 'active' : ''}"
            @click=${() => this._setThreadFilter('global')}>Global Only</span>
        `}
        <span class="divider"></span>
        ${(['newest', 'confidence', ...(this.searchQuery.trim() ? ['relevance'] : [])] as SortBy[]).map(s => html`
          <span class="filter-pill ${this.sortBy === s ? 'active' : ''}"
            @click=${() => this._setSortBy(s)}>${s}</span>
        `)}
        <span class="divider"></span>
        <button class="maintenance-btn" title="Run dedup consolidation"
          @click=${() => void this._runMaintenance('service:consolidation:dedup')}>Dedup</button>
        <button class="maintenance-btn" title="Run stale sweep"
          @click=${() => void this._runMaintenance('service:consolidation:stale_sweep')}>Stale Sweep</button>
        <span class="divider"></span>
        <button class="maintenance-btn" style="border-color:rgba(45,212,168,0.3);color:#2DD4A8"
          @click=${() => { this._showCreate = true; }}>+ Create Entry</button>
      </div>

      ${this._showCreate ? this._renderCreateForm() : nothing}
      ${this._editingId ? this._renderEditForm() : nothing}

      ${this._renderHealthWidget()}
      ${this._renderContradictions()}

      ${this.loading
        ? html`<div class="loading">Loading knowledge entries\u2026</div>`
        : sorted.length === 0
          ? this.total === 0 && !this.searchQuery.trim() && !this.filter
            ? html`<div class="glass empty-state">
                <div style="margin-bottom:8px;font-weight:600;color:var(--v-fg)">No knowledge entries yet.</div>
                <div>Knowledge is extracted automatically when colonies complete.</div>
                <div style="margin-top:4px">Try running a colony, then come back here to see what was learned.</div>
              </div>`
            : html`<div class="glass empty-state">
                No knowledge entries match the current filter.
                ${this.items.length === 0 && this.total > 0 ? html`
                  <div style="margin-top:8px;font-size:10px;color:var(--v-fg-dim)">
                    Entries exist but none are verified yet.
                    <button class="maintenance-btn" style="margin-left:4px"
                      @click=${() => void this._runMaintenance('service:consolidation:stale_sweep')}>Run maintenance</button>
                  </div>` : nothing}
              </div>`
          : html`<div class="entry-list">${sorted.map(e => this._renderEntry(e))}</div>`}
    `;
  }

  /** Wave 55: hot/warm/cold usage badge */
  private _usageBadge(e: KnowledgeItemPreview) {
    const count = e.usage_count ?? 0;
    if (count >= 5) return html`<span class="usage-badge usage-hot" title="${count} accesses">\u2726 hot</span>`;
    if (count >= 1) return html`<span class="usage-badge usage-warm" title="${count} accesses">\u2726 warm</span>`;
    return html`<span class="usage-badge usage-cold" title="unused">\u25CB cold</span>`;
  }

  private _betaConf(e: KnowledgeItemPreview): number {
    if (e.conf_alpha != null && e.conf_beta != null && (e.conf_alpha + e.conf_beta) > 0) {
      return e.conf_alpha / (e.conf_alpha + e.conf_beta);
    }
    return e.confidence;
  }

  private _betaCertainty(e: KnowledgeItemPreview): number {
    // Higher alpha+beta = more certain. Scale to 0..1 (50 = fully certain).
    const total = (e.conf_alpha ?? 0) + (e.conf_beta ?? 0);
    if (total <= 0) return 0.5; // unknown certainty
    return Math.min(total / 50, 1);
  }

  /** Classify a knowledge item into a confidence tier (mirrors engine/runner.py _confidence_tier). */
  private _confidenceTier(e: KnowledgeItemPreview): 'HIGH' | 'MODERATE' | 'LOW' | 'EXPLORATORY' | 'STALE' {
    let alpha = e.conf_alpha ?? 0;
    let beta = e.conf_beta ?? 0;
    if (alpha <= 0 || beta <= 0) {
      const conf = e.confidence ?? 0.5;
      alpha = Math.max(conf * 10, 1.0);
      beta = Math.max((1 - conf) * 10, 1.0);
    }
    const observations = alpha + beta - 2;
    const mean = alpha / (alpha + beta);
    const ciWidth = 1.96 * Math.sqrt(mean * (1 - mean) / (alpha + beta + 1));
    if (e.status === 'stale') return 'STALE';
    if (observations < 3) return 'EXPLORATORY';
    if (mean >= 0.7 && ciWidth < 0.20) return 'HIGH';
    if (mean >= 0.45) return 'MODERATE';
    return 'LOW';
  }

  /** Tier color for the confidence badge. */
  private _tierColor(tier: string): string {
    switch (tier) {
      case 'HIGH': return 'var(--v-tier-high)';
      case 'MODERATE': return 'var(--v-tier-moderate)';
      case 'LOW': return 'var(--v-tier-low)';
      case 'EXPLORATORY': return 'var(--v-tier-exploratory)';
      case 'STALE': return 'var(--v-tier-stale)';
      default: return 'var(--v-fg-dim)';
    }
  }

  /** Natural language confidence summary. */
  private _confSummary(e: KnowledgeItemPreview): string {
    const tier = this._confidenceTier(e);
    const conf = this._betaConf(e);
    const pct = (conf * 100).toFixed(0);
    const total = (e.conf_alpha ?? 5) + (e.conf_beta ?? 5);
    const obs = Math.max(0, Math.round(total - 10));
    const dc = (e as Record<string, unknown>).decay_class as string | undefined;
    const dcLabel = dc ? `, ${dc} decay` : '';
    return `${tier.charAt(0) + tier.slice(1).toLowerCase()} confidence (${pct}%) — ${obs} observations${dcLabel}.`;
  }

  /** Render horizontal stacked bar for score breakdown (Wave 35 A3). */
  private _renderScoreBar(e: KnowledgeItemPreview) {
    const sb = ((e as Record<string, unknown>).score_breakdown ?? (e as Record<string, unknown>)._score_breakdown) as Record<string, number> | undefined;
    if (!sb) return nothing;
    const signals = ['semantic', 'thompson', 'freshness', 'status', 'thread', 'cooccurrence', 'graph_proximity'] as const;
    const weights = (sb as Record<string, unknown>).weights as Record<string, number> | undefined ?? {};
    const contributions = signals.map(s => ({ name: s, raw: sb[s] ?? 0, w: weights[s] ?? 0, wc: (sb[s] ?? 0) * (weights[s] ?? 0) }));
    const total = contributions.reduce((s, c) => s + c.wc, 0) || 1;
    const expanded = (e as Record<string, unknown>)._scoreBarExpanded as boolean;
    return html`
      <div class="score-bar" @click=${() => { (e as Record<string, unknown>)._scoreBarExpanded = !expanded; this.requestUpdate(); }}
        title="Click to ${expanded ? 'hide' : 'show'} signal details">
        ${contributions.map(c => html`<div class="seg seg-${c.name}" style="width:${(c.wc / total * 100).toFixed(1)}%"></div>`)}
      </div>
      ${expanded ? html`<div class="score-detail">
        ${contributions.map(c => html`<strong>${c.name}</strong>: ${c.raw.toFixed(3)} × ${c.w.toFixed(2)} = ${c.wc.toFixed(4)}<br>`)}
      </div>` : nothing}
    `;
  }

  private _renderTrustPanel(detail: KnowledgeItemDetail) {
    const trust = detail.trust_rationale as TrustRationale | undefined;
    const prov = detail.provenance as KnowledgeProvenance | undefined;
    if (!trust && !prov) return nothing;

    const score = trust?.admission_score ?? 0;
    const scoreColor = score >= 0.7 ? '#2DD4A8' : score >= 0.5 ? '#F5B731' : '#F06464';

    return html`
      <div class="trust-panel">
        ${trust ? html`
          <div class="trust-panel-header">Trust Rationale</div>
          <div>
            Score: ${score.toFixed(2)}
            <span class="trust-score-bar">
              <span class="trust-score-fill" style="width:${(score * 100).toFixed(0)}%;background:${scoreColor}"></span>
            </span>
            — ${trust.rationale}
          </div>
          ${trust.flags.length > 0 ? html`
            <div style="margin-top:2px">
              ${trust.flags.map(f => html`<span class="trust-flag${f === 'federated' ? '' : f === 'rejected_status' ? '' : ' ok'}">${f}</span>`)}
            </div>
          ` : nothing}
        ` : nothing}
        ${prov ? html`
          <div class="trust-panel-header" style="margin-top:4px">Provenance</div>
          <div class="provenance-row">
            <span class="${prov.is_federated ? 'fed-badge' : 'local-badge'}">${prov.is_federated ? 'Federated' : 'Local'}</span>
            ${prov.source_colony_id ? html`
              <span class="provenance-item"><span class="provenance-label">Colony:</span> <span class="provenance-value">${prov.source_colony_id.slice(0, 8)}</span></span>
            ` : nothing}
            ${prov.source_peer ? html`
              <span class="provenance-item"><span class="provenance-label">Peer:</span> <span class="provenance-value">${prov.source_peer}</span></span>
            ` : nothing}
            ${prov.decay_class ? html`
              <span class="provenance-item"><span class="provenance-label">Decay:</span> <span class="provenance-value">${prov.decay_class}</span></span>
            ` : nothing}
            ${prov.thread_id ? html`
              <span class="provenance-item"><span class="provenance-label">Thread:</span> <span class="provenance-value">${prov.thread_id.slice(0, 8)}</span></span>
            ` : nothing}
            ${prov.federation_hop > 0 ? html`
              <span class="provenance-item"><span class="provenance-label">Hops:</span> <span class="provenance-value">${prov.federation_hop}</span></span>
            ` : nothing}
          </div>
          ${prov.forager_provenance ? html`
            <div class="trust-panel-header" style="margin-top:4px">Web Source</div>
            <div class="provenance-row">
              <span class="provenance-item"><span class="provenance-label">Domain:</span> <span class="provenance-value">${prov.forager_provenance.source_domain}</span></span>
              <span class="provenance-item"><span class="provenance-label">Credibility:</span> <span class="provenance-value">${(prov.forager_provenance.source_credibility * 100).toFixed(0)}%</span></span>
              <span class="provenance-item"><span class="provenance-label">Quality:</span> <span class="provenance-value">${(prov.forager_provenance.quality_score * 100).toFixed(0)}%</span></span>
              ${prov.forager_provenance.fetch_timestamp ? html`
                <span class="provenance-item"><span class="provenance-label">Fetched:</span> <span class="provenance-value">${timeAgo(prov.forager_provenance.fetch_timestamp)}</span></span>
              ` : nothing}
            </div>
            ${prov.forager_provenance.source_url ? html`
              <div style="font-size:10px;font-family:var(--f-mono);margin-top:3px;word-break:break-all">
                <a href="${prov.forager_provenance.source_url}" target="_blank" rel="noopener" style="color:var(--v-blue);text-decoration:underline">${prov.forager_provenance.source_url.slice(0, 80)}${prov.forager_provenance.source_url.length > 80 ? '…' : ''}</a>
              </div>
            ` : nothing}
            ${prov.forager_provenance.forager_query ? html`
              <div style="font-size:10px;margin-top:2px;color:var(--v-dim)">Query: ${prov.forager_provenance.forager_query}</div>
            ` : nothing}
          ` : nothing}
          ${prov.transaction_time ? html`
            <div class="trust-panel-header" style="margin-top:4px">Temporal</div>
            <div class="provenance-row">
              <span class="provenance-item"><span class="provenance-label">Learned at:</span> <span class="provenance-value">${timeAgo(prov.transaction_time)}</span></span>
              ${prov.status_changed_at ? html`
                <span class="provenance-item"><span class="provenance-label">Status changed:</span> <span class="provenance-value">${timeAgo(prov.status_changed_at)}</span></span>
              ` : nothing}
              ${prov.invalidated_at ? html`
                <span class="provenance-item" style="color:#F06464"><span class="provenance-label">Invalidated:</span> <span class="provenance-value">${timeAgo(prov.invalidated_at)}</span></span>
              ` : nothing}
            </div>
          ` : nothing}
        ` : nothing}
      </div>
    `;
  }

  // Wave 60 B1: render graph relationships for an expanded entry
  private _renderRelationships(entryId: string) {
    const rels = this._relCache[entryId];
    if (!rels || rels.length === 0) return nothing;
    return html`
      <div class="relationships-section">
        <div class="rel-header">Relationships</div>
        ${rels.map(r => html`
          <div class="rel-item">
            <span class="rel-predicate">${r.predicate}</span>
            <span class="rel-link" @click=${() => {
              this.expandedId = r.entry_id;
              void this._toggleDetail(r.entry_id);
            }}>${r.title || r.entry_id.slice(0, 16)}</span>
            ${r.confidence ? html`<span style="opacity:0.5"> (${(r.confidence * 100).toFixed(0)}%)</span>` : nothing}
          </div>
        `)}
      </div>
    `;
  }

  private _renderEntry(e: KnowledgeItemPreview) {
    const conf = this._betaConf(e);
    const confColor = conf >= 0.7 ? 'var(--v-success)' : conf >= 0.4 ? 'var(--v-warn)' : 'var(--v-accent)';
    const isLegacy = e.source_system === 'legacy_skill_bank';
    const polarityClass = e.polarity === 'positive' ? 'polarity-pos'
      : e.polarity === 'negative' ? 'polarity-neg' : 'polarity-neu';
    const polarityIcon = e.polarity === 'positive' ? '\u2191' : e.polarity === 'negative' ? '\u2193' : '\u2194';
    const age = e.created_at ? timeAgo(e.created_at) : '';
    const isExpanded = this.expandedId === e.id;
    const detail = this.detailCache[e.id];
    const detailBody = detail?.content?.trim() || detail?.summary?.trim() || detail?.content_preview || e.summary || e.content_preview;

    return html`
      <div class="glass entry-card">
        <div class="entry-row">
          <div class="entry-left">
            <div class="entry-header">
              <fc-pill class="${isLegacy ? 'source-legacy' : 'source-inst'}" sm>
                ${isLegacy ? 'Legacy' : 'Institutional'}
              </fc-pill>
              <fc-pill class="type-${e.canonical_type}" sm>${e.canonical_type}</fc-pill>
              <fc-pill class="status-${e.status}" sm>${e.status}</fc-pill>
              ${e.canonical_type === 'experience' ? html`
                <span class="${polarityClass}" style="font-size:11px;font-weight:600" title="${e.polarity}">${polarityIcon}</span>
              ` : nothing}
              ${e.status === 'stale' ? html`<fc-pill class="status-stale" sm>stale</fc-pill>` : nothing}
              ${e.source_colony_id === 'forager' ? html`<fc-pill class="source-web" sm>web</fc-pill>` : nothing}
              ${(() => { const scope = this._inferScope(e); return html`
                <span class="scope-badge scope-${scope}">${scope}</span>
              `; })()}
              ${this._isPromotionCandidate(e) ? html`
                <span class="promotion-candidate-hint" title="Qualifies for global promotion">promote?</span>
              ` : nothing}
              ${e.thread_id ? html`<span class="thread-badge">\u25B7 ${e.thread_id.slice(0, 12)}</span>` : nothing}
              ${this._usageBadge(e)}
              <span class="entry-title">${e.title}</span>
            </div>
            <div class="entry-content">${e.summary || e.content_preview}</div>
            <div class="entry-meta">
              ${e.source_colony_id ? html`
                <fc-pill color="var(--v-fg-dim)" sm>${e.source_colony_id.slice(0, 12)}</fc-pill>
              ` : nothing}
              ${age ? html`<span style="font-size:8px;font-family:var(--f-mono);color:var(--v-fg-dim)">${age}</span>` : nothing}
              ${isLegacy && e.legacy_metadata?.merge_count > 0 ? html`
                <fc-pill color="var(--v-secondary)" sm>merged \u00D7${e.legacy_metadata.merge_count}</fc-pill>
              ` : nothing}
            </div>
            ${(e.domains.length > 0 || e.tool_refs.length > 0) ? html`
              <div class="domains-row">
                ${e.domains.map(d => html`<span class="domain-tag">${d}</span>`)}
                ${e.tool_refs.map(t => html`<span class="domain-tag">${t}</span>`)}
              </div>` : nothing}
            ${this._renderScoreBar(e)}
            <div class="entry-actions">
              <button class="detail-toggle" @click=${() => void this._toggleDetail(e.id)}>
                ${isExpanded ? 'Hide detail' : 'Inspect'}
              </button>
              ${e.thread_id ? html`
                <button class="promote-btn" @click=${() => void this._promoteEntry(e.id)}
                  title="Promote to workspace-wide">\u2191 Promote</button>
              ` : nothing}
              ${this._inferScope(e) === 'workspace' || this._isPromotionCandidate(e) ? html`
                <button class="promote-global-btn"
                  @click=${() => { this._confirmPromoteGlobalId = e.id; }}
                  title="Promote to global scope">\u2191 Promote to Global</button>
              ` : nothing}
              <span class="feedback-row">
                <button class="fb-btn fb-up ${this._feedbackSent[e.id] ? 'fb-sent' : ''}"
                  @click=${() => void this._submitFeedback(e.id, true)}
                  title="Thumbs up — strengthens confidence">${this._feedbackSent[e.id] === 'positive' ? '\u2714' : '\u25B2'}</button>
                <button class="fb-btn fb-down ${this._feedbackSent[e.id] ? 'fb-sent' : ''}"
                  @click=${() => void this._submitFeedback(e.id, false)}
                  title="Thumbs down — weakens confidence">${this._feedbackSent[e.id] === 'negative' ? '\u2714' : '\u25BC'}</button>
              </span>
              <button class="promote-btn" @click=${() => this._startEdit(e)}
                title="Edit entry content">\u270E Edit</button>
              <button class="promote-btn" style="border-color:rgba(240,100,100,0.3);color:#F06464"
                @click=${() => void this._deleteEntry(e.id)}
                title="Soft-delete entry">\u2717 Delete</button>
            </div>
            ${this._confirmPromoteGlobalId === e.id ? html`
              <div class="confirm-overlay">
                Promote <strong>${e.title}</strong> to global scope?
                This will make it visible across all workspaces.
                <div class="confirm-actions">
                  <fc-btn variant="primary" sm @click=${() => void this._promoteToGlobal(e.id)}>Confirm</fc-btn>
                  <fc-btn variant="ghost" sm @click=${() => { this._confirmPromoteGlobalId = ''; }}>Cancel</fc-btn>
                </div>
              </div>
            ` : nothing}
          </div>
          <div class="entry-right">
            <div class="conf-big" style="color:${confColor}">${(conf * 100).toFixed(0)}%</div>
            <div class="conf-bar" style="width:${Math.round(this._betaCertainty(e) * 100)}%">
              <div class="conf-fill" style="width:${Math.round(conf * 100)}%;background:${confColor}"></div>
            </div>
            <span class="conf-tier tier-${this._confidenceTier(e)}">${this._confidenceTier(e)}</span>
            <div class="conf-summary">${this._confSummary(e)}</div>
            <div class="conf-hover-detail">
              Mean: ${conf.toFixed(3)} ± ${(1.96 * Math.sqrt(conf * (1 - conf) / ((e.conf_alpha ?? 5) + (e.conf_beta ?? 5) + 1))).toFixed(3)}<br>
              Observations: ${Math.max(0, Math.round(((e.conf_alpha ?? 5) + (e.conf_beta ?? 5)) - 10))}<br>
              Decay: ${(e as Record<string, unknown>).decay_class ?? 'ephemeral'}<br>
              ${(e as Record<string, unknown>).prediction_error_count ? html`Pred. errors: ${(e as Record<string, unknown>).prediction_error_count}<br>` : nothing}
            </div>
            ${e.last_accessed ? html`
              <div style="font-size:8px;font-family:var(--f-mono);color:var(--v-fg-dim);margin-top:2px">${timeAgo(e.last_accessed)}</div>
            ` : nothing}
          </div>
        </div>
        ${isExpanded ? html`
          <div class="entry-detail">
            ${this.detailLoadingId === e.id
              ? html`Loading full entry\u2026`
              : detailBody || 'Full detail unavailable for this entry.'}
            ${detail ? html`
              <div class="power-panel">
                <strong>Raw posteriors:</strong> α=${(detail as Record<string, unknown>).conf_alpha ?? '?'} β=${(detail as Record<string, unknown>).conf_beta ?? '?'}<br>
                ${(detail as Record<string, unknown>).merged_from ? html`<strong>Merged from:</strong> ${((detail as Record<string, unknown>).merged_from as string[])?.join(', ') ?? 'none'}<br>` : nothing}
                ${(detail as Record<string, unknown>).sub_type ? html`<strong>Sub-type:</strong> ${(detail as Record<string, unknown>).sub_type}<br>` : nothing}
              </div>
              ${this._renderTrustPanel(detail)}
            ` : nothing}
            ${this._renderRelationships(e.id)}
            ${this._renderProvenance(e.id)}
          </div>
        ` : nothing}
      </div>`;
  }

  // --- Wave 63: Knowledge CRUD ---

  private _startEdit(e: KnowledgeItemPreview) {
    this._editingId = e.id;
    this._editTitle = e.title;
    this._editContent = e.content_preview || e.summary || '';
  }

  private _renderEditForm() {
    return html`
      <div class="edit-overlay">
        <h4>Edit Entry</h4>
        <input class="form-input" placeholder="Title" .value=${this._editTitle}
          @input=${(e: Event) => { this._editTitle = (e.target as HTMLInputElement).value; }}>
        <textarea class="form-input form-textarea" placeholder="Content" .value=${this._editContent}
          @input=${(e: Event) => { this._editContent = (e.target as HTMLTextAreaElement).value; }}></textarea>
        <div class="form-actions">
          <fc-btn variant="primary" sm @click=${() => void this._saveEdit()}>Save</fc-btn>
          <fc-btn variant="ghost" sm @click=${() => { this._editingId = ''; }}>Cancel</fc-btn>
        </div>
      </div>`;
  }

  private async _saveEdit() {
    if (!this._editingId) return;
    try {
      await fetch(`/api/v1/knowledge/${encodeURIComponent(this._editingId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: this._editTitle, content: this._editContent }),
      });
      this._editingId = '';
      void this._fetchItems();
    } catch { /* best-effort */ }
  }

  private async _deleteEntry(id: string) {
    try {
      await fetch(`/api/v1/knowledge/${encodeURIComponent(id)}`, { method: 'DELETE' });
      void this._fetchItems();
    } catch { /* best-effort */ }
  }

  private _renderCreateForm() {
    return html`
      <div class="create-overlay">
        <h4>Create Knowledge Entry</h4>
        <input class="form-input" placeholder="Title" .value=${this._createTitle}
          @input=${(e: Event) => { this._createTitle = (e.target as HTMLInputElement).value; }}>
        <textarea class="form-input form-textarea" placeholder="Content" .value=${this._createContent}
          @input=${(e: Event) => { this._createContent = (e.target as HTMLTextAreaElement).value; }}></textarea>
        <div class="form-row">
          <select class="form-input" style="flex:1" .value=${this._createCategory}
            @change=${(e: Event) => { this._createCategory = (e.target as HTMLSelectElement).value; }}>
            <option value="experience">Experience</option>
            <option value="skill">Skill</option>
          </select>
          <input class="form-input" style="flex:1" placeholder="Primary domain" .value=${this._createDomain}
            @input=${(e: Event) => { this._createDomain = (e.target as HTMLInputElement).value; }}>
        </div>
        <div class="form-actions">
          <fc-btn variant="primary" sm @click=${() => void this._submitCreate()}>Create</fc-btn>
          <fc-btn variant="ghost" sm @click=${() => { this._showCreate = false; }}>Cancel</fc-btn>
        </div>
      </div>`;
  }

  private async _submitCreate() {
    if (!this._createTitle.trim() || !this._createContent.trim()) return;
    try {
      await fetch(`/api/v1/workspaces/${encodeURIComponent(this.workspaceId)}/knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: this._createTitle,
          content: this._createContent,
          category: this._createCategory,
          primary_domain: this._createDomain || undefined,
        }),
      });
      this._showCreate = false;
      this._createTitle = '';
      this._createContent = '';
      this._createDomain = '';
      void this._fetchItems();
    } catch { /* best-effort */ }
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-knowledge-browser': FcKnowledgeBrowser; }
}
