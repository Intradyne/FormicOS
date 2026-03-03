// FormicOS v0.7.9 — Colony state display and status management

import { ColonyStatus, STATUS_BADGE_CLASS, API_V1 } from '../Constants.js';
import {
    colonyState, colonyViewState, appState,
    _lastColonyHash, set_lastColonyHash,
    setAppStateValue, setColonyViewStateValue
} from '../state.js';
import { hashString, escapeHtml, showNotification } from '../utils.js';
import { apiGet } from '../api/client.js';

/**
 * Normalize a status string to uppercase, defaulting to IDLE.
 */
export function normalizeStatus(status) {
    return String(status || ColonyStatus.IDLE).toUpperCase();
}

/**
 * Check whether the create-colony modal is currently visible.
 */
export function isCreateModalOpen() {
    const modal = document.getElementById('create-colony-modal');
    return !!(modal && !modal.classList.contains('hidden'));
}

/**
 * Return the appropriate set of form elements depending on whether
 * the create-colony modal is open or the dashboard form is active.
 */
export function getCreateFormElements() {
    if (isCreateModalOpen()) {
        return {
            taskInput: document.getElementById('new-colony-task'),
            colonyIdInput: document.getElementById('new-colony-id'),
            roundsInput: document.getElementById('new-colony-rounds'),
            teamContainer: document.getElementById('modal-team-members-list'),
            suggestStatus: document.getElementById('modal-suggest-team-status'),
            suggestButton: document.getElementById('modal-suggest-team-btn')
        };
    }
    return {
        taskInput: document.getElementById('task-input'),
        colonyIdInput: document.getElementById('mission-colony-id'),
        roundsInput: document.getElementById('rounds-input'),
        teamContainer: document.getElementById('team-members-list'),
        suggestStatus: document.getElementById('suggest-team-status'),
        suggestButton: document.getElementById('suggest-team-btn')
    };
}

/**
 * Transition the global app state and update the badge in the header.
 */
export function setAppState(newState) {
    setAppStateValue(newState);
    const el = document.getElementById('app-state-badge');
    if (el) {
        el.textContent = newState;
        el.className = 'app-state-badge app-state-' + newState;
    }
}

/**
 * Update the colony view state machine.
 */
export function setColonyViewState(newState) {
    setColonyViewStateValue(newState);
}

/**
 * Fetch colony state from the API and update the local cache + display.
 */
export function fetchColonyState() {
    if (!colonyState.colony_id) return;
    const url = API_V1 + '/colonies/' + encodeURIComponent(colonyState.colony_id);
    apiGet(url).then(function (data) {
        const hash = hashString(JSON.stringify(data));
        if (hash === _lastColonyHash) return;
        set_lastColonyHash(hash);

        colonyState.status = normalizeStatus(data.status || data.state || ColonyStatus.IDLE);
        colonyState.task = data.task || '';
        colonyState.round = data.round || data.current_round || 0;
        colonyState.max_rounds = data.max_rounds || 0;
        colonyState.agents = data.agents ? (Array.isArray(data.agents) ? data.agents.length : data.agents) : 0;
        colonyState.colony_id = data.colony_id || colonyState.colony_id;
        colonyState.headless_client_id = data.headless_client_id || data.client_id || null;
        colonyState.is_test_flight = !!data.is_test_flight;

        // Update colony view state based on status
        const statusUpper = normalizeStatus(colonyState.status);
        if (statusUpper === ColonyStatus.RUNNING || statusUpper === ColonyStatus.PAUSED) {
            setColonyViewState('active');
        } else if (statusUpper === ColonyStatus.COMPLETED) {
            setColonyViewState('completed');
        } else if (statusUpper === ColonyStatus.FAILED) {
            setColonyViewState('failed');
        }

        updateColonyStatusDisplay();
    }).catch(function () {
        // Silently fail -- server may not be ready
    });
}

/**
 * Update all colony status DOM elements from the current colonyState cache.
 */
export function updateColonyStatusDisplay() {
    const statusEl = document.getElementById('colony-status-value');
    const taskEl = document.getElementById('colony-task-value');
    const roundEl = document.getElementById('colony-round-value');
    const agentsEl = document.getElementById('colony-agents-value');
    const cardEl = document.getElementById('colony-status-card');

    const nameEl = document.getElementById('colony-name-value');
    if (nameEl) nameEl.textContent = colonyState.colony_id || 'No colony selected';

    if (statusEl) {
        statusEl.textContent = colonyState.status;
        statusEl.className = 'status-value';
        const statusColor = getStatusColor(colonyState.status);
        if (statusColor) statusEl.style.color = statusColor;
    }
    if (taskEl) taskEl.textContent = colonyState.task || 'No task';
    if (roundEl) roundEl.textContent = colonyState.round + ' / ' + colonyState.max_rounds;
    if (agentsEl) agentsEl.textContent = String(colonyState.agents);

    // Test flight visual modifiers
    const missionTab = document.getElementById('tab-mission');
    const workspaceTab = document.getElementById('tab-colony-workspace');
    const testFlightBadge = document.getElementById('colony-test-flight-badge');
    if (colonyState.is_test_flight) {
        if (missionTab) missionTab.classList.add('test-flight-mode');
        if (workspaceTab) workspaceTab.classList.add('test-flight-mode');
        if (testFlightBadge) testFlightBadge.classList.remove('hidden');
    } else {
        if (missionTab) missionTab.classList.remove('test-flight-mode');
        if (workspaceTab) workspaceTab.classList.remove('test-flight-mode');
        if (testFlightBadge) testFlightBadge.classList.add('hidden');
    }

    // Update card border for visual emphasis
    if (cardEl) {
        const c = getStatusColor(colonyState.status);
        cardEl.style.borderLeftColor = c || 'var(--border-color)';
        cardEl.style.borderLeftWidth = c ? '3px' : '1px';
    }

    // Headless approval override detection
    const overridePanel = document.getElementById('headless-override-panel');
    if (overridePanel) {
        if (colonyState.status === ColonyStatus.WAITING_APPROVAL) {
            if (statusEl) {
                statusEl.innerHTML = '<span class="badge badge-warning">BLOCKED: Awaiting API Client (' + escapeHtml(colonyState.headless_client_id || 'Unknown') + ')</span>';
                statusEl.style.color = '';
            }
            if (cardEl) {
                cardEl.style.borderLeftColor = '#FFC107';
                cardEl.style.borderLeftWidth = '3px';
                cardEl.classList.add('status-card-warning');
            }
            overridePanel.classList.remove('hidden');
            const clientEl = document.getElementById('headless-override-client');
            if (clientEl) clientEl.textContent = colonyState.headless_client_id || 'Unknown';
        } else {
            overridePanel.classList.add('hidden');
            if (cardEl) cardEl.classList.remove('status-card-warning');
        }
    }

    // Queued state display
    if (colonyState.status === ColonyStatus.QUEUED) {
        if (statusEl) {
            statusEl.innerHTML = '<span class="badge badge-neutral">QUEUED (Waiting for Resources)</span>';
            statusEl.style.color = '';
        }
        if (taskEl) taskEl.style.opacity = '0.6';
        if (roundEl) roundEl.style.opacity = '0.6';
    } else {
        if (taskEl) taskEl.style.opacity = '';
        if (roundEl) roundEl.style.opacity = '';
    }

    // Update pause/resume button
    const pauseBtn = document.getElementById('btn-pause');
    if (pauseBtn) {
        if (colonyState.status === ColonyStatus.RUNNING) {
            pauseBtn.textContent = 'Pause';
            pauseBtn.disabled = false;
        } else if (colonyState.status === ColonyStatus.PAUSED) {
            pauseBtn.textContent = 'Resume';
            pauseBtn.disabled = false;
        } else {
            pauseBtn.textContent = 'Pause';
            pauseBtn.disabled = true;
        }
    }

    // renderTopoRoundProgress() will be called from the main module
    // that owns the topology rendering logic.
}

/**
 * Map a status string to its display color.
 */
export function getStatusColor(status) {
    const map = {
        [ColonyStatus.RUNNING]:                '#4CAF50',
        [ColonyStatus.PAUSED]:                 '#FFC107',
        [ColonyStatus.FAILED]:                 '#F44336',
        [ColonyStatus.COMPLETED]:              '#2196F3',
        [ColonyStatus.IDLE]:                   '#666666',
        [ColonyStatus.CREATED]:                '#9c27b0',
        [ColonyStatus.READY]:                  '#9c27b0',
        [ColonyStatus.WAITING_APPROVAL]:       '#FFC107',
        [ColonyStatus.BLOCKED]:                '#FFC107',
        [ColonyStatus.QUEUED]:                 '#666666'
    };
    return map[String(status).toUpperCase()] || null;
}
