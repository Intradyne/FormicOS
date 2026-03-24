import { css } from 'lit';

/** Void Protocol design tokens as CSS custom properties */
export const voidTokens = css`
  :host {
    /* Surfaces */
    --v-void: #08080F;
    --v-surface: #10111A;
    --v-elevated: #1A1B26;
    --v-recessed: #050508;

    /* Borders */
    --v-border: rgba(255,255,255,0.06);
    --v-border-hover: rgba(255,255,255,0.14);
    --v-border-accent: rgba(232,88,26,0.22);

    /* Foreground */
    --v-fg: #EDEDF0;
    --v-fg-muted: #6B6B76;
    --v-fg-dim: #45454F;
    --v-fg-on-accent: #0A0A0F;

    /* Accent */
    --v-accent: #E8581A;
    --v-accent-bright: #F4763A;
    --v-accent-deep: #B8440F;
    --v-accent-muted: rgba(232,88,26,0.08);
    --v-accent-glow: rgba(232,88,26,0.16);

    /* Secondary */
    --v-secondary: #3DD6F5;
    --v-secondary-muted: rgba(61,214,245,0.07);
    --v-secondary-glow: rgba(61,214,245,0.12);

    /* Semantic */
    --v-success: #2DD4A8;
    --v-warn: #F5B731;
    --v-danger: #F06464;
    --v-purple: #A78BFA;
    --v-blue: #5B9CF5;

    /* Confidence tiers */
    --v-tier-high: #2DD4A8;
    --v-tier-moderate: #F5B731;
    --v-tier-low: #F5B731;
    --v-tier-exploratory: #F06464;
    --v-tier-stale: #6B6B76;

    /* Service */
    --v-service: #22D3EE;
    --v-service-muted: rgba(34,211,238,0.08);
    --v-service-glow: rgba(34,211,238,0.14);

    /* Glass */
    --v-glass: rgba(16,17,26,0.60);
    --v-glass-hover: rgba(26,27,38,0.78);

    /* Pheromone levels */
    --v-pheromone-weak: rgba(232,88,26,0.04);
    --v-pheromone-mid: rgba(232,88,26,0.12);
    --v-pheromone-strong: rgba(232,88,26,0.25);

    /* Provider colors */
    --provider-local: var(--v-success);
    --provider-anthropic: var(--v-accent);
    --provider-gemini: var(--v-blue);

    /* Typography */
    --f-display: 'Satoshi','General Sans','DM Sans',system-ui,sans-serif;
    --f-body: 'Geist','DM Sans','Plus Jakarta Sans',system-ui,sans-serif;
    --f-mono: 'IBM Plex Mono','JetBrains Mono',monospace;
  }
`;

/** Common utility styles */
export const sharedStyles = css`
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.25; }
  }

  .glass {
    background: var(--v-glass);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--v-border);
    border-radius: 10px;
    padding: 14px;
    transition: all 0.25s cubic-bezier(0.22,1,0.36,1);
  }
  .glass:hover { border-color: var(--v-border-hover); }
  .glass.featured { border-color: var(--v-border-accent); box-shadow: 0 0 28px var(--v-accent-glow); }
  .glass.clickable { cursor: pointer; }
  .glass.clickable:hover { background: var(--v-glass-hover); transform: translateY(-1px); }

  .s-label {
    font-size: 10.5px;
    font-family: var(--f-mono);
    font-weight: 600;
    color: var(--v-fg-dim);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 7px;
  }

  .mono { font-family: var(--f-mono); }
  .tnum { font-feature-settings: 'tnum'; }
  .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .empty-state {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; height: 100%; gap: 8px;
    text-align: center; padding: 40px;
  }
  .empty-icon { font-size: 32px; opacity: 0.3; }
  .empty-title { font-size: 14px; font-weight: 600; color: var(--v-fg-muted); }
  .empty-desc { font-size: 12px; color: var(--v-fg-dim); max-width: 320px; line-height: 1.55; }
`;
