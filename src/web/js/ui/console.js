// FormicOS v0.7.9 — Streaming console output and round event handlers

import { ColonyStatus, MAX_LOG_ENTRIES } from '../Constants.js';
import { colonyState } from '../state.js';
import { truncateStr, showNotification } from '../utils.js';
import { setColonyViewState, updateColonyStatusDisplay, fetchColonyState } from './colony.js';

/** Tracks agents already registered in the filter dropdown. */
let _consoleSeenAgents = {};

/**
 * Append a streaming token from an agent to the console.
 */
export function appendStreamToken(msg) {
    const console_el = document.getElementById('streaming-console');
    if (!console_el) return;

    const agentId = msg.agent_id || 'agent';
    const token = msg.token || '';
    if (!console_el._agentStreams) console_el._agentStreams = {};
    let streamEl = console_el._agentStreams[agentId];
    if (!streamEl) {
        const divider = document.createElement('span');
        divider.className = 'console-divider';
        console_el.appendChild(divider);

        const row = document.createElement('div');
        row.className = 'console-agent-row';
        row.setAttribute('data-agent', agentId);
        registerConsoleAgent(agentId);

        // Respect active filter
        const activeFilter = document.getElementById('console-agent-filter');
        if (activeFilter && activeFilter.value && activeFilter.value !== agentId) {
            row.style.display = 'none';
        }

        const label = document.createElement('span');
        label.className = 'console-agent-label';
        label.textContent = '[' + agentId + ']';
        row.appendChild(label);

        streamEl = document.createElement('span');
        streamEl.className = 'console-token';
        row.appendChild(streamEl);

        console_el.appendChild(row);
        console_el._agentStreams[agentId] = streamEl;
    }
    streamEl.textContent += token;

    // DOM cap: prune oldest entries to prevent memory bloat
    pruneConsole(console_el);
    autoScrollConsole();
}

/**
 * Append a tool call entry to the console.
 */
export function appendToolCall(msg) {
    const console_el = document.getElementById('streaming-console');
    if (!console_el) return;

    const tool = msg.tool || msg.tool_name || msg.name || msg.id || '<missing-tool>';
    const args = msg.args || msg.arguments || {};
    const result = msg.result;

    const callEl = document.createElement('span');
    callEl.className = 'console-tool';
    callEl.textContent = 'TOOL: ' + tool + '(' + truncateStr(JSON.stringify(args), 200) + ')';
    console_el.appendChild(callEl);

    if (result !== undefined && result !== null) {
        const resultEl = document.createElement('span');
        resultEl.className = 'console-tool-result';
        resultEl.textContent = 'RESULT: ' + truncateStr(String(result), 500);
        console_el.appendChild(resultEl);
    }

    pruneConsole(console_el);
    autoScrollConsole();
}

/**
 * Handle a round_update event: update colony state and trigger data refresh.
 */
export function handleRoundUpdate(msg) {
    if (msg.round !== undefined) colonyState.round = msg.round;
    if (msg.phase) updatePhaseDisplay(msg.phase);
    setColonyViewState('active');
    // Trigger immediate refresh
    fetchColonyState();
    // fetchTopoHistory and loadFleet will be called from the main module
}

/**
 * Handle a colony_complete event: update state and show results.
 */
export function handleColonyComplete(msg) {
    const outcome = msg.outcome || 'completed';
    colonyState.status = outcome === 'success' ? ColonyStatus.COMPLETED : ColonyStatus.FAILED;
    setColonyViewState(outcome === 'success' ? 'completed' : 'failed');
    // Keep colony_id so workspace tab still shows files after completion
    updateColonyStatusDisplay();
    showNotification(
        'Colony ' + (msg.colony_id || '') + ' ' + outcome,
        outcome === 'success' ? 'success' : 'warning'
    );

    // refreshWorkspace and fetchAndShowResults will be called from the main module
}

/**
 * Handle a WS error event: show notification and append to console.
 */
export function handleWsError(msg) {
    showNotification(msg.message || 'Unknown error', 'error');
    const console_el = document.getElementById('streaming-console');
    if (console_el) {
        const errEl = document.createElement('span');
        errEl.className = 'console-error';
        errEl.textContent = '\nERROR: ' + (msg.message || 'Unknown') + '\n';
        console_el.appendChild(errEl);
        autoScrollConsole();
    }
}

/**
 * Update the phase display within the round status line.
 */
export function updatePhaseDisplay(phase) {
    const el = document.getElementById('colony-round-value');
    if (el) {
        el.textContent = colonyState.round + ' / ' + colonyState.max_rounds + '  [' + phase + ']';
    }
}

/**
 * Auto-scroll the console to the bottom if auto-scroll is enabled.
 */
export function autoScrollConsole() {
    const cb = document.getElementById('console-autoscroll');
    if (cb && cb.checked) {
        const console_el = document.getElementById('streaming-console');
        if (console_el) {
            console_el.scrollTop = console_el.scrollHeight;
        }
    }
}

/**
 * Clear all console output and reset agent tracking state.
 */
export function clearConsole() {
    const console_el = document.getElementById('streaming-console');
    if (console_el) {
        console_el.innerHTML = '';
        console_el._currentAgent = null;
        console_el._agentStreams = null;
    }
    _consoleSeenAgents = {};
    const select = document.getElementById('console-agent-filter');
    if (select) { select.innerHTML = '<option value="">All agents</option>'; }
}

/**
 * Register a new agent in the console filter dropdown.
 */
export function registerConsoleAgent(agentId) {
    if (_consoleSeenAgents[agentId]) return;
    _consoleSeenAgents[agentId] = true;
    const select = document.getElementById('console-agent-filter');
    if (!select) return;
    const opt = document.createElement('option');
    opt.value = agentId;
    opt.textContent = agentId;
    select.appendChild(opt);
}

/**
 * Show/hide console rows based on the selected agent filter.
 */
export function filterConsoleByAgent(agentId) {
    const console_el = document.getElementById('streaming-console');
    if (!console_el) return;
    const rows = console_el.querySelectorAll('.console-agent-row');
    for (let i = 0; i < rows.length; i++) {
        rows[i].style.display = (!agentId || rows[i].getAttribute('data-agent') === agentId) ? '' : 'none';
    }
}

/**
 * Memory hardening: enforce MAX_LOG_ENTRIES cap on console entries.
 * Removes oldest children (FIFO) when the cap is exceeded.
 * Also purges stale _agentStreams references whose DOM nodes have been removed.
 */
export function pruneConsole(console_el) {
    if (!console_el) return;
    while (console_el.childNodes.length > MAX_LOG_ENTRIES) {
        console_el.removeChild(console_el.firstChild);
    }
    // Purge stale _agentStreams references
    if (console_el._agentStreams) {
        for (const key in console_el._agentStreams) {
            if (!console_el._agentStreams[key].parentNode) {
                delete console_el._agentStreams[key];
            }
        }
    }
}
