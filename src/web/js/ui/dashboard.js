// FormicOS v0.7.9 — Dashboard module (mission surface + colony workspace commands)
// Handles colony run, pause/resume, extend, hint injection, and results display.

import { API_V1, ColonyStatus, STATUS_BADGE_CLASS } from '../Constants.js';
import {
    colonyState,
    lastResultsColonyId, setLastResultsColonyId,
    _lastDecisionHash, set_lastDecisionHash,
    _lastTopoHash, set_lastTopoHash,
    _lastTopologySignature, set_lastTopologySignature,
    _pendingTopologyData, set_pendingTopologyData,
    _pendingTopologyRenderTimer, set_pendingTopologyRenderTimer,
    _topologyLiveMode, set_topologyLiveMode,
    _topoHistoryIdx, set_topoHistoryIdx,
    _lastColonyHash, set_lastColonyHash,
    cy,
    workspaceCurrentPath, setWorkspaceCurrentPath
} from '../state.js';
import { escapeHtml, escapeAttr, renderMarkdown, showNotification, trapFocus, releaseFocusTrap } from '../utils.js';
import { apiGet, apiPost } from '../api/client.js';
import { updateColonyStatusDisplay, fetchColonyState, normalizeStatus, setAppState, setColonyViewState } from './colony.js';
import { loadFleet } from './fleet.js';
import { clearConsole } from './console.js';

// Forward-declared imports used via cross-module calls
// (these functions are from topology.js / workspace.js but are invoked indirectly)

// ── Mission Surface (was dashboard quick-run) ────────────────
export function loadMission() {
    try {
        fetchColonyState();
        // System stats are fetched by the polling loop
    } catch (err) {
        console.error('Mission surface load error:', err);
    }
}

// ── Colony Workspace Surface (was dashboard) ─────────────────
export function loadColonyWorkspace() {
    try {
        fetchColonyState();
        // Topology + decisions + system stats fetched by polling loop
    } catch (err) {
        console.error('Colony workspace load error:', err);
    }
    const rr = document.getElementById('reuse-rounds-input');
    if (rr && colonyState.max_rounds) rr.value = colonyState.max_rounds;
    // Topology controls + workspace refresh are invoked externally by main.js
}

// ── Dashboard Commands ───────────────────────────────────────
export function dashboardRunTask() {
    const taskInput = document.getElementById('task-input');
    const colonyIdInput = document.getElementById('mission-colony-id');
    const roundsInput = document.getElementById('rounds-input');
    if (!taskInput || !taskInput.value.trim()) {
        showNotification('Enter a task first', 'warning');
        return;
    }

    const task = taskInput.value.trim();
    const rounds = parseInt(roundsInput.value) || 5;
    const agents = [];
    const rows = document.querySelectorAll('#team-members-list .team-member-row');
    for (let i = 0; i < rows.length; i++) {
        const casteEl = rows[i].querySelector('.member-caste');
        const subcasteEl = rows[i].querySelector('.member-subcaste');
        const caste = casteEl ? casteEl.value : '';
        if (!caste) continue;
        agents.push({
            caste: caste,
            subcaste_tier: subcasteEl ? subcasteEl.value : 'balanced'
        });
    }

    const payload = { task: task, max_rounds: rounds };
    if (agents.length) payload.agents = agents;
    if (colonyIdInput && colonyIdInput.value.trim()) {
        payload.colony_id = colonyIdInput.value.trim();
    }

    apiPost(API_V1 + '/colonies', payload).then(function (data) {
        const colonyId = data.colony_id || (colonyIdInput ? colonyIdInput.value.trim() : '');
        if (!colonyId) throw new Error('Colony ID missing from create response');
        return apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/start', {}).then(function () {
            return colonyId;
        });
    }).then(function (colonyId) {
        showNotification('Colony started: ' + colonyId, 'success');
        colonyState.status = ColonyStatus.RUNNING;
        colonyState.task = task;
        colonyState.max_rounds = rounds;
        colonyState.round = 0;
        colonyState.colony_id = colonyId;
        setColonyViewState('active');
        updateColonyStatusDisplay();
        clearConsole();
        set_lastDecisionHash('');
        set_lastTopoHash('');
        set_lastTopologySignature('');
        set_pendingTopologyData(null);
        if (_pendingTopologyRenderTimer) { clearTimeout(_pendingTopologyRenderTimer); set_pendingTopologyRenderTimer(null); }
        set_topologyLiveMode(true);
        set_topoHistoryIdx(-1);
        // Subscribe to the new colony (handled by main.js subscribeToColony)
        if (typeof window.subscribeToColony === 'function') {
            window.subscribeToColony(colonyState.colony_id);
        }
        loadFleet();
        // Navigate to colony workspace
        if (colonyState.colony_id) {
            window.location.hash = '#colony/' + encodeURIComponent(colonyState.colony_id);
        }
    }).catch(function (err) {
        showNotification('Failed to create/start colony: ' + err.message, 'error');
    });
}

export function dashboardExtendRounds() {
    const roundsInput = document.getElementById('rounds-input') || document.getElementById('ws-extend-rounds');
    const n = parseInt(roundsInput ? roundsInput.value : '3') || 3;
    if (!colonyState.colony_id) {
        showNotification('No colony active', 'warning');
        return;
    }

    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyState.colony_id) + '/extend', { rounds: n }).then(function (data) {
        showNotification('Extended by ' + n + ' rounds', 'success');
        colonyState.max_rounds = data.new_max_rounds || data.new_max || (colonyState.max_rounds + n);
        updateColonyStatusDisplay();
    }).catch(function (err) {
        showNotification('Failed to extend: ' + err.message, 'error');
    });
}

export function dashboardPauseResume() {
    if (!colonyState.colony_id) return;
    const colonyId = encodeURIComponent(colonyState.colony_id);

    if (colonyState.status === ColonyStatus.RUNNING) {
        apiPost(API_V1 + '/colonies/' + colonyId + '/pause', {}).then(function () {
            colonyState.status = ColonyStatus.PAUSED;
            updateColonyStatusDisplay();
            showNotification('Colony paused', 'info');
        }).catch(function (err) {
            showNotification('Pause failed: ' + err.message, 'error');
        });
    } else if (colonyState.status === ColonyStatus.PAUSED) {
        apiPost(API_V1 + '/colonies/' + colonyId + '/resume', {}).then(function () {
            colonyState.status = ColonyStatus.RUNNING;
            updateColonyStatusDisplay();
            showNotification('Colony resumed', 'success');
        }).catch(function (err) {
            showNotification('Resume failed: ' + err.message, 'error');
        });
    }
}

export function dashboardInjectHint() {
    const hintInput = document.getElementById('hint-input') || document.getElementById('ws-hint-input');
    if (!hintInput || !hintInput.value.trim()) {
        showNotification('Enter a hint first', 'warning');
        return;
    }
    if (!colonyState.colony_id) {
        showNotification('No colony active', 'warning');
        return;
    }

    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyState.colony_id) + '/intervene', { hint: hintInput.value.trim() }).then(function () {
        showNotification('Hint injected', 'success');
        hintInput.value = '';
    }).catch(function (err) {
        showNotification('Hint failed: ' + err.message, 'error');
    });
}

// ── Results ──────────────────────────────────────────────────
export function fetchAndShowResults(colonyId) {
    const cid = colonyId || colonyState.colony_id;
    if (!cid) return;
    setLastResultsColonyId(cid);
    apiGet(API_V1 + '/colonies/' + encodeURIComponent(cid) + '/results').then(function (data) {
        const body = document.getElementById('results-body');
        if (!body) return;

        const answer = data.final_answer || data.answer || '';
        const summary = data.summary || '';
        const files = data.workspace_files || data.files || [];
        const status = normalizeStatus(data.status || '');
        const failure = data.failure || {};

        let html = '';
        if (status) {
            const badgeClass = STATUS_BADGE_CLASS[status] || 'badge-neutral';
            html += '<div style="margin-bottom:10px"><span class="badge ' + badgeClass + '">' + escapeHtml(status) + '</span></div>';
        }
        html += '<h4>Final Answer</h4>';
        if (answer) {
            html += '<div>' + renderMarkdown(answer) + '</div>';
        } else {
            html += '<p class="text-muted">No final answer produced.</p>';
            if (summary) {
                html += '<h4>Run Summary</h4>';
                html += '<div>' + renderMarkdown(summary) + '</div>';
            }
            if (failure && (failure.code || failure.detail)) {
                html += '<div class="governance-alert">';
                html += '<strong>' + escapeHtml(failure.code || 'COLONY_FAILED') + '</strong>';
                if (failure.detail) html += ': ' + escapeHtml(failure.detail);
                html += '</div>';
            }
        }

        if (files.length > 0) {
            html += '<h4>Workspace Files</h4><ul class="workspace-file-list">';
            for (let i = 0; i < files.length; i++) {
                html += '<li class="font-mono font-sm">' +
                    '<a href="#" class="workspace-file-link" onclick="viewWorkspaceFile(\'' +
                    escapeAttr(cid) + '\', \'' + escapeAttr(files[i]) +
                    '\'); return false;">' + escapeHtml(files[i]) + '</a></li>';
            }
            html += '</ul>';
        }

        body.innerHTML = html;
        const resultsModal = document.getElementById('results-modal');
        resultsModal.classList.remove('hidden');
        trapFocus(resultsModal);
    }).catch(function (err) {
        showNotification('Failed to load results: ' + err.message, 'error');
    });
}

export function hideResultsModal() {
    const modal = document.getElementById('results-modal');
    releaseFocusTrap(modal);
    if (modal) modal.classList.add('hidden');
}
