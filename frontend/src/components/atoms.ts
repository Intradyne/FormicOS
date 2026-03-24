import { LitElement, html, css, nothing } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { voidTokens } from '../styles/shared.js';

const statusColor: Record<string, string> = {
  running: '#2DD4A8', completed: '#3DD6F5', queued: '#F5B731', loaded: '#2DD4A8',
  connected: '#2DD4A8', active: '#2DD4A8', pending: '#F5B731', done: '#3DD6F5',
  failed: '#F06464', killed: '#F06464', 'no_key': '#F06464', error: '#F06464',
};

@customElement('fc-dot')
export class FcDot extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline-flex; align-items: center; }
    .dot { border-radius: 50%; flex-shrink: 0; }
    .dot.pulsing { animation: pulse 2.8s ease-in-out infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
  `];
  @property() status = '';
  @property({ type: Number }) size = 6;

  render() {
    const c = statusColor[this.status] || '#3A3A44';
    const pulsing = ['running', 'active', 'loaded'].includes(this.status);
    return html`<span class="dot ${pulsing ? 'pulsing' : ''}"
      style="width:${this.size}px;height:${this.size}px;background:${c};box-shadow:${pulsing ? `0 0 ${this.size + 4}px ${c}50` : 'none'}"></span>`;
  }
}

@customElement('fc-pill')
export class FcPill extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline-flex; }
    .pill {
      display: inline-flex; align-items: center; gap: 3px;
      padding: 2px 10px; border-radius: 999px;
      font-size: 11px; font-family: var(--f-mono);
      letter-spacing: 0.05em; font-weight: 500;
    }
    :host([sm]) .pill { padding: 1px 7px; font-size: 10px; }
  `];
  @property() color = '#6B6B76';
  @property({ type: Boolean }) glow = false;
  @property({ type: Boolean }) sm = false;

  render() {
    const c = this.color;
    return html`<span class="pill" style="color:${c};background:${c}12;border:1px solid ${c}18;
      box-shadow:${this.glow ? `0 0 14px ${c}18` : 'none'}"><slot></slot></span>`;
  }
}

@customElement('fc-meter')
export class FcMeter extends LitElement {
  static styles = [voidTokens, css`
    .row { display: flex; justify-content: space-between; margin-bottom: 2px; }
    .label { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); letter-spacing: 0.12em; text-transform: uppercase; font-weight: 600; }
    .val { font-size: 12px; font-family: var(--f-mono); color: var(--v-fg-muted); font-feature-settings: 'tnum'; }
    .dim { color: var(--v-fg-dim); }
    .track { height: 2px; background: rgba(255,255,255,0.03); border-radius: 1px; overflow: hidden; }
    .fill { height: 100%; border-radius: 1px; transition: width 0.6s cubic-bezier(0.22,1,0.36,1); }
  `];
  @property() label = '';
  @property({ type: Number }) value = 0;
  @property({ type: Number }) max = 1;
  @property() unit = '';
  @property() color = '#E8581A';

  render() {
    const p = this.max > 0 ? Math.min(this.value / this.max * 100, 100) : 0;
    const c = p > 85 ? '#F06464' : p > 65 ? '#F5B731' : this.color;
    const fmtVal = this.unit === '$'
      ? (this.value > 0 && this.value < 0.01 ? '<$0.01' : `$${this.value.toFixed(2)}`)
      : `${this.value.toFixed?.(1) ?? this.value}${this.unit}`;
    const fmtMax = this.max > 0
      ? (this.unit === '$' ? `$${this.max.toFixed(2)}` : `${this.max}${this.unit}`)
      : '—';
    return html`
      <div style="margin-bottom:5px">
        <div class="row"><span class="label">${this.label}</span><span class="val">${fmtVal}<span class="dim"> / ${fmtMax}</span></span></div>
        <div class="track"><div class="fill" style="width:${p}%;background:${c};box-shadow:${p > 10 ? `0 0 8px ${c}30` : 'none'}"></div></div>
      </div>`;
  }
}

@customElement('fc-btn')
export class FcBtn extends LitElement {
  static styles = [voidTokens, css`
    button {
      font-family: var(--f-body); font-size: 13px; font-weight: 500;
      cursor: pointer; border-radius: 999px; border: none;
      transition: all 0.2s cubic-bezier(0.22,1,0.36,1);
      padding: 7px 16px; display: inline-flex; align-items: center;
      gap: 4; white-space: nowrap; letter-spacing: 0.01em;
    }
    :host([sm]) button { font-size: 11.5px; padding: 4px 10px; }
    :host([disabled]) button { opacity: 0.3; cursor: default; }
    .primary { background: var(--v-accent); color: #fff; }
    .primary:hover { background: var(--v-accent-bright); box-shadow: 0 0 24px var(--v-accent-glow); }
    .secondary { background: transparent; color: var(--v-fg); border: 1px solid var(--v-border); }
    .secondary:hover { background: rgba(255,255,255,0.04); border-color: var(--v-border-hover); }
    .ghost { background: transparent; color: var(--v-fg-muted); }
    .ghost:hover { background: rgba(255,255,255,0.03); color: var(--v-fg); }
    .danger { background: transparent; color: var(--v-danger); border: 1px solid rgba(240,100,100,0.15); }
    .danger:hover { background: rgba(240,100,100,0.12); }
    .success { background: transparent; color: var(--v-success); border: 1px solid rgba(45,212,168,0.15); }
    .success:hover { background: rgba(45,212,168,0.12); }
    .merge { background: transparent; color: var(--v-secondary); border: 1px solid rgba(61,214,245,0.22); }
    .merge:hover { background: var(--v-secondary); color: var(--v-fg-on-accent); }
  `];
  @property() variant: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'merge' = 'primary';
  @property({ type: Boolean }) sm = false;
  @property({ type: Boolean }) disabled = false;

  render() {
    return html`<button class="${this.variant}" ?disabled=${this.disabled} @click=${this._click}><slot></slot></button>`;
  }
  private _click(e: Event) {
    if (this.disabled) { e.stopPropagation(); e.preventDefault(); }
  }
}

@customElement('fc-defense-gauge')
export class FcDefenseGauge extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline-flex; align-items: center; gap: 6px; }
    .val { font-family: var(--f-mono); font-size: 11px; font-weight: 600; font-feature-settings: 'tnum'; }
    .lbl { font-family: var(--f-mono); font-size: 8.5px; color: var(--v-fg-dim); letter-spacing: 0.1em; }
  `];
  @property({ type: Number }) score = 0;

  render() {
    const s = this.score;
    const c = s > 0.8 ? '#F06464' : s > 0.6 ? '#F5B731' : s > 0.3 ? '#F4763A' : '#2DD4A8';
    const label = s > 0.8 ? 'HALT' : s > 0.6 ? 'ESCALATE' : s > 0.3 ? 'WARN' : 'NOMINAL';
    const r = 16, circ = 2 * Math.PI * r, filled = circ * Math.min(s, 1);
    return html`
      <svg width="${r * 2 + 8}" height="${r * 2 + 8}" style="transform:rotate(-90deg)">
        <circle cx="${r + 4}" cy="${r + 4}" r="${r}" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="2"/>
        <circle cx="${r + 4}" cy="${r + 4}" r="${r}" fill="none" stroke="${c}" stroke-width="2"
          stroke-dasharray="${filled} ${circ - filled}" stroke-linecap="round"
          style="transition:stroke-dasharray 0.6s ease-out;filter:drop-shadow(0 0 4px ${c}40)"/>
      </svg>
      <div><div class="val" style="color:${c}">${(s * 100).toFixed(0)}%</div><div class="lbl">${label}</div></div>`;
  }
}

@customElement('fc-pheromone-bar')
export class FcPheromoneBar extends LitElement {
  static styles = [voidTokens, css`
    :host { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
    .label { font-size: 10px; font-family: var(--f-mono); color: var(--v-fg-dim); width: 80px; overflow: hidden; text-overflow: ellipsis; }
    .track { flex: 1; height: 3px; background: rgba(255,255,255,0.03); border-radius: 2px; overflow: hidden; }
    .fill { height: 100%; border-radius: 2px; transition: width 0.5s ease-out; }
    .val { font-size: 9px; font-family: var(--f-mono); color: var(--v-fg-muted); font-feature-settings: 'tnum'; width: 28px; text-align: right; }
    .trend { font-size: 9px; width: 10px; text-align: center; }
  `];
  @property() label = '';
  @property({ type: Number }) value = 0;
  @property({ type: Number }) max = 2;
  @property() trend: 'up' | 'down' | 'stable' = 'stable';

  render() {
    const p = Math.min(this.value / this.max * 100, 100);
    const icon = this.trend === 'up' ? '\u2191' : this.trend === 'down' ? '\u2193' : '\u00B7';
    const tc = this.trend === 'up' ? '#2DD4A8' : this.trend === 'down' ? '#F06464' : '#3A3A44';
    return html`
      <span class="label">${this.label}</span>
      <div class="track"><div class="fill" style="width:${p}%;background:linear-gradient(90deg,rgba(232,88,26,0.08),${p > 60 ? '#E8581A' : 'rgba(232,88,26,0.08)'});
        box-shadow:${p > 60 ? '0 0 6px rgba(232,88,26,0.16)' : 'none'}"></div></div>
      <span class="val">${this.value.toFixed(1)}</span>
      <span class="trend" style="color:${tc}">${icon}</span>`;
  }
}

@customElement('fc-sparkline')
export class FcSparkline extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline-flex; align-items: center; }
  `];
  @property({ type: Array }) data: number[] = [];
  @property({ type: Number }) width = 60;
  @property({ type: Number }) height = 16;
  @property() color = '#E8581A';

  render() {
    const d = this.data;
    if (!d || d.length < 2) return nothing;
    const max = Math.max(...d, 1);
    const min = Math.min(...d, 0);
    const range = max - min || 1;
    const w = this.width, h = this.height;
    const pts = d.map((v, i) => `${(i / (d.length - 1)) * w},${h - (((v - min) / range) * h)}`).join(' ');
    return html`
      <svg width="${w}" height="${h}" style="vertical-align:middle">
        <polyline points="${pts}" fill="none" stroke="${this.color}" stroke-width="1.2" stroke-linejoin="round" opacity="0.7"/>
      </svg>`;
  }
}

@customElement('fc-quality-dot')
export class FcQualityDot extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline-flex; align-items: center; }
    .qdot { border-radius: 50%; flex-shrink: 0; opacity: 0.8; }
  `];
  @property({ type: Number }) quality: number | null = null;
  @property({ type: Number }) size = 6;

  render() {
    if (this.quality == null) return nothing;
    const q = this.quality;
    const c = q >= 0.7 ? '#2DD4A8' : q >= 0.4 ? '#F5B731' : '#F06464';
    return html`<span class="qdot" title="Quality: ${(q * 100).toFixed(0)}%"
      style="width:${this.size}px;height:${this.size}px;background:${c}"></span>`;
  }
}

@customElement('fc-gradient-text')
export class FcGradientText extends LitElement {
  static styles = [voidTokens, css`
    :host { display: inline; }
    .gt {
      background: linear-gradient(135deg, var(--v-accent-bright), var(--v-accent), var(--v-secondary));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
  `];

  render() {
    return html`<span class="gt"><slot></slot></span>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'fc-dot': FcDot;
    'fc-pill': FcPill;
    'fc-meter': FcMeter;
    'fc-btn': FcBtn;
    'fc-defense-gauge': FcDefenseGauge;
    'fc-pheromone-bar': FcPheromoneBar;
    'fc-sparkline': FcSparkline;
    'fc-quality-dot': FcQualityDot;
    'fc-gradient-text': FcGradientText;
  }
}
