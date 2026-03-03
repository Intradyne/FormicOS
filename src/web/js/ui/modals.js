// FormicOS v0.7.9 — Modal dialogs: approvals, headless overrides, colony events

import { ColonyStatus, STATUS_BADGE_CLASS, APPROVAL_TIMEOUT_MS, API_V1 } from '../Constants.js';
import {
    colonyState,
    currentApprovalRequestId, approvalTimeoutTimer,
    _lastFleetHash,
    setCurrentApprovalRequestId, setApprovalTimeoutTimer,
    set_lastFleetHash
} from '../state.js';
import { escapeHtml, escapeAttr, showNotification, trapFocus, releaseFocusTrap } from '../utils.js';
import { apiPost } from '../api/client.js';

/**
 * Handle a headless approval request event — populate and show the override panel.
 */
export function handleHeadlessApprovalRequested(data) {
    // Populate override panel details
    const toolEl = document.getElementById('headless-override-tool');
    const argsEl = document.getElementById('headless-override-args');
    const clientEl = document.getElementById('headless-override-client');

    if (toolEl) toolEl.textContent = data.tool || 'unknown';
    if (argsEl) argsEl.textContent = JSON.stringify(data.args || {}, null, 2);
    if (clientEl) clientEl.textContent = data.client_id || 'Unknown';

    // Force panel visible (status display may not have caught up yet)
    const overridePanel = document.getElementById('headless-override-panel');
    if (overridePanel) overridePanel.classList.remove('hidden');

    const statusEl = document.getElementById('colony-status-value');
    if (statusEl) {
        statusEl.innerHTML = '<span class="badge badge-warning">BLOCKED: Awaiting API Client (' + escapeHtml(data.client_id || colonyState.headless_client_id || 'Unknown') + ')</span>';
        statusEl.style.color = '';
    }

    const cardEl = document.getElementById('colony-status-card');
    if (cardEl) {
        cardEl.style.borderLeftColor = '#FFC107';
        cardEl.style.borderLeftWidth = '3px';
        cardEl.classList.add('status-card-warning');
    }

    showNotification('Headless colony blocked -- awaiting API client or manual override', 'warning');
}

/**
 * Force-approve or force-deny a headless approval via the override API.
 */
export function overrideHeadlessApproval(approved) {
    if (!colonyState.colony_id) {
        showNotification('No colony selected for override', 'warning');
        return;
    }

    apiPost(API_V1 + '/approvals/override', {
        colony_id: colonyState.colony_id,
        approved: approved,
        reason: 'Manual UI Operator Override'
    }).then(function () {
        showNotification(approved ? 'Headless approval force-approved' : 'Headless approval force-denied', approved ? 'success' : 'info');

        const overridePanel = document.getElementById('headless-override-panel');
        if (overridePanel) overridePanel.classList.add('hidden');

        const cardEl = document.getElementById('colony-status-card');
        if (cardEl) cardEl.classList.remove('status-card-warning');
    }).catch(function (err) {
        showNotification('Override failed: ' + err.message, 'error');
    });
}

/**
 * Handle a colony.spawned event — insert a new row into the fleet table.
 */
export function handleColonySpawned(data) {
    const tbody = document.getElementById('fleet-tbody');
    // Import currentTab via state would create a dependency; check DOM instead
    if (!tbody) {
        set_lastFleetHash('');
        return;
    }
    const colonyId = data.colony_id || '--';
    const status = data.status || 'initializing';
    const statusUpper = String(status).toUpperCase();
    const badgeClass = STATUS_BADGE_CLASS[statusUpper] || 'badge-neutral';
    let originBadge = '';
    if (data.origin === 'api') {
        originBadge = ' <span class="badge-api-client">\uD83E\uDD16 API Client: ' + escapeHtml(data.client_id || 'Unknown') + '</span>';
    }
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="font-mono">' + escapeHtml(colonyId) + originBadge + '</td>'
        + '<td class="truncate" style="max-width:250px">--</td>'
        + '<td><span class="badge ' + badgeClass + '">' + escapeHtml(statusUpper) + '</span></td>'
        + '<td>0/0</td>'
        + '<td>Ready</td>'
        + '<td class="fleet-actions"><button class="btn btn-secondary btn-sm" onclick="viewColony(\'' + escapeAttr(colonyId) + '\')">View</button></td>';
    const emptyRow = tbody.querySelector('.empty-state');
    if (emptyRow) emptyRow.closest('tr').remove();
    tbody.insertBefore(tr, tbody.firstChild);
    set_lastFleetHash('');
    showNotification('New colony spawned: ' + colonyId, 'info');
}

/**
 * Handle a colony.epoch_advanced event — flash-update the round display.
 */
export function handleEpochAdvanced(data, env) {
    const cid = env.colony_id || data.colony_id;
    if (cid !== colonyState.colony_id) return;
    const roundEl = document.getElementById('colony-round-value');
    if (!roundEl) return;
    const round = data.round || data.epoch || colonyState.round;
    roundEl.textContent = round + ' / ' + (data.max_rounds || colonyState.max_rounds);
    roundEl.classList.add('flash-update');
    setTimeout(function () { roundEl.classList.remove('flash-update'); }, 600);
}

/**
 * Show the HITL approval modal with tool call details and timeout bar.
 */
export function showApprovalModal(data) {
    // Guard: headless approvals go through the override panel, not this modal
    if (colonyState.status === ColonyStatus.WAITING_APPROVAL) {
        handleHeadlessApprovalRequested(data);
        return;
    }

    setCurrentApprovalRequestId(data.request_id);

    const agentEl = document.getElementById('approval-agent');
    const toolEl = document.getElementById('approval-tool');
    const argsEl = document.getElementById('approval-args');

    if (agentEl) agentEl.textContent = data.agent_id || 'agent';
    if (toolEl) toolEl.textContent = data.tool || 'unknown';
    if (argsEl) argsEl.textContent = JSON.stringify(data.args, null, 2);

    // Show modal
    const approvalModal = document.getElementById('approval-modal');
    approvalModal.classList.remove('hidden');
    trapFocus(approvalModal);

    // Start timeout bar animation (5 minutes)
    const timeoutBar = document.getElementById('approval-timeout');
    if (timeoutBar) {
        timeoutBar.style.transition = 'none';
        timeoutBar.style.width = '100%';
        // Force reflow
        timeoutBar.offsetHeight;
        timeoutBar.style.transition = 'width ' + (APPROVAL_TIMEOUT_MS / 1000) + 's linear';
        timeoutBar.style.width = '0%';
    }

    // Auto-deny after timeout
    clearTimeout(approvalTimeoutTimer);
    const timer = setTimeout(function () {
        if (currentApprovalRequestId === data.request_id) {
            approveAction(false);
            showNotification('Approval timed out -- auto-denied', 'warning');
        }
    }, APPROVAL_TIMEOUT_MS);
    setApprovalTimeoutTimer(timer);

    // Sound/visual alert
    showNotification('Approval required: ' + (data.tool || ''), 'warning');
}

/**
 * Approve or deny the current approval request.
 */
export function approveAction(approved) {
    if (!currentApprovalRequestId) return;

    apiPost(API_V1 + '/approvals/' + encodeURIComponent(currentApprovalRequestId) + '/resolve', {
        approved: approved
    }).then(function () {
        showNotification(approved ? 'Action approved' : 'Action denied', approved ? 'success' : 'info');
    }).catch(function (err) {
        showNotification('Approval failed: ' + err.message, 'error');
    });

    dismissApprovalModal();
}

/**
 * Dismiss the approval modal and reset related state.
 */
export function dismissApprovalModal() {
    setCurrentApprovalRequestId(null);
    clearTimeout(approvalTimeoutTimer);
    const modal = document.getElementById('approval-modal');
    releaseFocusTrap(modal);
    if (modal) modal.classList.add('hidden');

    const timeoutBar = document.getElementById('approval-timeout');
    if (timeoutBar) {
        timeoutBar.style.transition = 'none';
        timeoutBar.style.width = '100%';
    }
}
