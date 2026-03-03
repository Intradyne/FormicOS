// FormicOS v0.7.9 — Shared constants and enumerations

/**
 * Colony status enum — maps friendly names to backend status strings.
 * Use ColonyStatus.* everywhere instead of hardcoded strings.
 */
export const ColonyStatus = Object.freeze({
    IDLE:                     'IDLE',
    CREATED:                  'CREATED',
    READY:                    'READY',
    RUNNING:                  'RUNNING',
    PAUSED:                   'PAUSED',
    COMPLETED:                'COMPLETED',
    FAILED:                   'FAILED',
    HALTED_BUDGET_EXHAUSTED:  'HALTED_BUDGET_EXHAUSTED',
    WAITING_APPROVAL:         'WAITING_FOR_MCP_APPROVAL_HEADLESS',
    BLOCKED:                  'BLOCKED',
    QUEUED:                   'QUEUED_PENDING_COMPUTE'
});

/**
 * CSS badge class keyed by backend status string (ColonyStatus values).
 */
export const STATUS_BADGE_CLASS = Object.freeze({
    [ColonyStatus.RUNNING]:                  'badge-running',
    [ColonyStatus.PAUSED]:                   'badge-paused',
    [ColonyStatus.FAILED]:                   'badge-failed',
    [ColonyStatus.COMPLETED]:                'badge-completed',
    [ColonyStatus.IDLE]:                     'badge-idle',
    [ColonyStatus.CREATED]:                  'badge-created',
    [ColonyStatus.READY]:                    'badge-created',
    [ColonyStatus.HALTED_BUDGET_EXHAUSTED]:  'badge-halted',
    [ColonyStatus.WAITING_APPROVAL]:         'badge-paused',
    [ColonyStatus.BLOCKED]:                  'badge-paused',
    [ColonyStatus.QUEUED]:                   'badge-neutral'
});

/**
 * Statuses that represent a terminal (finished) colony state.
 */
export const TERMINAL_STATUSES = Object.freeze([
    ColonyStatus.COMPLETED,
    ColonyStatus.FAILED,
    ColonyStatus.HALTED_BUDGET_EXHAUSTED
]);

/**
 * Caste accent colors for topology graph nodes.
 */
export const CASTE_COLORS = Object.freeze({
    manager:    '#e91e63',
    architect:  '#9c27b0',
    coder:      '#2196f3',
    reviewer:   '#ff9800',
    researcher: '#4caf50'
});

/**
 * Known surface (tab) identifiers.
 */
export const SURFACES = Object.freeze([
    'fleet',
    'colony-workspace',
    'objects',
    'operations',
    'mission'
]);

// ── API ──────────────────────────────────────────────────────
export const API_V1 = '/api/v1';

// ── Timing Constants ─────────────────────────────────────────
export const WS_RECONNECT_MAX   = 30000;
export const POLL_FAST          = 3000;
export const POLL_SLOW          = 10000;
export const POLL_IDLE          = 30000;
export const PING_INTERVAL      = 25000;
export const APPROVAL_TIMEOUT_MS = 300000; // 5 minutes

// ── Memory Hardening Caps ────────────────────────────────────
export const MAX_LOG_ENTRIES     = 500;
export const MAX_CYTOSCAPE_NODES = 1500;
