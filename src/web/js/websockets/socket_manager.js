// FormicOS v0.7.9 — WebSocket connection manager and event routing

import { ColonyStatus, PING_INTERVAL, WS_RECONNECT_MAX } from '../Constants.js';
import {
    ws, wsPingInterval, wsReconnectTimeout, wsReconnectDelay, wsReconnectAttempts,
    colonyState, appState, currentTab,
    setWs, setWsPingInterval, setWsReconnectTimeout,
    setWsReconnectDelay, setWsReconnectAttempts
} from '../state.js';
import { showNotification } from '../utils.js';
import {
    appendStreamToken, appendToolCall, handleRoundUpdate,
    handleColonyComplete, handleWsError
} from '../ui/console.js';
import {
    showApprovalModal, handleHeadlessApprovalRequested,
    handleColonySpawned, handleEpochAdvanced
} from '../ui/modals.js';
import { setAppState } from '../ui/colony.js';

/**
 * Establish WebSocket connection to the v1 event endpoint.
 */
export function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = protocol + '//' + window.location.host + '/api/v1/ws/events';

    updateWsIndicator('connecting');

    try {
        const socket = new WebSocket(url);
        setWs(socket);
    } catch (err) {
        console.error('WebSocket creation failed:', err);
        setAppState('disconnected');
        scheduleReconnect();
        return;
    }

    ws.onopen = function () {
        setWsReconnectDelay(3000);
        setWsReconnectAttempts(0);
        updateWsIndicator('connected');
        updateOperationsWsStatus('Connected');
        showNotification('WebSocket connected', 'success');

        if (appState === 'disconnected' || appState === 'degraded') {
            setAppState('ready');
        }

        // Subscribe to current colony if any
        if (colonyState.colony_id) {
            subscribeToColony(colonyState.colony_id);
        }

        // Start ping keepalive
        clearInterval(wsPingInterval);
        const pingId = setInterval(function () {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, PING_INTERVAL);
        setWsPingInterval(pingId);
    };

    ws.onmessage = function (event) {
        try {
            const msg = JSON.parse(event.data);
            // Route as v1 event envelope if it has a type field matching v1 patterns
            if (msg.type && msg.type.indexOf('.') >= 0) {
                routeEventEnvelope(msg);
            } else {
                routeWsMessage(msg);
            }
        } catch (err) {
            console.error('WS message parse error:', err);
        }
    };

    ws.onclose = function (event) {
        clearInterval(wsPingInterval);
        updateWsIndicator('disconnected');
        updateOperationsWsStatus('Disconnected');
        setAppState('disconnected');

        if (!event.wasClean) {
            scheduleReconnect();
        }
    };

    ws.onerror = function (err) {
        console.error('WebSocket error:', err);
        updateWsIndicator('disconnected');
        setAppState('degraded');
    };
}

/**
 * Subscribe the WS connection to colony-specific events.
 */
export function subscribeToColony(colonyId) {
    if (ws && ws.readyState === WebSocket.OPEN && colonyId) {
        ws.send(JSON.stringify({ action: 'subscribe', colony_id: colonyId }));
    }
}

/**
 * Schedule a reconnect attempt with exponential backoff.
 */
export function scheduleReconnect() {
    if (wsReconnectTimeout) clearTimeout(wsReconnectTimeout);
    setWsReconnectAttempts(wsReconnectAttempts + 1);
    updateOperationsWsReconnects(wsReconnectAttempts);

    const tid = setTimeout(function () {
        connectWebSocket();
    }, wsReconnectDelay);
    setWsReconnectTimeout(tid);

    // Exponential backoff: 3s -> 6s -> 12s -> 24s -> 30s max
    setWsReconnectDelay(Math.min(wsReconnectDelay * 2, WS_RECONNECT_MAX));
}

/**
 * Force-reconnect the WebSocket (close existing + fresh connect).
 */
export function reconnectWebSocket() {
    if (ws) {
        ws.close();
    }
    setWsReconnectDelay(3000);
    setWsReconnectAttempts(0);
    connectWebSocket();
}

/**
 * Update the visual WebSocket connection indicator.
 */
export function updateWsIndicator(state) {
    const el = document.getElementById('ws-status');
    if (!el) return;
    el.className = 'ws-indicator';
    if (state === 'connected')       el.classList.add('ws-connected');
    else if (state === 'connecting') el.classList.add('ws-connecting');
    else                             el.classList.add('ws-disconnected');
    el.title = 'WebSocket ' + state;
}

/**
 * Update the Operations page WS status text.
 */
export function updateOperationsWsStatus(text) {
    const el = document.getElementById('settings-ws-status');
    if (el) el.textContent = text;
}

/**
 * Update the Operations page WS reconnect count.
 */
export function updateOperationsWsReconnects(n) {
    const el = document.getElementById('settings-ws-reconnects');
    if (el) el.textContent = String(n);
}

/**
 * Route a v1-style event envelope (type contains '.') to the appropriate handler.
 */
export function routeEventEnvelope(env) {
    // Filter events to the currently active colony
    if (env.colony_id && colonyState.colony_id) {
        if (env.colony_id !== colonyState.colony_id) return;
    }
    const p = env.payload || {};

    switch (env.type) {
        case 'colony.round.phase':
            handleRoundUpdate({
                round: p.round !== undefined ? p.round : env.round,
                phase: p.phase || env.phase,
                colony_id: env.colony_id
            });
            break;
        case 'agent.token':
            appendStreamToken({
                agent_id: p.agent_id || env.agent_id,
                token: p.token || env.token
            });
            break;
        case 'agent.tool.call':
            appendToolCall({
                agent_id: p.agent_id || env.agent_id,
                tool: p.tool || env.tool || p.name || p.tool_name,
                args: p.args || env.args || p.arguments,
                result: p.result || env.result
            });
            break;
        case 'approval.requested':
            showApprovalModal({
                request_id: p.request_id || env.request_id,
                agent_id: p.agent_id || env.agent_id,
                tool: p.tool || env.tool || p.name || p.tool_name,
                args: p.args || env.args || p.arguments
            });
            break;
        case 'approval.requested.headless':
            handleHeadlessApprovalRequested({
                request_id: p.request_id || env.request_id,
                agent_id: p.agent_id || env.agent_id,
                tool: p.tool || env.tool || p.name || p.tool_name,
                args: p.args || env.args || p.arguments,
                client_id: p.client_id || env.client_id
            });
            break;
        case 'colony.spawned':
            handleColonySpawned(p);
            break;
        case 'colony.epoch_advanced':
            handleEpochAdvanced(p, env);
            break;
        case 'colony.completed':
            handleColonyComplete({
                colony_id: env.colony_id,
                outcome: p.outcome || 'success'
            });
            break;
        case 'colony.failed':
            if (p.message) handleWsError({ message: p.message });
            handleColonyComplete({ colony_id: env.colony_id, outcome: 'failed' });
            break;
        default:
            console.log('Unknown v1 event type:', env.type);
    }
}

/**
 * Route a legacy WS message (backward compat) to the appropriate handler.
 */
export function routeWsMessage(msg) {
    // Filter stream messages to the currently active colony
    const streamTypes = { token_stream: 1, tool_call: 1, round_update: 1, colony_complete: 1, error: 1 };
    if (msg.colony_id && colonyState.colony_id && streamTypes[msg.type]) {
        if (msg.colony_id !== colonyState.colony_id) return;
    }

    switch (msg.type) {
        case 'token_stream':
            appendStreamToken(msg);
            break;
        case 'tool_call':
            appendToolCall(msg);
            break;
        case 'round_update':
            handleRoundUpdate(msg);
            break;
        case 'approval_request':
            showApprovalModal(msg);
            break;
        case 'colony_complete':
            handleColonyComplete(msg);
            break;
        case 'error':
            handleWsError(msg);
            break;
        case 'colony_spawned':
            handleColonySpawned(msg);
            break;
        case 'epoch_advanced':
            handleEpochAdvanced(msg, msg);
            break;
        case 'pong':
            break; // keepalive reply
        default:
            console.log('Unknown WS message type:', msg.type);
    }
}
