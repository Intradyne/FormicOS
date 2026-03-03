// FormicOS v0.7.9 — Mutable shared application state

import { ColonyStatus } from './Constants.js';

// ── WebSocket State ──────────────────────────────────────────
export let ws = null;
export let wsPingInterval = null;
export let wsReconnectTimeout = null;
export let wsReconnectDelay = 3000;
export let wsReconnectAttempts = 0;

export function setWs(v) { ws = v; }
export function setWsPingInterval(v) { wsPingInterval = v; }
export function setWsReconnectTimeout(v) { wsReconnectTimeout = v; }
export function setWsReconnectDelay(v) { wsReconnectDelay = v; }
export function setWsReconnectAttempts(v) { wsReconnectAttempts = v; }

// ── Polling & Graph State ────────────────────────────────────
export let pollInterval = null;
export let cy = null;
export let currentTab = 'fleet';
export let currentGraphView = 'topology';
export let cachedTopology = null;
export let cachedTkg = null;

export function setPollInterval(v) { pollInterval = v; }
export function setCy(v) { cy = v; }
export function setCurrentTab(v) { currentTab = v; }
export function setCurrentGraphView(v) { currentGraphView = v; }
export function setCachedTopology(v) { cachedTopology = v; }
export function setCachedTkg(v) { cachedTkg = v; }

// ── Approval & Editor State ─────────────────────────────────
export let currentApprovalRequestId = null;
export let approvalTimeoutTimer = null;
export let currentPromptCaste = null;
export let editingSkillId = null;

export function setCurrentApprovalRequestId(v) { currentApprovalRequestId = v; }
export function setApprovalTimeoutTimer(v) { approvalTimeoutTimer = v; }
export function setCurrentPromptCaste(v) { currentPromptCaste = v; }
export function setEditingSkillId(v) { editingSkillId = v; }

// ── Workspace State ──────────────────────────────────────────
export let workspaceCurrentPath = '';
export let lastResultsColonyId = null;
export let workspaceArchiveState = {
    colonyId: null,
    files: [],
    selected: {},
    filter: ''
};

export function setWorkspaceCurrentPath(v) { workspaceCurrentPath = v; }
export function setLastResultsColonyId(v) { lastResultsColonyId = v; }
export function setWorkspaceArchiveState(v) { workspaceArchiveState = v; }

// ── API Key Management State ─────────────────────────────────
export let _lastApiKeysHash = '';
export let _generatedKeyFull = null;

export function set_lastApiKeysHash(v) { _lastApiKeysHash = v; }
export function set_generatedKeyFull(v) { _generatedKeyFull = v; }

// ── Compute & Queue State ────────────────────────────────────
export let _lastQueueHash = '';

export function set_lastQueueHash(v) { _lastQueueHash = v; }

// ── Diagnostics State ────────────────────────────────────────
export let _lastDiagnosticsHash = '';

export function set_lastDiagnosticsHash(v) { _lastDiagnosticsHash = v; }

// ── Hash Guards for DOM Update De-duplication ────────────────
export let _lastTopoHash = '';
export let _lastDecisionHash = '';
export let _lastColonyHash = '';
export let _lastSystemHash = '';
export let _lastHealthHash = '';
export let _lastFleetHash = '';

export function set_lastTopoHash(v) { _lastTopoHash = v; }
export function set_lastDecisionHash(v) { _lastDecisionHash = v; }
export function set_lastColonyHash(v) { _lastColonyHash = v; }
export function set_lastSystemHash(v) { _lastSystemHash = v; }
export function set_lastHealthHash(v) { _lastHealthHash = v; }
export function set_lastFleetHash(v) { _lastFleetHash = v; }

// ── Fleet Pagination ─────────────────────────────────────────
export let _fleetPage = 0;
export let _fleetPageSize = 50;
export let _fleetTotal = 0;

export function set_fleetPage(v) { _fleetPage = v; }
export function set_fleetPageSize(v) { _fleetPageSize = v; }
export function set_fleetTotal(v) { _fleetTotal = v; }

// ── Topology State ───────────────────────────────────────────
export let _lastTopoHistoryFetchTs = 0;
export let _lastTopologySignature = '';
export let _graphInteractionLock = false;
export let _graphInteractionTimer = null;
export let _pendingTopologyData = null;
export let _pendingTopologyRenderTimer = null;
export let _lastTopologyRenderTs = 0;
export let _topologyRenderIntervalMs = 220;
export let _topologyLiveMode = true;
export let _topoHistoryIdx = -1;
export let _topoHistory = [];

export function set_lastTopoHistoryFetchTs(v) { _lastTopoHistoryFetchTs = v; }
export function set_lastTopologySignature(v) { _lastTopologySignature = v; }
export function set_graphInteractionLock(v) { _graphInteractionLock = v; }
export function set_graphInteractionTimer(v) { _graphInteractionTimer = v; }
export function set_pendingTopologyData(v) { _pendingTopologyData = v; }
export function set_pendingTopologyRenderTimer(v) { _pendingTopologyRenderTimer = v; }
export function set_lastTopologyRenderTs(v) { _lastTopologyRenderTs = v; }
export function set_topologyRenderIntervalMs(v) { _topologyRenderIntervalMs = v; }
export function set_topologyLiveMode(v) { _topologyLiveMode = v; }
export function set_topoHistoryIdx(v) { _topoHistoryIdx = v; }
export function set_topoHistory(v) { _topoHistory = v; }

// ── App + Colony State Machines ──────────────────────────────
export let appState = 'booting';            // booting|ready|degraded|disconnected
export let colonyViewState = 'none_selected'; // none_selected|loading|active|completed|failed

export function setAppStateValue(v) { appState = v; }
export function setColonyViewStateValue(v) { colonyViewState = v; }

// ── Colony State Cache ───────────────────────────────────────
export const colonyState = {
    status: ColonyStatus.IDLE,
    task: '',
    round: 0,
    max_rounds: 0,
    agents: 0,
    colony_id: null,
    is_test_flight: false
};
