// FormicOS v0.7.9 — Fleet surface: colony listing, creation, and lifecycle management

import { ColonyStatus, STATUS_BADGE_CLASS, API_V1 } from '../Constants.js';
import {
    colonyState, _fleetPage, _fleetPageSize, _fleetTotal, _lastFleetHash,
    set_fleetPage, set_fleetTotal, set_lastFleetHash,
    set_lastTopoHash, set_lastTopologySignature, set_pendingTopologyData,
    set_pendingTopologyRenderTimer, set_topologyLiveMode, set_topoHistoryIdx,
    set_lastDecisionHash, set_lastColonyHash, set_lastSystemHash,
    _pendingTopologyRenderTimer
} from '../state.js';
import { hashString, escapeHtml, escapeAttr, truncateStr, showNotification, trapFocus, releaseFocusTrap } from '../utils.js';
import { apiGet, apiPost, apiDelete } from '../api/client.js';
import { setColonyViewState, getCreateFormElements, updateColonyStatusDisplay } from './colony.js';
import { subscribeToColony } from '../websockets/socket_manager.js';
import { clearConsole } from './console.js';
import { resetWorkspaceState } from './workspace.js';

/**
 * Load the fleet table from the API with pagination.
 */
export function loadFleet() {
    try {
        const offset = _fleetPage * _fleetPageSize;
        const url = API_V1 + '/colonies?limit=' + _fleetPageSize + '&offset=' + offset;
        // Anti-flash: dim table during load instead of clearing
        const tbody = document.getElementById('fleet-tbody');
        if (tbody) tbody.style.opacity = '0.5';
        apiGet(url).then(function (data) {
            const colonies = data.items || data.colonies || data || [];
            set_fleetTotal(data.total || colonies.length);
            const hash = hashString(JSON.stringify(colonies));
            if (hash !== _lastFleetHash) {
                set_lastFleetHash(hash);
                renderFleetTable(colonies);
            }
            if (tbody) tbody.style.opacity = '';
            updateFleetPagination();
        }).catch(function (err) {
            if (tbody) { tbody.style.opacity = ''; tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Failed to load: ' + escapeHtml(err.message) + '</td></tr>'; }
        });
    } catch (err) {
        console.error('Fleet surface error:', err);
    }
}

/**
 * Update the fleet pagination controls based on current page state.
 */
export function updateFleetPagination() {
    const prevBtn = document.getElementById('fleet-prev');
    const nextBtn = document.getElementById('fleet-next');
    const info = document.getElementById('fleet-page-info');
    const maxPage = Math.max(0, Math.ceil(_fleetTotal / _fleetPageSize) - 1);
    if (prevBtn) prevBtn.disabled = _fleetPage <= 0;
    if (nextBtn) nextBtn.disabled = _fleetPage >= maxPage;
    if (info) info.textContent = 'Page ' + (_fleetPage + 1) + ' of ' + (maxPage + 1);
}

/**
 * Navigate to the previous page of the fleet table.
 */
export function fleetPrevPage() {
    if (_fleetPage > 0) { set_fleetPage(_fleetPage - 1); set_lastFleetHash(''); loadFleet(); }
}

/**
 * Navigate to the next page of the fleet table.
 */
export function fleetNextPage() {
    const maxPage = Math.max(0, Math.ceil(_fleetTotal / _fleetPageSize) - 1);
    if (_fleetPage < maxPage) { set_fleetPage(_fleetPage + 1); set_lastFleetHash(''); loadFleet(); }
}

/**
 * Render the fleet as a table. Uses DocumentFragment for memory hardening.
 */
export function renderFleetTable(colonies) {
    const tbody = document.getElementById('fleet-tbody') || document.getElementById('fleet-table-body');
    if (!tbody) {
        // Fallback: render into supercolony-grid if fleet table not present
        const grid = document.getElementById('supercolony-grid');
        if (grid) {
            renderColonyCards(colonies);
        }
        return;
    }

    if (!colonies || colonies.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No colonies created yet. Click "+ New Colony" to begin.</td></tr>';
        return;
    }

    const fragment = document.createDocumentFragment();
    for (let i = 0; i < colonies.length; i++) {
        const c = colonies[i];
        const status = c.status || c.state || 'UNKNOWN';
        const statusUpper = String(status).toUpperCase();
        const badgeClass = STATUS_BADGE_CLASS[statusUpper] || 'badge-neutral';
        const colonyId = c.colony_id || c.id || 'colony-' + i;
        const task = c.task || 'No task';
        const round = c.round || c.current_round || 0;
        const maxRounds = c.max_rounds || 0;
        const agentCount = c.agent_count || (c.agents ? c.agents.length : 0);

        let health = 'Ready';
        if (statusUpper === ColonyStatus.RUNNING) health = 'Healthy';
        else if (statusUpper === ColonyStatus.FAILED) health = 'Failed';
        else if (statusUpper === ColonyStatus.PAUSED) health = 'Paused';
        else if (statusUpper === ColonyStatus.COMPLETED) health = 'Done';
        else if (statusUpper === ColonyStatus.HALTED_BUDGET_EXHAUSTED) health = 'Halted';
        else if (statusUpper === ColonyStatus.QUEUED) health = 'Queued';

        const displayStatus = statusUpper === ColonyStatus.QUEUED ? 'QUEUED' : statusUpper;

        // Origin badge (v0.7.3 backend adds origin/client_id)
        let originBadge = '';
        if (c.origin === 'api') {
            originBadge = ' <span class="badge-api-client">\uD83E\uDD16 API Client: ' + escapeHtml(c.client_id || 'Unknown') + '</span>';
        }
        let testFlightBadge = '';
        if (c.is_test_flight) {
            testFlightBadge = ' <span class="badge-test-flight">TEST FLIGHT</span>';
        }

        const tr = document.createElement('tr');

        let rowHtml = '';
        rowHtml += '<td class="font-mono">' + escapeHtml(colonyId) + originBadge + testFlightBadge + '</td>';
        rowHtml += '<td class="truncate" style="max-width:250px">' + escapeHtml(truncateStr(task, 100)) + '</td>';
        rowHtml += '<td><span class="badge ' + badgeClass + '">' + escapeHtml(displayStatus) + '</span></td>';
        rowHtml += '<td>' + round + '/' + maxRounds + '</td>';
        rowHtml += '<td>' + escapeHtml(health) + ' <span class="text-muted">(' + agentCount + ' agents)</span></td>';
        rowHtml += '<td class="fleet-actions">';

        if (statusUpper === ColonyStatus.CREATED || statusUpper === ColonyStatus.READY) {
            rowHtml += '<button class="btn btn-primary btn-sm" onclick="startColony(\'' + escapeAttr(colonyId) + '\')">Start</button> ';
        }
        if (statusUpper === ColonyStatus.RUNNING) {
            rowHtml += '<button class="btn btn-secondary btn-sm" onclick="pauseColony(\'' + escapeAttr(colonyId) + '\')">Pause</button> ';
        }
        if (statusUpper === ColonyStatus.PAUSED) {
            rowHtml += '<button class="btn btn-primary btn-sm" onclick="resumeColony(\'' + escapeAttr(colonyId) + '\')">Resume</button> ';
        }
        if (statusUpper !== ColonyStatus.RUNNING) {
            rowHtml += '<button class="btn btn-secondary btn-sm" onclick="reuseColony(\'' + escapeAttr(colonyId) + '\')">Reuse</button> ';
        }
        rowHtml += '<button class="btn btn-secondary btn-sm" onclick="viewColony(\'' + escapeAttr(colonyId) + '\')">View</button> ';
        rowHtml += '<button class="btn btn-danger btn-sm" onclick="destroyColony(\'' + escapeAttr(colonyId) + '\')">Destroy</button>';
        rowHtml += '</td>';

        tr.innerHTML = rowHtml;
        fragment.appendChild(tr);
    }

    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

/**
 * Fallback card renderer (backward compat if fleet-table-body not in HTML).
 * Uses DocumentFragment for memory hardening.
 */
export function renderColonyCards(colonies) {
    const grid = document.getElementById('supercolony-grid');
    if (!grid) return;

    if (!colonies || colonies.length === 0) {
        grid.innerHTML = '<div class="empty-state">No colonies created yet. Click "+ New Colony" to begin.</div>';
        return;
    }

    const fragment = document.createDocumentFragment();
    for (let i = 0; i < colonies.length; i++) {
        const c = colonies[i];
        const status = c.status || c.state || 'UNKNOWN';
        const statusUpper = String(status).toUpperCase();
        const badgeClass = STATUS_BADGE_CLASS[statusUpper] || 'badge-neutral';
        const colonyId = c.colony_id || c.id || 'colony-' + i;
        const task = c.task || 'No task';
        const round = c.round || c.current_round || 0;
        const maxRounds = c.max_rounds || 0;
        const agentCount = c.agent_count || (c.agents ? c.agents.length : 0);

        let originBadge = '';
        if (c.origin === 'api') {
            originBadge = ' <span class="badge-api-client">\uD83E\uDD16 API Client: ' + escapeHtml(c.client_id || 'Unknown') + '</span>';
        }

        const card = document.createElement('div');
        card.className = 'colony-card';

        let cardHtml = '';
        cardHtml += '<div class="colony-card-header">';
        cardHtml += '<span class="colony-card-id">' + escapeHtml(colonyId) + originBadge + '</span>';
        cardHtml += '<span class="badge ' + badgeClass + '">' + escapeHtml(statusUpper) + '</span>';
        cardHtml += '</div>';
        cardHtml += '<div class="colony-card-body">';
        cardHtml += '<span class="field-label">Task</span>';
        cardHtml += '<span>' + escapeHtml(truncateStr(task, 120)) + '</span>';
        cardHtml += '</div>';
        cardHtml += '<div class="colony-card-meta">';
        cardHtml += '<span>Round: ' + round + '/' + maxRounds + '</span>';
        cardHtml += '<span>Agents: ' + agentCount + '</span>';
        cardHtml += '</div>';
        cardHtml += '<div class="colony-card-actions">';

        if (statusUpper === ColonyStatus.CREATED || statusUpper === ColonyStatus.READY) {
            cardHtml += '<button class="btn btn-primary" onclick="startColony(\'' + escapeAttr(colonyId) + '\')">Start</button>';
        }
        if (statusUpper === ColonyStatus.RUNNING) {
            cardHtml += '<button class="btn btn-secondary" onclick="pauseColony(\'' + escapeAttr(colonyId) + '\')">Pause</button>';
        }
        if (statusUpper === ColonyStatus.PAUSED) {
            cardHtml += '<button class="btn btn-primary" onclick="resumeColony(\'' + escapeAttr(colonyId) + '\')">Resume</button>';
        }
        if (statusUpper !== ColonyStatus.RUNNING) {
            cardHtml += '<button class="btn btn-secondary" onclick="reuseColony(\'' + escapeAttr(colonyId) + '\')">Reuse</button>';
        }
        cardHtml += '<button class="btn btn-secondary" onclick="viewColony(\'' + escapeAttr(colonyId) + '\')">View</button>';
        cardHtml += '<button class="btn btn-danger" onclick="destroyColony(\'' + escapeAttr(colonyId) + '\')">Destroy</button>';
        cardHtml += '</div>';

        card.innerHTML = cardHtml;
        fragment.appendChild(card);
    }

    grid.innerHTML = '';
    grid.appendChild(fragment);
}

/**
 * Navigate to a colony's workspace view.
 */
export function viewColony(colonyId) {
    colonyState.colony_id = colonyId;
    // Clear stale hashes so data refreshes
    set_lastTopoHash('');
    set_lastTopologySignature('');
    set_pendingTopologyData(null);
    if (_pendingTopologyRenderTimer) { clearTimeout(_pendingTopologyRenderTimer); set_pendingTopologyRenderTimer(null); }
    set_topologyLiveMode(true);
    set_topoHistoryIdx(-1);
    set_lastDecisionHash('');
    set_lastColonyHash('');
    set_lastSystemHash('');
    // Reset workspace browsing state (clears stale hash + resets path to root)
    resetWorkspaceState();
    setColonyViewState('loading');
    // Navigate via hash -> triggers colony-workspace switch + subscribe
    var newHash = '#colony/' + encodeURIComponent(colonyId);
    if (window.location.hash === newHash) {
        // Hash unchanged (e.g. re-viewing same colony) — force route handler
        window.dispatchEvent(new HashChangeEvent('hashchange'));
    } else {
        window.location.hash = newHash;
    }
}

/**
 * View a colony and prepare it for reuse with a new task.
 */
export function reuseColony(colonyId) {
    viewColony(colonyId);
    setTimeout(function () {
        const input = document.getElementById('reuse-task-input');
        if (input) {
            input.focus();
            input.select();
        }
    }, 120);
    showNotification('Enter a new task in the reuse bar, then click "Reuse Colony".', 'info');
}

/**
 * Reuse the currently selected colony with a new task.
 */
export function reuseCurrentColony() {
    const colonyId = colonyState.colony_id;
    if (!colonyId) {
        showNotification('No colony selected to reuse', 'warning');
        return;
    }
    const taskEl = document.getElementById('reuse-task-input');
    const roundsEl = document.getElementById('reuse-rounds-input');
    const preserveEl = document.getElementById('reuse-preserve-history');
    const clearWsEl = document.getElementById('reuse-clear-workspace');

    const task = taskEl ? taskEl.value.trim() : '';
    if (!task) {
        showNotification('Enter a new task to reuse this colony', 'warning');
        return;
    }
    const maxRounds = parseInt(roundsEl ? roundsEl.value : '5', 10) || 5;
    const preserveHistory = !!(preserveEl && preserveEl.checked);
    const clearWorkspace = !!(clearWsEl && clearWsEl.checked);

    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/reuse', {
        task: task,
        max_rounds: maxRounds,
        preserve_history: preserveHistory,
        clear_workspace: clearWorkspace,
        start_immediately: true
    }).then(function (data) {
        colonyState.colony_id = colonyId;
        colonyState.task = task;
        colonyState.max_rounds = maxRounds;
        colonyState.round = 0;
        colonyState.status = data.started ? ColonyStatus.RUNNING : ColonyStatus.CREATED;
        setColonyViewState('active');
        updateColonyStatusDisplay();
        clearConsole();
        // workspaceCurrentPath reset will happen in the main module
        set_lastDecisionHash('');
        set_lastTopoHash('');
        set_lastTopologySignature('');
        set_pendingTopologyData(null);
        if (_pendingTopologyRenderTimer) { clearTimeout(_pendingTopologyRenderTimer); set_pendingTopologyRenderTimer(null); }
        set_topologyLiveMode(true);
        set_topoHistoryIdx(-1);
        set_lastColonyHash('');
        subscribeToColony(colonyId);
        // refreshWorkspace, fetchDecisions, fetchTopology, loadFleet called from main
        if (taskEl) taskEl.value = '';
        window.location.hash = '#colony/' + encodeURIComponent(colonyId);
        showNotification('Colony reused and started: ' + colonyId, 'success');
    }).catch(function (err) {
        showNotification('Reuse failed: ' + err.message, 'error');
    });
}

/**
 * Show the create-colony modal and initialize its form.
 */
export function showCreateColonyModal() {
    const modal = document.getElementById('create-colony-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    trapFocus(modal);

    const colonyIdInput = document.getElementById('new-colony-id');
    if (colonyIdInput) {
        colonyIdInput.value = 'colony-' + Date.now().toString(36);
    }
    const autoStart = document.getElementById('new-colony-start-immediately');
    if (autoStart) autoStart.checked = true;

    const status = document.getElementById('modal-suggest-team-status');
    if (status) {
        status.textContent = '';
        status.className = 'suggest-status';
    }

    // Initialize team builder with architect + coder (manager added server-side)
    const container = document.getElementById('modal-team-members-list');
    if (container) {
        container.innerHTML = '';
        addTeamMemberRow(container, 'architect', 'balanced');
        addTeamMemberRow(container, 'coder', 'balanced');
    }
}

/**
 * Add a team member row to the team builder using the form elements.
 */
export function addTeamMember() {
    const form = getCreateFormElements();
    const container = form.teamContainer;
    if (!container) return;
    addTeamMemberRow(container, 'coder', 'balanced');
}

/** Caste list cache for dropdown population. */
let _casteListCache = null;
let _casteListCacheTs = 0;
const CASTE_CACHE_TTL = 60000;

/**
 * Get the castes list, using a cached version if fresh enough.
 */
export function getCastesCached() {
    const now = Date.now();
    if (_casteListCache && (now - _casteListCacheTs) < CASTE_CACHE_TTL) {
        return Promise.resolve(_casteListCache);
    }
    return apiGet(API_V1 + '/castes').then(function (data) {
        _casteListCache = data;
        _casteListCacheTs = Date.now();
        return data;
    });
}

/**
 * Add a team member row to the specified container with caste/subcaste dropdowns.
 */
export function addTeamMemberRow(container, defaultCaste, defaultSubcaste) {
    const row = document.createElement('div');
    row.className = 'team-member-row';

    // Fetch castes for dropdown (cached)
    getCastesCached().then(function (castes) {
        const names = Object.keys(castes);
        let casteOpts = '';
        for (let i = 0; i < names.length; i++) {
            const sel = names[i] === defaultCaste ? ' selected' : '';
            casteOpts += '<option value="' + escapeAttr(names[i]) + '"' + sel + '>' + escapeHtml(names[i]) + '</option>';
        }
        row.innerHTML = '<select class="form-input member-caste">' + casteOpts + '</select>' +
            '<select class="form-input member-subcaste">' +
            '<option value="balanced"' + (defaultSubcaste === 'balanced' ? ' selected' : '') + '>balanced</option>' +
            '<option value="heavy"' + (defaultSubcaste === 'heavy' ? ' selected' : '') + '>heavy</option>' +
            '<option value="light"' + (defaultSubcaste === 'light' ? ' selected' : '') + '>light</option>' +
            '</select>' +
            '<button class="btn-icon btn-remove-member" onclick="this.parentElement.remove()" title="Remove">&#x2716;</button>';
    }).catch(function () {
        row.innerHTML = '<input type="text" class="form-input member-caste" value="' + escapeAttr(defaultCaste) + '">' +
            '<select class="form-input member-subcaste"><option value="balanced" selected>balanced</option><option value="heavy">heavy</option><option value="light">light</option></select>' +
            '<button class="btn-icon btn-remove-member" onclick="this.parentElement.remove()">&#x2716;</button>';
    });

    container.appendChild(row);
}

/**
 * Hide the create-colony modal.
 */
export function hideCreateColonyModal() {
    const modal = document.getElementById('create-colony-modal');
    releaseFocusTrap(modal);
    if (modal) modal.classList.add('hidden');
}

/** Team preset definitions. */
const TEAM_PRESETS = {
    'full-stack': {
        label: 'Full-Stack',
        agents: [
            { caste: 'architect', subcaste_tier: 'heavy' },
            { caste: 'coder', subcaste_tier: 'heavy' },
            { caste: 'coder', subcaste_tier: 'balanced' },
            { caste: 'reviewer', subcaste_tier: 'balanced' }
        ]
    },
    'code-review': {
        label: 'Code Review',
        agents: [
            { caste: 'coder', subcaste_tier: 'heavy' },
            { caste: 'reviewer', subcaste_tier: 'heavy' },
            { caste: 'reviewer', subcaste_tier: 'balanced' }
        ]
    },
    'research': {
        label: 'Research',
        agents: [
            { caste: 'architect', subcaste_tier: 'heavy' },
            { caste: 'architect', subcaste_tier: 'balanced' },
            { caste: 'reviewer', subcaste_tier: 'balanced' }
        ]
    }
};

/**
 * Apply a team preset to the team builder.
 */
export function applyTeamPreset(presetName) {
    const preset = TEAM_PRESETS[presetName];
    if (!preset) return;

    const form = getCreateFormElements();
    const container = form.teamContainer;
    if (!container) return;
    container.innerHTML = '';

    for (let i = 0; i < preset.agents.length; i++) {
        addTeamMemberRow(container, preset.agents[i].caste, preset.agents[i].subcaste_tier);
    }

    const status = form.suggestStatus;
    if (status) {
        status.textContent = preset.label + ' preset applied';
        status.className = 'suggest-status suggest-success';
    }
}

/**
 * Suggest a team composition via the API based on the entered task.
 */
export function suggestTeam() {
    const form = getCreateFormElements();
    const task = form.taskInput ? form.taskInput.value.trim() : '';
    if (!task) {
        showNotification('Enter a task first', 'warning');
        return;
    }

    const btn = form.suggestButton;
    const status = form.suggestStatus;
    if (!btn || !status) return;
    btn.disabled = true;
    btn.textContent = 'Thinking...';
    status.textContent = '';
    status.className = 'suggest-status';

    apiPost(API_V1 + '/suggest-team', { task: task }).then(function (data) {
        // Clear existing team rows
        const container = form.teamContainer;
        if (!container) throw new Error('Team editor is not available on this surface');
        container.innerHTML = '';

        // Add suggested agents
        const agents = data.agents || [];
        for (let i = 0; i < agents.length; i++) {
            addTeamMemberRow(
                container,
                agents[i].caste || 'coder',
                agents[i].subcaste_tier || 'balanced'
            );
        }

        // Fill colony name if suggested
        if (data.colony_name) {
            if (form.colonyIdInput) form.colonyIdInput.value = data.colony_name;
        }

        // Fill max rounds if suggested
        if (data.max_rounds) {
            if (form.roundsInput) form.roundsInput.value = data.max_rounds;
        }

        status.textContent = agents.length + ' agents suggested';
        status.className = 'suggest-status suggest-success';
        btn.disabled = false;
        btn.textContent = 'Suggest Team';
    }).catch(function (err) {
        status.textContent = 'Failed: ' + (err.message || 'unknown error');
        status.className = 'suggest-status suggest-error';
        btn.disabled = false;
        btn.textContent = 'Suggest Team';
    });
}

/**
 * Submit the create-colony form: create colony + optionally start it.
 */
export function submitCreateColony() {
    const form = getCreateFormElements();
    const colonyId = form.colonyIdInput ? form.colonyIdInput.value.trim() : '';
    const task = form.taskInput ? form.taskInput.value.trim() : '';
    const maxRounds = parseInt(form.roundsInput ? form.roundsInput.value : '5') || 5;
    const startNowEl = document.getElementById('new-colony-start-immediately');
    const startNow = !startNowEl || !!startNowEl.checked;

    if (!colonyId) {
        showNotification('Colony ID required', 'warning');
        return;
    }
    if (!task) {
        showNotification('Task required', 'warning');
        return;
    }

    // Collect agents from team builder
    const memberRows = (form.teamContainer ? form.teamContainer.querySelectorAll('.team-member-row') : []);
    const agents = [];
    for (let i = 0; i < memberRows.length; i++) {
        const row = memberRows[i];
        const casteEl = row.querySelector('.member-caste');
        const subcasteEl = row.querySelector('.member-subcaste');
        const caste = casteEl ? (casteEl.value || casteEl.textContent) : 'coder';
        const subcaste = subcasteEl ? subcasteEl.value : 'balanced';
        agents.push({ caste: caste, subcaste_tier: subcaste });
    }
    if (agents.length === 0) {
        agents.push({ caste: 'architect', subcaste_tier: 'balanced' });
        agents.push({ caste: 'coder', subcaste_tier: 'balanced' });
    }

    apiPost(API_V1 + '/colonies', {
        colony_id: colonyId,
        task: task,
        max_rounds: maxRounds,
        agents: agents
    }).then(function (created) {
        const createdId = created.colony_id || colonyId;
        if (!startNow) {
            showNotification('Colony created: ' + createdId, 'success');
            hideCreateColonyModal();
            loadFleet();
            return null;
        }
        return apiPost(API_V1 + '/colonies/' + encodeURIComponent(createdId) + '/start', {}).then(function () {
            return createdId;
        });
    }).then(function (startedId) {
        if (!startedId) return;
        showNotification('Colony created and started: ' + startedId, 'success');
        hideCreateColonyModal();
        colonyState.colony_id = startedId;
        colonyState.status = ColonyStatus.RUNNING;
        subscribeToColony(startedId);
        loadFleet();
        window.location.hash = '#colony/' + encodeURIComponent(startedId);
    }).catch(function (err) {
        showNotification('Create failed: ' + err.message, 'error');
    });
}

/**
 * Start a colony by ID.
 */
export function startColony(colonyId) {
    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/start', {}).then(function () {
        showNotification('Colony started: ' + colonyId, 'success');
        colonyState.colony_id = colonyId;
        colonyState.status = ColonyStatus.RUNNING;
        subscribeToColony(colonyId);
        loadFleet();
        window.location.hash = '#colony/' + encodeURIComponent(colonyId);
    }).catch(function (err) {
        showNotification('Start failed: ' + err.message, 'error');
    });
}

/**
 * Pause a colony by ID.
 */
export function pauseColony(colonyId) {
    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/pause', {}).then(function () {
        showNotification('Colony paused: ' + colonyId, 'info');
        loadFleet();
    }).catch(function (err) {
        showNotification('Pause failed: ' + err.message, 'error');
    });
}

/**
 * Resume a colony by ID.
 */
export function resumeColony(colonyId) {
    apiPost(API_V1 + '/colonies/' + encodeURIComponent(colonyId) + '/resume', {}).then(function () {
        showNotification('Colony resumed: ' + colonyId, 'success');
        loadFleet();
    }).catch(function (err) {
        showNotification('Resume failed: ' + err.message, 'error');
    });
}

/**
 * Destroy a colony by ID (with confirmation).
 */
export function destroyColony(colonyId) {
    if (!confirm('Destroy colony "' + colonyId + '"? This cannot be undone.')) return;

    apiDelete(API_V1 + '/colonies/' + encodeURIComponent(colonyId)).then(function () {
        showNotification('Colony destroyed: ' + colonyId, 'success');
        // If we were viewing this colony, reset
        if (colonyState.colony_id === colonyId) {
            colonyState.colony_id = null;
            setColonyViewState('none_selected');
        }
        loadFleet();
    }).catch(function (err) {
        showNotification('Destroy failed: ' + err.message, 'error');
    });
}

// ── Fleet Bulk Actions (stubs) ───────────────────────────────
export function fleetBulkPause() { showNotification('Bulk pause not yet implemented', 'info'); }
export function fleetBulkResume() { showNotification('Bulk resume not yet implemented', 'info'); }
export function fleetBulkDestroy() { showNotification('Bulk destroy not yet implemented', 'info'); }
