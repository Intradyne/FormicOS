import { LitElement, html, css, nothing, svg } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';
import type { TopologySnapshot } from '../types.js';

@customElement('fc-topology-graph')
export class FcTopologyGraph extends LitElement {
  static styles = [voidTokens, css`
    :host { display: block; width: 100%; height: 100%; }
    .no-topo {
      padding: 20px; color: var(--v-fg-dim); font-size: 9.5px;
      font-family: var(--f-mono); text-align: center; letter-spacing: 0.08em;
      height: 100%; display: flex; align-items: center; justify-content: center;
    }
  `];

  @property({ type: Object }) topology: TopologySnapshot | null = null;
  @state() private _hovered: string | null = null;

  render() {
    if (!this.topology) return html`<div class="no-topo">NO TOPOLOGY DATA</div>`;
    const t = this.topology;
    return html`
      <svg viewBox="0 0 400 270" style="width:100%;height:100%">
        <defs>
          <marker id="topoArr" viewBox="0 0 10 6" refX="10" refY="3"
            markerWidth="5" markerHeight="3.5" orient="auto">
            <path d="M0,0 L10,3 L0,6" fill="var(--v-fg-dim)"/>
          </marker>
          <filter id="edgeGlow">
            <feGaussianBlur stdDeviation="4" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        ${t.edges.map((e, i) => {
          const a = t.nodes.find(n => n.id === e.from);
          const b = t.nodes.find(n => n.id === e.to);
          if (!a || !b) return nothing;
          const strong = e.weight > 1.2;
          const isHov = this._hovered === e.from || this._hovered === e.to;
          return svg`<g>
            ${strong ? svg`<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
              stroke="var(--v-accent)" stroke-width="${e.weight * 2}" opacity="0.06"
              filter="url(#edgeGlow)"/>` : nothing}
            <line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
              stroke="${isHov ? 'rgba(255,255,255,0.22)' : strong ? 'var(--v-accent)' : `rgba(255,255,255,${Math.min(e.weight / 4, 0.1)})`}"
              stroke-width="${isHov ? e.weight + 0.5 : e.weight}"
              marker-end="url(#topoArr)"
              opacity="${strong ? 0.6 : 0.4}"
              stroke-dasharray="${e.weight < 0.8 ? '4 3' : 'none'}"
              style="transition:all 0.3s"/>
          </g>`;
        })}
        ${t.nodes.map(n => {
          const isH = this._hovered === n.id;
          return svg`
            <g @mouseenter=${() => { this._hovered = n.id; }}
               @mouseleave=${() => { this._hovered = null; }}
               style="cursor:pointer">
              ${isH ? svg`<circle cx="${n.x}" cy="${n.y}" r="24"
                fill="none" stroke="${n.color}" stroke-width="0.5" opacity="0.3"/>` : nothing}
              <rect x="${n.x - 32}" y="${n.y - 13}" width="64" height="26" rx="6"
                fill="${isH ? `${n.color}15` : 'var(--v-surface)'}"
                stroke="${isH ? `${n.color}50` : `${n.color}20`}" stroke-width="0.8"
                style="transition:all 0.2s"/>
              <text x="${n.x}" y="${n.y + 3}" text-anchor="middle"
                fill="${isH ? n.color : 'var(--v-fg-muted)'}"
                style="font-family:var(--f-mono);font-size:7.5px;letter-spacing:0.12em;font-weight:600;transition:fill 0.2s">${n.label}</text>
            </g>`;
        })}
      </svg>`;
  }
}

declare global {
  interface HTMLElementTagNameMap { 'fc-topology-graph': FcTopologyGraph; }
}
