import { LitElement, html, css, nothing } from 'lit';
import { customElement, state, property } from 'lit/decorators.js';
import { voidTokens, sharedStyles } from '../styles/shared.js';

interface QualityTrendPoint {
  round: number;
  quality: number;
}

interface PatternCount {
  learned_patterns: number;
  total_patterns: number;
  pattern_efficiency: number;
}

interface ColonyDashboardData {
  colony_id: string;
  colony_name: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  quality_trend: QualityTrendPoint[];
  pattern_count: PatternCount;
  last_updated: string;
}

@customElement('fc-colony-dashboard')
export class FcColonyDashboard extends LitElement {
  @property({ type: Object }) data?: ColonyDashboardData;
  @state() private _loading = false;

  static styles = [
    voidTokens,
    sharedStyles,
    css`
      :host {
        display: block;
        width: 100%;
      }
      .dashboard {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 16px;
        gap: 16px;
        display: flex;
        flex-direction: column;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      }
      .colony-title {
        font-family: var(--f-display);
        font-size: 16px;
        font-weight: 600;
        color: var(--v-fg);
      }
      .status-badge {
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .status-running { background: rgba(72, 187, 120, 0.2); color: var(--v-success); }
      .status-completed { background: rgba(102, 126, 234, 0.2); color: var(--v-info); }
      .status-failed { background: rgba(239, 68, 68, 0.2); color: var(--v-danger); }
      .status-pending { background: rgba(251, 191, 36, 0.2); color: var(--v-warn); }
      
      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 16px;
      }
      .metric-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 6px;
        padding: 12px;
      }
      .metric-label {
        font-size: 11px;
        color: var(--v-fg-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
      }
      .metric-value {
        font-family: var(--f-mono);
        font-size: 24px;
        font-weight: 600;
        color: var(--v-fg);
      }
      .metric-sub {
        font-size: 11px;
        color: var(--v-fg-dim);
        margin-top: 4px;
      }
      
      .chart-section {
        flex: 1;
        min-height: 200px;
      }
      .chart-title {
        font-size: 12px;
        font-weight: 600;
        color: var(--v-fg);
        margin-bottom: 12px;
      }
      .quality-chart {
        display: flex;
        align-items: flex-end;
        gap: 4px;
        height: 180px;
        padding: 8px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        border-left: 1px solid rgba(255, 255, 255, 0.08);
      }
      .quality-bar {
        flex: 1;
        background: linear-gradient(to top, var(--v-accent), var(--v-success));
        border-radius: 2px 2px 0 0;
        min-width: 8px;
        transition: all 0.3s ease;
        cursor: pointer;
        position: relative;
      }
      .quality-bar:hover {
        opacity: 0.8;
        transform: scaleY(1.02);
      }
      .quality-bar::after {
        content: attr(data-quality);
        position: absolute;
        top: -20px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 10px;
        color: var(--v-fg-muted);
        opacity: 0;
        transition: opacity 0.2s;
      }
      .quality-bar:hover::after {
        opacity: 1;
      }
      
      .pattern-section {
        display: flex;
        gap: 24px;
        align-items: center;
        padding: 16px;
        background: rgba(255, 255, 255, 0.02);
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 0.06);
      }
      .pattern-icon {
        width: 48px;
        height: 48px;
        background: linear-gradient(135deg, var(--v-accent), var(--v-success));
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
      }
      .pattern-stats {
        flex: 1;
      }
      .pattern-title {
        font-size: 12px;
        font-weight: 600;
        color: var(--v-fg);
        margin-bottom: 4px;
      }
      .pattern-detail {
        font-size: 11px;
        color: var(--v-fg-dim);
        margin-bottom: 2px;
      }
      .pattern-highlight {
        font-family: var(--f-mono);
        font-size: 14px;
        font-weight: 600;
        color: var(--v-success);
      }
      
      .empty-state {
        text-align: center;
        padding: 48px 24px;
        color: var(--v-fg-dim);
      }
      .empty-icon {
        font-size: 48px;
        margin-bottom: 16px;
        opacity: 0.5;
      }
      .empty-text {
        font-size: 14px;
        margin-bottom: 8px;
      }
      .empty-subtext {
        font-size: 12px;
        color: var(--v-fg-muted);
      }
      
      .loading {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 48px;
        gap: 12px;
      }
      .spinner {
        width: 24px;
        height: 24px;
        border: 2px solid rgba(255, 255, 255, 0.1);
        border-top-color: var(--v-accent);
        border-radius: 50%;
        animation: spin 1s linear infinite;
      }
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
    `
  ];

  private _getStatusClass(status: string): string {
    return `status-${status.toLowerCase()}`;
  }

  private _formatQuality(quality: number): string {
    return `${(quality * 100).toFixed(1)}%`;
  }

  private _renderLoading() {
    return html`
      <div class="loading">
        <div class="spinner"></div>
        <span style="color: var(--v-fg-muted); font-size: 14px;">Loading dashboard...</span>
      </div>
    `;
  }

  private _renderEmptyState() {
    return html`
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <div class="empty-text">No colony data available</div>
        <div class="empty-subtext">Select a colony to view quality trends and patterns</div>
      </div>
    `;
  }

  private _renderQualityChart(trend: QualityTrendPoint[]) {
    if (trend.length === 0) {
      return html`
        <div class="empty-state" style="padding: 24px;">
          <div class="empty-text">No quality data yet</div>
        </div>
      `;
    }

    const maxQuality = Math.max(...trend.map(p => p.quality), 0.1);
    
    return html`
      <div class="quality-chart">
        ${trend.map(point => {
          const height = (point.quality / maxQuality) * 100;
          const color = point.quality >= 0.7 ? 'var(--v-success)' : 
                       point.quality >= 0.4 ? 'var(--v-warn)' : 
                       'var(--v-accent)';
          return html`
            <div class="quality-bar" 
                 style="height: ${height}%; background: ${color};"
                 data-quality="${this._formatQuality(point.quality)}"
                 title="Round ${point.round}: ${this._formatQuality(point.quality)}">
            </div>
          `;
        })}
      </div>
    `;
  }

  private _renderPatternSection(patterns: PatternCount) {
    const efficiency = ((patterns.learned_patterns / patterns.total_patterns) * 100).toFixed(1);
    
    return html`
      <div class="pattern-section">
        <div class="pattern-icon">🧠</div>
        <div class="pattern-stats">
          <div class="pattern-title">Auto-Learned Patterns</div>
          <div class="pattern-detail">
            <span class="pattern-highlight">${patterns.learned_patterns}</span> learned out of 
            <span class="pattern-highlight">${patterns.total_patterns}</span> total
          </div>
          <div class="pattern-detail">
            Efficiency: <span class="pattern-highlight">${efficiency}%</span>
          </div>
        </div>
      </div>
    `;
  }

  override render() {
    if (this._loading) {
      return this._renderLoading();
    }

    if (!this.data) {
      return this._renderEmptyState();
    }

    const { quality_trend, pattern_count, colony_name, status, last_updated } = this.data;

    return html`
      <div class="dashboard">
        <div class="header">
          <div class="colony-title">${colony_name}</div>
          <div class="status-badge ${this._getStatusClass(status)}">${status}</div>
        </div>

        <div class="metrics-grid">
          <div class="metric-card">
            <div class="metric-label">Quality Score</div>
            <div class="metric-value">
              ${quality_trend.length > 0 
                ? this._formatQuality(quality_trend[quality_trend.length - 1].quality)
                : 'N/A'}
            </div>
            <div class="metric-sub">Latest round</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Learned Patterns</div>
            <div class="metric-value">${pattern_count.learned_patterns}</div>
            <div class="metric-sub">Auto-discovered</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Pattern Efficiency</div>
            <div class="metric-value">
              ${pattern_count.total_patterns > 0
                ? `${((pattern_count.learned_patterns / pattern_count.total_patterns) * 100).toFixed(1)}%`
                : '0%'}
            </div>
            <div class="metric-sub">Of total patterns</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Last Updated</div>
            <div class="metric-value" style="font-size: 14px;">
              ${new Date(last_updated).toLocaleTimeString()}
            </div>
            <div class="metric-sub">${new Date(last_updated).toLocaleDateString()}</div>
          </div>
        </div>

        <div class="chart-section">
          <div class="chart-title">Quality Trend Over Rounds</div>
          ${this._renderQualityChart(quality_trend)}
        </div>

        ${this._renderPatternSection(pattern_count)}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-colony-dashboard': FcColonyDashboard;
  }
}
